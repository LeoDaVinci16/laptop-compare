@echo off
REM ---------------------------------------------------------------------------
REM  Double-click this file to (re)generate the report and open it.
REM  Needs the "laptop-compare" conda environment (see INSTALL.md, step 3).
REM  You can also run it from a terminal with options, e.g.:
REM      run_report.bat --base "zenbook"
REM ---------------------------------------------------------------------------
cd /d "%~dp0"

REM Find Anaconda / Miniconda (double-clicked files don't know where conda is)
set "ACT="
for %%D in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "C:\ProgramData\anaconda3" "C:\ProgramData\miniconda3") do (
    if not defined ACT if exist "%%~D\Scripts\activate.bat" set "ACT=%%~D\Scripts\activate.bat"
)
if not defined ACT (
    echo Could not find Anaconda. Open "Anaconda Prompt", go to this folder and run:  laptop-compare
    pause
    exit /b 1
)
call "%ACT%" laptop-compare || (
    echo The environment "laptop-compare" does not exist yet. Follow INSTALL.md, step 3.
    pause
    exit /b 1
)

laptop-compare %*
if errorlevel 1 (
    pause
    exit /b 1
)
start "" "output\report.html"
