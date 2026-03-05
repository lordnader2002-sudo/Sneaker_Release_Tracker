@echo off
setlocal
echo Installing Node packages...
npm install
if errorlevel 1 (
  echo Failed to install Node dependencies.
  pause
  exit /b 1
)
echo Installing Python packages...
py -m pip install --user --upgrade pip
if errorlevel 1 goto :py_fallback
py -m pip install --user -r requirements.txt
if errorlevel 1 goto :py_fallback_done
goto :playwright

:py_fallback
python -m pip install --user --upgrade pip
if errorlevel 1 (
  echo Python not found.
  pause
  exit /b 1
)

:py_fallback_done
python -m pip install --user -r requirements.txt
if errorlevel 1 (
  echo Failed to install Python packages.
  pause
  exit /b 1
)

:playwright
py -m playwright install chromium
if errorlevel 1 goto :playwright_fallback
goto :done

:playwright_fallback
python -m playwright install chromium
if errorlevel 1 (
  echo Failed to install Playwright Chromium.
  pause
  exit /b 1
)

:done
if not exist data mkdir data
if not exist output mkdir output
if not exist archive mkdir archive
echo Setup complete.
pause
exit /b 0
