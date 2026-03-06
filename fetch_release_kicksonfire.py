from __future__ import annotations

import argparse
import json
import re
from datetime import date
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

SOURCE_URL = "https://www.kicksonfire.com/sneaker-release-dates"
SOURCE_NAME = "kicksonfire"

ANCHOR_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(.*)$", re.I)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=35)
    p.add_argument("--timeout-ms", type=int, default=60000)
    p.add_argument("-o", "--output", type=Path, default=Path("data/fallback_kicksonfire.json"))
    return p.parse_args()


def extract_rows(soup: BeautifulSoup) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    default_year = date.today().year

    for a in soup.find_all("a", href=True):
        text = normalize_text(a.get_text(" ", strip=True))
        m = ANCHOR_RE.match(text)
        if not m:
            continue

        month_day = f"{m.group(1)} {m.group(2)}"
        title = normalize_text(m.group(3))
        if not title:
            continue

        d = parse_date_flexible(month_day, default_year=default_year)
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
