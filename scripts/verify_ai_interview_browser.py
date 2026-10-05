"""AI Interview - a REAL browser session, end to end.

    venv\\Scripts\\python.exe -m scripts.verify_ai_interview_browser

What is real: Chrome, the SmartHR frontend (Vite on :3000), the SmartHR
backend (:8000 - the frontend's API address is fixed there), the applicant's
sign-in, `AiInterviewPage`, livekit-client, WebRTC to LiveKit Cloud, the
agent worker, STT, GPT-4o and TTS.

What is simulated: only the person. Chrome's own fake-media flags replace
the microphone with a WAV file - `--use-fake-device-for-media-stream` plus
`--use-file-for-fake-audio-capture` - so the browser captures, encodes and
sends that audio exactly as it would a microphone. The WAV holds the
applicant's answer WITH a 1.5 s thinking pause in the middle, preceded by
silence while the interviewer asks its question.

Chrome is driven over the DevTools protocol with the `websockets` package the
venv already has; no browser-automation dependency was added. The page is
read back from the DOM - the transcript bubbles and the state badges the
applicant sees - and a screenshot is saved.

Needs: Chrome, the worker running, backend on 8000 and Vite on 3000 serving
current code.
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import test_helpers as e2e  # noqa: E402

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]
FRONTEND = "http://127.0.0.1:3000"
DEBUG_PORT = 9333
#: Phase 5: an EXISTING applicant with a REAL CV (create_applicant_test_accounts.py):
#: ML Engineer at Cedar Analytics, data scientist before that. The CV does not
#: mention Kubernetes - answer 3 does, to catch a CV claim GPT-4o invents.
APPLICANT = "applicant05@smarthr.test"

#: Silence before the first answer: connect + dispatch + welcome + Q1.
LEAD_SILENCE_S = 15.0
PAUSE_S = 1.5
#: Answer 1 has a mid-sentence thinking pause (Phase 2's test, kept).
PART_1 = "Hi. For the last four years I have worked in machine learning engineering, and"
PART_2 = "before that I spent a year as a data scientist building churn models for a telecom company."
#: Answers 2 and 3 (Phase 3: the interview must move Q1 -> Q2 -> Q3).
ANSWER_2 = ("Last year a database migration failed on release night. I rolled it back, "
            "found the cause the next morning, and we shipped it safely a week later.")
ANSWER_3 = "I agree on clear goals early, I review my teammates' code, and I deploy our models on Kubernetes."
#: Between answers: end of turn + acknowledgement + the next question
#: (~10 s measured in the live progression scenario) with margin.
GAP_S = 17.0
TAIL_SILENCE_S = 35.0
OUT_RATE = 48000

passed = 0
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}{f'  ({detail})' if detail else ''}")
    else:
        failed.append(f"{name}{f' - {detail}' if detail else ''}")
        print(f"  FAIL  {name}{f' - {detail}' if detail else ''}")
    return bool(ok)


async def build_wav(path: Path) -> tuple[float, float]:
    """The fake microphone's content. Returns (answer start, answer end) in s."""
    import numpy as np

    from scripts.verify_ai_interview_voice import SAMPLE_RATE, synthesise

    def pcm(frames):
        return np.frombuffer(b"".join(bytes(f.data) for f in frames), dtype=np.int16)

    a, b = pcm(await synthesise(PART_1)), pcm(await synthesise(PART_2))
    c, d = pcm(await synthesise(ANSWER_2)), pcm(await synthesise(ANSWER_3))
    silence = lambda s: np.zeros(int(SAMPLE_RATE * s), dtype=np.int16)  # noqa: E731
    audio = np.concatenate([silence(LEAD_SILENCE_S), a, silence(PAUSE_S), b, silence(GAP_S),
                            c, silence(GAP_S), d, silence(TAIL_SILENCE_S)])
    # Resample 24 kHz -> 48 kHz (linear) - the rate Chrome captures at.
    x = np.arange(len(audio) * OUT_RATE // SAMPLE_RATE) * SAMPLE_RATE / OUT_RATE
    out = np.interp(x, np.arange(len(audio)), audio.astype(np.float64)).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(OUT_RATE)
        w.writeframes(out.tobytes())
    start = LEAD_SILENCE_S
    end = start + (len(a) + len(b) + len(c) + len(d)) / SAMPLE_RATE + PAUSE_S + 2 * GAP_S
    return start, end


class Cdp:
    def __init__(self, ws):
        self.ws = ws
        self.next_id = 0

    async def call(self, method: str, **params):
        self.next_id += 1
        my_id = self.next_id
        await self.ws.send(json.dumps({"id": my_id, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == my_id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    async def js(self, expression: str):
        r = await self.call("Runtime.evaluate", expression=expression,
                            returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")


READ_PAGE = r"""(() => {
  const badges = [...document.querySelectorAll('dl > div')].map(d => [
    (d.querySelector('dt')||{}).textContent?.trim(), (d.querySelector('dd')||{}).textContent?.trim()]);
  const bubbles = [...document.querySelectorAll('[aria-live="polite"] .rounded-2xl')].map(b => {
    const ps = b.querySelectorAll('p'); return [ps[0]?.textContent?.trim(), ps[1]?.textContent?.trim()]; });
  return {badges, bubbles, meter: document.querySelector('[role=meter]')?.getAttribute('aria-valuenow')};
})()"""


def click_text(label: str) -> str:
    return f"""(() => {{
      const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim() === {json.dumps(label)});
      if (!b) return 'missing'; if (b.disabled) return 'disabled'; b.click(); return 'clicked'; }})()"""


#: Set in main(): the applicant's interview and the job it is for (Phase 4).
JOB: dict = {}


def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("\u2019", "'").split()).rstrip(".?")


async def drive(chrome_ws: str, token: str, me: dict, answer: tuple[float, float], shot: Path,
                plan: list[str]) -> None:
    import websockets

    async with websockets.connect(chrome_ws, max_size=50_000_000) as ws:
        cdp = Cdp(ws)
        await cdp.call("Page.enable")
        await cdp.call("Runtime.enable")
        await cdp.call("Page.navigate", url=FRONTEND)
        await asyncio.sleep(3)
        await cdp.js(
            f"localStorage.setItem('smarthr_access_token', {json.dumps(token)});"
            f"localStorage.setItem('smarthr_user_id', {json.dumps(str(me['id']))});"
            f"localStorage.setItem('smarthr_role_id', {json.dumps(str(me['role_id']))});"
            "localStorage.setItem('smarthr_locale', 'en'); true")
        await cdp.call("Page.reload")
        await asyncio.sleep(5)

        r = await cdp.js(click_text("AI Interview"))
        check("browser: signed in as the applicant and opened AI Interview", r == "clicked", r)
        await asyncio.sleep(3)
        before = dict((await cdp.js(READ_PAGE) or {}).get("badges") or [])
        check("browser: the page shows the interview's job title before starting",
              before.get("Position") == JOB["job_title"], repr(before.get("Position")))
        r = await cdp.js(click_text("Start interview"))
        check("browser: 'Start interview' clicked (voice service configured)", r == "clicked", r)
        clicked_at = time.monotonic()

        timeline: list[tuple[float, str, str]] = []
        positions_shown: set = set()
        last = None
        page = {}
        deadline = clicked_at + answer[1] + 30
        while time.monotonic() < deadline:
            page = await cdp.js(READ_PAGE) or {}
            badges = dict(page.get("badges") or [])
            positions_shown.add(badges.get("Position"))
            snap = (badges.get("Interview"), badges.get("Interviewer"), badges.get("Question"))
            if snap != last:
                timeline.append((time.monotonic() - clicked_at, *snap))
                last = snap
            # Done once the third answer has moved the interview on to
            # question 4 and the turn is back with the applicant.
            if snap[0] == "Your turn" and snap[2] and snap[2].startswith("4 of"):
                await asyncio.sleep(1)
                page = await cdp.js(READ_PAGE) or page
                break
            await asyncio.sleep(0.5)

        shot_data = await cdp.call("Page.captureScreenshot", format="png")
        shot.write_bytes(base64.b64decode(shot_data["data"]))
        await cdp.js(click_text("End session"))
        await asyncio.sleep(2)

    print("\n  interview state timeline (seconds after 'Start interview'):")
    for t, istate, agent, qn in timeline:
        print(f"    +{t:5.1f}s  question={qn!s:8} interview={istate!s:26} interviewer={agent}")
    print("\n  transcript as shown on the page:")
    for speaker, text in page.get("bubbles") or []:
        print(f"    {speaker:11}: {text}")

    bubbles = page.get("bubbles") or []
    check("the job title stayed on screen for the whole session (from the backend's session response)",
          positions_shown == {JOB["job_title"]}, str(positions_shown))
    first_line = next((t for sp, t in bubbles if sp == "Interviewer"), "")
    check("the spoken welcome names the same job (the worker got the room's Job Context)",
          _norm(JOB["job_title"]) in _norm(first_line), repr(first_line))
    states = [st for _, st, _, _ in timeline]
    questions_seen = [qn for _, _, _, qn in timeline]
    # `plan` is every active MAIN question in bank order; the test answers
    # three, so Q1-Q3 must be asked and Q4 may already have been.
    bank, plan = plan, plan[:3]

    # Where each bank question appears in the conversation.
    positions = []
    for q in plan:
        idx = next((i for i, (sp, t) in enumerate(bubbles)
                    if sp == "Interviewer" and _norm(q) in _norm(t)), None)
        positions.append(idx)
    all_found = all(i is not None for i in positions)
    check("Q1, Q2, Q3 were all asked, each verbatim from the Question Bank",
          all_found, str(list(zip(plan, positions))))
    check("...in the bank's order (Q1 before Q2 before Q3)",
          all_found and positions == sorted(positions), str(positions))
    for n in range(len(plan)):
        if positions[n] is None:
            continue
        nxt = positions[n + 1] if n + 1 < len(positions) and positions[n + 1] is not None else len(bubbles)
        between = [t for sp, t in bubbles[positions[n] + 1:nxt] if sp == "You"]
        check(f"an applicant answer was heard after Q{n + 1}, before the next question",
              bool(between), f"{len(between)} bubble(s)")
    if all_found:
        first_answer = " ".join(t for sp, t in bubbles[positions[0] + 1:positions[1]] if sp == "You").lower()
        check("Q1's paused answer arrived whole (both halves before Q2)",
              "machine learning" in first_answer and "churn" in first_answer, repr(first_answer[:140]))

    generated = []
    for i, (sp, t) in enumerate(bubbles):
        if sp != "Interviewer":
            continue
        # Remove the bank question the line carries (if any); whatever is
        # left is the model's wording and must not ask anything.
        rest = _norm(t)
        for q in bank:
            if _norm(q) in rest:
                rest = rest.replace(_norm(q), "")
                break
        if "?" in rest:
            generated.append(t)
    check("no interviewer line asked a question that is not from the bank",
          not generated, repr(generated[:2]))
    import re
    cited = [t for sp, t in bubbles if sp == "Interviewer"
             for sent in re.split(r"(?<=[.!?])\s+", t)
             if "kubernetes" in sent.lower() and re.search(r"\b(cv|resume|r.sum.)\b", sent, re.I)]
    check("no interviewer line claims the CV shows Kubernetes (the CV does not; only the applicant said it)",
          not cited, repr(cited))
    page_text = " ".join(t for _, t in bubbles).lower()
    check("the page shows no CV content beyond what was spoken aloud",
          "tensorflow developer certificate" not in page_text and ".docx" not in page_text)
    check("the page counted the questions: 1 of 5 -> 2 of 5 -> 3 of 5 -> 4 of 5",
          all(f"{k} of 5" in questions_seen for k in (1, 2, 3, 4)),
          str(sorted({q for q in questions_seen if q})))
    check("the turn came back to the applicant after every question ('Your turn' x4)",
          states.count("Your turn") >= 4, str(states.count("Your turn")))


def main() -> int:
    chrome = next((c for c in CHROME_CANDIDATES if Path(c).is_file()), None)
    if not chrome:
        print("No Chrome/Edge found.")
        return 2

    print("SmartHR - AI Interview REAL browser session")
    e2e.BASE = "http://127.0.0.1:8000"
    token = e2e.login(APPLICANT)
    if not token:
        print(f"{APPLICANT} not found - run scripts.create_applicant_test_accounts first.")
        return 2
    me = e2e.request("GET", "/auth/me", token=token).body
    # Phase 4: the applicant has a real interview for an existing job; the
    # page lists it and sends only its id.
    JOB.update(e2e.ensure_ai_interview(token))
    print(f"  interview {JOB['interview_id']} for job {JOB['job_title']!r}")
    # The questions the interview SHOULD ask, read from the bank as HR sees it.
    e2e.ensure_staff_account("aiinterview.hr@smarthr.test", 2)
    hr = e2e.login("aiinterview.hr@smarthr.test")
    rows = e2e.request("GET", "/ai-interview/questions?active=true&question_type=main",
                       token=hr).body["questions"]
    plan = [q["question_text"] for q in sorted(rows, key=lambda q: (q["position"], q["id"]))]
    print("  expected from the Question Bank: " + " | ".join(f"Q{i}: {q}" for i, q in enumerate(plan[:3], 1)))

    from app.ai.interview.config import export_livekit_environment
    export_livekit_environment()

    work = Path(tempfile.mkdtemp(prefix="smarthr-browser-"))
    wav = work / "applicant.wav"
    answer = asyncio.run(build_wav(wav))
    print(f"  fake microphone: {answer[0]:.0f}s silence, then 3 answers until {answer[1]:.0f}s "
          f"(answer 1 has a {PAUSE_S}s pause; {GAP_S:.0f}s between answers)")

    profile = work / "profile"
    proc = subprocess.Popen([
        chrome, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-audio-capture={wav}%noloop",
        "--autoplay-policy=no-user-gesture-required", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/list", timeout=2) as r:
                    pages = [p for p in json.load(r) if p.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                time.sleep(0.5)
        if not ws_url:
            print("Chrome did not expose a page target.")
            return 2
        shot = Path(__file__).resolve().parents[1] / "uploads" / "ai_interview_browser_test.png"
        shot.parent.mkdir(exist_ok=True)
        asyncio.run(drive(ws_url, token, me, answer, shot, plan))
        print(f"\n  screenshot: {shot}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(work, ignore_errors=True)

    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
