<#
.SYNOPSIS
    Запускает приложение (API, сайт и индексатор в одном процессе) и открывает вкладку браузера.
.PARAMETER Hidden
    Не открывать окно консоли, писать лог в logs\app.log.
.PARAMETER NoBrowser
    Не открывать вкладку браузера.
.PARAMETER Port
    Порт приложения (по умолчанию 8000).
#>
param(
    [switch]$Hidden,
    [switch]$NoBrowser,
    [int]$Port = 8000
)

. "$PSScriptRoot\common.ps1"

$uv = Get-Uv
Ensure-EnvFile

if (-not (Test-Path (Join-Path $script:Backend '.venv'))) {
    throw 'Нет backend\.venv. Сначала выполните .\scripts\setup.ps1'
}
if (-not (Test-Path (Join-Path $script:Frontend 'dist\index.html'))) {
    Build-Frontend
}

# Не запускаем второй экземпляр поверх первого.
$pidFile = Join-Path $script:RunDir 'pids.txt'
if (Test-Path $pidFile) {
    $alive = Get-Content $pidFile | Where-Object { $_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue) }
    if ($alive) {
        Write-Host 'Приложение уже запущено, открываю его.'
        if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }
        exit 0
    }
}
New-Item -ItemType Directory -Force $script:RunDir, $script:LogDir | Out-Null

$appArgs = "--port $Port"
if ($NoBrowser) { $appArgs += ' --no-browser' }
$cmd = "& '$uv' run gallery $appArgs"

if ($Hidden) {
    $log = Join-Path $script:LogDir 'app.log'
    # Через cmd: PowerShell 5.1 оборачивает каждую строку stderr в запись об ошибке.
    # Внешние кавычки вокруг всей команды: cmd /c снимает первую и последнюю.
    $inner = "`"$uv`" run gallery $appArgs >> `"$log`" 2>&1"
    $proc = Start-Process cmd.exe -WindowStyle Hidden -PassThru -WorkingDirectory $script:Backend -ArgumentList '/c', "`"$inner`""
    Write-Host "Приложение запущено в фоне, лог: $log"
}
else {
    $inner = "`$Host.UI.RawUI.WindowTitle = 'AI Search Gallery'; Set-Location '$($script:Backend)'; $cmd"
    $proc = Start-Process powershell -PassThru -ArgumentList '-NoProfile', '-NoExit', '-Command', $inner
    Write-Host 'Приложение запущено в отдельном окне.'
}
$proc.Id | Set-Content $pidFile

Write-Host "Адрес: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host 'Остановить: .\scripts\stop.ps1 (или Ctrl+C в окне приложения)'
