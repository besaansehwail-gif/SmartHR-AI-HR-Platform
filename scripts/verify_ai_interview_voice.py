"""AI Interview - Phase 1 LIVE verification of the complete voice loop.

    venv\\Scripts\\python.exe -m scripts.verify_ai_interview_voice

Needs real LiveKit Cloud credentials (in `.env.local`) and the agent worker
running (`python -m app.ai.interview.worker dev`). It launches its own backend
on port 8044, so the running dev server is not involved.

It plays the applicant's part without a microphone or a person:

  1. SmartHR issues a session         POST /ai-interview/session (real JWT, real RBAC)
  2. LiveKit accepts the token        rtc.Room.connect()
  3. the interviewer is dispatched    an agent participant joins the room
  4. TTS works                        the greeting arrives as audible audio
  5. applicant audio input works      a microphone track is published and the
                                      agent's STT transcribes what it carried
  6. STT works                        the applicant transcript contains the words
  7. GPT-4o answers                   a new interviewer reply appears after it
  8. TTS speaks the reply             audible audio arrives after the reply started
  9. the loop is complete             steps 5-8 happened in that order

The "applicant speech" is itself synthesised with LiveKit Inference TTS, then
published as an ordinary microphone track - so the agent receives exactly what
it would receive from a browser: 48 kHz-ish PCM frames on a microphone source,
with no shortcut into the pipeline. Nothing is stored anywhere.

This is an **integration check**, not a unit test: its failure can mean the
network, LiveKit Cloud, an Inference provider or the worker - which is why
each step is reported separately.
"""

import argparse
import asyncio
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import test_helpers as e2e  # noqa: E402

PORT = 8044
BASE = f"http://127.0.0.1:{PORT}"
APPLICANT = "aiinterview.voicecheck@smarthr.test"

#: What the synthetic applicant says. Short, unambiguous words, so a correct
#: transcription is easy to recognise.
APPLICANT_LINE = "Yes, I can hear you clearly. Thank you. Can you hear me?"
EXPECTED_WORDS = ("hear", "clearly")

SAMPLE_RATE = 24000
FRAME_MS = 10
#: RMS (int16) above which an audio frame counts as sound rather than silence.
AUDIBLE_RMS = 300

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
class Observed:
    agent_identity: str | None = None
    agent_states: list[str] = field(default_factory=list)
    # (monotonic time, speaker, segment id, text, final)
    segments: dict[str, tuple[float, str, str, bool]] = field(default_factory=dict)
    audible_at: list[float] = field(default_factory=list)


class Server:
    """A backend of its own, reading the real `.env.local` like production."""

    def __init__(self, port: int):
        self.port = port
        self._process: subprocess.Popen | None = None

    def __enter__(self) -> "Server":
        self._process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--port", str(self.port), "--log-level", "warning"],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/", timeout=2):
                    return self
            except urllib.error.HTTPError:
                return self
            except Exception:
                time.sleep(0.25)
        raise SystemExit(f"The backend on port {self.port} did not start.")

    def __exit__(self, *_exc) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                self._process.kill()


async def synthesise(text: str) -> list:
    """The applicant's words as audio frames, via LiveKit Inference TTS."""
    import aiohttp
    from livekit.agents import inference

    from app.ai.interview.config import voice_settings

    frames = []
    async with aiohttp.ClientSession() as http:
        tts = inference.TTS(model=voice_settings().tts_model, http_session=http,
                            sample_rate=SAMPLE_RATE)
        async for chunk in tts.synthesize(text):
            frames.append(chunk.frame)
    return frames


def _rms(frame) -> float:
    import numpy as np

    data = np.frombuffer(frame.data, dtype=np.int16).astype(np.float64)
    return float(np.sqrt(np.mean(data * data))) if data.size else 0.0


def _rechunk(frames: list) -> list[bytes]:
    """Split synthesised audio into 10 ms mono int16 chunks."""
    pcm = b"".join(bytes(f.data) for f in frames)
    step = SAMPLE_RATE * FRAME_MS // 1000 * 2
    return [pcm[i:i + step] for i in range(0, len(pcm) - step + 1, step)]


async def wait_for(predicate, timeout: float, interval: float = 0.1) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


async def run(session: dict) -> None:
    from livekit import rtc

    obs = Observed()
    me = session["participant_identity"]
    room = rtc.Room()
    tasks: set[asyncio.Task] = set()

    def spawn(coro) -> None:
        task = asyncio.ensure_future(coro)
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    async def read_segment(reader, identity: str) -> None:
        speaker = "applicant" if identity == me else "interviewer"
        attrs = reader.info.attributes or {}
        seg = attrs.get("lk.segment_id") or reader.info.id
        started = obs.segments.get(seg, (time.monotonic(),))[0]
        text = ""
        try:
            async for chunk in reader:
                text += chunk
                obs.segments[seg] = (started, speaker, text, False)
        except Exception:
            pass
        final = (reader.info.attributes or {}).get("lk.transcription_final") == "true"
        obs.segments[seg] = (started, speaker, text, final)

    room.register_text_stream_handler(
        "lk.transcription", lambda reader, identity: spawn(read_segment(reader, identity))
    )

    async def listen(track) -> None:
        async for event in rtc.AudioStream(track, sample_rate=SAMPLE_RATE, num_channels=1):
            if _rms(event.frame) > AUDIBLE_RMS:
                obs.audible_at.append(time.monotonic())

    def note_agent(p) -> None:
        if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
            obs.agent_identity = p.identity
            state = p.attributes.get("lk.agent.state")
            if state and (not obs.agent_states or obs.agent_states[-1] != state):
                obs.agent_states.append(state)

    room.on("participant_connected", note_agent)
    room.on("participant_attributes_changed", lambda _changed, p: note_agent(p))
    room.on(
        "track_subscribed",
        lambda track, _pub, p: spawn(listen(track))
        if track.kind == rtc.TrackKind.KIND_AUDIO and p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
        else None,
    )

    print("\n  (synthesising the applicant's line with LiveKit Inference TTS...)")
    applicant_audio = _rechunk(await synthesise(APPLICANT_LINE))

    t0 = time.monotonic()
    try:
        await room.connect(session["server_url"], session["participant_token"])
        check("2. LiveKit accepted the SmartHR-issued token", True,
              f"{time.monotonic() - t0:.1f}s")
    except Exception as exc:
        check("2. LiveKit accepted the SmartHR-issued token", False, type(exc).__name__)
        return

    # Publish the "microphone" immediately and keep it fed with silence, the
    # way a browser's microphone track is live before anybody speaks.
    source = rtc.AudioSource(SAMPLE_RATE, 1)
    track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_MICROPHONE
    await room.local_participant.publish_track(track, options)

    speech_queue: asyncio.Queue[bytes] = asyncio.Queue()
    silence = bytes(SAMPLE_RATE * FRAME_MS // 1000 * 2)
    samples = SAMPLE_RATE * FRAME_MS // 1000

    async def microphone() -> None:
        while True:
            chunk = silence if speech_queue.empty() else speech_queue.get_nowait()
            await source.capture_frame(rtc.AudioFrame(chunk, SAMPLE_RATE, 1, samples))

    spawn(microphone())
    for p in room.remote_participants.values():
        note_agent(p)

    ok = await wait_for(lambda: obs.agent_identity is not None, 30)
    check("3. the interviewer agent was dispatched into the room", ok,
          obs.agent_identity or "no agent within 30s")
    if not ok:
        await room.disconnect()
        return

    def interviewer_text() -> str:
        return " ".join(s[2] for s in sorted(obs.segments.values()) if s[1] == "interviewer")

    # Audible audio AND spoken words. The greeting's wording is not asserted:
    # since Phase 3 it is the Question Bank welcome, not Phase 1's "can you hear me?".
    ok = await wait_for(lambda: bool(obs.audible_at) and bool(interviewer_text().strip()), 30)
    check("4. TTS: the greeting arrived as audible audio", ok,
          f"{len(obs.audible_at)} audible frames")
    print(f"        interviewer said: {interviewer_text()[:160]!r}")

    # Let the greeting finish: wait for the agent to go back to listening, or
    # for 1.5 s without audible audio, whichever comes first.
    await wait_for(
        lambda: (obs.agent_states and obs.agent_states[-1] == "listening")
        or (obs.audible_at and time.monotonic() - obs.audible_at[-1] > 1.5),
        30,
    )
    await asyncio.sleep(0.5)

    spoke_at = time.monotonic()
    for chunk in applicant_audio:
        speech_queue.put_nowait(chunk)
    check("5. applicant audio published on a microphone track", True,
          f"{len(applicant_audio) * FRAME_MS / 1000:.1f}s of speech")

    def applicant_text() -> str:
        return " ".join(s[2] for s in sorted(obs.segments.values())
                        if s[1] == "applicant" and s[0] >= spoke_at - 1)

    ok = await wait_for(lambda: all(w in applicant_text().lower() for w in EXPECTED_WORDS), 30)
    check("6. STT: the agent transcribed the applicant's words", ok,
          repr(applicant_text()[:120]))

    def replies() -> list[tuple[float, str, str, bool]]:
        return [s for s in sorted(obs.segments.values())
                if s[1] == "interviewer" and s[0] > spoke_at and s[2].strip()]

    ok = await wait_for(lambda: bool(replies()), 45)
    reply_text = " ".join(r[2] for r in replies())
    check("7. GPT-4o: the interviewer produced a reply to what was said", ok,
          repr(reply_text[:160]))

    reply_start = replies()[0][0] if replies() else time.monotonic()
    ok = await wait_for(lambda: any(t >= reply_start - 0.5 for t in obs.audible_at), 30)
    check("8. TTS: the reply arrived as audible audio", ok)

    seen = set(obs.agent_states)
    check("9. full loop: agent went listening -> thinking -> speaking",
          {"listening", "thinking", "speaking"} <= seen, " -> ".join(obs.agent_states))

    await asyncio.sleep(2)
    await room.disconnect()
    for task in list(tasks):
        task.cancel()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    from app.ai.interview.config import export_livekit_environment, voice_settings

    print("SmartHR - AI Interview Phase 1 LIVE voice-loop verification")
    settings = voice_settings()
    if not settings.configured:
        print(f"\nNot configured. Missing: {', '.join(settings.missing)}")
        print("Add them to .env.local (see livekit.env.example) and re-run.")
        return 2
    export_livekit_environment(settings)
    print(f"models: stt={settings.stt_model} llm={settings.llm_model} tts={settings.tts_model}")

    e2e.BASE = BASE
    with Server(PORT):
        token = e2e.register_applicant(APPLICANT, "Voice Check")
        interview = e2e.ensure_ai_interview(token)
        r = e2e.request("POST", "/ai-interview/session", token=token,
                        json_body={"interview_id": interview["interview_id"]})
        if not check("1. SmartHR issued a session to a signed-in applicant", r.ok, f"HTTP {r.status}"):
            return 1
        asyncio.run(run(r.body))

    print(f"\n{passed} passed, {len(failed)} failed")
    for failure in failed:
        print(f"  - {failure}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
