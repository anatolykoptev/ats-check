// Cover letter, one US-letter page. Styled as a set with templates/resume.typ of the tailor-resume skill:
// same face, ink, slate and rule colours. The face is the first installed of the list below.
//
// Data: `typst compile --input meta='<json>' letter.typ out.pdf`, body in `body.typ` beside this file
// (pandoc -t typst). scripts/render_letter.sh does both. Keys of meta, all strings unless noted:
//   name, location, phone, email, links (array of bare URLs), date, recipient, subject,
//   salutation, closing. A missing key drops its line; nothing is invented.
#let m = json(bytes(sys.inputs.at("meta", default: "{}")))
#let f(k) = m.at(k, default: none)
#let ink = rgb("#0f172a")
#let slate = rgb("#64748b")
#let hairline = rgb("#cbd5e1")
#let blue = rgb("#26428b")
#let dot = h(0.45em) + sym.dot.c + h(0.45em)
#let url(u) = link(if u.contains("://") { u } else { "https://" + u })[#u]
#let links = if f("links") == none { () } else if type(f("links")) == array { f("links") } else { (f("links"),) }

#set document(title: "Cover letter" + if f("name") != none { ", " + f("name") } else { "" },
              author: if f("name") != none { f("name") } else { "" })
#set page(paper: "us-letter", margin: (x: 25.4mm, top: 22mm, bottom: 20mm))
// ligatures off: keeps "fi"/"fl" as plain letters when a parser extracts the text.
#set text(font: ("IBM Plex Sans", "Helvetica Neue", "Arial", "Liberation Sans", "DejaVu Sans"), size: 11pt, fill: ink, ligatures: false, lang: "en")
// Body rhythm: line leading well under the paragraph gap, so each paragraph reads as one unit.
// runt cost: keeps a paragraph from ending on a one-word line where the line breaker can avoid it.
#set text(costs: (runt: 600%))
#set par(leading: 0.74em, spacing: 1.45em, justify: false, linebreaks: "optimized")
#show link: set text(fill: blue)

// ── header: name and contacts, as on the resume ──
#if f("name") != none {
  block(below: 3.4mm, text(size: 24pt, weight: "bold", tracking: -0.4pt, f("name")))
  block(above: 0mm, below: 3mm, line(length: 100%, stroke: hairline + 0.7pt))
}
#{
  let parts = ()
  if f("location") != none { parts.push(f("location")) }
  if f("phone") != none { parts.push(f("phone")) }
  if f("email") != none { parts.push(link("mailto:" + f("email"))[#f("email")]) }
  for u in links { parts.push(url(u)) }
  show link: set text(fill: slate)
  text(size: 9.5pt, fill: slate, parts.join(dot))
}

#v(9mm)

// ── date, recipient, subject ──
#if f("date") != none { text(fill: slate, f("date")); v(4.5mm, weak: true) }
#if f("recipient") != none { f("recipient"); v(4.5mm, weak: true) }
#if f("subject") != none { text(weight: "bold", f("subject")) }

#v(4mm)

// ── salutation and body ──
#if f("salutation") != none { f("salutation") }

#include "body.typ"

// ── sign-off: kept together, set apart by an accent rule ──
#v(3mm)
#block(breakable: false)[
  #if f("closing") != none { f("closing") }
  #v(2.5mm)
  #block(stroke: (left: 2.2pt + blue), inset: (left: 11pt, top: 3pt, bottom: 3pt))[
    #set par(leading: 0.62em, spacing: 0.62em)
    #if f("name") != none { text(size: 13pt, weight: "bold", f("name")) }

    #{
      let parts = ()
      if f("phone") != none { parts.push(f("phone")) }
      if f("email") != none { parts.push(link("mailto:" + f("email"))[#f("email")]) }
      show link: set text(fill: slate)
      if parts.len() > 0 { text(size: 10pt, fill: slate, parts.join(dot)) }
    }

    #if links.len() > 0 { text(size: 10pt, links.map(url).join(dot)) }
  ]
]
