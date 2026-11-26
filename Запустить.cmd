@echo off
rem Двойной щелчок: запускает AI Search Gallery и открывает вкладку браузера.
rem При первом запуске сначала ставит зависимости и модели (scripts\setup.ps1).
chcp 65001 >nul
if not exist "%~dp0backend\.venv" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
    if errorlevel 1 goto :error
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo Не удалось запустить, подробности выше.
pause
exit /b 1
