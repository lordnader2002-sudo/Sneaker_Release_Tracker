@echo off
setlocal
if not exist data mkdir data
if not exist output mkdir output
if not exist archive mkdir archive

echo Running Node primary fetcher...
node fetch_releases_primary.js --days 35 --output data\primary_releases.json
if errorlevel 1 (
  echo Primary fetch failed.
  pause
  exit /b 1
)

echo Running Python fallback fetcher...
py fetch_release_fallback.py --days 35 --output data\fallback_releases.json
if errorlevel 1 goto :py_fallback_fetch
goto :merge

:py_fallback_fetch
python fetch_release_fallback.py --days 35 --output data\fallback_releases.json
if errorlevel 1 (
  echo Fallback fetch failed.
  pause
  exit /b 1
)

:merge
echo Merging and validating...
py merge_and_compare.py --primary data\primary_releases.json --fallback data\fallback_releases.json --previous data\final_releases.json --output data\final_releases.json --changes data\changes.json --archive-dir archive
if errorlevel 1 goto :py_fallback_merge
goto :build

:py_fallback_merge
python merge_and_compare.py --primary data\primary_releases.json --fallback data\fallback_releases.json --previous data\final_releases.json --output data\final_releases.json --changes data\changes.json --archive-dir archive
if errorlevel 1 (
  echo Merge failed.
  pause
  exit /b 1
)

:build
echo Building workbooks...
py build_tracker_workbook.py data\final_releases.json --changes data\changes.json --weekly-output output\weekly_tracker.xlsx --monthly-output output\monthly_tracker.xlsx
if errorlevel 1 goto :py_fallback_build
goto :done

:py_fallback_build
python build_tracker_workbook.py data\final_releases.json --changes data\changes.json --weekly-output output\weekly_tracker.xlsx --monthly-output output\monthly_tracker.xlsx
if errorlevel 1 (
  echo Workbook build failed.
  pause
  exit /b 1
)

:done
echo Done.
echo Weekly: output\weekly_tracker.xlsx
echo Monthly: output\monthly_tracker.xlsx
pause
exit /b 0
