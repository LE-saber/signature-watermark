@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv not found. Run setup.bat first.
    pause
    exit /b 1
)

if not exist ".env" (
    echo ERROR: .env not found.
    pause
    exit /b 1
)

if not exist "signature.png" (
    echo ERROR: signature.png not found in %~dp0
    pause
    exit /b 1
)

".venv\Scripts\python.exe" "signature_watermark_blind.py" embed
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo FAILED. See the error above.
) else (
    echo Done.
)
echo.
pause
exit /b %RC%
