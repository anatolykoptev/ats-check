---
name: ats-check
description: Check a resume PDF against one job posting with the local ATS simulator (parse health across five extractors, keyword match with a truth column from the master resume, advisory AI grade) and apply only the truthful fixes. Use before sending a resume to a Workday, Greenhouse, Ashby or Lever job, or when asked to "run the ATS check", "tune this resume for the job", "will this parse".
---

# ats-check

Tool: `${CLAUDE_PLUGIN_ROOT}/offersmith` (installed as the CLI `offersmith`; `honest-ats` and `ats-check` are the same command). The README says what its numbers can and cannot mean. It needs the master resume for the truth column; without `--master` (or `master` in `offersmith.toml`) nothing is ever marked "true, add it".

## Per-vacancy loop

1. **Get the posting text.** Save it to a file and pass `--jd file.txt`, or fetch it: `--jd-url <url>` (Greenhouse, Ashby, Lever, Workday job URL, any page), or `--workday-req JR123456` with `--workday-base https://<tenant>.wdN.myworkdayjobs.com/<site>` (or `workday_base` in `offersmith.toml`).
2. **Check.** `${CLAUDE_PLUGIN_ROOT}/offersmith --resume R.pdf --jd jd.txt [--master M.md] [--out DIR]`. Read `report.md`: the verdict line, then the five top fixes.
3. **Parse first.** Any parse FAIL means "FIX PARSING FIRST": change the layout (the render path, not the content), re-render, re-run. Keyword work before a clean parse is wasted.
4. **Apply only truthful fixes**, to the resume markdown, never the PDF:
   - `TRUE, ADD IT`: open the quoted master line, confirm it supports the exact claim, then put the master's own wording into a current-role bullet or the summary.
   - `add the other form`: write `Model Context Protocol (MCP)` once, not twice.
   - `use in a role bullet`: move the claim from Skills into the role where the master shows it.
   - Stuffing fixes: cut repetitions.
5. **Re-render, re-run.** Repeat 2 to 4 until parse is all PASS and required coverage stops improving between two runs (gain under 3 points) or only `gap` and `REJECTED` items remain.
6. **Report** to the candidate: parse verdict, required coverage before and after, the remaining gaps (genuine, not to be added), the knock-outs that need the candidate's own answer, and the advisory AI grade labelled advisory.

## Boundaries

- Never add a claim, number, title, client or tool that is not in the usable part of the master. A word match in the master is not proof: read the quoted line. Gap items and "not supported by master" items are not added until the master records them as true.
- Never stuff: no term more than 3 times, no invisible text, no keyword dumps outside Skills.
- The AI grade and the coverage percent compare versions of one resume against one posting. They are not a shortlisting probability; never present them as one.
- Knock-outs (years, degree, location, clearance, work authorization) are the candidate's truthful answers: surface them, never "fix" them in the resume.
- The LLM layers run sandboxed through the `claude` CLI; if the tool says the sandbox self-check failed, use `--no-llm` and say so rather than working around it. Only those calls leave the machine.
