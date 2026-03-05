# file: merge_and_compare.py

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


HIGH_BRANDS = {"air jordan", "nike", "yeezy"}
COLLAB_KEYWORDS = {
    "travis scott", "off-white", "j balvin", "union", "supreme", "fear of god",
    "kith", "trophy room", "clot", "a ma maniere", "action bronson",
    "salehe bembury", "sacai", "fragment", "undefeated", "concepts",
    "bodega", "strangelove", "parra", "stussy", "patta", "futura",
}
LIMITED_KEYWORDS = {"limited", "exclusive", "special box", "qs", "pe", "promo"}
HOT_MODELS = {"jordan 1", "jordan 3", "jordan 4", "jordan 11", "dunk", "sb dunk", "air max 95", "kobe"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge sources, compare changes, and validate quality.")
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--fallback", type=Path, default=None)
    parser.add_argument("--previous", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--changes", type=Path, default=None)
    parser.add_argument("--archive-dir", type=Path, default=None)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--min-records", type=int, default=3)
    return parser.parse_args()


def load_json(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def normalize_brand(value: Any, shoe_name: str) -> str:
    brand = normalize_text(value)
    if brand:
        lowered = brand.lower()
        mapping = {
            "jordan": "Air Jordan",
            "air jordan": "Air Jordan",
            "nike": "Nike",
            "adidas": "Adidas",
            "new balance": "New Balance",
            "asics": "ASICS",
            "crocs": "Crocs",
            "converse": "Converse",
        }
        return mapping.get(lowered, brand.title())

    lowered = shoe_name.lower()
    if "jordan" in lowered:
        return "Air Jordan"
    if "nike" in lowered or "dunk" in lowered or "air max" in lowered:
        return "Nike"
    if "adidas" in lowered or "samba" in lowered or "gazelle" in lowered:
        return "Adidas"
    if "new balance" in lowered:
        return "New Balance"
    if "asics" in lowered:
        return "ASICS"
    if "crocs" in lowered:
        return "Crocs"
    if "converse" in lowered:
        return "Converse"
    return "Unknown"


def parse_price(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(round(value)))
    try:
        return max(0, int(round(float(str(value).replace("$", "").replace(",", "").strip()))))
    except ValueError:
        return 0


def score_hype(brand: str, style: str, retail: int, resale: int | None) -> tuple[int, str]:
    score = 0
    lowered_style = style.lower()
    lowered_brand = brand.lower()

    if lowered_brand in HIGH_BRANDS:
        score += 12
    else:
        score += 4

    if any(token in lowered_style for token in COLLAB_KEYWORDS):
        score += 18
    if any(token in lowered_style for token in LIMITED_KEYWORDS):
        score += 10
    if any(token in lowered_style for token in HOT_MODELS):
        score += 10

    if retail >= 250:
        score += 2
    elif 0 < retail <= 110:
        score += 3

    if resale is not None and retail > 0:
        ratio = resale / retail
        spread = resale - retail

        if ratio >= 2.0:
            score += 30
        elif ratio >= 1.5:
            score += 20
        elif ratio >= 1.2:
            score += 10

        if spread >= 150:
            score += 12
        elif spread >= 75:
            score += 7
        elif spread >= 30:
            score += 3

    if score >= 42:
        return score, "HIGH"
    if score >= 22:
        return score, "MED"
    return score, "LOW"


def score_confidence(record: dict[str, Any]) -> tuple[int, str]:
    score = 0

    if record.get("sourcePrimary"):
        score += 25
    if record.get("sourceSecondary"):
        score += 15
    if record.get("retailPrice", 0) > 0:
        score += 15
    if record.get("imageUrl"):
        score += 10
    if record.get("releaseUrl"):
        score += 10
    if record.get("matchedSources", 0) >= 2:
        score += 20

    if score >= 60:
        return score, "HIGH"
    if score >= 35:
        return score, "MED"
    return score, "LOW"


def derive_priority(hype: str, confidence: str) -> str:
    if hype == "HIGH" and confidence == "HIGH":
        return "Must Watch"
    if (hype == "HIGH" and confidence == "MED") or (hype == "MED" and confidence == "HIGH"):
        return "Watch"
    return "Low Priority"


def derive_tags(style: str) -> list[str]:
    lowered = style.lower()
    tags: list[str] = []

    if any(token in lowered for token in COLLAB_KEYWORDS):
        tags.append("collab")
    if any(token in lowered for token in HOT_MODELS):
        tags.append("hot-model")
    if "retro" in lowered:
        tags.append("retro")
    if any(token in lowered for token in ("running", "pegasus", "vomero", "air max")):
        tags.append("running")
    if any(token in lowered for token in ("lebron", "kobe", "kd ", "sabrina", "basketball")):
        tags.append("basketball")
    if any(token in lowered for token in ("women", "wmns")):
        tags.append("women")
    if any(token in lowered for token in LIMITED_KEYWORDS):
        tags.append("exclusive")

    return tags


def make_key(record: dict[str, Any]) -> tuple[str, str]:
    return (
        normalize_text(record.get("releaseDate")),
        normalize_text(record.get("shoeName")).lower(),
    )


def choose_better(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    def quality(item: dict[str, Any]) -> int:
        return (
            int(bool(item.get("imageUrl")))
            + int(parse_price(item.get("retailPrice")) > 0)
            + int(parse_price(item.get("estimatedMarketValue")) > 0)
            + int(bool(item.get("sourceSecondary")))
        )

    return b if quality(b) > quality(a) else a


def merge_records(primary: list[dict[str, Any]], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}

    for source_name, rows in (("primary", primary), ("fallback", fallback)):
        for row in rows:
            release_date = normalize_text(row.get("releaseDate"))
            shoe_name = normalize_text(row.get("shoeName"))
            if not release_date or not shoe_name:
                continue
            if parse_date(release_date) is None:
                continue

            normalized = {
                "releaseDate": release_date,
                "shoeName": shoe_name,
                "brand": normalize_brand(row.get("brand"), shoe_name),
                "retailPrice": parse_price(row.get("retailPrice")),
                "estimatedMarketValue": (
                    parse_price(row.get("estimatedMarketValue"))
                    if row.get("estimatedMarketValue") not in (None, "")
                    else None
                ),
                "imageUrl": normalize_text(row.get("imageUrl")) or None,
                "sourcePrimary": normalize_text(row.get("sourcePrimary")) or source_name,
                "sourceSecondary": normalize_text(row.get("sourceSecondary")) or None,
                "sourceUrl": normalize_text(row.get("sourceUrl")) or None,
                "releaseUrl": normalize_text(row.get("releaseUrl")) or normalize_text(row.get("sourceUrl")) or None,
            }

            key = make_key(normalized)
            existing = merged.get(key)

            if existing is None:
                normalized["matchedSources"] = 1
                merged[key] = normalized
                continue

            picked = choose_better(existing, normalized)
            if picked is existing:
                if normalized["sourcePrimary"] and normalized["sourcePrimary"] != existing.get("sourcePrimary"):
                    existing["sourceSecondary"] = existing.get("sourceSecondary") or normalized["sourcePrimary"]
                existing["matchedSources"] = int(existing.get("matchedSources", 1)) + 1
                if not existing.get("sourceUrl") and normalized.get("sourceUrl"):
                    existing["sourceUrl"] = normalized["sourceUrl"]
                if not existing.get("releaseUrl") and normalized.get("releaseUrl"):
                    existing["releaseUrl"] = normalized["releaseUrl"]
                continue

            picked["matchedSources"] = int(existing.get("matchedSources", 1)) + 1
            if existing.get("sourcePrimary") and existing.get("sourcePrimary") != picked.get("sourcePrimary"):
                picked["sourceSecondary"] = picked.get("sourceSecondary") or existing["sourcePrimary"]
            merged[key] = picked

    final_rows: list[dict[str, Any]] = []

    for row in merged.values():
        hype_score, hype = score_hype(
            brand=row["brand"],
            style=row["shoeName"],
            retail=row["retailPrice"],
            resale=row["estimatedMarketValue"],
        )
        confidence_score, confidence = score_confidence(row)
        tags = derive_tags(row["shoeName"])
        row["hypeScore"] = hype_score
        row["hype"] = hype
        row["confidenceScore"] = confidence_score
        row["confidence"] = confidence
        row["priority"] = derive_priority(hype, confidence)
        row["tags"] = tags
        row["recordHash"] = hashlib.sha256(
            json.dumps(
                {
                    "releaseDate": row["releaseDate"],
                    "shoeName": row["shoeName"],
                    "brand": row["brand"],
                    "retailPrice": row["retailPrice"],
                    "estimatedMarketValue": row["estimatedMarketValue"],
                    "sourcePrimary": row["sourcePrimary"],
                    "sourceSecondary": row["sourceSecondary"],
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        final_rows.append(row)

    return sorted(
        final_rows,
        key=lambda item: (item["releaseDate"], item["brand"].lower(), item["shoeName"].lower()),
    )


def compare_changes(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previous_map = {make_key(row): row for row in previous if make_key(row) != ("", "")}
    current_map = {make_key(row): row for row in current if make_key(row) != ("", "")}
    changes: list[dict[str, Any]] = []
    detected_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    for key, row in current_map.items():
        if key not in previous_map:
            changes.append({
                "changeType": "NEW",
                "date": row.get("releaseDate"),
                "brand": row.get("brand"),
                "style": row.get("shoeName"),
                "fieldChanged": "",
                "oldValue": "",
                "newValue": "",
                "detectedAt": detected_at,
            })
            continue

        old = previous_map[key]

        fields = [
            ("retailPrice", "RETAIL_CHANGED"),
            ("estimatedMarketValue", "MARKET_CHANGED"),
            ("sourcePrimary", "SOURCE_CHANGED"),
            ("sourceSecondary", "SOURCE_CHANGED"),
            ("confidence", "CONFIDENCE_CHANGED"),
            ("priority", "PRIORITY_CHANGED"),
        ]

        for field_name, change_type in fields:
            if old.get(field_name) != row.get(field_name):
                changes.append({
                    "changeType": change_type,
                    "date": row.get("releaseDate"),
                    "brand": row.get("brand"),
                    "style": row.get("shoeName"),
                    "fieldChanged": field_name,
                    "oldValue": old.get(field_name, ""),
                    "newValue": row.get(field_name, ""),
                    "detectedAt": detected_at,
                })

    for key, row in previous_map.items():
        if key not in current_map:
            changes.append({
                "changeType": "REMOVED",
                "date": row.get("releaseDate"),
                "brand": row.get("brand"),
                "style": row.get("shoeName"),
                "fieldChanged": "",
                "oldValue": "",
                "newValue": "",
                "detectedAt": detected_at,
            })

    return sorted(
        changes,
        key=lambda item: (
            item.get("date") or "",
            item.get("changeType") or "",
            (item.get("style") or "").lower(),
        ),
    )


def validate_records(rows: list[dict[str, Any]], min_records: int) -> None:
    if len(rows) < min_records:
        raise SystemExit(f"Validation failed: only {len(rows)} record(s), expected at least {min_records}")

    low_confidence = sum(1 for row in rows if str(row.get("confidence", "")).upper() == "LOW")
    if rows and (low_confidence / len(rows)) > 0.9:
        raise SystemExit("Validation failed: more than 90% of rows are low confidence")


def write_json(path: Path | None, data: list[dict[str, Any]]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def archive_snapshot(archive_dir: Path | None, rows: list[dict[str, Any]]) -> None:
    if archive_dir is None:
        return
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    snapshot_path = archive_dir / f"final_releases_{stamp}.json"
    snapshot_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()

    if args.validate_only:
        rows = load_json(args.primary)
        validate_records(rows, min_records=args.min_records)
        print(f"Validated rows: {len(rows)}")
        return

    primary_rows = load_json(args.primary)
    fallback_rows = load_json(args.fallback)
    previous_rows = load_json(args.previous)

    merged_rows = merge_records(primary_rows, fallback_rows)
    changes = compare_changes(previous_rows, merged_rows)

    validate_records(merged_rows, min_records=args.min_records)
    write_json(args.output, merged_rows)
    write_json(args.changes, changes)
    archive_snapshot(args.archive_dir, merged_rows)

    print(f"Primary rows: {len(primary_rows)}")
    print(f"Fallback rows: {len(fallback_rows)}")
    print(f"Merged rows: {len(merged_rows)}")
    print(f"Detected changes: {len(changes)}")


if __name__ == "__main__":
    main()
