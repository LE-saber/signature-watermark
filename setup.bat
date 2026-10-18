@echo off
setlocal
cd /d "%~dp0"

echo.
echo [1/3] Creating Python 3.12 virtual environment...
py -3.12 -m venv .venv
if errorlevel 1 goto :fail

echo.
echo [2/3] Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo.
echo [3/3] Installing blind-watermark and image dependencies...
".venv\Scripts\python.exe" -m pip install blind-watermark pillow numpy opencv-python PyWavelets
if errorlevel 1 goto :fail

if not exist ".env" copy /y ".env.example" ".env" >nul
if not exist "out\images" mkdir "out\images"
if not exist "out\watermark" mkdir "out\watermark"

echo.
echo SETUP COMPLETE
echo.
echo Next steps:
echo   1. Edit .env and set WATERMARK_PASSWORD.
echo   2. Keep the transparent master as signature.png.
echo   3. Double-click run-signature-watermark.bat.
echo.
pause
exit /b 0

:fail
echo.
echo SETUP FAILED
echo Copy the error above and send it to ChatGPT.
echo.
pause
exit /b 1
