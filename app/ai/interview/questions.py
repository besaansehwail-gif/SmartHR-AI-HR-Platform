"""Question progression and answer association - the controller's memory.

    Question Bank  -> the plan (ordered MAIN questions, fetched once per room)
    this module    -> which question is current, and which answer belongs to it
    GPT-4o         -> only the words of the acknowledgement between questions

`QuestionProgress.decide()` is the whole progression rule for Phase 3, and it
is code, not prompt:

    substantive answer            -> record it against the CURRENT question,
                                     then advance to the next (or finish)
    short answer ("yes", "okay")  -> record it, and invite more - ONCE per
                                     question; a second short answer advances
    filler / empty                -> never reaches here (refused earlier)

The answer is recorded against the question that was current when the
applicant spoke, BEFORE the index moves - so association can never be off by
one. Transcripts are never logged.

Follow-ups (Phase 11.1). A MAIN question may carry ONE predefined follow-up
from the Question Bank (`PlannedQuestion.follow_up`, parent = that main
question). When the answer to the main question would otherwise advance,
`follow_up_candidate()` names that follow-up; the controller asks GPT-4o only
"ask it: yes or no?", and `decide(..., ask_follow_up=True)` then speaks the
follow-up's bank text verbatim. Its answer is recorded against the
follow-up's own id, under the main question's number, and always advances -
never a second follow-up. `followed_up` is what makes
"at most one per main question" and "no loop" hold even across a reopened
decision (which restores it, like everything else it undoes).

Adaptive order (Phase 11.2). WHICH main question comes next may be chosen by
GPT-4o - by Question Bank id, from the main questions of this plan not yet
asked (`adaptive_options`). `decide(..., next_question_id=...)` accepts the id
only if it is exactly one of those; anything else - a missing, malformed,
hallucinated, repeated or follow-up id - falls back to the deterministic
order: the first not-yet-asked main question in plan order, which is what
every interview did before. `asked` holds the plan indices in the order they
were asked, so a main question is never asked twice and the interview always
ends after `total` main questions. Numbers are the order ASKED ("Question N
of M" as the applicant heard it); with no adaptive choice they equal the plan
positions, as before. The text spoken is always the chosen row's bank text.

Persistence (Phase 7): an answer is FINAL when the reply to it starts playing
(`commit`) - until then the applicant may still be talking and the answer may
be reopened and merged. `commit` numbers every final answer in order
(`sequence`, 1-based) and hands it back, and only those numbered answers are
sent to the backend. At the end of a session `flush` numbers whatever is left:
an answer whose reply never played (the time limit, the applicant leaving),
and the first part of a reopened answer whose rest never came.

Pure Python - no LiveKit, no database.
"""

import time
from dataclasses import dataclass, field

from app.ai.interview.turn_policy import classify_utterance

#: NOISE_OR_INCOMPLETE turns re-ask the current question at most this many
#: times; the next one moves on to the next question, recording nothing for
#: this one (a skipped question is "not answered", never a negative finding).
#: (The Phase 3 "say a bit more" invitation for a short answer was removed: a
#: short answer is an answer, and moves on like any other.)
MAX_NOISE_REASKS = 2

#: Said by the controller - never by GPT-4o - when the interview ends.
CLOSING_AFTER_LAST = (
    "That was my last question. Thank you for your time today - "
    "this is the end of the practice interview. Goodbye."
)


@dataclass(frozen=True)
class PlannedQuestion:
    id: int
    position: int
    category: str
    text: str
    #: Phase 11.1: this MAIN question's predefined follow-up, from the Question
    #: Bank (its parent_question_id is this question's id) - or None.
    follow_up: "PlannedQuestion | None" = None


@dataclass
class AnswerRecord:
    question_id: int
    question_number: int  # 1-based, as the applicant heard it
    text: str
    kind: str  # "answer" | "short" (or "filler" only when it ended a reopened answer)
    words: int
    at: float = field(default_factory=time.monotonic)
    #: Wall-clock (epoch seconds) when the turn was accepted - stored as
    #: answered_at. `at` is monotonic and means nothing outside this process.
    wall: float = field(default_factory=time.time)
    #: 1-based order among FINAL answers, set by `commit` / `flush`. None
    #: while the answer can still be reopened. Never reused.
    sequence: int | None = None


@dataclass(frozen=True)
class Directive:
    """What the controller wants from the reply GPT-4o is about to generate."""

    kind: str               # "advance" | "finish" | "follow_up"
                            # | non-answer (nothing recorded): "side_reply" | "repeat" | "reask"
                            # | "skip" (moved on after repeated noise, nothing recorded)
    note: str               # system instruction for this one reply
    say_after: str | None   # appended VERBATIM by code after GPT-4o's words
    question_number: int    # the question current AFTER this directive


ACK_NOTE = (
    "[Interview controller] Acknowledge the applicant's last answer in ONE short, "
    "warm sentence that reflects something they actually said. Do NOT ask any question, "
    "do NOT give feedback, praise their quality or evaluate them, and do NOT announce "
    "what comes next - the interview system will ask the next question itself."
)


#: Non-answer turns (utterance classifier). Nothing is recorded, nothing is
#: committed. Directive kind -> the instruction for GPT-4o, or None when the
#: reply is a FIXED lead spoken by code with no model call at all.
NON_ANSWER_NOTES: dict[str, str | None] = {
    # SIDE_QUESTION: one very short model sentence, then the current question.
    "side_reply": (
        "[Interview controller] The applicant said something aside instead of answering "
        "(for example asking whether you can hear them). Reply with ONE very short, polite "
        "statement (not a question) - for example that you can hear them - and nothing "
        "else. Do NOT answer general-knowledge or unrelated questions, do NOT explain or "
        "hint at how to answer the interview question, and do NOT evaluate them. The "
        "interview system will repeat the question itself."
    ),
    # REPEAT_REQUEST / NOISE_OR_INCOMPLETE: fixed words, no model call.
    "repeat": None,
    "reask": None,
    # Repeated noise: move on.
    "skip": None,
}
#: Said by code before re-speaking the next question when its audio was cut
#: off before the applicant could hear it (the answer before it is still
#: pending - see InterviewController._answer_not_heard).
REPEAT_AFTER_CUT = "Let me repeat the question."
#: What is spoken before the question, by code.
FIXED_LEADS = {
    "repeat": "Of course.",
    "reask": "Sorry, I didn't catch that.",
    "skip": "Let's move on to the next question.",
}
#: Used when every sentence GPT-4o produced for a side reply was removed.
NON_ANSWER_FALLBACKS = {"side_reply": "Let's continue with the interview."}
#: At most this many of GPT-4o's sentences before the question is repeated.
NON_ANSWER_MAX_SENTENCES = 1


@dataclass
class QuestionProgress:
    questions: list[PlannedQuestion]
    index: int = 0
    answers: list[AnswerRecord] = field(default_factory=list)
    #: NOISE_OR_INCOMPLETE re-asks per question id (main or follow-up).
    noise_reasks: dict[int, int] = field(default_factory=dict)
    #: The state before the latest re-ask / skip, until its reply is HEARD
    #: (`confirm_pending`) or dropped unheard (`revert_pending`). Separate from
    #: `_undo`, which belongs to answers: a re-ask or skip records no answer.
    _pending: tuple | None = field(default=None, repr=False)
    finished: bool = False
    #: The state before the latest decision, until its reply is HEARD
    #: (`commit`) or cancelled unheard (`reopen`).
    _undo: tuple | None = field(default=None, repr=False)
    #: An answer whose reply was cancelled before it was heard: the applicant
    #: was still talking. Their next turn is the rest of THIS answer.
    resumed: "AnswerRecord | None" = None
    #: How many answers have been made final (`sequence` of the latest).
    committed: int = 0
    #: Phase 11.1: the follow-up being asked now (its main question is
    #: `questions[index]`), and the MAIN question ids whose follow-up was asked.
    in_follow_up: PlannedQuestion | None = None
    followed_up: set[int] = field(default_factory=set)
    #: Phase 11.2: plan indices of the MAIN questions asked, in the order
    #: asked. Never shrinks except by `reopen`; never holds an index twice.
    asked: list[int] = field(default_factory=list)
    closing_text: str = CLOSING_AFTER_LAST

    def __post_init__(self) -> None:
        if not self.asked and 0 <= self.index < len(self.questions):
            self.asked = [self.index]

    @property
    def total(self) -> int:
        return len(self.questions)

    @property
    def current(self) -> PlannedQuestion | None:
        """The question being answered: the main question, or its follow-up
        while that is being asked."""
        if self.finished or not 0 <= self.index < self.total:
            return None
        return self.in_follow_up or self.questions[self.index]

    @property
    def current_main(self) -> PlannedQuestion | None:
        if self.finished or not 0 <= self.index < self.total:
            return None
        return self.questions[self.index]

    def _merged(self, q: PlannedQuestion, kind: str, text: str) -> tuple[str, str]:
        """(kind, text) of this turn, joined to a reopened answer it completes."""
        if self.resumed is not None and self.resumed.question_id == q.id:
            # Phase 11.6.2: the same words delivered twice are one turn, not
            # "words words" - only an EXACT repeat of the open answer is dropped.
            if " ".join(text.split()) != " ".join(self.resumed.text.split()):
                text = f"{self.resumed.text} {text}".strip()
            else:
                text = self.resumed.text
            kind = classify_utterance(text)
        return kind, text

    def effective_text(self, kind: str, text: str) -> str:
        """Read-only: the words `decide` would record for this turn - joined to
        a reopened answer it completes. Changes nothing (the classifier reads
        it before anything is decided)."""
        q = self.current
        return self._merged(q, kind, text)[1] if q is not None else text

    def note_noise(self) -> bool:
        """A NOISE_OR_INCOMPLETE turn on the current question. True = re-ask
        it (the first MAX_NOISE_REASKS times); False = it is time to move on
        (`skip`). Records no answer."""
        q = self.current
        if q is None:
            return False
        count = self.noise_reasks.get(q.id, 0)
        if count < MAX_NOISE_REASKS:
            self._hold()
            self.noise_reasks[q.id] = count + 1
            return True
        return False

    def skip(self) -> PlannedQuestion | None:
        """Move on from the current question WITHOUT recording an answer:
        to the next main question in the bank's order (a follow-up being asked
        is simply dropped), or finish. Returns the new current question, or
        None when the interview is over."""
        if self.current is None:
            return None
        self._hold()
        self.in_follow_up = None
        rest = self.remaining()
        if not rest:
            self.finished = True
            return None
        self.index = rest[0]
        self.asked.append(self.index)
        return self.questions[self.index]

    def _hold(self) -> None:
        """Remember the state before a re-ask / skip (only the first time)."""
        if self._pending is None:
            self._pending = (self.index, dict(self.noise_reasks), self.finished,
                             self.in_follow_up, list(self.asked))

    def confirm_pending(self) -> bool:
        """The re-ask / skip reply is being HEARD: keep its effect."""
        held, self._pending = self._pending is not None, None
        return held

    def revert_pending(self) -> bool:
        """The re-ask / skip reply was never heard: undo its effect, so the
        interview stays on the question the applicant actually heard and an
        unheard re-ask does not count. True when something was undone."""
        if self._pending is None:
            return False
        (self.index, self.noise_reasks, self.finished, self.in_follow_up, self.asked) = self._pending
        self._pending = None
        return True

    def follow_up_candidate(self, kind: str, text: str) -> tuple[PlannedQuestion, PlannedQuestion, str] | None:
        """(main question, its follow-up, the complete answer text) when THIS
        turn would move on from a main question whose predefined follow-up has
        not been asked - i.e. when a follow-up decision is worth making.
        None otherwise: no follow-up in the bank, already asked, or answering a
        follow-up."""
        q = self.current
        if q is None or self.in_follow_up is not None or q.follow_up is None or q.id in self.followed_up:
            return None
        kind, text = self._merged(q, kind, text)
        return q, q.follow_up, text

    @property
    def number(self) -> int:
        """1-based number of the current question, in the order asked (0
        before / none). A follow-up shares its main question's number."""
        return len(self.asked) if self.current else 0

    def remaining(self) -> list[int]:
        """Plan indices of the main questions not asked yet, in plan order."""
        taken = set(self.asked)
        return [i for i in range(self.total) if i not in taken]

    def adaptive_options(self, kind: str, text: str) -> tuple[PlannedQuestion, str, list[PlannedQuestion]] | None:
        """(main question, the complete answer, the main questions that may
        come next) when this turn moves on from a MAIN question and there is a
        real choice (two or more left). None otherwise - including while a
        follow-up is being answered.
        Called only after the follow-up path has been ruled out."""
        q = self.current
        if q is None or self.in_follow_up is not None:
            return None
        kind, text = self._merged(q, kind, text)
        options = [self.questions[i] for i in self.remaining()]
        return (q, text, options) if len(options) >= 2 else None

    def _next_index(self, next_question_id) -> tuple[int, bool]:
        """(plan index to ask next, was it the adaptive choice?). The choice
        must be an int id of a main question in this plan not asked yet."""
        remaining = self.remaining()
        if isinstance(next_question_id, int) and not isinstance(next_question_id, bool):
            for i in remaining:
                if self.questions[i].id == next_question_id:
                    return i, True
        return remaining[0], False

    def answers_for(self, question_id: int) -> list[AnswerRecord]:
        return [a for a in self.answers if a.question_id == question_id]

    def decide(self, kind: str, text: str, ask_follow_up: bool = False,
               next_question_id: int | None = None) -> Directive | None:
        """Record the answer against the current question, then decide.

        The decision is PROVISIONAL: the controller `commit`s it when the
        reply carrying it starts playing, or `reopen`s it when LiveKit
        cancels that reply unheard because the applicant was still talking
        (the turn detector took a mid-answer pause for the end). Without that,
        the second half of one answer would be recorded against the NEXT
        question, and that question would never be asked.
        """
        q = self.current
        if q is None:
            return None

        # The rest of an answer the applicant had not finished, if any.
        kind, text = self._merged(q, kind, text)
        self.resumed = None

        self._undo = (self.index, dict(self.noise_reasks), self.finished,
                      self.in_follow_up, set(self.followed_up), list(self.asked))
        self.answers.append(AnswerRecord(q.id, self.number, text, kind, len(text.split())))

        if self.in_follow_up is not None:
            # A follow-up's answer always moves on: no second follow-up - this is what keeps it from looping. It moves
            # on in the Question Bank's order, as in Phase 11.1: adaptive
            # choice applies only when no follow-up was asked (Phase 11.2).
            self.in_follow_up = None
            next_question_id = None
        else:
            # A short answer is an answer: no "say a bit more" invitation.
            if ask_follow_up is True and q.follow_up is not None and q.id not in self.followed_up:
                self.followed_up.add(q.id)
                self.in_follow_up = q.follow_up
                return Directive("follow_up", ACK_NOTE, q.follow_up.text, self.number)

        if self.remaining():
            # Phase 11.2: the adaptive choice when valid, else plan order.
            self.index, _ = self._next_index(next_question_id)
            self.asked.append(self.index)
            nxt = self.questions[self.index]
            return Directive("advance", ACK_NOTE, nxt.text, self.number)

        self.finished = True
        return Directive("finish", ACK_NOTE, self.closing_text, self.total)

    def commit(self) -> list[AnswerRecord]:
        """The reply carrying the latest decision is being heard: keep it.

        Returns the answers that became final with it, numbered in order.
        """
        self._undo = None
        return self._number(self.answers)

    def flush(self) -> list[AnswerRecord]:
        """The session is ending: every accepted answer not yet final becomes
        final now - including the first part of a reopened answer whose rest
        never came (it was accepted; it is kept, never merged into anything)."""
        self._undo = None
        if self.resumed is not None:
            self.answers.append(self.resumed)
            self.resumed = None
        return self._number(self.answers)

    def _number(self, records: list[AnswerRecord]) -> list[AnswerRecord]:
        done = []
        for record in records:
            if record.sequence is None:
                self.committed += 1
                record.sequence = self.committed
                done.append(record)
        return done

    def reopen(self) -> "AnswerRecord | None":
        """Undo the latest decision: its reply was cancelled unheard.

        The answer goes back to being open on the SAME question, and is
        returned so the caller can correct its counters.
        """
        if self._undo is None or not self.answers:
            return None
        (self.index, self.noise_reasks, self.finished, self.in_follow_up, self.followed_up,
         self.asked) = self._undo
        self._undo = None
        self.resumed = self.answers.pop()
        return self.resumed


# --- keeping GPT-4o's acknowledgement free of questions ------------------------
#: Sentence openings that make a question (or a request for one) even without
#: a question mark: "Tell me more about...", "Could you...". An acknowledgement
#: needs none of them.
_QUESTION_OPENERS = (
    "tell me", "describe", "explain", "could you", "can you", "would you", "will you",
    "please", "share", "walk me", "let's talk", "what", "why", "how", "when", "where",
    "which", "who", "do you", "did you", "are you", "have you", "is there", "was there",
)

#: Used when every sentence GPT-4o produced had to be removed.
FALLBACK_ACK = "Thank you."
MAX_ACK_SENTENCES = 2


def is_questionlike(sentence: str) -> bool:
    s = sentence.strip().lower().lstrip("\"'([ ")
    return "?" in s or s.startswith(_QUESTION_OPENERS)


def split_sentences(buffer: str) -> tuple[list[str], str]:
    """Complete sentences out of a streaming buffer, and the unfinished rest."""
    done, start = [], 0
    for i, ch in enumerate(buffer):
        if ch in ".!?" and (i + 1 == len(buffer) or buffer[i + 1].isspace()):
            if i + 1 < len(buffer):  # only when we can see the sentence really ended
                done.append(buffer[start:i + 1].strip())
                start = i + 1
    return [s for s in done if s], buffer[start:]
