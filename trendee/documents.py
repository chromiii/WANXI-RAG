"""Page-preserving PDF ingestion and bounded, same-origin website capture."""
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser

from .config import ROOT, runtime_data_dir

SITE = "https://www.wanxitech.cn/"
ALLOWED_HOSTS = {"www.wanxitech.cn", "wanxitech.cn"}
USER_AGENT = "TrendeeExamDemo/1.0"


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize_text(text):
    # Retain line boundaries and percentages. Do not silently correct the source's claims.
    return "\n".join(re.sub(r"[ \t\u00a0]+", " ", line).strip()
                     for line in text.replace("\r", "").splitlines() if line.strip())


def parse_pdf(path):
    from pypdf import PdfReader
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF is encrypted; use an unlocked copy")
    pages = []
    for number, page in enumerate(reader.pages, 1):
        text = normalize_text(page.extract_text() or "")
        pages.append({"page": number, "text": text,
                      "extraction_issue": "text_layer_missing_or_sparse" if len(text) < 15 else None})
    if not any(len(p["text"]) > 30 for p in pages):
        raise ValueError("PDF has no usable text layer. OCR is required; ingestion was not fabricated.")
    return pages


def prepare_brand(data_dir=None, force=False):
    data_dir = Path(data_dir) if data_dir is not None else runtime_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "trendee_brand.pdf"
    cache = data_dir / "brand_pages.json"
    manifest_path = data_dir / "brand_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    # Source documents and derived caches are private runtime data and are not stored in Git.
    # When an authorized source PDF is present, its SHA-256 is recorded and the page cache
    # can be generated beside it for the current runtime only.
    if not path.exists():
        if not cache.exists():
            raise FileNotFoundError(
                f"Missing {path.name} and {cache.name}; provide the source PDF or a validated cache."
            )
        pages = json.loads(cache.read_text(encoding="utf-8"))
        cached = dict(manifest)
        cached["source_file_available"] = False
        cached["runtime_source"] = "validated_page_cache"
        return pages, cached

    digest = sha256(path)
    if force or not cache.exists() or manifest.get("sha256") != digest:
        pages = parse_pdf(path)
        cache.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = {"file": path.name, "sha256": digest, "page_count": len(pages),
                    "extracted_at_utc": now_utc(), "parser": "pypdf text layer",
                    "source": "Employer-provided Feishu attachment",
                    "page_numbering": "1-based physical PDF pages",
                    "source_file_available": True,
                    "runtime_source": "source_pdf",
                    "limitations": ["No OCR; diagrams and table relations may require original-page review.",
                                    "Company marketing claims are attributed to the brochure, not independently verified."]}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        manifest = dict(manifest)
        manifest["source_file_available"] = True
        manifest["runtime_source"] = "source_pdf"
    return json.loads(cache.read_text(encoding="utf-8")), manifest


class PageParser(HTMLParser):
    def __init__(self, include_body=False):
        super().__init__(convert_charrefs=True)
        self.blocks, self.headings, self.links, self.meta, self.jsonld = [], [], [], {}, []
        self.skip = 0
        self.depth = 0
        self.main_depth = None
        self.buffer = []
        self.heading_buffer = None
        self.heading_tag = None
        self.title_buffer = None
        self.jsonld_buffer = None
        self.anchor = None
        self.current_heading = "页面概览"
        self.include_body = include_body
        self.in_body = False

    def flush(self):
        text = normalize_text("".join(self.buffer))
        if text and len(text) >= 8:
            self.blocks.append({"heading": self.current_heading, "text": text})
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in {"meta", "link", "img", "br", "input", "hr", "source", "wbr"}:
            self.depth += 1
        if tag == "meta":
            key = attrs.get("name", attrs.get("property", ""))
            if key in {"description", "robots", "og:title", "og:description"}:
                self.meta[key] = attrs.get("content", "")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.meta["canonical"] = attrs.get("href", "")
        if tag == "title":
            self.title_buffer = []
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.jsonld_buffer = []
        if tag in {"script", "style", "noscript", "nav", "footer", "header", "button", "form"}:
            self.skip += 1
        if tag == "main":
            self.main_depth = self.depth
        if tag == "body":
            self.in_body = True
        if tag == "a":
            self.anchor = {"url": attrs.get("href", ""), "label": ""}
        if self.skip:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self.flush()
            self.heading_buffer = []
            self.heading_tag = tag
        elif tag in {"p", "li"}:
            self.flush()
        elif tag == "br":
            self.buffer.append("\n")

    def handle_endtag(self, tag):
        if tag == "title" and self.title_buffer is not None:
            self.meta["title"] = "".join(self.title_buffer).strip()
            self.title_buffer = None
        if tag == "script" and self.jsonld_buffer is not None:
            self.jsonld.append("".join(self.jsonld_buffer))
            self.jsonld_buffer = None
        if tag == "a" and self.anchor:
            self.links.append(self.anchor)
            self.anchor = None
        if tag in {"script", "style", "noscript", "nav", "footer", "header", "button", "form"}:
            self.skip = max(0, self.skip - 1)
        elif not self.skip:
            if self.heading_buffer is not None and tag == self.heading_tag:
                text = normalize_text("".join(self.heading_buffer))
                if text:
                    self.current_heading = text
                    self.headings.append({"level": int(tag[1]), "text": text})
                self.heading_buffer, self.heading_tag = None, None
            elif tag in {"p", "li", "section", "article", "main"}:
                self.flush()
        if tag == "main":
            self.main_depth = None
        if tag == "body":
            self.in_body = False
        if tag not in {"meta", "link", "img", "br", "input", "hr", "source", "wbr"}:
            self.depth = max(0, self.depth - 1)

    def handle_data(self, data):
        if self.title_buffer is not None:
            self.title_buffer.append(data)
        if self.jsonld_buffer is not None:
            self.jsonld_buffer.append(data)
        if self.anchor:
            self.anchor["label"] += data
        if self.skip:
            return
        if self.heading_buffer is not None:
            self.heading_buffer.append(data)
        elif self.main_depth is not None or (self.include_body and self.in_body):
            self.buffer.append(data)


def page_snapshot(html, url, captured_at=None):
    parser = PageParser()
    parser.feed(html)
    parser.flush()
    capture_root = "main"
    if sum(len(x["text"]) for x in parser.blocks) < 100:
        parser = PageParser(include_body=True)
        parser.feed(html)
        parser.flush()
        capture_root = "body_without_navigation"
    seen, blocks = set(), []
    for block in parser.blocks:
        key = block["text"]
        if key not in seen:
            blocks.append(block)
            seen.add(key)
    if sum(len(x["text"]) for x in blocks) < 100:
        raise ValueError("Static HTML has insufficient readable main content; rendered-browser capture may be required")
    return {"url": url, "captured_at_utc": captured_at or now_utc(),
            "sha256_html": hashlib.sha256(html.encode()).hexdigest(), "capture_method": "HTTP static HTML",
            "capture_root": capture_root,
            "title": parser.meta.get("title", ""), "meta": parser.meta, "headings": parser.headings,
            "h1_count": sum(x["level"] == 1 for x in parser.headings),
            "jsonld_count": len(parser.jsonld), "blocks": blocks,
            "links": [{"url": urljoin(url, x["url"]), "label": normalize_text(x["label"])}
                      for x in parser.links if x["url"] and x["label"].strip()],
            "scope_note": "Only captured static HTML; missing features are not proof of a whole-site or rendered-DOM absence."}


class SameSiteRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_site_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_site_url(url):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or
            parsed.port not in {None, 443} or parsed.username or parsed.password):
        raise ValueError("Website capture is restricted to the specified official HTTPS site")


def fetch_site_url(url, limit=3_000_000):
    check_site_url(url)
    opener = build_opener(SameSiteRedirects())
    with opener.open(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20) as response:
        check_site_url(response.url)
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("Website response exceeds the size limit")
        return raw.decode("utf-8", errors="replace"), response.url


def capture_site(data_dir=None, max_pages=3):
    """Capture only the bounded official site into private runtime storage."""
    data_dir = Path(data_dir) if data_dir is not None else runtime_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    robots = RobotFileParser()
    robots_error = None
    try:
        text, _ = fetch_site_url(urljoin(SITE, "/robots.txt"), 100_000)
        robots.parse(text.splitlines())
    except Exception as exc:
        robots_error = type(exc).__name__
        # Unavailable robots does not grant permission to fetch hidden/private paths.
        robots.parse([])
    urls, pages, errors = [SITE], [], []
    while urls and len(pages) < max(1, min(max_pages, 5)):
        url = urls.pop(0)
        if not robots.can_fetch(USER_AGENT, url):
            errors.append({"url": url, "error": "robots_disallowed"})
            continue
        try:
            html, final_url = fetch_site_url(url)
            page = page_snapshot(html, final_url)
            pages.append(page)
            if len(pages) == 1:
                for link in page["links"]:
                    candidate = link["url"].rstrip("/")
                    if urlparse(candidate).path in {"/about", "/geo-agent"} and candidate not in urls:
                        check_site_url(candidate)
                        urls.append(candidate)
        except Exception as exc:
            errors.append({"url": url, "error": type(exc).__name__})
    if not pages:
        raise ValueError("Website capture failed; any existing private runtime snapshot was left unchanged")
    snapshot = {"site": SITE, "captured_at_utc": now_utc(), "page_count": len(pages),
                "robots_fetch_issue": robots_error, "errors": errors, "pages": pages,
                "scope": "Public homepage and linked about/agent pages, up to three pages by default"}
    target = data_dir / "website_snapshot.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return snapshot
