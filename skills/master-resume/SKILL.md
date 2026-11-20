---
name: master-resume
description: Build and keep the master resume, the private fact bank every resume, cover letter and form answer is cut from, with ids, a metrics bank, a claim guard and provenance. Use to start a master, add a role or a fact, record a number with its source, run the lint, or when asked for "my master resume", "add this to the master", "what can I claim".
---

# master-resume

The master is a private inventory, never sent. No page limit: every role, every bullet, every number with a source. A sent resume is a cut of it; the ATS check trusts only what is written here. The shared rules are in `${CLAUDE_PLUGIN_ROOT}/docs/voice-and-truth.md`.

## Where it lives

Anywhere outside the Offersmith repository, as a folder of files named `<Name> — <part>.md` (an em dash with spaces):

- `master resume.md`: the bank. Sections: Rules, 1 Header, 2 Variants, 3 Skills, 4 Experience, 5 Projects, 6 Open source, 7 Education, 8 Metrics bank.
- `claim guard.md`: binding. "Claims not supported" and "Metrics not used" tables, wording rules, and a "Never mention in a letter" list.
- `provenance.md`: the source of each bullet id. `change log.md`: dated, newest first. `open questions.md`: facts to confirm with the candidate.

Start from the synthetic set in `${CLAUDE_PLUGIN_ROOT}/examples/` (`Jane Example — …`): copy the five files, rename the prefix, replace every line. Tell Offersmith where the master is with `offersmith.toml` (`master = "…"`, see the README) or `OFFERSMITH_MASTER`.

## Invariants

1. **Only what you have done.** No absence notes ("never", "not yet", "no work with X"). A missing skill simply does not appear. The one negative list is the claim guard, phrased "not supported".
2. **Every bullet has an id**: `<ROLE>-nn` with a 2 to 4 letter code per role block (one code per block), `P-<PROJECT>-nn` for projects, `OSS-nn` for open source. Backticked tags after a bullet (`AP`, `oss`) name the variants it belongs to.
3. **One home per number.** Written in full in one home bullet; the Metrics bank row `M-nn` gives value, window, source, strength and home. Summaries use `{M-nn}` tokens.
4. **Method stated once** (see the shared rules): who designs, who writes the code.
5. **Candidate-stated facts** carry "stated by the candidate, YYYY-MM-DD" in provenance; a fact with an artifact (repo, pull request, dashboard) cites it.
6. **Confidential names** live in the claim guard's "Never mention in a letter" list.

## Add a fact

1. Verify it: repo (`git log`, `gh pr view`), a live probe, a dashboard; otherwise record it as candidate-stated with today's date.
2. Place it under the role or project where the work happened, next free id, tags. A number gets a Metrics bank row and a home bullet that contains it (or cites its `M-nn`).
3. Add the provenance row and a change-log line; strike the open question it answers.
4. Run the lint: `python3 -I "${CLAUDE_SKILL_DIR}/scripts/check_master.py" [MASTER.md]` must print `0 findings`. The lint checks sidecars exist, bullet ids and role codes, metrics homes and values, absence notes (with the same cue list the ATS check uses), Skills evidence ids, and claims the guard rejects.

## Cut a resume for a posting

Use the `tailor-resume` skill. Mirror the posting's words only where a master bullet or the Skills table has the term; a term the master lacks is a gap to report, not to write.

## Quarterly review

Walk `open questions.md` with the candidate, one question at a time. Re-verify strong metrics older than 90 days by re-running their source. Add results shipped since the last change-log entry. Lint.

## Boundaries

- Never send, post or attach the master. Never write a fact into a sent document that is not in the master.
- Never delete a fact without the candidate's say; move it to the claim guard with a reason.
- Keep the master outside this repository: the repository holds synthetic examples only.
