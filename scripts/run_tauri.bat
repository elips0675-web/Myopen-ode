@echo off
rem My OpenCode - Tauri (WebView2) desktop wrapper launcher
rem Usage: run_tauri.bat  (first run builds the wrapper via cargo)
setlocal
set ROOT=%~dp0..
set EXE=%ROOT%\src-tauri\target\debug\myopencode.exe

if not exist "%EXE%" (
    echo Building Tauri wrapper (first run, a few minutes)...
    where cargo >nul 2>nul
    if errorlevel 1 (
        echo Rust toolchain not found. Install: winget install Rustlang.Rustup ^
        echo then "rustup default stable" and MSVC Build Tools:
        echo winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override ^
        echo "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
        pause
        exit /b 1
    )
    pushd "%ROOT%\src-tauri"
    call cargo build
    popd
    if not exist "%EXE%" (
        echo Build failed.
        pause
        exit /b 1
    )
)

start "" "%EXE%"
