<#
.SYNOPSIS
    Запускает весь сервис: Docker (Postgres + Redis), Celery-воркер и FastAPI.
.PARAMETER Hidden
    Не открывать окна консоли, писать логи в logs\api.log и logs\worker.log.
.PARAMETER Open
    Открыть фронтенд (http://127.0.0.1:5180) в браузере, когда всё готово.
    Если фронтенд не установлен, откроется Swagger (http://127.0.0.1:8000/docs).
#>
param(
    [switch]$Hidden,
    [switch]$Open,
    [int]$Port = 8000
)

. "$PSScriptRoot\common.ps1"

$uv = Get-Uv
Ensure-EnvFile
Start-Infra

if (-not (Test-Path (Join-Path $script:Backend '.venv'))) {
    throw 'Нет backend\.venv. Сначала выполните .\scripts\setup.ps1'
}

# Не запускаем второй экземпляр поверх первого.
$pidFile = Join-Path $script:RunDir 'pids.txt'
if (Test-Path $pidFile) {
    $alive = Get-Content $pidFile | Where-Object { $_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue) }
    if ($alive) { throw 'Сервис уже запущен (см. .run\pids.txt). Остановите его: .\scripts\stop.ps1' }
}
New-Item -ItemType Directory -Force $script:RunDir, $script:LogDir | Out-Null

$apiDir = $script:Backend
$workerDir = Join-Path $script:Backend 'src'   # модуль `worker` лежит в src

$apiCmd = "& '$uv' run --env-file .env fastapi run src/app.py --host 127.0.0.1 --port $Port"
# --pool=solo: prefork Celery на Windows не работает.
$workerCmd = "& '$uv' run celery -A worker worker --pool=solo --loglevel=info"

function Start-Service-Window($title, $dir, $cmd, $logName) {
    if ($Hidden) {
        $log = Join-Path $script:LogDir $logName
        $inner = "Set-Location '$dir'; $cmd *>> '$log'"
        return Start-Process powershell -WindowStyle Hidden -PassThru `
            -ArgumentList '-NoProfile', '-Command', $inner
    }
    $inner = "`$Host.UI.RawUI.WindowTitle = '$title'; Set-Location '$dir'; $cmd"
    return Start-Process powershell -PassThru `
        -ArgumentList '-NoProfile', '-NoExit', '-Command', $inner
}

$worker = Start-Service-Window 'AI Gallery - worker' $workerDir $workerCmd 'worker.log'
$api = Start-Service-Window 'AI Gallery - API' $apiDir $apiCmd 'api.log'
$ids = @($worker.Id, $api.Id)

# Фронтенд (Vite) запускаем, только если он установлен (setup.ps1 делает npm install).
$frontendPort = 5180
$hasFrontend = (Test-Path (Join-Path $script:Frontend 'node_modules')) -and (Get-Command npm.cmd -ErrorAction SilentlyContinue)
if ($hasFrontend) {
    $frontend = Start-Service-Window 'AI Gallery - frontend' $script:Frontend 'npm.cmd run dev -- --host 127.0.0.1' 'frontend.log'
    $ids += $frontend.Id
}
$ids | Set-Content $pidFile

Write-Host "Жду готовности API на порту $Port (миграции применяются при старте) ..."
$url = "http://127.0.0.1:$Port/docs"
$ready = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    if ($api.HasExited) { break }
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    }
    catch { }
}

if (-not $ready) {
    Write-Host 'API не поднялся. Смотрите окно API или logs\api.log.' -ForegroundColor Red
    exit 1
}

Write-Host ''
if ($hasFrontend) { Write-Host "Сайт:    http://127.0.0.1:$frontendPort" -ForegroundColor Green }
Write-Host "API:     $url" -ForegroundColor Green
Write-Host 'Остановить: .\scripts\stop.ps1'
Write-Host 'Первый поиск/индексация медленнее: модели загружаются в память при первом обращении.'
if ($Open) {
    if ($hasFrontend) {
        Start-Sleep -Seconds 2   # Vite стартует чуть позже API
        Start-Process "http://127.0.0.1:$frontendPort"
    }
    else { Start-Process $url }
}
