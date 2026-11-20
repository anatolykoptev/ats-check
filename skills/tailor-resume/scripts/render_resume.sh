#!/usr/bin/env bash
# Render a resume: <resume>.md -> PDF (typst), then report pages and characters.
#
# Usage: render_resume.sh <resume.md> [--png]
#   --png   also rasterise the PDF at 110 dpi to <pdf-stem>-page-N.png, to look at the layout.
# The PDF name is the frontmatter key `pdf:` (default <resume-stem>.pdf), written beside the resume.
# Template: $RESUME_TEMPLATE, else ../templates/resume.typ. Needs pandoc, typst, pdfinfo, jq (pdftoppm for --png).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
[ $# -ge 1 ] || { echo "usage: render_resume.sh <resume.md> [--png]" >&2; exit 2; }
md="$1"; png="${2:-}"
[ -f "$md" ] || { echo "no such resume: $md" >&2; exit 2; }
tpl="${RESUME_TEMPLATE:-$here/../templates/resume.typ}"
[ -f "$tpl" ] || { echo "template not found: $tpl" >&2; exit 2; }
for t in pandoc typst pdfinfo jq; do command -v "$t" >/dev/null || { echo "missing tool: $t" >&2; exit 2; }; done

dir="$(cd "$(dirname "$md")" && pwd)"; stem="$(basename "$md" .md)"
build="$(mktemp -d)"; trap 'rm -f "$build"/*; rmdir "$build"' EXIT
meta="$(pandoc "$md" -f markdown-smart -t plain --template="$here/meta-json.tpl")"
jq -e 'type == "object" and has("name")' <<<"$meta" >/dev/null \
  || { echo "frontmatter must be YAML with at least name: $md" >&2; exit 2; }
pdf="$dir/$(jq -r --arg d "$stem.pdf" '.pdf // $d' <<<"$meta")"

cp "$tpl" "$build/resume.typ"
pandoc "$md" -f markdown -t typst > "$build/body.typ"
typst compile --input "meta=$meta" "$build/resume.typ" "$pdf"

pages="$(pdfinfo "$pdf" | awk '/^Pages:/ {print $2}')"
chars="$(pandoc "$md" -f markdown-smart -t plain --wrap=none | wc -c | tr -d ' ')"
if [ "$png" = "--png" ]; then
  rm -f "${pdf%.pdf}"-page-*.png
  pdftoppm -r 110 -png "$pdf" "${pdf%.pdf}-page"
fi
echo "pdf: $pdf"
echo "pages: $pages"
echo "characters: $chars"
