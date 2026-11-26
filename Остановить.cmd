@echo off
rem Двойной щелчок: останавливает AI Search Gallery.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1" %*
timeout /t 3 >nul
