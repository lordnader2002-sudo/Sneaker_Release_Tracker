# Sneaker Release Tracker

An automated sneaker release tracking pipeline that collects release data, merges multiple free sources, scores release hype/confidence, tracks changes over time, and generates polished Excel workbooks for weekly and monthly review.

## What this repo does

This project is built to replace manual sneaker release spreadsheets with a fully automated workflow.

It:

- pulls sneaker release data automatically
- uses a **primary source** plus a **fallback source**
- merges and cleans release records
- scores each release for:
  - **Hype**
  - **Confidence**
  - **Priority**
- detects changes from the previous run
- archives snapshots
- generates styled Excel workbooks
- runs automatically with **GitHub Actions**

## Pipeline overview

The workflow runs in this order:

1. **Primary fetcher**
   - `fetch_releases_primary.js`
   - Uses **Sneaks-API** in Node.js
   - Pulls broad sneaker/product data

2. **Fallback fetcher**
   - `fetch_release_fallback.py`
   - Uses **Playwright** + Python
   - Scrapes public release pages when the primary source is weak or incomplete

3. **Merge + compare**
   - `merge_and_compare.py`
   - Merges primary and fallback records
   - Deduplicates entries
   - Calculates:
     - hype
     - confidence
     - priority
     - tags
   - Detects changes from the prior run
   - Writes archive snapshots

4. **Workbook builder**
   - `build_tracker_workbook.py`
   - Generates:
     - `output/weekly_tracker.xlsx`
     - `output/monthly_tracker.xlsx`

5. **GitHub Actions**
   - `.github/workflows/update_trackers.yml`
   - Runs the entire pipeline on a schedule or manually
   - Uploads generated files as artifacts
   - Commits updated outputs back into the repo

## Output files

After a successful run, the repo produces:

### Data
- `data/primary_releases.json`
- `data/fallback_releases.json`
- `data/final_releases.json`
- `data/changes.json`

### Excel
- `output/weekly_tracker.xlsx`
- `output/monthly_tracker.xlsx`

### Archive
- timestamped snapshots in `archive/`

## Workbook tabs

The generated workbook includes multiple sheets for different workflows:

- **Tracker**
  - main action sheet for current releases

- **Monthly**
  - broader release window

- **Changes**
  - shows new, removed, or updated releases

- **Raw Data**
  - normalized merged records

- **High Hype**
  - filtered high-priority releases

- **Summary**
  - counts, breakdowns, and quick metrics

## Scoring model

### Hype
Each release is scored and labeled:

- `LOW`
- `MED`
- `HIGH`

Inputs may include:
- brand
- collaboration keywords
- model popularity
- retail price
- resale spread

### Confidence
Each release is also scored for data reliability:

- `LOW`
- `MED`
- `HIGH`

Confidence is based on factors like:
- source coverage
- image presence
- retail price presence
- secondary source confirmation

### Priority
Operational priority is derived from hype + confidence:

- `Must Watch`
- `Watch`
- `Low Priority`

## Repo structure

```text
.github/workflows/update_trackers.yml
.gitignore
README.md
package.json
requirements.txt

fetch_releases_primary.js
fetch_release_fallback.py
merge_and_compare.py
build_tracker_workbook.py

setup_local.bat
run_local_full.bat

data/
output/
archive/
