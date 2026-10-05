"""AI Interview - the voice interviewer.

Phase 1 is the voice foundation only: an applicant joins a LiveKit room, a
Python `livekit-agents` worker joins the same room, and the conversation runs
STT -> GPT-4o -> TTS through LiveKit Inference.

    applicant browser
      -> POST /ai-interview/session       app/routers/ai_interview.py
           (SmartHR checks the JWT, mints a short-lived LiveKit token
            that names this room and dispatches the agent to it)
      -> LiveKit Cloud room               audio in both directions
      -> app/ai/interview/worker.py       the agent process
           STT (speech -> text) -> openai/gpt-4o -> TTS (text -> speech)

Two processes, deliberately. The backend authorises and hands out tokens; the
worker speaks. **The worker never touches the database** - nothing in this
package imports `app.models` or `app.database`, and the tests assert it. When
later phases need the job, the CV or the matching result, the worker will ask
the backend for a trimmed context over HTTP rather than read tables itself.

Modules:

    config.py   LiveKit + model settings (env -> .env.local -> .env)
    agent.py    the interviewer's instructions and greeting
    worker.py   the livekit-agents entry point (`python -m app.ai.interview.worker dev`)
"""
