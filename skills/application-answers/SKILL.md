---
name: application-answers
description: Draft answers to application-form questions (why this company, years with a tool, notice period, links, short free-text fields) from the master resume, without inventing anything. Use when asked to "fill in this application", "answer these form questions", "what do I put in this field".
---

# application-answers

Form fields are where invented claims slip in, because each looks small. Every answer comes from the master resume or from the candidate. Truth and voice rules: `${CLAUDE_PLUGIN_ROOT}/docs/voice-and-truth.md`.

## Procedure

1. **List the fields** with their limits (characters, choices, required or not). Read the posting for what it says about each.
2. **Classify each field:**
   - *Fact from the master* (tools, years, employers, links, education): answer from the bullets and the Skills table, in the master's wording. Years of a skill are computed from dated entries that name it, never from the career span.
   - *Free text* (why us, tell us about a project): 3 to 6 sentences, one real finding about the employer or one real project of yours with its id, same kill-list as the cover letter (`${CLAUDE_PLUGIN_ROOT}/docs/kill-list.txt`).
   - *Personal and legal* (work authorization, sponsorship, salary expectation, start date, demographic questions, clearance, relocation): do not answer. Write the field name under "Candidate must answer" and stop. Never infer these from the master.
3. **Check each factual answer** against the master and the claim guard: no number, tool, title or client that is not there, nothing the guard lists, no name under "Never mention in a letter".
4. **Present** a table: field, answer, source id (or "candidate"), characters used against the limit. Mark every "Candidate must answer" first.

## Boundaries

- Never submit a form, create an account, or paste into a live page. Hand over text only.
- A required field you cannot answer from the master is a question, not a guess.
- Keep the answer in the form's language and within its limit; do not abbreviate a claim until it says something the master does not.
