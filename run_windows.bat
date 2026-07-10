@echo off
setlocal
REM Development launcher only. This is not a packaged Windows executable.
python -m badge_relief_maker.app --gui
set EXIT_CODE=%ERRORLEVEL%
if not "%EXIT_CODE%"=="0" (
  echo.
  echo Badge Relief Maker exited with code %EXIT_CODE%.
  echo Install GUI dependencies with: python -m pip install -e ".[gui]"
)
exit /b %EXIT_CODE%
