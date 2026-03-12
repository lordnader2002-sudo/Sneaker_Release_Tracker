# file: enrich_market_value_ebay.py
#
# Enriches estimatedMarketValue for each release by scraping eBay completed/sold
# listings.  No API key required — uses eBay's public search page.
#
# Strategy:
#   1. Search for the exact shoe name (e.g. "Nike Dunk Low Panda")
#   2. If < 3 sold results, fall back to the model only (e.g. "Nike Dunk Low")
#   3. Use the MEDIAN sold price (DS / deadstock preferred via keyword)
#   4. Only overwrite if we find at least MIN_RESULTS listings

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# eBay completed-listings search (includes sold items)
_EBAY_SEARCH = (
    "https://www.ebay.com/sch/i.html"
    "?_nkw={query}"
    "&LH_Sold=1"          # sold listings only
    "&LH_Complete=1"      # completed listings
    "&LH_ItemCondition=1000"  # New / DS
    "&_sacat=15709"       # Athletic Shoes category
    "&_sop=13"            # sort: highest first (gives us recent high-confidence prices)
)

_PRICE_RE = re.compile(r"[\$£€]?\s*([\d,]+(?:\.\d{2})?)")
_MIN_PRICE = 40
_MAX_PRICE = 2500
_MIN_RESULTS = 3          # need at least this many sold prices to trust the median


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enrich estimatedMarketValue from eBay sold listings.")
    p.add_argument("input_json", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--max",     type=int,   default=100,  help="Max rows to enrich per run")
    p.add_argument("--timeout", type=int,   default=15,   help="HTTP timeout in seconds")
    p.add_argument("--sleep",   type=float, default=0.6,  help="Delay between eBay requests")
    p.add_argument("--force",   action="store_true",      help="Re-enrich rows that already have a market value")
    return p.parse_args()


def load_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []


def save_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _build_query(shoe_name: str, brand: str) -> tuple[str, str]:
    """Return (exact_query, fallback_model_query)."""
    name = shoe_name.strip()

    # Exact query: shoe name + "deadstock" to prefer DS listings
    exact = f"{name} deadstock"

    # Fallback: extract brand + key model words (first 4 tokens after brand removal)
    name_lower = name.lower()
    brand_lower = brand.lower() if brand else ""
    tokens = name_lower.replace(brand_lower, "").split()
    # Keep only alpha-numeric tokens, drop colorway noise (long hex-like strings)
    model_tokens = [t for t in tokens if re.match(r"^[a-z0-9\-]+$", t) and len(t) <= 12][:4]
    fallback = f"{brand} {' '.join(model_tokens)} deadstock".strip()

    return exact, fallback


def _fetch_sold_prices(query: str, timeout: int) -> list[float]:
    """Fetch eBay completed-listings page and return list of sold prices."""
    url = _EBAY_SEARCH.format(query=quote_plus(query))
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": UA,
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            },
        )
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    prices: list[float] = []

    # eBay sold prices are in <span class="s-item__price"> with green text nearby
    for item in soup.select(".s-item"):
        # Skip "shop on eBay" placeholder items
        title_el = item.select_one(".s-item__title")
        if title_el and "shop on ebay" in title_el.get_text(strip=True).lower():
            continue

        price_el = item.select_one(".s-item__price")
        if not price_el:
            continue

        raw = price_el.get_text(" ", strip=True)
        # Handle price ranges like "$120.00 to $150.00" — take the lower
        raw = raw.split(" to ")[0]
        m = _PRICE_RE.search(raw)
        if not m:
            continue
        try:
            val = float(m.group(1).replace(",", ""))
        except ValueError:
            continue

        if _MIN_PRICE <= val <= _MAX_PRICE:
            prices.append(val)

    return prices


def get_market_value(shoe_name: str, brand: str, timeout: int, sleep: float) -> int | None:
    exact_q, fallback_q = _build_query(shoe_name, brand)

    prices = _fetch_sold_prices(exact_q, timeout)
    time.sleep(sleep)

    if len(prices) < _MIN_RESULTS and fallback_q != exact_q:
        prices = _fetch_sold_prices(fallback_q, timeout)
        time.sleep(sleep)

    if len(prices) < _MIN_RESULTS:
        return None

    return int(round(median(prices)))


def main() -> None:
    args = parse_args()
    out_path = args.output or args.input_json

    rows = load_rows(args.input_json)

    updated = 0
    attempted = 0

    for row in rows:
        if updated >= args.max:
            break

        # Skip rows that already have a market value unless --force
        if not args.force and row.get("estimatedMarketValue") not in (None, 0, ""):
            continue

        shoe_name = str(row.get("shoeName") or "").strip()
        brand = str(row.get("brand") or "").strip()
        if not shoe_name:
            continue

        attempted += 1
        mv = get_market_value(shoe_name, brand, timeout=args.timeout, sleep=args.sleep)
        if mv is not None:
            row["estimatedMarketValue"] = mv
            updated += 1
            print(f"  ✓ {shoe_name[:50]:<50} → ${mv}")
        else:
            print(f"  – {shoe_name[:50]}")

    save_rows(out_path, rows)
    print(f"\neBay enrich: attempted={attempted} updated={updated} → {out_path.resolve()}")


if __name__ == "__main__":
    main()
