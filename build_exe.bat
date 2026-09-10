@echo off
title Build AVA School Assistant 2 Standalone Executable
echo ========================================================
echo Building AVA School Assistant 2 Standalone Executable
echo ========================================================
echo.

REM Remove leftover local build folder if unlocked
if exist "build" rmdir /s /q "build" 2>nul

python -m pip install pyinstaller --quiet
REM Route temporary work files to %TEMP% to prevent OneDrive sync file-locking
pyinstaller AVA_School_Assistant_2.spec --workpath "%TEMP%\ava_build" --clean --noconfirm

if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================================
    echo Build Successful!
    echo Standalone executable located at: dist\AVA_School_Assistant_2.exe
    echo You can freely copy and move this .exe anywhere!
    echo ========================================================
) else (
    echo.
    echo Build failed with error code %ERRORLEVEL%.
)
pause
