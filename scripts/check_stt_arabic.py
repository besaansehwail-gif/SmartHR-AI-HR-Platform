"""Real Arabic speech-to-text check through LiveKit Inference (the worker's own path).

    venv\\Scripts\\python.exe -m scripts.check_stt_arabic                 # synthesise the clip, then transcribe
    venv\\Scripts\\python.exe -m scripts.check_stt_arabic --wav me.wav    # transcribe YOUR recording instead
    venv\\Scripts\\python.exe -m scripts.check_stt_arabic --models deepgram/nova-3:ar,speechmatics/enhanced:ar

MAKES REAL CALLS (small LiveKit Inference usage, billed to the project in
.env.local / the environment): one TTS call to make the clip unless --wav is
given, then one STT stream per model:language pair. Credentials are read
exactly as the worker reads them and are never printed.

For each pair it prints the transcript, how much of it is Arabic script, and
a word-overlap score against the sentence that was spoken. A synthetic voice
is easier than a real applicant (clean, no accent, no noise): a pass here is
necessary, not sufficient - confirm with a human recording (--wav).
"""

import argparse
import asyncio
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SENTENCE = "اسمي سارة، وأعمل محللة بيانات منذ ثلاث سنوات، وأستخدم بايثون ولغة الاستعلام يومياً."
DEFAULT_PAIRS = "deepgram/nova-3:ar,deepgram/nova-3:multi,speechmatics/enhanced:ar"
SAMPLE_RATE = 16000


def arabic_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum(1 for c in letters if "؀" <= c <= "ۿ") / len(letters) if letters else 0.0


def _norm(text: str) -> list[str]:
    strip = "ًٌٍَُِّْ"          # harakat
    table = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})
    words = "".join(c if c.isalnum() else " " for c in text).translate(table).split()
    return ["".join(ch for ch in w if ch not in strip) for w in words]


def overlap(reference: str, heard: str) -> float:
    ref, got = _norm(reference), set(_norm(heard))
    return sum(1 for w in ref if w in got) / len(ref) if ref else 0.0


async def synthesise(http, text: str):
    from livekit.agents import inference

    tts = inference.TTS(model="cartesia/sonic-3", language="ar", http_session=http)
    frames = [ev.frame async for ev in tts.synthesize(text)]
    return frames


def read_wav(path: Path):
    from livekit import rtc

    with wave.open(str(path)) as w:
        if w.getsampwidth() != 2:
            raise SystemExit("--wav must be 16-bit PCM")
        rate, channels, data = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    step = rate // 100 * channels * 2                      # 10 ms frames
    return [rtc.AudioFrame(data[i:i + step], rate, channels, len(data[i:i + step]) // (2 * channels))
            for i in range(0, len(data), step) if len(data[i:i + step]) >= 2 * channels]


async def transcribe(http, frames, model: str, language: str) -> str:
    from livekit import rtc
    from livekit.agents import inference, stt as stt_mod

    stt = inference.STT(model=model, language=language, http_session=http)
    stream = stt.stream()
    finals: list[str] = []

    async def read():
        async for ev in stream:
            if ev.type == stt_mod.SpeechEventType.FINAL_TRANSCRIPT and ev.alternatives:
                finals.append(ev.alternatives[0].text)

    reader = asyncio.ensure_future(read())
    rate = frames[0].sample_rate
    for frame in frames:
        stream.push_frame(frame)
        await asyncio.sleep(frame.samples_per_channel / rate)   # real-time, as a microphone would
    silence = rtc.AudioFrame(b"\x00\x00" * (rate // 100) * frames[0].num_channels, rate, frames[0].num_channels,
                             rate // 100)
    for _ in range(150):                                         # 1.5 s of silence to close the utterance
        stream.push_frame(silence)
        await asyncio.sleep(0.01)
    stream.end_input()
    try:
        await asyncio.wait_for(reader, 15)
    except asyncio.TimeoutError:
        reader.cancel()
    await stream.aclose()
    return " ".join(t for t in finals if t).strip()


async def main() -> int:
    try:  # Windows consoles default to a code page that cannot show Arabic
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", type=Path, help="a 16-bit PCM WAV of an Arabic speaker (instead of TTS)")
    parser.add_argument("--text", default=SENTENCE, help="the sentence spoken (for the overlap score)")
    parser.add_argument("--models", default=DEFAULT_PAIRS, help="comma list of model:language")
    args = parser.parse_args()

    import aiohttp

    from app.ai.interview.config import export_livekit_environment, voice_settings
    settings = voice_settings()
    if not settings.configured:
        print("MISSING: LiveKit credentials (" + ", ".join(settings.missing) + ") - nothing was sent.")
        return 2
    export_livekit_environment(settings)

    async with aiohttp.ClientSession() as http:
        if args.wav:
            frames, source = read_wav(args.wav), f"recording {args.wav.name}"
        else:
            try:
                frames, source = await synthesise(http, args.text), "cartesia/sonic-3 (language=ar)"
            except Exception as exc:
                print(f"TTS failed ({type(exc).__name__}: {str(exc)[:160]}) - pass --wav with a recording instead.")
                return 3
        seconds = sum(f.samples_per_channel / f.sample_rate for f in frames)
        print(f"clip: {source}, {seconds:.1f} s")
        print(f"spoken: {args.text}\n")
        worst = 0
        for pair in [p.strip() for p in args.models.split(",") if p.strip()]:
            model, _, language = pair.rpartition(":")
            try:
                heard = await transcribe(http, frames, model, language)
                share, score = arabic_share(heard), overlap(args.text, heard)
                verdict = "ARABIC" if share >= 0.8 else ("MIXED" if share > 0 else "NOT ARABIC")
                print(f"{pair:28} -> {verdict:10} arabic_script={share:.0%} word_overlap={score:.0%}\n"
                      f"{'':31}{heard or '(no transcript)'}")
                worst = max(worst, 0 if share >= 0.8 else 1)
            except Exception as exc:
                print(f"{pair:28} -> ERROR {type(exc).__name__}: {str(exc)[:200]}")
                worst = 1
    return worst


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
