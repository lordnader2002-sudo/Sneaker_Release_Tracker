from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from fetch_release_multisource_common import (
    infer_brand,
    normalize_text,
    parse_date_flexible,
    render_html,
    window_filter,
)

SOURCE_URL = "https://sneakernews.com/release-dates/"
SOURCE_NAME = "sneakernews"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=35)
    p.add_argument("--timeout-ms", type=int, default=60000)
    p.add_argument("-o", "--output", type=Path, default=Path("data/fallback_sneakernews.json"))
    return p.parse_args()


DATE_RE = re.compile(r"\b([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})\b")  # March 05, 2026


def extract_rows(soup: BeautifulSoup) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    # SneakerNews "release-dates" page has repeated sections containing:
    # "March 05, 2026" and then an H2 link like "Nike Air Max 95"
    for h2 in soup.find_all("h2"):
        a = h2.find("a", href=True)
        if not a:
            continue

        title = normalize_text(a.get_text(" ", strip=True))
        if not title:
            continue

        # Find the nearest preceding text in the document that looks like "March 05, 2026"
        container = h2.parent
        blob = normalize_text(container.get_text(" ", strip=True)) if container else ""
        m = DATE_RE.search(blob)
        if not m:
            # try scanning a few previous elements
            prev = h2
            found = None
            for _ in range(8):
                prev = prev.find_previous()
                if not prev:
                    break
                t = normalize_text(prev.get_text(" ", strip=True))
                mm = DATE_RE.search(t)
                if mm:
                    found = mm.group(0)
                    break
            if not found:
                continue
            date_text = found
        else:
            date_text = m.group(0)

        d = parse_date_flexible(date_text)
        if not d:
            continue

        rows.append(
            {
                "releaseDate": d.isoformat(),
                "shoeName": title,
                "brand": infer_brand(title),
                "retailPrice": 0,
                "estimatedMarketValue": None,
                "imageUrl": None,
                "sourcePrimary": SOURCE_NAME,
                "sourceSecondary": SOURCE_URL,
                "sourceUrl": SOURCE_URL,
                "releaseUrl": a["href"],
            }
        )

    return rows


def dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r.get("releaseDate", ""), str(r.get("shoeName", "")).lower())
        if not key[0] or not key[1]:
            continue
        if key not in best:
            best[key] = r
    return sorted(best.values(), key=lambda x: (x["releaseDate"], x.get("brand", ""), x["shoeName"].lower()))


def main() -> None:
    args = parse_args()
    html = render_html(SOURCE_URL, timeout_ms=args.timeout_ms)
    soup = BeautifulSoup(html, "html.parser")

    rows = dedupe(extract_rows(soup))
    rows = window_filter(rows, days=args.days)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"{SOURCE_NAME} saved: {len(rows)} -> {args.output}")


if __name__ == "__main__":
    main()
