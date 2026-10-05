"""The interview's state machine - explicit, in Python, not in the prompt.

GPT-4o decides what to *say*. It does not decide what *phase* the interview
is in: that lives here, so it can be logged, tested, published to the
applicant's screen and - in later phases - used to choose the next question
from the Question Bank.

    WAITING     the room exists; the applicant has not been greeted yet
    INTRO       the interviewer is saying hello
    ASKING      the interviewer is asking a question
    LISTENING   the applicant has the floor; nothing is being said to them
    PROCESSING  the applicant finished a turn; GPT-4o is working on a reply
    FOLLOW_UP_DECISION  (Phase 11.1) the answer to a MAIN question that has a
                predefined follow-up is being judged: ask it, or move on?
                GPT-4o returns only yes/no; the question text is the bank's
    ADAPTIVE_SELECTION  (Phase 11.2) no follow-up: which predefined MAIN
                question comes next? GPT-4o returns only a Question Bank id;
                an unusable one means the bank's own order
    SPEAKING    the interviewer is answering / following up
    ENDING      the interviewer is closing the interview
    COMPLETED   finished - nothing further happens in this room

Every transition is checked against `TRANSITIONS`. An illegal one is refused
(and logged by the caller) instead of silently corrupting the state - that is
what stops, for example, a second question being asked while the applicant
still has the floor, or anything happening after COMPLETED.

This module imports nothing from LiveKit, so it is unit-tested directly.
"""

import time
from dataclasses import dataclass, field
from enum import Enum


class InterviewState(str, Enum):
    WAITING = "waiting"
    INTRO = "intro"
    ASKING = "asking"
    LISTENING = "listening"
    PROCESSING = "processing"
    FOLLOW_UP_DECISION = "follow_up_decision"
    ADAPTIVE_SELECTION = "adaptive_selection"
    SPEAKING = "speaking"
    ENDING = "ending"
    COMPLETED = "completed"


S = InterviewState

#: Which state may follow which. ENDING is reachable from every active state
#: (the time limit can fall anywhere); COMPLETED only from ENDING - except via
#: `abort()`, for an applicant who simply leaves.
TRANSITIONS: dict[InterviewState, frozenset[InterviewState]] = {
    S.WAITING: frozenset({S.INTRO, S.ENDING}),
    S.INTRO: frozenset({S.ASKING, S.LISTENING, S.ENDING}),
    # The applicant may start answering before the question has finished
    # playing (barge-in), so ASKING can go straight to PROCESSING.
    S.ASKING: frozenset({S.LISTENING, S.PROCESSING, S.ENDING}),
    # LISTENING -> SPEAKING is the fixed silence nudge ("take your time"),
    # which is said without asking the model anything.
    S.LISTENING: frozenset({S.PROCESSING, S.SPEAKING, S.ENDING}),
    # PROCESSING -> LISTENING is a turn that was ignored (noise, "uh").
    # PROCESSING -> ASKING is the controller moving to the next Question Bank
    # question after an answer; -> SPEAKING is anything else it says
    # (an invitation to elaborate); -> ENDING follows the last answer.
    S.PROCESSING: frozenset({S.ASKING, S.SPEAKING, S.LISTENING, S.ENDING, S.FOLLOW_UP_DECISION,
                             S.ADAPTIVE_SELECTION}),
    # Phase 11.1: entered only when the main question just answered has an
    # eligible follow-up. -> ASKING carries the follow-up OR the next main
    # question (both are spoken verbatim from the bank); -> LISTENING /
    # PROCESSING when the applicant resumed talking and LiveKit dropped the
    # reply; -> SPEAKING for any other reply; -> ENDING for the last answer
    # or the time limit.
    S.FOLLOW_UP_DECISION: frozenset({S.ASKING, S.SPEAKING, S.LISTENING, S.PROCESSING, S.ENDING,
                                     S.ADAPTIVE_SELECTION}),
    # Phase 11.2: entered only after the follow-up path was ruled out (from
    # PROCESSING when there was no follow-up to decide, from FOLLOW_UP_DECISION
    # after a "no") and only with two or more main questions left. Exits as
    # FOLLOW_UP_DECISION does; -> ASKING carries the chosen bank question.
    S.ADAPTIVE_SELECTION: frozenset({S.ASKING, S.SPEAKING, S.LISTENING, S.PROCESSING, S.ENDING}),
    # SPEAKING -> PROCESSING: the applicant interrupted and finished a new
    # turn before the "agent is listening" event arrived.
    S.SPEAKING: frozenset({S.LISTENING, S.PROCESSING, S.ENDING}),
    S.ENDING: frozenset({S.COMPLETED}),
    S.COMPLETED: frozenset(),
}

ACTIVE_STATES = frozenset(set(S) - {S.COMPLETED})


class IllegalTransition(Exception):
    pass


@dataclass
class TurnCounters:
    """What happened in the conversation, counted - never what was said."""

    answers: int = 0        # substantive applicant turns sent to GPT-4o
    short: int = 0          # very short but meaningful ("yes", "okay")
    ignored: int = 0        # empty / filler-only turns never sent to GPT-4o
    interruptions: int = 0  # interviewer speech cut off by the applicant
    nudges: int = 0         # fixed "take your time" prompts after silence

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


@dataclass
class InterviewStateMachine:
    state: InterviewState = S.WAITING
    counters: TurnCounters = field(default_factory=TurnCounters)
    history: list[tuple[float, InterviewState]] = field(default_factory=list)
    #: Silence nudges already given since the applicant last spoke.
    nudges_since_speech: int = 0
    end_reason: str | None = None

    def __post_init__(self) -> None:
        self.history.append((time.monotonic(), self.state))

    def can(self, target: InterviewState) -> bool:
        return target == self.state or target in TRANSITIONS[self.state]

    def to(self, target: InterviewState) -> bool:
        """Move to `target`. Returns True if the state changed.

        Moving to the current state is a no-op, not an error: LiveKit can
        report the same agent state twice. Anything not in `TRANSITIONS`
        raises, so a bug shows up as an exception in a test rather than as an
        interviewer that talks over the applicant.
        """
        if target == self.state:
            return False
        if target not in TRANSITIONS[self.state]:
            raise IllegalTransition(f"{self.state.value} -> {target.value}")
        self.state = target
        self.history.append((time.monotonic(), target))
        return True

    def abort(self, reason: str) -> None:
        """The applicant left, or the session closed: stop, from anywhere."""
        if self.state != S.COMPLETED:
            self.end_reason = self.end_reason or reason
            self.state = S.COMPLETED
            self.history.append((time.monotonic(), S.COMPLETED))

    @property
    def active(self) -> bool:
        return self.state in ACTIVE_STATES

    def path(self) -> list[str]:
        return [state.value for _, state in self.history]
