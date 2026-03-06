from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None

    normalized = raw.replace(",", " ").replace("  ", " ").strip()
    candidates = [raw, normalized, normalized.replace("/", "-")]

    formats = (
        "%Y-%m-%d",
        "%m-%d-%Y",
        "%m/%d/%Y",
        "%b %d %Y",
        "%B %d %Y",
        "%b %d %y",
        "%B %d %y",
    )

    for c in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(c, fmt).date()
            except ValueError:
                continue

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_price(text: str) -> int:
    if not text:
        return 0
    m = re.search(r"\$\s*([0-9]{2,4})(?:\.[0-9]{2})?", text.replace(",", ""))
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


def infer_brand(name: str) -> str:
    lowered = name.lower()
    if "jordan" in lowered:
        return "Air Jordan"
    if "nike" in lowered or "dunk" in lowered or "air max" in lowered or "air force" in lowered:
        return "Nike"
    if "adidas" in lowered or "samba" in lowered or "gazelle" in lowered or "yeezy" in lowered:
        return "Adidas"
    if "new balance" in lowered or lowered.startswith("nb "):
        return "New Balance"
    if "asics" in lowered:
        return "ASICS"
    if "puma" in lowered:
        return "Puma"
    if "reebok" in lowered:
        return "Reebok"
    if "converse" in lowered:
        return "Converse"
    if "crocs" in lowered:
        return "Crocs"
    return "Unknown"


def window_filter(records: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    start = date.today()
    end = start + timedelta(days=days)
    out: list[dict[str, Any]] = []
    for r in records:
        d = parse_date(r.get("releaseDate"))
        if d is None:
            continue
        if start <= d < end:
            r["releaseDate"] = d.isoformat()
            out.append(r)
    return out


def extract_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        text = (script.string or script.get_text(strip=False) or "").strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
        elif isinstance(payload, list):
            out.extend([x for x in payload if isinstance(x, dict)])
    return out


def iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from iter_dicts(v)
    elif isinstance(value, list):
        for item in value:
            yield from iter_dicts(item)


def harvest_from_jsonld(payloads: list[dict[str, Any]], source_name: str, source_url: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for payload in payloads:
        for node in iter_dicts(payload):
            name = normalize_text(node.get("name") or node.get("headline") or node.get("title"))
            if not name:
                continue
            date_value = node.get("releaseDate") or node.get("startDate") or node.get("datePublished") or node.get(
                "dateCreated"
            )
            d = parse_date(str(date_value)) if date_value is not None else None
            if d is None:
                continue
            image = node.get("image")
            image_url = image[0] if isinstance(image, list) and image else (image if isinstance(image, str) else None)
            records.append(
                {
                    "releaseDate": d.isoformat(),
                    "shoeName": name,
                    "brand": infer_brand(name),
                    "retailPrice": 0,
                    "estimatedMarketValue": None,
                    "imageUrl": image_url,
                    "sourcePrimary": source_name,
                    "sourceSecondary": "jsonld",
                    "sourceUrl": source_url,
                    "releaseUrl": source_url,
                }
            )
    return records


def harvest_from_cards(soup: BeautifulSoup, source_name: str, source_url: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for time_tag in soup.find_all("time"):
        dt = time_tag.get("datetime")
        d = parse_date(dt) if dt else None
        if d is None:
            continue
        title = ""
        parent = time_tag.parent
        for _ in range(4):
            if parent is None:
                break
            h = parent.find(["h1", "h2", "h3", "a"])
            if h:
                title = normalize_text(h.get_text(" ", strip=True))
                if title:
                    break
            parent = parent.parent
        if not title:
            continue
        price = parse_price(parent.get_text(" ", strip=True)) if parent else 0
        records.append(
            {
                "releaseDate": d.isoformat(),
                "shoeName": title,
                "brand": infer_brand(title),
                "retailPrice": price,
                "estimatedMarketValue": None,
                "imageUrl": None,
                "sourcePrimary": source_name,
                "sourceSecondary": "timecard",
                "sourceUrl": source_url,
                "releaseUrl": source_url,
            }
        )

    for a in soup.find_all("a", href=True):
        text = normalize_text(a.get_text(" ", strip=True))
        if len(text) < 8:
            continue
        container = a.parent
        blob = ""
        for _ in range(3):
            if container is None:
                break
            blob = normalize_text(container.get_text(" ", strip=True))
            if blob:
                break
            container = container.parent
        possible_date = None
        for pat in (r"\b\d{4}-\d{2}-\d{2}\b", r"\b[A-Z][a-z]+ \d{1,2},? \d{4}\b"):
            m = re.search(pat, blob)
            if m:
                possible_date = parse_date(m.group(0))
                if possible_date:
                    break
        if possible_date is None:
            continue
        price = parse_price(blob)
        records.append(
            {
                "releaseDate": possible_date.isoformat(),
                "shoeName": text,
                "brand": infer_brand(text),
                "retailPrice": price,
                "estimatedMarketValue": None,
                "imageUrl": None,
                "sourcePrimary": source_name,
                "sourceSecondary": "anchorcard",
                "sourceUrl": source_url,
                "releaseUrl": source_url,
            }
        )

    return records


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
