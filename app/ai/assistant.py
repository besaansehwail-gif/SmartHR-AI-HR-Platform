"""Orchestration for one chat turn.

    user message
      -> MCP tools/list        what this caller may do
      -> LLM                   which tool answers this, with what arguments
      -> MCP tools/call        SmartHR runs it against PostgreSQL
      -> LLM                   phrase the real result
      -> reply

The assistant reaches SmartHR **only** through the MCP layer. It holds no
queries, no table names and no role rules of its own; `app/mcp/` owns the tool
surface and `app/services/` owns the behaviour. That separation is the point:
the model chooses, MCP authorises, SmartHR answers.

Two paths exist, and the response always says which one ran:

* `generated_by: "llm"` - a model selected the tool and wrote the answer.
* `generated_by: "tool"` - no model is configured, or the model could not be
  reached. A keyword match picks the tool instead and the real tool result is
  rendered directly. This is a labelled fallback, not the intended path, and
  it never writes a sentence that is not backed by tool output.

Nothing is ever invented. Every figure in every reply came out of an MCP tool
result, which came out of the database.
"""

import json
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.ai.config import llm_settings
from app.ai.provider import LlmError, LlmNotConfigured, get_provider
from app.mcp import client as mcp
from app.mcp.client import McpTool, McpToolResult
from app.mcp.identity import Principal
from app.models import User

logger = logging.getLogger("smarthr.ai")

MAX_HISTORY_MESSAGES = 10

SYSTEM_PROMPT = """You are the SmartHR AI Assistant, built into an HR management system.

Rules you must follow:

1. Every fact about employees, leave, attendance, training, performance or
   recruitment must come from a SmartHR tool result in this conversation. You
   have no other knowledge of this company's data. If you have not called a
   tool, you do not know the answer.
2. Never invent, estimate, extrapolate or illustrate HR data. No example
   numbers, no plausible-looking figures, no placeholder names.
3. If a tool reports that something is not available in the database, say so
   plainly. SmartHR stores no leave entitlement or balance table, so you can
   report days requested and days approved but never a remaining balance.
4. If a tool is refused because of the user's role, explain that they do not
   have access, and do not speculate about what the data might contain.
5. Answer in the same language the user wrote in. Arabic questions get Arabic
   answers.
6. Be brief and concrete. Lead with the number the user asked for.
7. The tools always answer for the signed-in user. You cannot request another
   person's records, and you must not offer to.

Answering from HR policy documents (`search_hr_policies`):

8. Use ONLY the passages the tool returned. They are the whole of what the
   documents say on the subject; your own knowledge of how companies usually
   handle something is not evidence about this one.
9. Quote figures - days, hours, deadlines, amounts - exactly as the passage
   writes them. Do not convert, round or combine them.
10. Name the source in the answer, for example "According to the Leave Policy,
    section 3. Sick leave...". A policy answer without a source is not useful.
11. If the tool returns no passages, say the documents do not cover it and stop.
    Do not fall back on general knowledge, and do not guess what the policy is
    likely to say. "The policy does not address that" is a complete answer.
12. If the passages are marked as DEMO content, say so - they are test
    documents, not real company policy, and the reader must not act on them.
13. Keep the two kinds of question apart. Documents say what the rules are;
    database tools say what a person actually did. If someone asks how much
    leave they have *taken*, that is a database question, not a policy one.
"""


# ---------------------------------------------------------------------------
# Fallback intent matching
#
# Used only when no model is available to choose a tool. Requirement: intent
# detection must not be the primary mechanism - when a model is configured it
# selects the tool, and these keywords are never consulted.
# ---------------------------------------------------------------------------
INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Checked BEFORE get_my_leave: "what is the leave policy?" is a document
    # question even though it contains the word "leave", and dict order decides.
    "search_hr_policies": (
        "policy", "policies", "rule", "rules", "entitle", "entitlement",
        "allowed", "allowance", "handbook", "procedure", "guideline",
        "onboarding", "probation", "remote work", "work from home", "hybrid",
        "working hours", "overtime", "lateness", "dress code", "notice period",
        "سياسة", "سياسات", "اللائحة", "لائحة", "قواعد", "نظام العمل",
        "دوام", "العمل عن بعد", "التأخير", "فترة التجربة",
    ),
    "get_my_leave": (
        "leave", "leaves", "holiday", "holidays", "vacation", "time off",
        "timeoff", "day off", "days off", "absence", "absent", "pto",
        "إجازة", "إجازات", "اجازة", "اجازات", "الاجازات", "الإجازات",
        "عطلة", "عطل", "غياب",
    ),
}


#: Arguments the fallback path must supply per tool.
#:
#: `get_my_leave` takes only optional filters, so an empty call works. A
#: retrieval tool does not: `search_hr_policies` requires the text to search
#: for, and calling it without one is rejected by the tool's own schema. When a
#: model is driving it writes these arguments itself; on the fallback path
#: there is nobody to write them, so the user's message is passed through as
#: the query.
FALLBACK_ARGUMENTS = {
    "search_hr_policies": lambda message: {"query": message},
}


def _fallback_arguments(tool_name: str, message: str) -> dict[str, Any]:
    builder = FALLBACK_ARGUMENTS.get(tool_name)
    return builder(message) if builder else {}


def _match_intent(message: str, allowed: set[str]) -> str | None:
    haystack = (message or "").lower()

    for tool_name, keywords in INTENT_KEYWORDS.items():
        if tool_name in allowed and any(word in haystack for word in keywords):
            return tool_name

    return None


def is_arabic(text: str) -> bool:
    """True when the message is written in Arabic script."""
    return any("؀" <= character <= "ۿ" for character in text or "")


# ---------------------------------------------------------------------------
# Rendering for the fallback path
# ---------------------------------------------------------------------------

def _render_leave_en(data: dict[str, Any]) -> str:
    total = data.get("total_requests", 0)
    name = (data.get("employee") or {}).get("full_name") or "You"

    if total == 0:
        return f"{name} has no leave requests recorded in SmartHR."

    lines = [f"{name} has {total} leave request{'s' if total != 1 else ''} on record."]

    counts = data.get("counts_by_status") or {}
    if counts:
        lines.append(
            "By status: "
            + ", ".join(f"{count} {status.lower()}" for status, count in counts.items())
            + "."
        )

    days = data.get("days_taken_by_type") or {}
    if days:
        lines.append(
            "Requested or approved: "
            + ", ".join(
                f"{value} day{'s' if value != 1 else ''} {key}" for key, value in days.items()
            )
            + "."
        )

    next_leave = data.get("next_leave")
    if data.get("upcoming_count") and isinstance(next_leave, dict):
        lines.append(
            f"Next up: {next_leave.get('leave_type')} from {next_leave.get('start_date')} "
            f"to {next_leave.get('end_date')} ({next_leave.get('duration_days')} days, "
            f"{next_leave.get('status')})."
        )

    lines.append(
        "SmartHR does not store a leave entitlement table, so a remaining "
        "balance cannot be shown."
    )
    return " ".join(lines)


def _render_leave_ar(data: dict[str, Any]) -> str:
    total = data.get("total_requests", 0)
    name = (data.get("employee") or {}).get("full_name") or ""

    if total == 0:
        return f"لا توجد طلبات إجازة مسجّلة في النظام لـ {name}.".strip()

    status_ar = {
        "Pending": "قيد الانتظار",
        "Approved": "موافق عليها",
        "Rejected": "مرفوضة",
        "Cancelled": "ملغاة",
    }

    parts = [f"لدى {name} {total} طلب إجازة مسجّل في النظام.".strip()]

    counts = data.get("counts_by_status") or {}
    if counts:
        parts.append(
            "حسب الحالة: "
            + "، ".join(
                f"{count} {status_ar.get(status, status)}" for status, count in counts.items()
            )
            + "."
        )

    days = data.get("days_taken_by_type") or {}
    if days:
        parts.append(
            "الأيام المطلوبة أو الموافق عليها: "
            + "، ".join(f"{value} يوم {key}" for key, value in days.items())
            + "."
        )

    next_leave = data.get("next_leave")
    if data.get("upcoming_count") and isinstance(next_leave, dict):
        parts.append(
            f"الإجازة القادمة: {next_leave.get('leave_type')} من "
            f"{next_leave.get('start_date')} إلى {next_leave.get('end_date')} "
            f"({next_leave.get('duration_days')} أيام، "
            f"{status_ar.get(next_leave.get('status'), next_leave.get('status'))})."
        )

    parts.append("لا يحتفظ النظام بجدول لرصيد الإجازات، لذلك لا يمكن عرض الرصيد المتبقي.")
    return " ".join(parts)


def _render_policies_en(data: dict[str, Any]) -> str:
    """The fallback rendering of a document search, with no model involved.

    It quotes the retrieved passages and names their source. It deliberately
    does not summarise: summarising without a model would mean inventing
    wording, and the whole point of retrieval is that the reader sees what the
    document actually says.
    """
    chunks = data.get("chunks") or []

    if not chunks:
        return (
            "The HR documents do not cover that. Nothing in the indexed "
            "policies matches your question, so there is no answer to give "
            "from them - rather than guess, SmartHR is telling you the "
            "documents are silent on it."
        )

    demo = data.get("contains_demo_content")
    parts: list[str] = []

    if demo:
        parts.append(
            "Note: these passages come from DEMO policy documents created for "
            "testing SmartHR. They are not real company policy."
        )

    parts.append(f"Found {len(chunks)} relevant passage"
                 f"{'s' if len(chunks) != 1 else ''}:")

    for chunk in chunks:
        text = " ".join((chunk.get("text") or "").split())
        parts.append(f"\n— {chunk.get('citation')} —\n{text}")

    sources = data.get("sources") or []
    if sources:
        parts.append("\nSource" + ("s" if len(sources) != 1 else "") + ": "
                     + "; ".join(sources))

    return "\n".join(parts)


def _render_policies_ar(data: dict[str, Any]) -> str:
    chunks = data.get("chunks") or []

    if not chunks:
        return (
            "لا تغطي مستندات الموارد البشرية هذا الموضوع. لم يُعثر على أي فقرة "
            "مطابقة، ولن يتم تخمين الإجابة."
        )

    parts: list[str] = []

    if data.get("contains_demo_content"):
        parts.append(
            "ملاحظة: هذه الفقرات مأخوذة من مستندات سياسات تجريبية (DEMO) "
            "أُنشئت لاختبار النظام، وليست سياسة شركة حقيقية."
        )

    parts.append(f"تم العثور على {len(chunks)} فقرة ذات صلة:")

    for chunk in chunks:
        text = " ".join((chunk.get("text") or "").split())
        parts.append(f"\n— {chunk.get('citation')} —\n{text}")

    sources = data.get("sources") or []
    if sources:
        parts.append("\nالمصدر: " + "؛ ".join(sources))

    return "\n".join(parts)


RENDERERS = {
    "get_my_leave": {"en": _render_leave_en, "ar": _render_leave_ar},
    "search_hr_policies": {"en": _render_policies_en, "ar": _render_policies_ar},
}

DENIAL_AR = {
    "no_employee_link": "هذا الحساب غير مرتبط بسجل موظف، لذلك لا توجد بيانات إجازات خاصة به.",
    "forbidden": "صلاحيتك لا تسمح بالوصول إلى هذه البيانات.",
    "database_error": "تعذّرت قراءة قاعدة بيانات النظام في الوقت الحالي.",
}


def _render(result: McpToolResult, arabic: bool) -> str:
    if not result.ok:
        if arabic and result.error_code in DENIAL_AR:
            return DENIAL_AR[result.error_code]
        return result.error or "That could not be completed."

    renderer = (RENDERERS.get(result.tool) or {}).get("ar" if arabic else "en")

    if renderer and result.data:
        return renderer(result.data)

    return json.dumps(result.data, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------

def _history_messages(history: list[dict[str, str]] | None) -> list[dict[str, Any]]:
    """Prior turns, trimmed and sanitised. Only user/assistant turns survive,
    so a crafted `system` entry in the request body cannot reach the model."""
    cleaned: list[dict[str, Any]] = []

    for entry in (history or [])[-MAX_HISTORY_MESSAGES:]:
        role = entry.get("role")
        content = (entry.get("content") or "").strip()

        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content[:4000]})

    return cleaned


def _tool_schemas(tools: list[McpTool]) -> list[dict[str, Any]]:
    """MCP tool descriptors in the provider-neutral shape `provider.py` takes."""
    return [
        {"name": tool.name, "description": tool.description, "parameters": tool.input_schema}
        for tool in tools
    ]


def answer(
    message: str,
    history: list[dict[str, str]] | None,
    user: User,
    db: Session,
) -> dict[str, Any]:
    """Produce a grounded answer for one chat turn."""
    started = time.perf_counter()

    # The role is read from the database, not from the token claim and not from
    # anything the browser sent.
    account = db.query(User).filter(User.id == user.id).first() or user
    principal = Principal(user_id=account.id, email=account.email, role_id=account.role_id)

    logger.info(
        "AI turn start | user_id=%s role_id=%s chars=%s arabic=%s",
        principal.user_id,
        account.role_id,
        len(message or ""),
        is_arabic(message),
    )

    tools = mcp.list_tools(principal, account.role_id)
    allowed_names = {tool.name for tool in tools}

    settings = llm_settings()
    provider = get_provider(settings)
    base_messages = _history_messages(history) + [{"role": "user", "content": message}]

    tool_result: McpToolResult | None = None
    notice: str | None = None

    if provider.configured:
        try:
            logger.info(
                "LLM tool-selection call | provider=%s model=%s tools=%s",
                provider.name,
                provider.model,
                sorted(allowed_names),
            )
            first = provider.complete(SYSTEM_PROMPT, base_messages, _tool_schemas(tools))

            if first.tool_call is not None:
                logger.info(
                    "LLM selected MCP tool | tool=%s args=%s",
                    first.tool_call.name,
                    sorted((first.tool_call.arguments or {}).keys()),
                )

                if first.tool_call.name not in allowed_names:
                    # The model asked for something outside this caller's set.
                    # MCP would refuse it anyway; refusing here saves a round
                    # trip and records the attempt.
                    logger.warning(
                        "LLM requested a tool outside the caller's set | tool=%s user_id=%s",
                        first.tool_call.name,
                        principal.user_id,
                    )
                    tool_result = McpToolResult(
                        tool=first.tool_call.name,
                        ok=False,
                        error="That capability is not available to your role.",
                        error_code="forbidden",
                    )
                else:
                    tool_result = mcp.call_tool(
                        principal, first.tool_call.name, first.tool_call.arguments
                    )

                follow_up = base_messages + [
                    {
                        "role": "assistant",
                        "content": f"Calling the SmartHR tool {tool_result.tool}.",
                    },
                    {
                        "role": "user",
                        "content": (
                            "SmartHR MCP tool result (this is the only data you "
                            "have; answer the original question from it and add "
                            "nothing that is not in it):\n"
                            + json.dumps(
                                {
                                    "tool": tool_result.tool,
                                    "ok": tool_result.ok,
                                    "error": tool_result.error,
                                    "data": tool_result.data,
                                },
                                ensure_ascii=False,
                                default=str,
                            )
                        ),
                    },
                ]

                logger.info("LLM wording call | tool=%s ok=%s", tool_result.tool, tool_result.ok)
                second = provider.complete(SYSTEM_PROMPT, follow_up, None)
                reply = second.text or _render(tool_result, is_arabic(message))
            else:
                logger.info("LLM answered without calling a tool")
                reply = first.text or (
                    "I can answer questions about your own SmartHR records. "
                    "Try asking about your leave."
                )

            return _envelope(
                reply=reply,
                tool_result=tool_result,
                provider=provider.name,
                model=provider.model,
                llm_configured=True,
                generated_by="llm",
                notice=None,
                tools=tools,
                started=started,
                principal=principal,
            )

        except LlmNotConfigured:
            pass  # falls through to the labelled fallback
        except LlmError as exc:
            logger.warning("LLM unreachable, falling back to direct tool call | %s", exc)
            notice = (
                f"The language model could not be reached ({exc}). The figures "
                f"below still come straight from the SmartHR database."
            )

    if notice is None:
        notice = (
            "No language model is configured, so this answer is the MCP tool "
            "result itself rather than a generated reply. Set "
            "SMARTHR_LLM_PROVIDER and SMARTHR_LLM_API_KEY to enable "
            "natural-language answers."
        )

    arabic = is_arabic(message)
    intent = _match_intent(message, allowed_names)
    logger.info("Fallback intent match | tool=%s", intent)

    if intent is None:
        return _envelope(
            reply=(
                "لم أتمكن من تحديد ما تسأل عنه. يمكنني الإجابة عن أسئلتك حول "
                "إجازاتك (مثل: كم طلب إجازة لدي؟) أو حول سياسات الموارد البشرية "
                "(مثل: ما هي سياسة العمل عن بعد؟)."
                if arabic
                else "I could not tell what you are asking about. I can answer "
                "questions about your own records - for example \"how many leave "
                "requests do I have?\" - and questions about the HR policy "
                "documents, for example \"what is the remote work policy?\"."
            ),
            tool_result=None,
            provider=provider.name,
            model=provider.model,
            llm_configured=provider.configured,
            generated_by="tool",
            notice=notice,
            tools=tools,
            started=started,
            principal=principal,
        )

    tool_result = mcp.call_tool(principal, intent, _fallback_arguments(intent, message))

    return _envelope(
        reply=_render(tool_result, arabic),
        tool_result=tool_result,
        provider=provider.name,
        model=provider.model,
        llm_configured=provider.configured,
        generated_by="tool",
        notice=notice,
        tools=tools,
        started=started,
        principal=principal,
    )


def _envelope(
    reply: str,
    tool_result: McpToolResult | None,
    provider: str,
    model: str,
    llm_configured: bool,
    generated_by: str,
    notice: str | None,
    tools: list[McpTool],
    started: float,
    principal: Principal,
) -> dict[str, Any]:
    """The response body the chat endpoint returns.

    `data` carries the raw MCP tool result so the UI can show exactly what the
    answer was based on - the assistant is auditable, not a black box.
    """
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    logger.info(
        "AI turn done | user_id=%s generated_by=%s tool=%s ok=%s %sms",
        principal.user_id,
        generated_by,
        tool_result.tool if tool_result else None,
        tool_result.ok if tool_result else None,
        elapsed_ms,
    )

    return {
        "reply": reply,
        "generated_by": generated_by,
        "llm_configured": llm_configured,
        "provider": provider,
        "model": model or None,
        "notice": notice,
        "tool_used": tool_result.tool if tool_result else None,
        "tool_ok": tool_result.ok if tool_result else None,
        "tool_error_code": tool_result.error_code if tool_result else None,
        "data": tool_result.data if tool_result and tool_result.ok else None,
        "available_tools": [tool.name for tool in tools],
        # Makes the protocol layer visible to the client rather than implied.
        "tool_transport": "mcp",
        "mcp_server": mcp.server_info()["name"],
        "elapsed_ms": elapsed_ms,
    }
