"""Fetch a job description as plain text: Workday (CXS JSON), Greenhouse, Ashby, Lever, JSON-LD / HTML."""
from __future__ import annotations

import html
import json
import re
import time
import subprocess
import urllib.parse
from html.parser import HTMLParser

UA = "Mozilla/5.0"
WD_HOST = re.compile(r"^([\w-]+)\.wd(\d+)\.myworkdayjobs\.com$")


class FetchError(RuntimeError):
    pass


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "table"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(s: str) -> str:
    p = _Text()
    p.feed(s)
    t = "".join(p.out).replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return "\n".join(l.strip() for l in t.splitlines()).strip()


def _http(url: str, data: bytes | None = None, headers: dict | None = None, timeout=30) -> str:
    """GET/POST via system curl: Workday's edge answers 429 to Python's urllib TLS client on
    the job-detail call but not to curl (measured 2026-11-19)."""
    h = {"Accept": "application/json"}
    h.update(headers or {})
    for attempt in range(4):
        cmd = ["curl", "-sS", "-L", "--max-time", str(timeout), "-A", UA, "-w", "\n%{http_code}"]
        for k, v in h.items():
            cmd += ["-H", f"{k}: {v}"]
        if data is not None:
            cmd += ["--data-binary", "@-"]
        cmd.append(url)
        try:
            p = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout + 10)
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            raise FetchError(f"curl failed for {url}: {e}") from e
        if p.returncode != 0:
            raise FetchError(f"network error for {url}: {p.stderr.decode(errors='replace').strip()[:200]}")
        body, _, code = p.stdout.decode("utf-8", errors="replace").rpartition("\n")
        if code in ("429", "503") and attempt < 3:
            time.sleep(2 ** (attempt + 1))
            continue
        if not code.startswith("2"):
            raise FetchError(f"HTTP {code} for {url}")
        return body
    raise FetchError(f"gave up on {url}")


def parse_workday_base(url: str) -> tuple[str, str, str]:
    """'https://<tenant>.wdN.myworkdayjobs.com/[locale/]<site>[/job/...]' -> (origin, tenant, site)"""
    u = urllib.parse.urlparse(url)
    m = WD_HOST.match(u.netloc or "")
    if not m:
        raise FetchError(f"not a Workday URL: {url}")
    parts = [p for p in u.path.split("/") if p]
    if parts and re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", parts[0]):
        parts = parts[1:]
    if not parts or parts[0] == "job":
        raise FetchError(f"no site segment in Workday URL: {url}")
    return f"{u.scheme}://{u.netloc}", m.group(1), parts[0]


def workday_description(job: dict) -> str:
    info = job.get("jobPostingInfo", job)
    parts = [info.get("title", ""), info.get("location", "")]
    for k in ("additionalLocations",):
        if info.get(k):
            parts.append("; ".join(info[k]))
    parts.append(html_to_text(info.get("jobDescription", "")))
    return "\n".join(p for p in parts if p).strip()


def fetch_workday(base: str, req: str | None = None, job_url: str | None = None) -> str:
    origin, tenant, site = parse_workday_base(job_url or base)
    api = f"{origin}/wday/cxs/{tenant}/{site}"
    if job_url and "/job/" in job_url:
        path = "/job/" + job_url.split("/job/", 1)[1].split("?")[0]
    else:
        body = json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": req}).encode()
        res = json.loads(_http(f"{api}/jobs", body, {"Content-Type": "application/json"}))
        posts = res.get("jobPostings", [])
        hit = next((p for p in posts if req and req.lower() in (p.get("externalPath", "") + " " + " ".join(p.get("bulletFields", []))).lower()), None)
        if not hit:
            raise FetchError(f"no Workday posting matches {req!r} ({len(posts)} results)")
        path = hit["externalPath"]
    job = json.loads(_http(f"{api}{path}"))
    return workday_description(job)


def fetch_url(url: str) -> str:
    u = urllib.parse.urlparse(url)
    host, path = u.netloc.lower(), [p for p in u.path.split("/") if p]
    if WD_HOST.match(host):
        return fetch_workday(url, job_url=url)
    if host.endswith("greenhouse.io") and "jobs" in path:
        board, jid = path[0], path[path.index("jobs") + 1]
        if board == "embed":
            q = urllib.parse.parse_qs(u.query)
            board, jid = q["for"][0], q["token"][0]
        d = json.loads(_http(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{jid}"))
        return "\n".join([d.get("title", ""), (d.get("location") or {}).get("name", ""), html_to_text(html.unescape(d.get("content", "")))]).strip()
    if host.endswith("ashbyhq.com") and path:
        org = path[0]
        jid = path[1] if len(path) > 1 else ""
        d = json.loads(_http(f"https://api.ashbyhq.com/posting-api/job-board/{org}"))
        job = next((j for j in d.get("jobs", []) if j.get("id") == jid or j.get("jobUrl", "").rstrip("/").endswith(jid)), None)
        if not job:
            raise FetchError(f"Ashby job {jid} not found on board {org}")
        return "\n".join([job.get("title", ""), job.get("location", ""), job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml", ""))]).strip()
    if host.endswith("lever.co") and len(path) >= 2:
        d = json.loads(_http(f"https://api.lever.co/v0/postings/{path[0]}/{path[1]}"))
        parts = [d.get("text", ""), (d.get("categories") or {}).get("location", ""), d.get("descriptionPlain", "")]
        for l in d.get("lists", []):
            parts += [l.get("text", ""), html_to_text(l.get("content", ""))]
        parts.append(d.get("additionalPlain", ""))
        return "\n".join(p for p in parts if p).strip()
    page = _http(url, headers={"Accept": "text/html"})
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for d in (data if isinstance(data, list) else [data]):
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                loc = d.get("jobLocation")
                loc = (loc[0] if isinstance(loc, list) and loc else loc) or {}
                addr = (loc.get("address") or {}) if isinstance(loc, dict) else {}
                return "\n".join([d.get("title", ""), ", ".join(str(addr.get(k, "")) for k in ("addressLocality", "addressRegion") if addr.get(k)),
                                  html_to_text(html.unescape(d.get("description", "")))]).strip()
    return html_to_text(page)
