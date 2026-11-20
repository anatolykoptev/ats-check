#!/usr/bin/env bash
# Render a cover letter: <letter>.md -> PDF (typst) and <letter>.txt (plain text for ATS text boxes),
# then report pages and body word count.
#
# Usage: render_letter.sh <letter.md> [--png]
#   --png   also rasterise the PDF at 110 dpi to <pdf-stem>-page-N.png, to look at the layout.
# The PDF name is the frontmatter key `pdf:` (default <letter-stem>.pdf), written beside the letter.
# Template: $LETTER_TEMPLATE, else ../templates/letter.typ. Needs pandoc, typst, pdfinfo, jq (pdftoppm for --png).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
[ $# -ge 1 ] || { echo "usage: render_letter.sh <letter.md> [--png]" >&2; exit 2; }
md="$1"; png="${2:-}"
[ -f "$md" ] || { echo "no such letter: $md" >&2; exit 2; }
tpl="${LETTER_TEMPLATE:-$here/../templates/letter.typ}"
[ -f "$tpl" ] || { echo "template not found: $tpl" >&2; exit 2; }
for t in pandoc typst pdfinfo jq; do command -v "$t" >/dev/null || { echo "missing tool: $t" >&2; exit 2; }; done

dir="$(cd "$(dirname "$md")" && pwd)"; stem="$(basename "$md" .md)"
build="$(mktemp -d)"; trap 'rm -f "$build"/*; rmdir "$build"' EXIT
# -smart: values and the text file keep ASCII quotes; the PDF gets typographic quotes from typst itself.
meta="$(pandoc "$md" -f markdown-smart -t plain --template="$here/meta-json.tpl")"
jq -e 'type == "object" and has("name") and has("salutation")' <<<"$meta" >/dev/null \
  || { echo "frontmatter must be YAML with at least name and salutation: $md" >&2; exit 2; }
pdf="$dir/$(jq -r --arg d "$stem.pdf" '.pdf // $d' <<<"$meta")"
txt="$dir/$stem.txt"

cp "$tpl" "$build/letter.typ"
pandoc "$md" -f markdown -t typst > "$build/body.typ"
typst compile --input "meta=$meta" "$build/letter.typ" "$pdf"

# Plain text: salutation, one line per paragraph, sign-off with contacts. No date or address block:
# an ATS form already holds them, and a text box keeps line breaks and nothing else.
{
  jq -r '.salutation' <<<"$meta"; echo
  pandoc "$md" -f markdown-smart -t plain --wrap=none
  echo; jq -r '.closing // "Best regards,"' <<<"$meta"
  jq -r '.name' <<<"$meta"
  jq -r '[.phone, .email] | map(select(. != null)) | join(" | ")' <<<"$meta"
  jq -r '(.links // []) | if type == "array" then . else [.] end | join(" | ")' <<<"$meta"
} | sed -e $'s/\xc2\xa0/ /g' -e 's/[[:space:]]*$//' | awk 'NF || prev; { prev = NF }' > "$txt"

pages="$(pdfinfo "$pdf" | awk '/^Pages:/ {print $2}')"
words="$(pandoc "$md" -f markdown-smart -t plain --wrap=none | wc -w | tr -d ' ')"
if [ "$png" = "--png" ]; then
  rm -f "${pdf%.pdf}"-page-*.png
  pdftoppm -r 110 -png "$pdf" "${pdf%.pdf}-page"
fi
echo "pdf: $pdf"
echo "txt: $txt"
echo "pages: $pages"
echo "body words: $words"
