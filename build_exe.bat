@echo off
title Build AVA School Assistant 2 Standalone Executable
echo ========================================================
echo Building AVA School Assistant 2 Standalone Executable
echo ========================================================
echo.

REM Remove leftover local build folder if unlocked
if exist "build" rmdir /s /q "build" 2>nul

REM Resolve PyInstaller executable (prefer project venv if present)
set "PYINSTALLER_EXE="
if exist ".venv\Scripts\pyinstaller.exe" (
    set "PYINSTALLER_EXE=.venv\Scripts\pyinstaller.exe"
) else (
    where pyinstaller >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        set "PYINSTALLER_EXE=pyinstaller"
    ) else (
        where uv >nul 2>&1
        if %ERRORLEVEL% equ 0 (
            uv pip install -r requirements.txt pyinstaller --quiet 2>nul
            if exist ".venv\Scripts\pyinstaller.exe" (
                set "PYINSTALLER_EXE=.venv\Scripts\pyinstaller.exe"
            )
        ) else (
            python -m pip install pyinstaller --quiet 2>nul
            set "PYINSTALLER_EXE=pyinstaller"
        )
    )
)

if "%PYINSTALLER_EXE%"=="" set "PYINSTALLER_EXE=pyinstaller"

REM Route temporary work files to %TEMP% to prevent OneDrive sync file-locking
"%PYINSTALLER_EXE%" AVA_School_Assistant_2.spec --workpath "%TEMP%\ava_build" --clean --noconfirm

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
