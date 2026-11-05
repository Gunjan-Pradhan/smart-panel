@echo off
title Smart Load Protection Panel Launcher
echo ======================================================================
echo   Launching Smart Load Protection Panel Full-Stack Environment...
echo ======================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-SmartPanel.ps1" %*
pause

