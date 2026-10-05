"""AI Interview - Phase 2 LIVE turn-taking scenarios, against LiveKit Cloud.

    venv\\Scripts\\python.exe -m scripts.verify_ai_interview_turns
    venv\\Scripts\\python.exe -m scripts.verify_ai_interview_turns --only pause,interrupt

Needs `.env.local` credentials and the worker running
(`python -m app.ai.interview.worker dev`). Launches its own backend on 8044.

Each scenario gets a FRESH room - its own session, its own agent job - so one
scenario's leftovers cannot pass or fail another. The "applicant" speaks
audio synthesised with LiveKit Inference TTS and published on an ordinary
microphone track, exactly what a browser sends. What the agent did is read
from the room itself: the interviewer's audio, the `lk.transcription` text
streams (both sides), LiveKit's `lk.agent.state` attribute, and the
interview's own `smarthr.interview.state` / `smarthr.interview.turns`
attributes published by the controller.

Scenarios (the Phase 2 brief's list):

    handoff    the interviewer finishes the question and hands over the turn
    normal     a normal answer -> one turn -> one reply
    pause      an answer with a 1.5 s mid-sentence pause stays ONE turn
    long       a ~20 s answer is not cut off
    silence    22 s of silence -> no model reply, exactly one fixed nudge
    short      noise and "uh" are ignored; "yes" is answered as short
    interrupt  the applicant talks over the interviewer -> it stops and listens
    progression (Phase 3) Q1 -> Q2 -> Q3 from the Question Bank, verbatim, with
               each answer moving to the next bank question and GPT-4o's
               acknowledgement containing no question of its own

This is an integration check: a failure can be the network, LiveKit Cloud,
an Inference provider, the worker, or the turn policy - each assertion names
what it measured.
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import test_helpers as e2e  # noqa: E402
from scripts.verify_ai_interview_voice import (  # noqa: E402
    AUDIBLE_RMS, FRAME_MS, SAMPLE_RATE, Server, _rms, synthesise,
)

PORT = 8044
BASE = f"http://127.0.0.1:{PORT}"
APPLICANT = "aiinterview.turns@smarthr.test"

SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
CHUNK_BYTES = SAMPLES * 2

LINES = {
    "normal": "My name is Sam. I am a software engineer with five years of experience building web applications for banks.",
    "pause_1": "Before my current job, I worked at a bank for three years, and",
    "pause_2": "then I moved into software engineering, where I now build backend services.",
    "long": (
        "Sure. I studied computer science at university, where I first became interested in databases. "
        "After graduating, I joined a small startup as a junior developer and worked on their payment system. "
        "Two years later I moved to a larger company, where I led a team of four engineers. "
        "We rebuilt the customer portal and cut page load times by half. "
        "Outside of work I enjoy teaching programming to high school students on weekends."
    ),
    "uh": "Uh.",
    "yes": "Yes.",
    "interrupt_setup": "Could you describe what a typical working day in this role would look like, in detail?",
    "interrupt": "Sorry to interrupt, can I ask about the team instead?",
    "split_1": "I studied computer science at university.",
    "split_2": "After that I spent four years building payment systems for a bank.",
    "cv_q": "Before I answer, which company did my CV list as my most recent employer?",
    "cv_k8s": "In that job I also deployed all of our models on Kubernetes clusters myself.",
    "job_q": "Before I start, could you remind me which position this interview is for?",
    "job_a": "I built a machine learning model in Python that sorts customer support tickets by topic.",
    "a1": "I'm Sam. I studied computer science and I have worked as a backend developer for four years.",
    "a2": "Last year a database migration failed on release night, so I rolled it back, found the cause and we shipped it safely the next week.",
    "a3": "I like to agree on clear goals early, I review my teammates' code, and I ask for help when I'm stuck.",
}

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


@dataclass
class Segment:
    started: float
    speaker: str
    text: str = ""
    final: bool = False


@dataclass
class Room:
    """One live session as the applicant sees it."""

    identity: str
    agent_states: list[tuple[float, str]] = field(default_factory=list)
    interview_states: list[tuple[float, str]] = field(default_factory=list)
    counters: dict = field(default_factory=dict)
    question: dict = field(default_factory=dict)
    segments: dict[str, Segment] = field(default_factory=dict)
    audible: list[float] = field(default_factory=list)

    def agent_state(self) -> str | None:
        return self.agent_states[-1][1] if self.agent_states else None

    def interview_state(self) -> str | None:
        return self.interview_states[-1][1] if self.interview_states else None

    def said(self, speaker: str, after: float = 0.0) -> list[Segment]:
        return sorted((s for s in self.segments.values()
                       if s.speaker == speaker and s.started >= after and s.text.strip()),
                      key=lambda s: s.started)

    def text(self, speaker: str, after: float = 0.0) -> str:
        return " ".join(s.text for s in self.said(speaker, after))

    def agent_states_between(self, t0: float, t1: float) -> list[str]:
        return [s for t, s in self.agent_states if t0 <= t <= t1]

    def interview_path(self) -> str:
        path = []
        for _, s in self.interview_states:
            if not path or path[-1] != s:
                path.append(s)
        return " > ".join(path)


async def wait_for(predicate, timeout: float, interval: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return bool(predicate())


class Applicant:
    """Connects, publishes a live microphone, speaks on demand."""

    def __init__(self, session: dict, audio: dict[str, list[bytes]]):
        from livekit import rtc

        self.rtc = rtc
        self.session = session
        self.audio = audio
        self.room = rtc.Room()
        self.obs = Room(identity=session["participant_identity"])
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.tasks: set[asyncio.Task] = set()
        self.drained = asyncio.Event()

    def spawn(self, coro) -> None:
        task = asyncio.ensure_future(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _note(self, p) -> None:
        rtc = self.rtc
        if p.kind != rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
            return
        now = time.monotonic()
        state = p.attributes.get("lk.agent.state")
        if state and self.obs.agent_state() != state:
            self.obs.agent_states.append((now, state))
        istate = p.attributes.get("smarthr.interview.state")
        if istate and self.obs.interview_state() != istate:
            self.obs.interview_states.append((now, istate))
        q = p.attributes.get("smarthr.interview.question")
        if q:
            try:
                self.obs.question = json.loads(q)
            except ValueError:
                pass
        turns = p.attributes.get("smarthr.interview.turns")
        if turns:
            try:
                self.obs.counters = json.loads(turns)
            except ValueError:
                pass

    async def _segment(self, reader, identity: str) -> None:
        speaker = "applicant" if identity == self.obs.identity else "interviewer"
        attrs = reader.info.attributes or {}
        seg_id = attrs.get("lk.segment_id") or reader.info.id
        seg = self.obs.segments.setdefault(seg_id, Segment(time.monotonic(), speaker))
        text = ""
        try:
            async for chunk in reader:
                text += chunk
                seg.text = text
        except Exception:
            pass
        seg.text = text
        seg.final = (reader.info.attributes or {}).get("lk.transcription_final") == "true"

    async def _listen(self, track) -> None:
        async for ev in self.rtc.AudioStream(track, sample_rate=SAMPLE_RATE, num_channels=1):
            if _rms(ev.frame) > AUDIBLE_RMS:
                self.obs.audible.append(time.monotonic())

    async def _microphone(self, source) -> None:
        silence = bytes(CHUNK_BYTES)
        rtc = self.rtc
        while True:
            if self.queue.empty():
                self.drained.set()
                chunk = silence
            else:
                chunk = self.queue.get_nowait()
            await source.capture_frame(rtc.AudioFrame(chunk, SAMPLE_RATE, 1, SAMPLES))

    async def connect(self) -> None:
        rtc = self.rtc
        self.room.register_text_stream_handler(
            "lk.transcription", lambda r, ident: self.spawn(self._segment(r, ident)))
        self.room.on("participant_connected", self._note)
        self.room.on("participant_attributes_changed", lambda _c, p: self._note(p))
        self.room.on("track_subscribed", lambda track, _pub, p: self.spawn(self._listen(track))
                     if track.kind == rtc.TrackKind.KIND_AUDIO
                     and p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT else None)
        await self.room.connect(self.session["server_url"], self.session["participant_token"])
        # A short queue, so "the audio has been sent" is known to within 0.1 s.
        source = rtc.AudioSource(SAMPLE_RATE, 1, queue_size_ms=100)
        track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
        opts = rtc.TrackPublishOptions()
        opts.source = rtc.TrackSource.SOURCE_MICROPHONE
        await self.room.local_participant.publish_track(track, opts)
        self.spawn(self._microphone(source))
        for p in self.room.remote_participants.values():
            self._note(p)

    async def speak(self, key: str) -> tuple[float, float]:
        """Say a line; returns (start, end) - when the audio left this client."""
        self.drained.clear()
        start = time.monotonic()
        for chunk in self.audio[key]:
            self.queue.put_nowait(chunk)
        await self.drained.wait()
        return start, time.monotonic() + 0.1

    async def speak_noise(self, seconds: float) -> tuple[float, float]:
        import numpy as np

        self.drained.clear()
        rng = np.random.default_rng(7)
        pcm = (rng.normal(0, 3000, int(SAMPLE_RATE * seconds))).clip(-32768, 32767).astype(np.int16).tobytes()
        start = time.monotonic()
        for i in range(0, len(pcm) - CHUNK_BYTES + 1, CHUNK_BYTES):
            self.queue.put_nowait(pcm[i:i + CHUNK_BYTES])
        await self.drained.wait()
        return start, time.monotonic() + 0.1

    async def opening(self) -> bool:
        """Wait until the interviewer has asked the question and is listening."""
        ok = await wait_for(lambda: self.obs.interview_state() == "listening", 45)
        await asyncio.sleep(0.5)
        return ok

    async def close(self) -> None:
        await self.room.disconnect()
        for t in list(self.tasks):
            t.cancel()


def rechunk(frames) -> list[bytes]:
    pcm = b"".join(bytes(f.data) for f in frames)
    return [pcm[i:i + CHUNK_BYTES] for i in range(0, len(pcm) - CHUNK_BYTES + 1, CHUNK_BYTES)]


# ---------------------------------------------------------------------------
async def s_handoff(a: Applicant) -> None:
    ok = await a.opening()
    check("handoff: interviewer finished the question and is LISTENING", ok, a.obs.interview_path())
    q = a.obs.text("interviewer").lower()
    check("handoff: the question was asked", "tell me about yourself" in q, repr(q[:90]))
    check("handoff: WAITING/INTRO -> ASKING -> LISTENING order",
          a.obs.interview_path().endswith("intro > asking > listening"), a.obs.interview_path())
    t0 = time.monotonic()
    await asyncio.sleep(4)
    states = a.obs.agent_states_between(t0, time.monotonic())
    check("handoff: nobody spoke -> the interviewer did not start talking",
          "thinking" not in states and "speaking" not in states and not a.obs.said("interviewer", t0),
          str(states))


async def s_normal(a: Applicant) -> None:
    await a.opening()
    start, end = await a.speak("normal")
    got = await wait_for(lambda: bool(a.obs.said("interviewer", start)), 30)
    reply = a.obs.said("interviewer", start)
    heard = a.obs.text("applicant", start - 1).lower()
    check("normal: VAD + STT heard the whole answer",
          all(w in heard for w in ("sam", "software", "banks")), repr(heard[:120]))
    check("normal: GPT-4o replied", got, repr(a.obs.text("interviewer", start)[:140]))
    check("normal: the reply started only after the answer ended",
          bool(reply) and reply[0].started >= end - 0.2,
          f"reply at +{reply[0].started - end:.2f}s after answer end" if reply else "no reply")
    await wait_for(lambda: a.obs.interview_state() == "listening" and reply and time.monotonic() - reply[0].started > 1, 30)
    check("normal: counted as ONE answer", a.obs.counters.get("answers") == 1, str(a.obs.counters))
    check("normal: reply was audible (TTS)", any(t >= reply[0].started - 0.5 for t in a.obs.audible) if reply else False)
    path = a.obs.interview_path()
    check("normal: LISTENING -> PROCESSING -> ASKING (next bank question) -> LISTENING",
          "listening > processing > asking > listening" in path, path)


async def s_pause(a: Applicant) -> None:
    await a.opening()
    s1, e1 = await a.speak("pause_1")
    await asyncio.sleep(1.5)
    s2, e2 = await a.speak("pause_2")
    await wait_for(lambda: bool(a.obs.said("interviewer", s1)), 30)
    early = [s for s in a.obs.said("interviewer", s1) if s.started < e2 - 0.2]
    states = a.obs.agent_states_between(e1, e2 - 0.2)
    check("pause: the interviewer did NOT speak during the 1.5 s pause",
          not early and "speaking" not in states,
          f"early replies={len(early)} agent states in pause={states}")
    heard = a.obs.text("applicant", s1 - 1).lower()
    check("pause: STT received both halves", "bank" in heard and "software" in heard, repr(heard[:140]))
    await asyncio.sleep(3)
    check("pause: both halves were ONE turn / one answer",
          a.obs.counters.get("answers") == 1 and a.obs.counters.get("ignored", 0) == 0, str(a.obs.counters))
    check("pause: GPT-4o replied after the full answer", bool(a.obs.said("interviewer", e2 - 0.2)),
          repr(a.obs.text("interviewer", s1)[:140]))


async def s_long(a: Applicant) -> None:
    await a.opening()
    start, end = await a.speak("long")
    await wait_for(lambda: bool(a.obs.said("interviewer", start)), 40)
    early = [s for s in a.obs.said("interviewer", start) if s.started < end - 0.2]
    check(f"long: a {end - start:.0f} s answer was not cut off", not early,
          f"interviewer began {min((end - s.started) for s in early):.1f}s before the end" if early else "")
    heard = a.obs.text("applicant", start - 1).lower()
    check("long: STT has the first and last sentences",
          "computer science" in heard and "weekends" in heard, f"{len(heard.split())} words")
    await asyncio.sleep(3)
    check("long: ONE answer", a.obs.counters.get("answers") == 1, str(a.obs.counters))
    check("long: GPT-4o replied", bool(a.obs.said("interviewer", end - 0.2)))


async def s_silence(a: Applicant) -> None:
    await a.opening()
    t0 = time.monotonic()
    await asyncio.sleep(22)
    states = a.obs.agent_states_between(t0, time.monotonic())
    said = a.obs.said("interviewer", t0)
    check("silence: GPT-4o was never asked (no 'thinking')", "thinking" not in states, str(states))
    check("silence: exactly one fixed nudge",
          len(said) == 1 and "take your time" in said[0].text.lower() and a.obs.counters.get("nudges") == 1,
          f"{len(said)} interviewer lines: {[s.text[:40] for s in said]}")
    check("silence: the interview did not advance",
          a.obs.counters.get("answers", 0) == 0 and a.obs.interview_state() == "listening",
          f"{a.obs.counters} state={a.obs.interview_state()}")


async def s_short(a: Applicant) -> None:
    await a.opening()
    t0, _ = await a.speak_noise(0.25)
    await asyncio.sleep(6)
    states = a.obs.agent_states_between(t0, time.monotonic())
    check("short: a 0.25 s noise burst -> no reply",
          not a.obs.said("interviewer", t0) and "thinking" not in states, str(states))

    t1, _ = await a.speak("uh")
    await asyncio.sleep(7)
    states = a.obs.agent_states_between(t1, time.monotonic())
    check("short: 'uh' -> GPT-4o not asked, no reply",
          not a.obs.said("interviewer", t1) and "thinking" not in states,
          f"states={states} counters={a.obs.counters} heard={a.obs.text('applicant', t1 - 1)!r}")
    check("short: nothing counted as an answer yet", a.obs.counters.get("answers", 0) == 0, str(a.obs.counters))

    t2, e2 = await a.speak("yes")
    got = await wait_for(lambda: bool(a.obs.said("interviewer", t2)), 25)
    await asyncio.sleep(2)
    check("short: 'yes' IS answered", got, repr(a.obs.text("interviewer", t2)[:140]))
    check("short: 'yes' counted as short, not as an answer",
          a.obs.counters.get("short") == 1 and a.obs.counters.get("answers", 0) == 0, str(a.obs.counters))


async def s_interrupt(a: Applicant) -> None:
    await a.opening()
    s0, e0 = await a.speak("interrupt_setup")
    ok = await wait_for(lambda: a.obs.agent_state() == "speaking" and bool(a.obs.said("interviewer", s0)), 30)
    if not ok:
        check("interrupt: interviewer started a reply to talk over", False, str(a.obs.agent_states[-5:]))
        return
    await asyncio.sleep(1.2)
    if a.obs.agent_state() != "speaking":
        check("interrupt: interviewer still speaking when interrupted (reply too short to test)", False)
        return
    s1, e1 = await a.speak("interrupt")
    stopped = await wait_for(lambda: a.obs.agent_state() != "speaking", 3)
    stop_at = next((t for t, s in a.obs.agent_states if t >= s1 and s != "speaking"), None)
    check("interrupt: the interviewer stopped speaking",
          stopped, f"stopped {stop_at - s1:.2f}s after the applicant started" if stop_at else "still speaking")
    audible_after = [t for t in a.obs.audible if t > s1 + 2.0 and t < e1]
    check("interrupt: no interviewer audio while the applicant kept talking", not audible_after,
          f"{len(audible_after)} audible frames")
    got = await wait_for(lambda: bool(a.obs.said("interviewer", e1 - 0.2)), 30)
    heard = a.obs.text("applicant", s1 - 1).lower()
    check("interrupt: STT heard the interruption", "team" in heard, repr(heard[:100]))
    check("interrupt: GPT-4o answered the NEW turn", got, repr(a.obs.text("interviewer", e1 - 0.2)[:140]))
    await asyncio.sleep(2)
    check("interrupt: counted as an interruption", a.obs.counters.get("interruptions", 0) >= 1, str(a.obs.counters))


def expected_plan(n: int = 3) -> list[str]:
    """The first n bank questions, learned the way HR would see them."""
    hr = "aiinterview.hr@smarthr.test"
    e2e.ensure_staff_account(hr, 2)
    r = e2e.request("GET", "/ai-interview/questions?active=true&question_type=main", token=e2e.login(hr))
    rows = sorted(r.body["questions"], key=lambda q: (q["position"], q["id"]))
    return [q["question_text"] for q in rows[:n]]


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split())


async def s_progression(a: Applicant) -> None:
    plan = expected_plan(3)
    ok = await a.opening()
    first = a.obs.text("interviewer")
    check("progression: Q1 is the bank's first question, verbatim",
          ok and _norm(plan[0]).rstrip(".?") in _norm(first), repr(first[-90:]))
    check("progression: 'question 1 of N' published", a.obs.question.get("number") == 1, str(a.obs.question))
    for n, key in ((2, "a1"), (3, "a2")):
        start, end = await a.speak(key)
        moved = await wait_for(lambda: a.obs.question.get("number") == n
                               and a.obs.interview_state() == "listening"
                               and bool(a.obs.said("interviewer", end - 0.2)), 45)
        reply = a.obs.text("interviewer", end - 0.2)
        target = _norm(plan[n - 1]).rstrip(".?")
        check(f"progression: answer {n - 1} -> Q{n} asked, verbatim from the bank",
              moved and target in _norm(reply), repr(reply[:200]))
        ack = _norm(reply).split(target)[0] if target in _norm(reply) else _norm(reply)
        check(f"progression: GPT-4o's acknowledgement before Q{n} asks nothing", "?" not in ack, repr(ack))
        check(f"progression: interview state went through ASKING for Q{n}",
              "asking" in [s for t, s in a.obs.interview_states if t >= end - 0.2], a.obs.interview_path())
    start, end = await a.speak("a3")
    await wait_for(lambda: a.obs.question.get("number") == 4 and a.obs.interview_state() == "listening", 45)
    await asyncio.sleep(1)
    check("progression: three answers, three questions - each answer counted once",
          a.obs.counters.get("answers") == 3, str(a.obs.counters))


async def s_split(a: Applicant) -> None:
    """Two finished sentences with a pause between: the turn detector may end
    the turn after the first. Whichever it decides, it must stay ONE answer to
    Q1 and the next question must be Q2 - never a skipped question."""
    plan = expected_plan(3)
    await a.opening()
    s1, e1 = await a.speak("split_1")
    await asyncio.sleep(SPLIT_PAUSE_S)
    s2, e2 = await a.speak("split_2")
    await wait_for(lambda: a.obs.question.get("number") == 2
                   and a.obs.interview_state() == "listening"
                   and bool(a.obs.said("interviewer", e2 - 0.2)), 45)
    await asyncio.sleep(2)
    after = a.obs.text("interviewer", s1)
    split = "processing" in [st for t, st in a.obs.interview_states if e1 <= t < s2 + 0.3]
    print(f"        turn ended during the pause: {split}")
    check("split: the next question is the bank's Q2, verbatim",
          _norm(plan[1]).rstrip(".?") in _norm(after), repr(after[-120:]))
    check("split: Q3 was NOT asked (no question skipped)",
          _norm(plan[2]).rstrip(".?") not in _norm(after), repr(after[-120:]))
    check("split: the page shows question 2", a.obs.question.get("number") == 2, str(a.obs.question))
    check("split: both halves counted as ONE answer",
          a.obs.counters.get("answers") == 1, str(a.obs.counters))


async def s_cv(a: Applicant) -> None:
    """Phase 5, as applicant05 (a real CV: ML Engineer at Cedar Analytics;
    it does NOT mention Kubernetes)."""
    import re
    plan = expected_plan(3)
    await a.opening()
    opening = a.obs.text("interviewer")
    check("cv: Q1 is still the bank's first question, verbatim",
          _norm(plan[0]).rstrip(".?") in _norm(opening), repr(opening[-90:]))
    check("cv: the job title is still in the welcome (Phase 4 intact)",
          _norm(CV_RUN["job_title"]) in _norm(opening), repr(opening[:120]))
    # The backend parses the CV when the session starts; give it time to land
    # in GPT-4o's instructions before asking about it (still < the 15 s nudge).
    await asyncio.sleep(CV_SETTLE_S)

    # Only the CV can answer this.
    start, end = await a.speak("cv_q")
    moved = await wait_for(lambda: a.obs.question.get("number") == 2
                           and a.obs.interview_state() == "listening"
                           and bool(a.obs.said("interviewer", end - 0.2)), 60)
    reply = a.obs.text("interviewer", end - 0.2)
    target = _norm(plan[1]).rstrip(".?")
    ack = _norm(reply).split(target)[0] if target in _norm(reply) else _norm(reply)
    print(f"        GPT-4o said: {ack!r}")
    check("cv: GPT-4o answers from the CV Context (names Cedar Analytics)", "cedar analytics" in ack, repr(ack))
    check("cv: ...asks nothing of its own", "?" not in ack, repr(ack))
    check("cv: ...and the next question is the bank's Q2, verbatim",
          moved and target in _norm(reply), repr(reply[-120:]))

    # Not in the CV: GPT-4o may discuss it, but must not cite the CV for it.
    start, end = await a.speak("cv_k8s")
    moved = await wait_for(lambda: a.obs.question.get("number") == 3
                           and a.obs.interview_state() == "listening"
                           and bool(a.obs.said("interviewer", end - 0.2)), 60)
    reply = a.obs.text("interviewer", end - 0.2)
    target = _norm(plan[2]).rstrip(".?")
    ack = _norm(reply).split(target)[0] if target in _norm(reply) else _norm(reply)
    print(f"        GPT-4o said: {ack!r}")
    cites = [sent for sent in re.split(r"(?<=[.!?])\s+", ack)
             if "kubernetes" in sent and re.search(r"\b(cv|resume|r.sum.)\b", sent)]
    check("cv: GPT-4o does not claim the CV shows Kubernetes (it does not)", not cites, repr(cites))
    check("cv: ...asks nothing of its own", "?" not in ack, repr(ack))
    check("cv: ...and the interview moves to the bank's Q3, verbatim",
          moved and target in _norm(reply), repr(reply[-120:]))

    # Nothing from the CV in anything LiveKit carries.
    seen = [a.room.metadata or ""]
    for p in a.room.remote_participants.values():
        seen += [p.metadata or "", json.dumps(dict(p.attributes))]
    blob = " ".join(seen).lower()
    leaked = [w for w in ("cedar", "tensorflow", "scikit", "forecast", "beirut", "cv", ".docx")
              if w in blob]
    check("cv: no CV data in room metadata or participant metadata/attributes", not leaked,
          f"{leaked} in {blob[:200]}")


async def s_job(a: Applicant) -> None:
    """Phase 4: the room's Job Context reached the interviewer."""
    plan = expected_plan(3)
    ok = await a.opening()
    opening = a.obs.text("interviewer")
    check("job: the welcome names the interview's job title (resolved by the backend)",
          ok and _norm(JOB["job_title"]) in _norm(opening), repr(opening[:160]))
    check("job: Q1 is still the bank's first question, verbatim",
          _norm(plan[0]).rstrip(".?") in _norm(opening), repr(opening[-90:]))

    # GPT-4o can only answer this from the Job Context in its instructions.
    start, end = await a.speak("job_q")
    moved = await wait_for(lambda: a.obs.question.get("number") == 2
                           and a.obs.interview_state() == "listening"
                           and bool(a.obs.said("interviewer", end - 0.2)), 45)
    reply = a.obs.text("interviewer", end - 0.2)
    target = _norm(plan[1]).rstrip(".?")
    ack = _norm(reply).split(target)[0] if target in _norm(reply) else _norm(reply)
    print(f"        GPT-4o said: {ack!r}")
    check("job: GPT-4o's reply names the role from the Job Context",
          any(w in ack for w in JOB_WORDS), repr(ack))
    check("job: ...asks nothing of its own", "?" not in ack, repr(ack))
    check("job: ...and the next question is the bank's Q2, verbatim",
          moved and target in _norm(reply), repr(reply[-120:]))

    # A job-relevant answer must not turn into a job-specific question.
    start, end = await a.speak("job_a")
    moved = await wait_for(lambda: a.obs.question.get("number") == 3
                           and a.obs.interview_state() == "listening"
                           and bool(a.obs.said("interviewer", end - 0.2)), 45)
    reply = a.obs.text("interviewer", end - 0.2)
    target = _norm(plan[2]).rstrip(".?")
    ack = _norm(reply).split(target)[0] if target in _norm(reply) else _norm(reply)
    print(f"        GPT-4o said: {ack!r}")
    check("job: after a job-relevant answer GPT-4o asks no question of its own", "?" not in ack, repr(ack))
    check("job: ...and the interview moves to the bank's Q3, verbatim",
          moved and target in _norm(reply), repr(reply[-120:]))


SCENARIOS = {
    "handoff": s_handoff, "normal": s_normal, "pause": s_pause, "long": s_long,
    "silence": s_silence, "short": s_short, "interrupt": s_interrupt,
    "progression": s_progression, "job": s_job, "split": s_split, "cv": s_cv,
}

#: Phase 5: the `cv` scenario runs as an EXISTING applicant with a real CV
#: (create_applicant_test_accounts.py), not as the turn tester.
CV_APPLICANT = "applicant05@smarthr.test"
CV_RUN: dict = {}
CV_SETTLE_S = 8.0

#: Long enough for the turn detector to end the turn after a finished
#: sentence (min_delay 1.2 s), short enough to resume before the reply plays.
SPLIT_PAUSE_S = 2.0

#: Set in main(): the interview (and its job) every session in this run is for.
JOB: dict = {}
#: Words of "DEMO - AI Engineering Intern" a reply naming the role would use.
JOB_WORDS = ("ai engineering", "engineering intern", "ai intern")


async def run_all(names: list[str], token: str) -> None:
    print("\n  (synthesising the applicant's lines with LiveKit Inference TTS...)")
    audio = {k: rechunk(await synthesise(v)) for k, v in LINES.items()}

    for name in names:
        print(f"\n[{name}]")
        run = CV_RUN if name == "cv" else JOB
        r = e2e.request("POST", "/ai-interview/session", token=run["token"],
                        json_body={"interview_id": run["interview_id"]})
        if not check(f"{name}: SmartHR issued a session", r.ok, f"HTTP {r.status}"):
            continue
        a = Applicant(r.body, audio)
        try:
            await a.connect()
            await SCENARIOS[name](a)
            print(f"        interview path: {a.obs.interview_path()}")
            print(f"        counters: {a.obs.counters}")
        except Exception as exc:
            check(f"{name}: ran without error", False, f"{type(exc).__name__}: {exc}")
        finally:
            await a.close()
            await asyncio.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="", help="comma-separated scenario names")
    args = parser.parse_args()
    names = [n for n in args.only.split(",") if n] or list(SCENARIOS)

    from app.ai.interview.config import export_livekit_environment, voice_settings

    print("SmartHR - AI Interview Phase 2 LIVE turn-taking scenarios")
    settings = voice_settings()
    if not settings.configured:
        print(f"\nNot configured. Missing: {', '.join(settings.missing)}")
        return 2
    export_livekit_environment(settings)

    e2e.BASE = BASE
    with Server(PORT):
        token = e2e.register_applicant(APPLICANT, "Turn Tester")
        # Phase 4: every session is for this applicant's interview, for an
        # existing job; the worker resolves the job through the backend.
        JOB.update(e2e.ensure_ai_interview(token), token=token)
        print(f"  interview {JOB['interview_id']} for job {JOB['job_title']!r}")
        if "cv" in names:
            cv_token = e2e.login(CV_APPLICANT)
            if not cv_token:
                print(f"{CV_APPLICANT} missing - run scripts.create_applicant_test_accounts")
                return 2
            CV_RUN.update(e2e.ensure_ai_interview(cv_token), token=cv_token)
            print(f"  cv scenario: {CV_APPLICANT}, interview {CV_RUN['interview_id']}")
        asyncio.run(run_all(names, token))

    print(f"\n{passed} passed, {len(failed)} failed")
    for failure in failed:
        print(f"  - {failure}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
