// file: fetch_releases_primary.js

"use strict";

const fs = require("fs");
const path = require("path");
const SneaksAPI = require("sneaks-api");
const sneaks = new SneaksAPI();

function parseArgs(argv) {
  const args = {
    days: 35,
    limit: 250,
    output: path.join("data", "primary_releases.json"),
  };

  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];

    if (arg === "--days" && argv[i + 1]) {
      args.days = Number.parseInt(argv[i + 1], 10);
      i += 1;
      continue;
    }

    if (arg === "--limit" && argv[i + 1]) {
      args.limit = Number.parseInt(argv[i + 1], 10);
      i += 1;
      continue;
    }

    if (arg === "--output" && argv[i + 1]) {
      args.output = argv[i + 1];
      i += 1;
    }
  }

  if (!Number.isFinite(args.days) || args.days <= 0) {
    throw new Error("--days must be a positive integer");
  }

  if (!Number.isFinite(args.limit) || args.limit <= 0) {
    throw new Error("--limit must be a positive integer");
  }

  return args;
}

function ensureDirForFile(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function parseDate(value) {
  if (!value) {
    return null;
  }

  const raw = String(value).trim();
  if (!raw) {
    return null;
  }

  const candidate = raw.includes("T") ? raw : raw.replace(/\//g, "-");
  const parsed = new Date(candidate);

  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  return parsed;
}

function toIsoDate(value) {
  const parsed = parseDate(value);
  if (!parsed) {
    return null;
  }
  return parsed.toISOString().slice(0, 10);
}

function normalizePrice(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  if (typeof value === "number" && Number.isFinite(value)) {
    return value >= 0 ? Math.round(value) : null;
  }

  const cleaned = String(value)
    .replace(/[$,]/g, "")
    .replace(/USD/gi, "")
    .trim();

  if (!cleaned) {
    return null;
  }

  const parsed = Number.parseFloat(cleaned);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }

  return Math.round(parsed);
}

function deriveBrand(shoeName, brand) {
  if (brand && String(brand).trim()) {
    const normalized = String(brand).trim();
    const lower = normalized.toLowerCase();

    if (lower === "jordan" || lower === "air jordan") return "Air Jordan";
    if (lower === "new balance") return "New Balance";
    if (lower === "asics") return "ASICS";

    return normalized
      .split(/\s+/)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join(" ");
  }

  const style = String(shoeName || "").toLowerCase();

  if (style.includes("jordan")) return "Air Jordan";
  if (style.includes("nike") || style.includes("air max") || style.includes("dunk")) return "Nike";
  if (style.includes("adidas") || style.includes("samba") || style.includes("gazelle")) return "Adidas";
  if (style.includes("new balance")) return "New Balance";
  if (style.includes("asics")) return "ASICS";
  if (style.includes("crocs")) return "Crocs";
  if (style.includes("converse")) return "Converse";

  return "Unknown";
}

function normalizeName(record) {
  const value =
    record.shoeName ||
    record.name ||
    record.title ||
    record.productName ||
    record.shortDescription ||
    "Unknown Style";

  return String(value).replace(/\s+/g, " ").trim();
}

function pullResale(record) {
  const candidates = [
    record.lowestResellPrice,
    record.lowest_ask,
    record.estimatedMarketValue,
    record.marketValue,
    record.resellPrice,
    record.tradeRangeLow,
    record.salePrice,
  ];

  for (const candidate of candidates) {
    const parsed = normalizePrice(candidate);
    if (parsed !== null) {
      return parsed;
    }
  }

  if (record.resellLinks && typeof record.resellLinks === "object") {
    for (const value of Object.values(record.resellLinks)) {
      if (value && typeof value === "object") {
        for (const nested of Object.values(value)) {
          const parsed = normalizePrice(nested);
          if (parsed !== null) {
            return parsed;
          }
        }
      } else {
        const parsed = normalizePrice(value);
        if (parsed !== null) {
          return parsed;
        }
      }
    }
  }

  return null;
}

function normalizeRecord(record) {
  const shoeName = normalizeName(record);
  const releaseDate = toIsoDate(record.releaseDate || record.release_date || record.date);

  if (!releaseDate) {
    return null;
  }

  const brand = deriveBrand(shoeName, record.brand);
  const retailPrice = normalizePrice(
    record.retailPrice || record.retail_price || record.retail || record.msrp
  ) ?? 0;

  return {
    releaseDate,
    shoeName,
    brand,
    retailPrice,
    estimatedMarketValue: pullResale(record),
    imageUrl: record.thumbnail || record.image || record.imageUrl || null,
    sourcePrimary: "sneaks-api",
    sourceSecondary: null,
    sourceUrl: null,
  };
}

function dedupe(records) {
  const best = new Map();

  for (const record of records) {
    const key = `${record.releaseDate}__${record.shoeName.toLowerCase()}`;
    const existing = best.get(key);

    if (!existing) {
      best.set(key, record);
      continue;
    }

    const existingScore =
      Number(Boolean(existing.imageUrl)) +
      Number((existing.retailPrice || 0) > 0) +
      Number((existing.estimatedMarketValue || 0) > 0);

    const incomingScore =
      Number(Boolean(record.imageUrl)) +
      Number((record.retailPrice || 0) > 0) +
      Number((record.estimatedMarketValue || 0) > 0);

    if (incomingScore > existingScore) {
      best.set(key, record);
    }
  }

  return Array.from(best.values()).sort((a, b) => {
    if (a.releaseDate !== b.releaseDate) {
      return a.releaseDate.localeCompare(b.releaseDate);
    }
    if (a.brand !== b.brand) {
      return a.brand.localeCompare(b.brand);
    }
    return a.shoeName.localeCompare(b.shoeName);
  });
}

function filterByWindow(records, days) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const end = new Date(today);
  end.setDate(end.getDate() + days);

  return records.filter((record) => {
    const parsed = parseDate(record.releaseDate);
    return parsed && parsed >= today && parsed < end;
  });
}

function getProducts(limit) {
  return new Promise((resolve, reject) => {
    let settled = false;

    const finish = (error, products) => {
      if (settled) {
        return;
      }
      settled = true;

      if (error) {
        reject(error);
        return;
      }

      resolve(Array.isArray(products) ? products : []);
    };

    try {
      if (typeof sneaks.getMostPopular === "function") {
        sneaks.getMostPopular(limit, finish);
        return;
      }

      if (typeof sneaks.getProducts === "function") {
        sneaks.getProducts(limit, finish);
        return;
      }

      reject(new Error("Sneaks-API method not found. Expected getMostPopular or getProducts."));
    } catch (error) {
      reject(error);
    }
  });
}

async function main() {
  const args = parseArgs(process.argv);
  const raw = await getProducts(args.limit);

  const normalized = raw
    .map(normalizeRecord)
    .filter(Boolean);

  const filtered = filterByWindow(normalized, args.days);
  const cleaned = dedupe(filtered);

  ensureDirForFile(args.output);
  fs.writeFileSync(args.output, JSON.stringify(cleaned, null, 2), "utf8");

  console.log(`Fetched raw records: ${raw.length}`);
  console.log(`Normalized records: ${normalized.length}`);
  console.log(`Filtered records: ${filtered.length}`);
  console.log(`Saved primary records: ${cleaned.length}`);
  console.log(`Output: ${path.resolve(args.output)}`);
}

main().catch((error) => {
  console.error(error && error.message ? error.message : error);
  process.exit(1);
});
