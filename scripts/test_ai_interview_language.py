"""Per-session AI Interview language selection tests.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_language

No database, network or LiveKit connection is used.
"""

import inspect
import secrets
from types import SimpleNamespace
from unittest.mock import patch

from app.ai.interview import agent, plan_client, worker
from app.ai.interview.agent_auth import mint_agent_token
from app.ai.interview.config import VoiceSettings
from app.models import Candidate, Interview
from app.routers.ai_interview import SessionRequest, agent_plan
from app.services import interview_context_service


passed = 0
failed: list[str] = []


def check(name: str, ok: bool) -> None:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}")


def make_plan(language_marker=...) -> dict:
    payload = {
        "room_name": "smarthr-ai-interview-language-test",
        "questions": [],
        "job": {"job_id": 1, "title": "Test role", "requirements": []},
    }
    if language_marker is not ...:
        payload["language"] = language_marker
    return payload


def test_request_validation() -> None:
    print("\n1. Session request validation")
    check("accepts en", SessionRequest(interview_id=1, language="en").language == "en")
    check("accepts ar", SessionRequest(interview_id=1, language="ar").language == "ar")
    check("missing language remains optional", SessionRequest(interview_id=1).language is None)
    check("explicit null remains compatible", SessionRequest(interview_id=1, language=None).language is None)
    try:
        SessionRequest(interview_id=1, language="fr")
        valid = False
    except ValueError:
        valid = True
    check("rejects unsupported language", valid)


def test_plan_language() -> None:
    print("\n2. Agent plan validation and room binding")
    for language in ("en", "ar"):
        check(f"plan accepts {language}", plan_client.parse_interview(make_plan(language), "smarthr-ai-interview-language-test").language == language)
    for label, payload in (
        ("missing", make_plan()),
        ("null", make_plan(None)),
    ):
        check(f"plan accepts {label} language for environment fallback",
              plan_client.parse_interview(payload, "smarthr-ai-interview-language-test").language is None)
    try:
        plan_client.parse_interview(make_plan([]), "smarthr-ai-interview-language-test")
        valid = False
    except plan_client.PlanUnavailable:
        valid = True
    check("rejects malformed plan language", valid)

    settings = VoiceSettings(
        livekit_url="wss://test.invalid",
        api_key="test-key",
        api_secret=secrets.token_urlsafe(32),
        stt_model="deepgram/nova-3",
        tts_model="cartesia/sonic-3",
        llm_model="openai/gpt-4o",
        language="en",
        token_ttl_minutes=10,
    )
    token = mint_agent_token(settings.api_key, settings.api_secret,
                             "smarthr-ai-interview-language-test")
    requested_plan_languages = []

    def fake_plan(_db, *, language):
        requested_plan_languages.append(language)
        return []

    with (
        patch("app.routers.ai_interview.voice_settings", return_value=settings),
        patch("app.routers.ai_interview.interview_context_service.plan_context_for_room",
              return_value=({"job_id": 1, "title": "Test role", "requirements": []}, "ar")),
        patch("app.routers.ai_interview.question_bank_service.interview_plan", side_effect=fake_plan),
    ):
        result = agent_plan(f"Bearer {token}", db=object())
    check("protected agent plan returns language from the room binding",
          result["language"] == "ar" and result["room_name"] == "smarthr-ai-interview-language-test")
    check("the session language selects the corresponding bank text variant",
          requested_plan_languages == ["ar"])

    class FakeDb:
        binding = None

        def add(self, row):
            self.binding = row

        def commit(self):
            pass

    db = FakeDb()
    interview_context_service.bind_room(
        db, "smarthr-ai-interview-language-test", Interview(id=1), Candidate(id=1), 10,
        language="ar",
    )
    check("room binding persists the selected language", db.binding.language == "ar")


def test_stt_language_and_fallback() -> None:
    print("\n3. Worker STT language and environment fallback")
    captured: dict = {}

    class FakeSession:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    settings = VoiceSettings(
        livekit_url="wss://test.invalid",
        api_key="test-key",
        api_secret=secrets.token_urlsafe(32),
        stt_model="deepgram/nova-3",
        tts_model="cartesia/sonic-3",
        llm_model="openai/gpt-4o",
        language="multi",
        token_ttl_minutes=10,
    )

    def build(language):
        captured.clear()
        with (
            patch.object(worker, "voice_settings", return_value=settings),
            patch.object(worker, "AgentSession", FakeSession),
            patch.object(worker.inference, "STT", side_effect=lambda **kwargs: SimpleNamespace(**kwargs)),
            patch.object(worker.inference, "LLM", return_value=object()),
            patch.object(
                worker.inference,
                "TTS",
                side_effect=lambda **kwargs: (captured.update(tts_kwargs=kwargs) or object()),
            ),
            patch.object(worker.turn_policy, "vad", return_value=object()),
            patch.object(worker.turn_policy, "turn_handling", return_value=object()),
            patch.object(worker, "SessionConnectOptions", return_value=object()),
        ):
            worker.build_session(language)
        return captured["stt"].language, captured["tts_kwargs"]

    en_stt, en_tts = build("en")
    ar_stt, ar_tts = build("ar")
    legacy_stt, legacy_tts = build(None)
    check("selected English configures English STT and TTS",
          en_stt == "en" and en_tts.get("language") == "en")
    check("selected Arabic configures Arabic STT and TTS",
          ar_stt == "ar" and ar_tts.get("language") == "ar")
    check("missing/legacy language uses environment STT fallback and leaves multi TTS unchanged",
          legacy_stt == "multi" and "language" not in legacy_tts)
    check("Arabic is rejected for an unverified configured TTS model",
          worker.tts_language_for(settings, "ar") == "ar"
          and worker.tts_language_for(SimpleNamespace(tts_model="cartesia/sonic-2", language="en"), None)
          == "en")
    try:
        worker.tts_language_for(SimpleNamespace(tts_model="cartesia/sonic-2", language="en"), "ar")
        unsupported_arabic_tts = False
    except ValueError:
        unsupported_arabic_tts = True
    check("unverified Arabic model fails explicitly", unsupported_arabic_tts)
    check("legacy Arabic environment language selects Arabic TTS",
          worker.tts_language_for(SimpleNamespace(tts_model="cartesia/sonic-3", language="ar"), None) == "ar")
    from livekit.agents import inference
    configured_tts = inference.TTS(
        model=settings.tts_model, language="ar", api_key="offline-test-key",
        api_secret=secrets.token_urlsafe(32),
    )
    check("installed LiveKit Inference accepts Arabic for the configured Sonic 3 model",
          configured_tts._opts.model == settings.tts_model
          and str(configured_tts._opts.language) == "ar")
    source = inspect.getsource(worker.interview_session)
    check("worker passes the validated plan language into session construction",
          "questions, job, session_language = plan.questions, plan.job, plan.language" in source
          and "effective_language = session_language or settings.language" in source
          and "build_session(effective_language if effective_language in {\"en\", \"ar\"} else None)" in source
          and "log_stt_configuration(settings, effective_language)" in source)
    check("worker passes the same effective language into the GPT interviewer",
          "language=effective_language" in source)

    check("English session instructions constrain GPT-generated replies",
          "answer in English" in agent.build_instructions(None, language="en"))
    check("Arabic session instructions constrain GPT-generated replies",
          "answer in Arabic" in agent.build_instructions(None, language="ar"))
    check("legacy multi-language setting retains applicant-language behavior",
          "answer in the language the applicant uses" in agent.build_instructions(None, language="multi"))
    check("legacy Arabic regional language keeps Arabic generated replies",
          "answer in Arabic" in agent.build_instructions(None, language="ar-SA"))
    check("language instruction is additive to the existing interviewer rules",
          agent.build_instructions(None, language="ar").startswith(agent.INSTRUCTIONS)
          and "never invent interview questions" in agent.INSTRUCTIONS.lower())

    warning = worker.log_stt_configuration(settings, language="ar")
    check("selected Arabic logs the actual STT language and raises model-specific warning",
          warning is not None and "partly reliable" in warning)
    check("selected English suppresses Arabic STT warning",
          worker.log_stt_configuration(settings, language="en") is None)

    from app.models import InterviewQuestion
    from app.services import question_bank_service as bank
    with patch("app.ai.interview.config.interview_setting", return_value="ar"):
        check("legacy NULL question language follows the environment fallback",
              bank.question_language(None) == "ar")
    try:
        bank.planned_question(InterviewQuestion(id=99, question_text="An old question."), "ar")
        missing_translation_refused = False
    except bank.QuestionBankError as exc:
        missing_translation_refused = exc.code == "translation_missing"
    check("missing Arabic variant is refused rather than silently replaced by English",
          missing_translation_refused)

    from app.ai.interview.questions import PlannedQuestion, QuestionProgress
    from app.ai.interview.spoken import PHRASES, spoken_phrase

    arabic_closing = spoken_phrase("closing_after_last", "ar")
    progress = QuestionProgress(
        [PlannedQuestion(1, 10, "general", "Tell me about yourself.")],
        closing_text=arabic_closing,
    )
    check("Arabic fixed interviewer phrases are available across the voice path",
          all(any("\u0600" <= c <= "\u06ff" for c in spoken_phrase(
                  key, "ar", count=3, title="Data Analyst"
              )) and spoken_phrase(key, "ar", count=3, title="Data Analyst") != english
              for key, (english, _arabic) in PHRASES.items()))
    check("the selected language localizes the deterministic final question phrase",
          progress.decide("answer", "I am a software engineer.").say_after == arabic_closing)
    arabic_follow_up = PlannedQuestion(101, 10, "follow_up", "ما الذي دفعك إلى اختيار هذا المسار؟")
    arabic_q1 = PlannedQuestion(1, 10, "general", "حدّثني عن نفسك.", follow_up=arabic_follow_up)
    arabic_q2 = PlannedQuestion(2, 20, "behavioral", "صف موقفًا صعبًا واجهته.")
    arabic_q3 = PlannedQuestion(3, 30, "general", "ما أبرز نقاط قوتك؟")
    arabic_q4 = PlannedQuestion(4, 40, "technical", "كيف تتعلم تقنية جديدة؟")
    adaptive_progress = QuestionProgress([arabic_q1, arabic_q2, arabic_q3, arabic_q4])
    follow_up_directive = adaptive_progress.decide(
        "answer", "بدأت مسيرتي في تحليل البيانات.", ask_follow_up=True
    )
    adaptive_progress.commit()
    adaptive_progress.decide("answer", "اخترت هذا المسار بسبب اهتمامي بالتحليل.")
    adaptive_progress.commit()
    adaptive_directive = adaptive_progress.decide(
        "answer", "عملت ضمن فريق متعدد التخصصات.", next_question_id=4
    )
    check("Arabic follow-up text is spoken under its existing logical question id",
          follow_up_directive.say_after == arabic_follow_up.text
          and adaptive_progress.answers[0].question_id == arabic_q1.id
          and adaptive_progress.answers[1].question_id == arabic_follow_up.id)
    check("adaptive selection chooses the same logical id and speaks its Arabic variant",
          adaptive_directive.say_after == arabic_q4.text
          and adaptive_progress.current.id == arabic_q4.id)

    class Handle:
        async def wait_for_playout(self):
            pass

    class Session:
        def __init__(self):
            self.said = []

        def say(self, text, **kwargs):
            self.said.append(text)
            return Handle()

    from app.ai.interview.controller import InterviewController
    from app.ai.interview.state import InterviewStateMachine

    session = Session()
    controller = InterviewController(
        session, InterviewStateMachine(), "language-test",
        progress=QuestionProgress([PlannedQuestion(1, 10, "general", "Tell me about yourself.")]),
        language="ar",
    )
    import asyncio
    asyncio.run(controller.run_opening())
    check("Arabic selected language localizes the actual welcome without changing question identity",
          session.said[0] == spoken_phrase("welcome", "ar", count=1)
          and session.said[1] == "Tell me about yourself.")


def main() -> int:
    test_request_validation()
    test_plan_language()
    test_stt_language_and_fallback()
    print(f"\n{passed} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
