"""Independent text extractors. Each returns one Extraction; failures are data, not exceptions."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
import pymupdf



@dataclass
class Extraction:
    name: str
    ok: bool
    text: str = ""
    version: str = ""
    error: str = ""
    pages: list[str] = field(default_factory=list)


def _split_pages(text: str) -> list[str]:
    return text.split("\f")


def pdftotext(pdf: Path, mode: str) -> Extraction:
    name = f"pdftotext-{mode}"
    exe = shutil.which("pdftotext")
    if not exe:
        return Extraction(name, False, error="pdftotext (poppler) not installed")
    p = subprocess.run([exe, f"-{mode}", "-enc", "UTF-8", str(pdf), "-"], capture_output=True, timeout=120)
    if p.returncode != 0:
        return Extraction(name, False, error=p.stderr.decode(errors="replace")[:200])
    t = p.stdout.decode("utf-8", errors="replace")
    return Extraction(name, True, t, "poppler", pages=_split_pages(t))


def pymupdf_text(pdf: Path) -> Extraction:
    try:
        with pymupdf.open(pdf) as d:
            pages = [pg.get_text("text", sort=False) for pg in d]
        return Extraction("pymupdf", True, "\f".join(pages), pymupdf.version[0], pages=pages)
    except Exception as e:
        return Extraction("pymupdf", False, error=str(e)[:200])


def pdfplumber_text(pdf: Path) -> Extraction:
    try:
        with pdfplumber.open(pdf) as d:
            pages = [(pg.extract_text() or "") for pg in d.pages]
        return Extraction("pdfplumber", True, "\f".join(pages), "pdfminer", pages=pages)
    except Exception as e:
        return Extraction("pdfplumber", False, error=str(e)[:200])


def pypdfium2_text(pdf: Path) -> Extraction:
    """PDFium: the engine inside Chrome / Edge PDF viewers."""
    try:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(pdf))
        pages = [pg.get_textpage().get_text_range() for pg in doc]
        doc.close()
        return Extraction("pypdfium2", True, "\f".join(pages), str(pdfium.version.PYPDFIUM_INFO), pages=pages)
    except Exception as e:
        return Extraction("pypdfium2", False, error=str(e)[:200])


def filee_text(pdf: Path) -> Extraction:
    """Filee's PDF -> TXT (PdfPig, the .NET port of Apache PDFBox): the Java/PDFBox family without a JVM.
    Installed CLI (`filee` on PATH or ATS_CHECK_FILEE); absent = this extractor is skipped with a WARN."""
    exe = os.environ.get("ATS_CHECK_FILEE") or shutil.which("filee")
    if not exe or not Path(exe).exists():
        return Extraction("filee", False, error="filee CLI not installed (set ATS_CHECK_FILEE); PdfPig/PDFBox family skipped")
    try:
        ver = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=30).stdout.strip()
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.pdf"
            shutil.copyfile(pdf, src)
            out = Path(d) / "out"
            p = subprocess.run([exe, "convert", str(src), "--to", "txt", "-o", str(out), "--overwrite", "--quiet"],
                               capture_output=True, text=True, timeout=180)
            txts = sorted(out.glob("*.txt")) if out.exists() else []
            if p.returncode != 0 or not txts:
                return Extraction("filee", False, version=ver, error=(p.stderr or p.stdout or "no output").strip()[:200])
            t = txts[0].read_text(encoding="utf-8-sig", errors="replace").replace("\t", "  ")
        return Extraction("filee", True, t, ver, pages=[t])
    except Exception as e:
        return Extraction("filee", False, error=str(e)[:200])


def run_all(pdf: Path) -> list[Extraction]:
    """Five engine families: poppler (two modes), MuPDF, pdfminer.six, PDFium, PdfPig (~PDFBox). No JVM."""
    return [pdftotext(pdf, "layout"), pdftotext(pdf, "raw"), pymupdf_text(pdf), pdfplumber_text(pdf),
            pypdfium2_text(pdf), filee_text(pdf)]
