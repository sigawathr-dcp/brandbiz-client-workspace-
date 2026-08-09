"""
app/eval/

Offline evaluation for the case-study matching pipeline
(app/services/case_match.py, POST /client/cases).

This package is NEVER imported by any request path — nothing under
app/routers/ or app/services/ (besides the eval scripts driving it)
depends on it. It exists to answer one question with numbers instead of a
vibe: "are the case studies we show a client actually the right ones for
what they told us?" See backend/eval/case_match/ for the golden set and
backend/scripts/eval_case_match_{export,import,run}.py for the CLI.
"""
