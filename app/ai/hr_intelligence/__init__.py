"""HR Intelligence (Phase 12): the specialised AI roles around the AI Interview.

    SmartHR
      |-- Interviewer Agent        app/ai/interview/            (live, unchanged)
      '-- HR Intelligence          app/ai/hr_intelligence/      (after the interview)
            |-- Analysis Agent     app/ai/interview_analysis.py + interview_analysis_service
            |-- Report Agent       report_agent.py over interview_report_service
            '-- Recruitment Agent  matching_agent.py over interview_matching_service

`roles.py` states each role's responsibilities and boundaries, `contracts.py`
the structured data each one may receive, and `orchestrator.py` runs the
post-interview roles in a fixed order. No role calls another: the
orchestrator hands each one the data it needs, from the existing services.
"""
