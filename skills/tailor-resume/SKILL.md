---
name: tailor-resume
description: Cut a tailored one-to-two page resume for one job posting from the master resume, in an ATS-safe format, render it to PDF and check it. Use when asked to "tailor my resume", "write a resume for this job", "cut a variant", or to review a resume draft that reads like a product portfolio or runs past two pages.
---

# tailor-resume

A resume is about the person, not a product list. This skill cuts one from the master and holds it to a format a human skims and a parser reads. Truth and voice rules: `${CLAUDE_PLUGIN_ROOT}/docs/voice-and-truth.md`. The fact bank: `master-resume`.

## Procedure

1. **Read the posting.** List what it requires and prefers in its own words, and its seniority.
2. **Pick the variant** the master's section 2 offers for this role (or the nearest) and follow its cut procedure.
3. **Copy bullets by id** from the master, in the master's own wording; reorder by relevance to the posting. Mirror a posting term only where a master bullet or the Skills table has it. A term the master lacks is a gap: list it for the candidate, never write it.
4. **Write the markdown** to the rules below. Frontmatter: `name`, `location`, `phone`, `email`, `links`, `pdf`. Start from `${CLAUDE_PLUGIN_ROOT}/examples/resume/resume.md`.
5. **Check:** `python3 -I "${CLAUDE_SKILL_DIR}/scripts/check_resume.py" resume.md --master "<master>"` must print `0 findings`.
6. **Render:** `${CLAUDE_SKILL_DIR}/scripts/render_resume.sh resume.md --png` writes the PDF (needs pandoc, typst, jq, pdfinfo) and a PNG; look at the PNG yourself.
7. **ATS check:** run the `ats-check` skill on the PDF. Fix parse failures by changing layout, then truthful keyword gaps by editing the markdown, then re-render.

## The rules

1. Every bullet starts with the candidate's action as a past-tense verb (Built, Designed, Cut, Migrated, Directed). The system is the object, never the subject.
2. No first-person pronouns in bullets.
3. No product-name subheadings inside a role. A product becomes an object inside a chronological bullet list. A separate Projects section is the one place a product may be the subject; prefer "Author of …".
4. Role heading: `### Title, Company · YYYY-MM to Present · Location`, then bullets.
5. One shape per bullet: action + system + measured outcome, or action + system + scope, or action + system + rationale.
6. Section order: header, Summary (2 to 3 sentences), Experience (newest first), Projects, Skills, Education. Use standard section names; parsers map by keyword.
7. Budget: current role 5 to 7 bullets, the next 3 to 5, anything older than three years 1 to 3. Bullets 6 to 22 words, two lines at most. One to two pages, never three.
8. **Gloss every name the reader cannot decode.** A recruiter has never heard of your repositories or your last company: "Author of X, a Go headless-browser library". Names the audience knows (PostgreSQL, Kubernetes) need no gloss. This check is yours to do: read the draft as a stranger and list every name you could not decode.
9. No keyword soup: removing a keyword must change more than the keyword; no verbless line of four or more items outside Skills; no term more than twice in a section.
10. Put the strongest metric in the first 80 characters of a bullet.
11. No proof gap: an impressive claim needs something a skeptic can open (a repository, a merged pull request, a public benchmark).

## Boundaries

- The master is the only source of facts and numbers. Do not edit the master from here.
- Do not edit the PDF; edit the markdown and re-render.
- Never send or upload the resume. Immigration and work-authorization status never go in the file.
