@echo off
title AVA School Assistant 2
echo Starting AVA School Assistant 2...

if exist "dist\AVA_School_Assistant_2.exe" (
    start "" "dist\AVA_School_Assistant_2.exe" %*
) else if exist "dist\AVA_School_Assistant_2\AVA_School_Assistant_2.exe" (
    start "" "dist\AVA_School_Assistant_2\AVA_School_Assistant_2.exe" %*
) else (
    python main.py %*
)
exit /b
