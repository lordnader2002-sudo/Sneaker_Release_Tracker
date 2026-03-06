# file: fetch_release_multisource_common.py

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def parse_date_flexible(text: str, default_year: int | None = None) -> date | None:
    if not text:
        return None

    s = normalize_text(text).replace(",", "")
    if not s:
        return None

    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass

    for fmt in ("%B %d %Y", "%b %d %Y", "%B %d %y", "%b %d %y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    if default_year:
        for fmt in ("%B %d", "%b %d"):
            try:
                d = datetime.strptime(s, fmt).date()
                return date(default_year, d.month, d.day)
            except ValueError:
                continue

    return None


def window_filter(records: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    start = date.today()
    end = start + timedelta(days=days)

    out: list[dict[str, Any]] = []
    for r in records:
        d = parse_date_flexible(str(r.get("releaseDate", "")))
        if d is None:
            continue
        if start <= d < end:
            r["releaseDate"] = d.isoformat()
            out.append(r)

    return out


def render_html(url: str, timeout_ms: int) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 15000))
        except PlaywrightTimeoutError:
            pass
        html = page.content()
        browser.close()
        return html


def infer_brand(name: str) -> str:
    n = name.lower()
    if "jordan" in n:
        return "Air Jordan"
    if any(x in n for x in ("nike", "dunk", "air max", "air force", "shox", "pegasus", "vomero")):
        return "Nike"
    if any(x in n for x in ("adidas", "yeezy", "samba", "gazelle", "superstar")):
        return "Adidas"
    if "new balance" in n or n.startswith("nb "):
        return "New Balance"
    if "asics" in n:
        return "ASICS"
    if "puma" in n:
        return "Puma"
    if "reebok" in n:
        return "Reebok"
    if "converse" in n:
        return "Converse"
    if "crocs" in n:
        return "Crocs"
    return "Unknown"


_PRICE_RE = re.compile(r"(?:USD\s*)?\$\s*([0-9]{2,4})(?:\.[0-9]{2})?", re.I)
_COUNTDOWN_RE = re.compile(r"\b\d{1,3}D:\d{1,2}H:\d{1,2}M:\d{1,2}S\b", re.I)


def extract_retail_price(text: str) -> int:
    if not text:
        return 0
    m = _PRICE_RE.search(text.replace(",", ""))
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


def clean_title(text: str) -> str:
    """
    Removes countdowns, 'COMING SOON', and inline prices from titles.
    """
    t = normalize_text(text)
    if not t:
        return t
    t = _COUNTDOWN_RE.sub("", t)
    t = re.sub(r"\bCOMING\s+SOON\b", "", t, flags=re.I)
    t = _PRICE_RE.sub("", t)
    t = normalize_text(t)
    return t
