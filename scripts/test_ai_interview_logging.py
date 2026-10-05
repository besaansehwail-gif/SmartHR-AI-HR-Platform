"""AI Interview - Phase 10 worker logging tests. Offline: no LiveKit, no model.

    venv\\Scripts\\python.exe -m scripts.test_ai_interview_logging

LiveKit's library logs the applicant's words at DEBUG (`lk.pii.user_transcript`,
"received user transcript"). The worker must not emit them even when started
with `--log-level debug`. This imports the REAL worker module (which applies
`logging_policy`), then runs LiveKit's OWN logging setup at DEBUG - exactly
what `--log-level debug` does - and logs through LiveKit's own logger with the
same record shape its speech recognition uses.
"""

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

passed = 0
failed: list[str] = []

SPOKEN = "My salary at Acme was 4200 and my phone is 0790000000"


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(name)
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)

    def text(self) -> str:
        return "\n".join(f"{r.getMessage()} {vars(r)}" for r in self.records)


def main() -> int:
    print("SmartHR - AI Interview worker logging (Phase 10)")

    print("\n1. The worker module applies the policy on import")
    import app.ai.interview.worker  # noqa: F401  - applies configure_worker_logging()
    from app.ai.interview.logging_policy import DropPii, configure_worker_logging
    from livekit.agents.log import logger as lk_logger

    check("livekit.agents is pinned to INFO", lk_logger.level == logging.INFO, logging.getLevelName(lk_logger.level))
    check("the PII filter is installed once", sum(isinstance(f, DropPii) for f in lk_logger.filters) == 1)
    configure_worker_logging()
    configure_worker_logging()
    check("re-applying (job processes re-import the worker) adds no second filter",
          sum(isinstance(f, DropPii) for f in lk_logger.filters) == 1)

    print("\n2. `--log-level debug`: LiveKit's own setup does not lower it")
    from livekit.agents.cli.log import setup_logging
    root = logging.getLogger()
    before_handlers = list(root.handlers)
    setup_logging("DEBUG", devmode=True, console=False)
    for h in root.handlers:           # keep the test's output readable
        if h not in before_handlers:
            root.removeHandler(h)
    capture = Capture()
    root.addHandler(capture)
    check("root logger is DEBUG, as the flag asks", root.level == logging.DEBUG)
    check("livekit.agents stays INFO", lk_logger.level == logging.INFO, logging.getLevelName(lk_logger.level))

    print("\n3. Transcript records are not emitted")
    # The exact calls LiveKit's speech recognition makes (audio_recognition.py).
    lk_logger.debug("received user transcript",
                    extra={"lk.pii.user_transcript": SPOKEN, "language": "en", "transcript_delay": 0.3})
    lk_logger.debug("received user preflight transcript",
                    extra={"lk.pii.user_transcript": SPOKEN, "language": "en"})
    check("DEBUG transcript records -> nothing emitted", SPOKEN not in capture.text(), capture.text()[:200])
    lk_logger.info("received user transcript", extra={"lk.pii.user_transcript": SPOKEN})
    check("even at INFO, a record carrying lk.pii.* is dropped", SPOKEN not in capture.text())
    lk_logger.setLevel(logging.DEBUG)          # somebody lowers it later, by hand
    lk_logger.debug("received user transcript", extra={"lk.pii.user_transcript": SPOKEN})
    check("even if the level is lowered later, the filter still drops it", SPOKEN not in capture.text())
    lk_logger.setLevel(logging.INFO)

    print("\n4. Operational logging still works")
    capture.records.clear()
    lk_logger.info("registered worker", extra={"agent_name": "smarthr-interviewer"})
    check("LiveKit INFO without personal data is kept (e.g. 'registered worker')",
          any(r.getMessage() == "registered worker" for r in capture.records))
    logging.getLogger("smarthr.interview.worker").debug("room=%s state -> listening", "smarthr-ai-interview-x")
    check("SmartHR's own worker logs still follow the requested level (DEBUG kept)",
          any("state -> listening" in r.getMessage() for r in capture.records))

    print("\n5. The filter matches what the installed LiveKit actually emits")
    src = (Path(sys.modules["livekit.agents"].__file__).parent / "voice" / "audio_recognition.py").read_text(
        encoding="utf-8")
    check("LiveKit's transcript field is still named lk.pii.* (else this filter would miss it)",
          '"lk.pii.user_transcript"' in src)

    root.removeHandler(capture)
    print(f"\n{passed} passed, {len(failed)} failed")
    for f in failed:
        print(f"  - {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
