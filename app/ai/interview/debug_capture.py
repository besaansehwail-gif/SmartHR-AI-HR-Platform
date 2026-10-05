"""Debug-only capture of each applicant turn: audio + transcript + decisions.

    SMARTHR_INTERVIEW_DEBUG_CAPTURE=true      (env -> .env.local -> .env)
    SMARTHR_INTERVIEW_DEBUG_CAPTURE=raw       ... and also the untrimmed audio

Off by default and **refused in production** (`production.validate_production`
and `capture_enabled()` both check `SMARTHR_ENV`). When on, the worker writes,
per applicant turn, next to each other:

    debug_captures/<room>/turn-<n>.wav    the applicant's speech in this turn:
                                          LiveKit's started/stopped_speaking_at
                                          (VAD) +- 300 ms, 16-bit PCM; the whole
                                          buffer when no speech times are known
    debug_captures/<room>/turn-<n>.raw.wav  ("raw" only) everything the
                                          microphone delivered since the
                                          previous turn
    debug_captures/<room>/turn-<n>.json   the transcript, STT confidence,
                                          speech duration, the classification,
                                          the directive and the words spoken
                                          back, with per-stage timings

so an STT error (the audio says one thing, the transcript another) can be
told apart from a pipeline error (the transcript is right, the reply is not).

This is the ONLY place in the worker that writes speech or transcripts
anywhere, and only to local disk on a development machine. Normal logs stay
metadata-only. Delete the folder after debugging.
"""

import json
import logging
import math
import time
import wave
from pathlib import Path
from typing import Any

logger = logging.getLogger("smarthr.interview.debug_capture")

CAPTURE_VAR = "SMARTHR_INTERVIEW_DEBUG_CAPTURE"
CAPTURE_DIR = Path(__file__).resolve().parents[3] / "debug_captures"
#: At most this much audio is kept per turn (the head is dropped beyond it).
MAX_TURN_AUDIO_S = 120.0
#: Kept on each side of the speech when trimming.
PADDING_S = 0.3
RAW = "raw"


def capture_mode() -> str | None:
    """None (off), "trimmed" or "raw" - as requested, before the production check."""
    from app.ai.interview.config import interview_setting

    value = (interview_setting(CAPTURE_VAR) or "").strip().lower()
    if value == RAW:
        return RAW
    return "trimmed" if value in ("1", "true", "yes", "on") else None


def capture_requested() -> bool:
    return capture_mode() is not None


def capture_enabled() -> bool:
    """Requested AND not production. Production never captures."""
    from app.settings import PRODUCTION, environment

    return capture_requested() and environment() != PRODUCTION


class TurnCapture:
    """Per-room buffer of microphone frames, written out per turn."""

    def __init__(self, room_name: str, enabled: bool | None = None, root: Path = CAPTURE_DIR,
                 raw: bool | None = None) -> None:
        self.enabled = capture_enabled() if enabled is None else enabled
        self.raw = (capture_mode() == RAW) if raw is None else raw
        self.dir = root / "".join(c for c in room_name if c.isalnum() or c in "-_")
        #: (wall-clock start time, frame). Frames carry no timestamp, so a
        #: SAMPLE clock is kept: t0 at the first frame, then samples / rate -
        #: arrival times jitter, the sample count does not.
        self._frames: list = []
        self._samples = 0
        self._t0: float | None = None
        self._clock_samples = 0
        if self.enabled:
            logger.warning("DEBUG CAPTURE ON: audio and transcripts are written to %s", self.dir)

    def add_frame(self, frame, now: float | None = None) -> None:
        if not self.enabled:
            return
        rate = frame.sample_rate or 1
        if self._t0 is None:
            self._t0 = (time.time() if now is None else now) - frame.samples_per_channel / rate
        self._frames.append((self._t0 + self._clock_samples / rate, frame))
        self._clock_samples += frame.samples_per_channel
        self._samples += frame.samples_per_channel
        limit = int(MAX_TURN_AUDIO_S * rate)
        while self._samples > limit and len(self._frames) > 1:
            _, dropped = self._frames.pop(0)
            self._samples -= dropped.samples_per_channel

    @staticmethod
    def _write(path: Path, frames: list) -> None:
        from livekit import rtc

        audio = rtc.combine_audio_frames(frames)
        with wave.open(str(path), "wb") as out:
            out.setnchannels(audio.num_channels)
            out.setsampwidth(2)
            out.setframerate(audio.sample_rate)
            out.writeframes(bytes(audio.data))

    def end_turn(self, turn: int, start: float | None = None, stop: float | None = None, **meta: Any) -> None:
        """Write this turn's audio and metadata; start a new buffer.

        `start` / `stop`: the applicant's speech in this turn, wall clock
        (LiveKit's started/stopped_speaking_at). The WAV keeps only the frames
        overlapping [start - 0.3 s, stop + 0.3 s]; without them, all of it."""
        if not self.enabled:
            return
        stamped, self._frames, self._samples = self._frames, [], 0
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            window = (isinstance(start, (int, float)) and isinstance(stop, (int, float))
                      and not isinstance(start, bool) and math.isfinite(start) and math.isfinite(stop)
                      and 0 < start <= stop)
            kept, note = [], None
            if window:
                low, high = start - PADDING_S, stop + PADDING_S
                kept = [f for t, f in stamped
                        if t < high and t + f.samples_per_channel / (f.sample_rate or 1) > low]
                if not kept:
                    note = "speech window outside the captured audio"
            elif start is not None or stop is not None:
                note = "unusable speech times"
            if not kept:
                # No usable window: keep everything rather than nothing.
                window, kept = False, [f for _, f in stamped]
            if kept:
                self._write(self.dir / f"turn-{turn}.wav", kept)
            raw_file = None
            if self.raw and stamped:
                raw_file = f"turn-{turn}.raw.wav"
                self._write(self.dir / raw_file, [f for _, f in stamped])
            self.update(turn, captured_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                        audio_file=f"turn-{turn}.wav" if kept else None, raw_audio_file=raw_file,
                        trimmed=bool(window and kept), padding_ms=int(PADDING_S * 1000) if window else None,
                        speech_window_ms=int((stop - start) * 1000) if window else None, trim_note=note, **meta)
        except Exception as exc:  # debugging must never break an interview
            logger.warning("debug capture failed for turn %s (%s)", turn, type(exc).__name__)

    def update(self, turn: int, **meta: Any) -> None:
        """Merge more fields into the turn's JSON (classification, reply...)."""
        if not self.enabled:
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            path = self.dir / f"turn-{turn}.json"
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"turn": turn}
            data.update(meta)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("debug capture update failed for turn %s (%s)", turn, type(exc).__name__)
