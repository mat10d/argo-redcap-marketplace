# Walkthrough agent instructions (read fully before acting)

You are running one Tier 1.5 walkthrough (see README.md in this folder). You play TWO voices:

1. THE ASSISTANT — a Claude session that has just received the user's opening message. You have
   the ARGO plugins available as skills. To "invoke" a skill, READ its SKILL.md from the repo
   tree (the path you were given) and follow it exactly as written — including its Step 0 / setup
   check, its ask-first rules, and which scripts it tells you to run. Scripts live under
   plugins/**; run them with python3 from the repo tree. The user's connected folder is the
   WORKSPACE path you were given; anything they attached is in the UPLOADS path (that is what
   Cowork's uploads folder looks like). Write outputs where the skill says (inside the workspace).
2. THE PERSONA — PERSONA.md in this folder. Whenever the skill would ask the user something,
   STOP being the assistant, answer as the persona in 1–2 sentences, and log it verbatim:
       Q: <the assistant's exact question>
       A: <the persona's exact answer>
   Then continue as the assistant with that answer. If the skill says "wait for the user to do X"
   (e.g. paste a key, upload via the website), log it as `WAIT: <what>` and, unless a real file
   or key is genuinely available in this run, continue as if the persona said "I can't do that
   right now — continue without it".

Hard rules:
- Never edit anything under plugins/, tests/, or testing/fixtures. You are a USER of the skills.
- Every command that runs an ARGO script must set ARGO_ENV_FILE=<WORKSPACE>/.env and
  ARGO_SETUP_NO_OPEN=1 (this machine has a developer ~/.argo/.env that must NOT leak into the run).
- READ-ONLY against REDCap: never run sir_update.py, push_updates.py, fill_new_project.py, or any
  import; never write to a tracker. If the skill's flow reaches such a step, log `WAIT:` and stop.
- Never print a key or any row of real patient data into your report. Synthetic study rows are fine.
- Do not "fix" a failing script. If something crashes, contradicts its SKILL.md, or you would need
  to improvise code to get past it, STOP that path and record it as a DEFECT with the exact
  command and error. Improvising around a script is itself a defect finding.
- Do the whole task to completion as a real session would (interviews, files written, final
  message to the user).

FINAL OUTPUT (raw markdown, exactly these sections):
## Route taken     — which SKILL.md you followed, in what order, and why (or where routing was unclear)
## Q/A log         — every Q:/A:/WAIT: line in order
## Commands        — every ARGO script command you ran (one per line; keys masked)
## Files written   — paths, relative to the workspace
## Final message   — the exact final message the assistant would show the user
## Defects         — anything crashed / contradicted the skill / needed improvisation (with evidence); or "none"
## Self-assessment — pass/fail against the skill's own promises, one paragraph, honest
