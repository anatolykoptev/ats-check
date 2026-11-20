---
name: cover-letter
description: Write, lay out and check a one-page cover letter for one job posting, as PDF plus plain text, with every number traced to the master resume. Use when asked for "a cover letter", "a letter for this posting", or to fix a letter's layout, length or tone.
---

# cover-letter

A letter says what the resume cannot: one real finding about the employer, how you would start, and the gap the posting raises. Truth and voice rules: `${CLAUDE_PLUGIN_ROOT}/docs/voice-and-truth.md`. The fact bank: `master-resume`.

## Procedure

1. **Read the posting and its application form.** List what it asks for in its own words. Check whether the form takes a cover-letter upload, a text box, or neither. Neither: tell the candidate before writing; the letter then travels as a page of the resume PDF or outside the form.
2. **Collect facts with ids** from the master and read the claim guard. A fact with no id is a question for the candidate, not a sentence.
3. **Find one concrete finding.** Prefer a small real check of the employer's own product when it costs minutes (one prompt per call, empty working directory, raw outputs kept beside the letter). Never an invented one.
4. **Draft** to the structure below. Copy `${CLAUDE_PLUGIN_ROOT}/examples/cover-letter/cover-letter.md` for the frontmatter and layout.
5. **Write the fact map** `<letter>.facts.json`: a list of `{"text": "<verbatim sentence>", "ids": ["KPE-01"]}` or `{"text": …, "artifact": "<file beside the letter>"}`. Map every factual sentence, not only the ones with numbers.
6. **Voice pass:** read the draft against the kill-list (`${CLAUDE_PLUGIN_ROOT}/docs/kill-list.txt`); add no number, name or scope while editing.
7. **Render and check:**
   `${CLAUDE_SKILL_DIR}/scripts/render_letter.sh letter.md --png` writes the PDF, `<letter>.txt`, page and word counts and a PNG (needs pandoc, typst, jq, pdfinfo).
   `python3 -I "${CLAUDE_SKILL_DIR}/scripts/check_letter.py" letter.md` must print `0 findings`. It reads the master from `offersmith.toml` or `--master`.
   Look at the PNG yourself: header, date, recipient, spaced paragraphs, sign-off, no one-word last line.
8. **Hand over** the PDF path, the txt path, the checker line, the "read yourself" list the checker prints, and what the candidate must decide (date, recipient name, how the letter travels).

## Structure

- 250 to 320 words, four or five paragraphs, one page. A text box wants less: cut toward 5 to 10 sentences.
- Subject line carries the exact posting title. Salutation: "Hi <Company> team," for an informal company, "Dear Hiring Manager," otherwise.
- Paragraph 1: the specific thing, tied to the posting's own words. No template opener.
- Middle: two proofs with numbers and their source or window. Do not walk through the resume.
- Close: what you would do first and one concrete offer. No "I look forward to hearing".
- State the working method once, as the master states it. No em-dashes.

## Gap handling

One sentence, only for a requirement the posting itself names, in plain words, followed by the nearest real evidence. No apology, no "despite", no second gap.

## What the checker cannot do

It compares digits with the cited master bullets and metric rows, and lists the entries that rest on an artifact under "read yourself". It cannot check that a number matches its artifact, or that a sentence with no number is true. Those are yours to read.

## Boundaries

- Never write a fact the master lacks or anything the claim guard lists. Names under "Never mention in a letter" stay out.
- Never invent a finding, a recipient name or a reason for interest: a missing fact is a question for the candidate.
- Never send, upload or email the letter. Never put the candidate's name, phone or email into a search query or an outside service.
