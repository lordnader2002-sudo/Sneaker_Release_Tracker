# file: fetch_release_solecollector.py
#
# Scrapes the Sole Collector sneaker release calendar.
# US-based source: USD prices, major brands, good image coverage.

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from fetch_release_multisource_common import (
    clean_title,
    extract_image_url,
    extract_price_smart,
    infer_brand,
    normalize_text,
    parse_date_flexible,
    purge_placeholder_images,
    render_html,
    window_filter,
)

SOURCE_URL  = "https://solecollector.com/release-dates/sneakers"
SOURCE_NAME = "solecollector"

DATE_RE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s+(\d{1,2})(?:,?\s*(\d{4}))?\b",
    re.I,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch Sole Collector release calendar.")
    p.add_argument("--days",       type=int,  default=35)
    p.add_argument("--timeout-ms", type=int,  default=60000)
    p.add_argument("-o", "--output", type=Path, default=Path("data/fallback_solecollector.json"))
    return p.parse_args()


def extract_rows(soup: BeautifulSoup) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    default_year = date.today().year

    for a in soup.find_all("a", href=True):
        title = clean_title(normalize_text(a.get_text(" ", strip=True)))
        if len(title) < 8:
            continue

        # Walk up to find a card container with a date
        container = a.parent
        blob = ""
        for _ in range(5):
            if container is None:
                break
            blob = normalize_text(container.get_text(" ", strip=True))
            if DATE_RE.search(blob):
                break
            container = container.parent

        m = DATE_RE.search(blob)
        if not m:
            continue

        month = m.group(1)
        day   = m.group(2)
        year  = m.group(3)
        date_str = f"{month} {day} {year}" if year else f"{month} {day}"

        d = parse_date_flexible(date_str, default_year=default_year)
        if not d:
            continue

        # Labeled-only price from the immediate parent — avoids placeholder price pollution
        price_blob = a.parent.get_text(" ", strip=True) if a.parent else blob
        retail = extract_price_smart(normalize_text(price_blob[:400]))

        href = a["href"]
        if href.startswith("/"):
            href = "https://solecollector.com" + href
        if not href.startswith("http"):
            continue

        image_url = extract_image_url(container, base_url="https://solecollector.com")

        rows.append(
            {
                "releaseDate":          d.isoformat(),
                "shoeName":             title,
                "brand":                infer_brand(title),
                "retailPrice":          retail,
                "estimatedMarketValue": None,
                "imageUrl":             image_url,
                "sourcePrimary":        SOURCE_NAME,
                "sourceSecondary":      SOURCE_URL,
                "sourceUrl":            SOURCE_URL,
                "releaseUrl":           href,
            }
        )

    return rows


def dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    purge_placeholder_images(rows)
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r.get("releaseDate", ""), str(r.get("shoeName", "")).lower())
        if not key[0] or not key[1]:
            continue
        existing = best.get(key)
        if existing is None:
            best[key] = r
            continue
        def score(x: dict[str, Any]) -> int:
            return int(bool(x.get("imageUrl"))) + int((x.get("retailPrice") or 0) > 0)
        if score(r) > score(existing):
            best[key] = r

    return sorted(
        best.values(),
        key=lambda x: (x["releaseDate"], x.get("brand", ""), x["shoeName"].lower()),
    )


def main() -> None:
    args = parse_args()
    html = render_html(SOURCE_URL, timeout_ms=args.timeout_ms)
    soup = BeautifulSoup(html, "html.parser")

    rows = window_filter(dedupe(extract_rows(soup)), days=args.days)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"{SOURCE_NAME} saved: {len(rows)} -> {args.output}")


if __name__ == "__main__":
    main()
