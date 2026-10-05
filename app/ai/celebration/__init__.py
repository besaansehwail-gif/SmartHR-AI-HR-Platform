"""AI Employee Celebration - a three-agent LangGraph workflow.

    celebration_service.py   the tools: employee facts, out of PostgreSQL
    state.py                 the shared state, and each agent's result type
    prompts.py               one prompt per agent, never one shared prompt
    agents.py                the three agents: occasion, message, review
    graph.py                 the LangGraph wiring and the retry bound

The shape of it, and why it is this shape:

  * **The agents never reach the database.** `app/services/celebration_service.py`
    reads the rows and the router hands the result to the graph as data, so
    "a model cannot read a record it was not shown" is enforced by there
    being no connection to reach rather than by a rule in a prompt.
  * **The agents never write anything.** There is no tool to post, to store a
    message or to change an employee, so this feature cannot alter SmartHR.
    The `app/ai/interviewer.py` module makes the same argument about its own
    missing verbs.
  * **The Review Agent's rejection is real.** `final_celebration` is set only
    on the approved path, so an unreviewed or rejected message has nowhere to
    go, and the retry loop is bounded in Python.

This is the first module in SmartHR to use LangGraph. Everything else here -
the provider, the settings, the structured-output-through-a-tool pattern, the
validate-before-you-trust rule - is the existing architecture, reused.
"""
