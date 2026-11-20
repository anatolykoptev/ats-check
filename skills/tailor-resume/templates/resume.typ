// Resume, US-letter, one text column, built to survive a parser: real text, no tables, no icons, no images,
// contact in the body (not the page header), standard section names, ligatures off.
//
// Data: `typst compile --input meta='<json>' resume.typ out.pdf`, body in `body.typ` beside this file
// (pandoc -t typst). scripts/render_resume.sh does both. Keys of meta, all strings unless noted:
//   name, location, phone, email, links (array of bare URLs). A missing key drops its line.
// Body markdown: `## Section`, `### Title, Company · YYYY-MM to Present · Location`, `- bullet`.
#let m = json(bytes(sys.inputs.at("meta", default: "{}")))
#let f(k) = m.at(k, default: none)
#let ink = rgb("#0f172a")
#let slate = rgb("#64748b")
#let hairline = rgb("#cbd5e1")
#let blue = rgb("#26428b")
#let dot = h(0.45em) + sym.dot.c + h(0.45em)
#let url(u) = link(if u.contains("://") { u } else { "https://" + u })[#u]
#let links = if f("links") == none { () } else if type(f("links")) == array { f("links") } else { (f("links"),) }

#set document(title: "Resume" + if f("name") != none { ", " + f("name") } else { "" },
              author: if f("name") != none { f("name") } else { "" })
#set page(paper: "us-letter", margin: (x: 18mm, top: 15mm, bottom: 14mm))
#set text(font: ("IBM Plex Sans", "Helvetica Neue", "Arial", "Liberation Sans", "DejaVu Sans"), size: 10pt, fill: ink, ligatures: false, lang: "en")
#set par(leading: 0.55em, spacing: 0.7em, justify: false)
#set list(indent: 0.3em, body-indent: 0.6em, spacing: 0.5em)
#show link: set text(fill: blue)

#show heading.where(level: 2): it => {
  v(3.2mm, weak: true)
  text(size: 10.5pt, weight: "bold", tracking: 0.6pt, fill: blue, upper(it.body))
  v(-1.2mm)
  line(length: 100%, stroke: hairline + 0.7pt)
  v(0.6mm)
}
#show heading.where(level: 3): it => {
  v(1.6mm, weak: true)
  text(size: 10pt, weight: "bold", it.body)
  v(0.2mm)
}

// header: name, then contacts, as plain text lines in the body
#if f("name") != none {
  block(below: 2.2mm, text(size: 22pt, weight: "bold", tracking: -0.3pt, f("name")))
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

#include "body.typ"
