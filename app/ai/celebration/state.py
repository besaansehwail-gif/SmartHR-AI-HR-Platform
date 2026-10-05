"""The shared state, and the three structured results the agents return.

Two different kinds of type live here, and the difference is the point:

  * **`CelebrationState` is a TypedDict** - LangGraph's shared state, the
    thing every node reads from and writes to. It is a dictionary at runtime,
    which is what LangGraph merges between nodes.
  * **`OccasionResult`, `MessageResult` and `ReviewResult` are Pydantic
    models** - what each *agent* must hand back. A model's reply is untrusted
    input, so it is validated on the way in, exactly as `cv_parser.py`
    validates a parsed CV.

**The state is not a database.** It holds one run of the workflow and is
thrown away when the run ends; the employee facts inside it were copied out
of PostgreSQL by `celebration_service` and are a snapshot, not a record.
Nothing here is persisted, and no node writes to a table.
"""

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: The occasions this version knows about - one per employee date column
#: (`celebration_service.OCCASION_FIELDS`). `none` is a real answer and the
#: most likely one on any given day - most people are not celebrating
#: anything, and a workflow that cannot say so would invent occasions.
OCCASIONS = (
    "birthday", "work_anniversary", "promotion", "graduation", "wedding", "new_baby", "none",
)

Occasion = Literal[
    "birthday", "work_anniversary", "promotion", "graduation", "wedding", "new_baby", "none",
]

#: How many times the Message Agent may be sent back by the Review Agent.
#: The brief asks for a safe maximum and this is it: a rejected message is
#: rewritten twice at most, after which the run ends unapproved rather than
#: looping. The graph enforces it in code, so a model that always rejects
#: cannot spin.
MAX_RETRIES = 2


class CelebrationModel(BaseModel):
    """Shared Pydantic configuration for every agent result.

    `extra="ignore"` because a model that adds a field it was not asked for
    has made a formatting slip, not an error worth failing a run over -
    `cv_parser._CvModel` makes the same judgement.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class OccasionResult(CelebrationModel):
    """What the Occasion Agent returns."""

    occasion: Occasion
    years: int | None = Field(default=None, ge=0, le=80)
    reason: str = Field(default="", max_length=600)

    @field_validator("occasion", mode="before")
    @classmethod
    def _normalise(cls, value: Any) -> Any:
        """An unknown occasion becomes `none`, never a guess at what was meant.

        Guessing which of seven tokens a model intended is exactly the guess
        this feature must not make, and `none` is the answer that celebrates
        nobody by accident.
        """
        text = str(value or "").strip().lower().replace(" ", "_")
        return text if text in OCCASIONS else "none"

    @field_validator("years", mode="before")
    @classmethod
    def _years(cls, value: Any) -> Any:
        if value in (None, "", "null"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class MessageResult(CelebrationModel):
    """What the Message Agent returns."""

    message: str = Field(min_length=1, max_length=1200)


class ReviewResult(CelebrationModel):
    """What the Review Agent returns."""

    approved: bool
    reason: str = Field(default="", max_length=600)
    suggestions: str | None = Field(default=None, max_length=600)

    @field_validator("approved", mode="before")
    @classmethod
    def _approved(cls, value: Any) -> Any:
        """Anything that is not plainly an approval is a rejection.

        The asymmetry is deliberate and is the whole reason a Review Agent
        exists: a rejected good message costs a rewrite, while an approved
        bad one is published under a real person's name.
        """
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "yes", "1", "approved")


class CelebrationState(TypedDict, total=False):
    """Everything one run of the workflow needs, and nothing else.

    `total=False` so a node may write just the keys it owns; LangGraph merges
    the returned dictionary into the state it already has.
    """

    # --- put in by the caller, before the graph starts -------------------
    employee_id: int
    employee_name: str
    employee_data: dict
    events: dict

    # --- written by the Occasion Agent -----------------------------------
    occasion: str
    years: int | None
    occasion_reason: str

    # --- written by the Message Agent ------------------------------------
    message: str

    # --- written by the Review Agent -------------------------------------
    review_approved: bool
    review_reason: str
    review_suggestions: str | None

    # --- the loop guard --------------------------------------------------
    retry_count: int

    # --- written by the final node ---------------------------------------
    final_celebration: str | None

    # --- diagnostics, so a run can be read afterwards --------------------
    #: One line per node, in the order they ran.
    trace: list[str]
    #: Set when an agent could not be used at all (no model, a network
    #: failure, a reply that would not validate). Never an invented result.
    error_code: str | None
