"""How the interviewer decides whose turn it is - every number explained.

Three different mechanisms are involved, and they answer three different
questions. Keeping them apart is the point of this module:

    VAD                 "is there speech in this audio right now?"
                        (runs locally, frame by frame; knows nothing about words)
    turn detector       "has the applicant FINISHED, or only paused?"
                        (LiveKit's turn-detector model, on the audio stream)
    endpointing delays  "how long do we wait in silence before we believe it?"

None of them evaluates the answer. Whether an answer is *good* is a later
phase's question; these only decide *when* the interviewer may speak.

`classify_utterance()` is the fourth, and the only one that looks at words: a
completed turn that is empty or only "uh"/"um" is never sent to GPT-4o, so
noise and a cleared throat cannot move the interview on.

Pure Python except for `turn_handling()`, which builds LiveKit's options.
"""

import re

# --- VAD ---------------------------------------------------------------------
#: Speech must last this long before VAD reports "the applicant started
#: speaking". Above the 0.05 s default so a click or a tap on the desk is not
#: speech, far below a real syllable (~0.15 s).
VAD_MIN_SPEECH_S = 0.1
#: Silence needed before VAD reports "the applicant stopped speaking". Kept at
#: the library default: VAD's "stopped" only *starts* the end-of-turn decision
#: below, it does not end the turn by itself.
VAD_MIN_SILENCE_S = 0.25

# --- End of turn -------------------------------------------------------------
#: When the turn detector judges the applicant has finished (a complete
#: sentence, a falling tone), wait this long in silence before replying.
#: The streaming default is 0.3 s - right for a chat assistant, wrong for an
#: interview answer, which is several complete sentences in a row.
#: MEASURED: at 0.6 s a 21 s, five-sentence answer was split into four turns
#: in the live test - the ~0.6 s silence between two complete sentences was
#: taken as "finished" each time. 1.2 s is twice that gap; the cost is that
#: every reply comes ~0.6 s later than it would at 0.6 s.
MIN_ENDPOINTING_DELAY_S = 1.2
#: When the detector judges the applicant is MID-thought ("...and then I"),
#: wait up to this long before giving them the turn anyway. Interview answers
#: have thinking pauses; 4 s lets someone search for a word without the
#: interviewer jumping in, while a genuinely finished-but-ambiguous answer is
#: still picked up well before it feels like a dead line. (Default 2.5 s.)
MAX_ENDPOINTING_DELAY_S = 4.0

# --- Interruptions (barge-in) ------------------------------------------------
#: The applicant must speak this long over the interviewer before the
#: interviewer stops. Filters coughs and a short "mm-hm"; a real "sorry, can
#: I ask..." is well over it. (Default 0.5 s.)
MIN_INTERRUPTION_S = 0.6
#: Phase 11.6.2: AND at least this many transcribed words. A cough, a door or
#: background noise can last 0.6 s but produces no words, so it no longer
#: stops the interviewer mid-sentence; a real "sorry, can I..." does. The
#: duration threshold above is unchanged - this is an additional condition.
MIN_INTERRUPTION_WORDS = 1
#: If the interviewer stopped for what turned out to be noise (no words
#: followed within this many seconds), it resumes where it was.
FALSE_INTERRUPTION_TIMEOUT_S = 2.0

# --- Speculative replies ----------------------------------------------------
#: See turn_handling(): off, because the controller's directive must exist
#: before GPT-4o is asked anything.
PREEMPTIVE_GENERATION = False

# --- Silence -----------------------------------------------------------------
#: Seconds of silence (nobody speaking) before the applicant is considered
#: "away" and gets ONE fixed, model-free nudge. Long enough to think about an
#: answer; the nudge is a courtesy, not a move to the next question.
SILENCE_NUDGE_AFTER_S = 15.0
#: Nudges allowed per stretch of silence. After this the interviewer simply
#: keeps waiting: repeating "are you there?" is worse than patience.
MAX_NUDGES_PER_SILENCE = 1

# --- What counts as an answer ------------------------------------------------
#: Sounds that carry no content. A turn made only of these is not an answer.
FILLERS = frozenset({
    "uh", "uhh", "um", "umm", "uhm", "er", "erm", "ah", "ahh", "eh", "hm",
    "hmm", "mm", "mmm", "mhm", "mm-hm", "mm-hmm", "uh-huh", "huh", "oh",
    # Arabic hesitation sounds, for when STT is switched to Arabic.
    "اه", "آه", "امم", "ام", "ممم", "يعني",
})
#: Up to this many words (and not filler) is "short": answered, but the model
#: is told it was brief so it asks for more instead of moving on.
SHORT_MAX_WORDS = 2

_WORD = re.compile(r"[\w'-]+", re.UNICODE)


def classify_utterance(text: str | None) -> str:
    """'empty' | 'filler' | 'short' | 'answer' for one completed turn."""
    words = [w.strip("'-").lower() for w in _WORD.findall(text or "")]
    words = [w for w in words if w]
    if not words:
        return "empty"
    if all(w in FILLERS for w in words):
        return "filler"
    if len(words) <= SHORT_MAX_WORDS:
        return "short"
    return "answer"


#: Appended, by code, to a short turn before GPT-4o sees it. The decision that
#: the turn was short is ours; the model only chooses the words.
SHORT_ANSWER_NOTE = (
    "[Interviewer note, not spoken by the applicant: this reply was very short. "
    "If it does not answer your question, warmly invite them to say more about it "
    "rather than moving on to a new topic.]"
)


# --- Deployment overrides ----------------------------------------------------
#: The numbers above are the defaults. Each may be overridden per deployment
#: (env -> .env.local -> .env), within bounds, so turn timing can be tuned
#: from a live test without a code change. An unusable value is ignored.
ENDPOINT_MIN_VAR = "SMARTHR_INTERVIEW_ENDPOINT_MIN_S"
ENDPOINT_MAX_VAR = "SMARTHR_INTERVIEW_ENDPOINT_MAX_S"
VAD_MIN_SILENCE_VAR = "SMARTHR_INTERVIEW_VAD_MIN_SILENCE_S"
MIN_STT_CONFIDENCE_VAR = "SMARTHR_INTERVIEW_MIN_STT_CONFIDENCE"


def _seconds(name: str, default: float, low: float, high: float) -> float:
    from app.ai.interview.config import interview_setting

    raw = interview_setting(name)
    try:
        value = float(raw) if raw is not None else default
    except ValueError:
        return default
    return value if low <= value <= high else default


def endpointing_delays() -> tuple[float, float]:
    """(min_delay, max_delay) - the defaults above unless overridden."""
    low = _seconds(ENDPOINT_MIN_VAR, MIN_ENDPOINTING_DELAY_S, 0.8, 2.5)
    high = _seconds(ENDPOINT_MAX_VAR, MAX_ENDPOINTING_DELAY_S, 2.0, 8.0)
    return low, max(high, low)


def vad_min_silence() -> float:
    return _seconds(VAD_MIN_SILENCE_VAR, VAD_MIN_SILENCE_S, 0.1, 1.5)


# --- Noise / incomplete turns (before any model is asked) ----------------------
#: Below this average STT confidence a turn is treated as noise. Applied only
#: when the provider actually reports a confidence (LiveKit fills 1.0 when it
#: does not), so an unreported value never drops a real answer.
DEFAULT_MIN_STT_CONFIDENCE = 0.35
#: Speech shorter than this is a click, a cough or a clipped syllable.
MIN_SPEECH_MS = 300
#: A 1-2 word turn ending in one of these is a sentence that stopped, not an
#: answer ("That's", "uh... that's", "because", "and the").
DANGLING_WORDS = frozenset({
    "that's", "thats", "that", "it's", "its", "is", "are", "was", "the", "a", "an", "and",
    "but", "or", "so", "because", "if", "when", "which", "to", "of", "in", "my", "i", "i'm",
    "im", "we", "there's", "this",
    # Arabic: "and", "but", "because", "that", "the one that", "in", "from", "to", "on"
    "و", "لكن", "بس", "لأن", "لان", "إن", "ان", "أن", "اللي", "الذي", "في", "من", "إلى", "على",
})


def min_stt_confidence() -> float:
    return _seconds(MIN_STT_CONFIDENCE_VAR, DEFAULT_MIN_STT_CONFIDENCE, 0.0, 0.95)


def _words(text: str | None) -> list[str]:
    words = [w.strip("'-").lower().replace("’", "'") for w in _WORD.findall((text or "").replace("’", "'"))]
    return [w for w in words if w]


def noise_reason(text: str | None, confidence: float | None = None, speech_ms: int | None = None,
                 min_confidence: float | None = None) -> str | None:
    """Why this completed turn is NOISE_OR_INCOMPLETE - or None when it is not.

    Deterministic and model-free, so junk never costs a model call:
    `empty`, `filler`, `low_confidence`, `too_short` or `dangling`. A short
    but complete answer ("No.", "Python.", "I don't know.") is never noise.
    """
    words = _words(text)
    if not words:
        return "empty"
    if all(w in FILLERS for w in words):
        return "filler"
    threshold = min_stt_confidence() if min_confidence is None else min_confidence
    if confidence is not None and confidence < 1.0 and confidence < threshold:
        return "low_confidence"
    if speech_ms is not None and 0 < speech_ms < MIN_SPEECH_MS:
        return "too_short"
    content = [w for w in words if w not in FILLERS]
    if len(content) <= 2 and content[-1] in DANGLING_WORDS:
        return "dangling"
    return None


def turn_handling():
    """LiveKit's TurnHandlingOptions built from the values above."""
    from livekit.agents import inference

    min_delay, max_delay = endpointing_delays()
    return {
        # LiveKit's end-of-turn model, fed the applicant's audio. It is what
        # lets "I worked at a bank, and... then I moved to software" stay ONE
        # turn: after "and" it predicts the applicant is not finished.
        "turn_detection": inference.TurnDetector(),
        "endpointing": {
            "mode": "fixed",
            "min_delay": min_delay,
            "max_delay": max_delay,
        },
        "interruption": {
            "enabled": True,
            "min_duration": MIN_INTERRUPTION_S,
            "min_words": MIN_INTERRUPTION_WORDS,
            "resume_false_interruption": True,
            "false_interruption_timeout": FALSE_INTERRUPTION_TIMEOUT_S,
        },
        # OFF since Phase 3. Preemptive generation starts GPT-4o on the
        # transcript BEFORE the turn is confirmed - i.e. before the controller
        # has decided which question comes next. Every reply now carries the
        # controller's directive, so a speculative reply generated without it
        # could never be used and would only cost a model call per pause.
        # GPT-4o receives the completed answer and the directive together.
        "preemptive_generation": {"enabled": PREEMPTIVE_GENERATION},
        # user_turn_limit is deliberately NOT set (Phase 11.6.2): when it
        # fires, LiveKit makes the agent reply mid-answer, which would cut a
        # long but valid answer. A turn already ends by the endpointing above
        # (at most MAX_ENDPOINTING_DELAY_S of silence), the silence nudge
        # covers an applicant who stops, and the session's time limit bounds
        # the whole interview.
    }


def vad():
    """The local VAD, with the thresholds above."""
    from livekit.agents import inference

    return inference.VAD(
        min_speech_duration=VAD_MIN_SPEECH_S,
        min_silence_duration=vad_min_silence(),
    )
