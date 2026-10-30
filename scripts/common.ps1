# Общие функции для scripts\*.ps1 (подключается через dot-sourcing).
# Continue, а не Stop: в Windows PowerShell 5.1 любая строка в stderr нативной команды
# (docker, uv) иначе превращается в ошибку. Коды возврата проверяем явно.
$ErrorActionPreference = 'Continue'

$script:Root = Split-Path -Parent $PSScriptRoot
$script:Backend = Join-Path $script:Root 'backend'
$script:Frontend = Join-Path $script:Root 'frontend'
$script:RunDir = Join-Path $script:Root '.run'
$script:LogDir = Join-Path $script:Root 'logs'

function Get-Uv {
    <# Возвращает путь к uv.exe; если uv нет, ставит его через pip --user (без прав администратора). #>
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Не найден ни uv, ни python. Установите Python 3.13 (https://www.python.org/downloads/) и запустите скрипт снова.'
    }
    $scripts = (& python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))").Trim()
    $uv = Join-Path $scripts 'uv.exe'
    if (-not (Test-Path $uv)) {
        Write-Host 'uv не найден, ставлю через pip --user ...'
        & python -m pip install --user --quiet uv 2>&1 | Out-Null
        if (-not (Test-Path $uv)) { throw "Не удалось установить uv (ожидал $uv)." }
    }
    return $uv
}

function Test-DockerReady {
    & docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Wait-Docker {
    <# Убеждается, что демон Docker работает; при необходимости запускает Docker Desktop. #>
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Docker не найден. Установите Docker Desktop: https://www.docker.com/products/docker-desktop/'
    }
    if (Test-DockerReady) { return }

    $exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $exe)) { throw 'Демон Docker не отвечает, а Docker Desktop.exe не найден. Запустите Docker вручную.' }
    Write-Host 'Запускаю Docker Desktop ...'
    Start-Process $exe
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 3
        if (Test-DockerReady) { Write-Host 'Docker готов.'; return }
    }
    throw 'Docker Desktop не запустился за 3 минуты. Запустите его вручную и повторите.'
}

function Start-Infra {
    <# Поднимает Postgres (pgvector) и Redis из compose.yml и ждёт их healthcheck. #>
    Wait-Docker
    Write-Host 'Поднимаю Postgres и Redis (docker compose) ...'
    & docker compose -f (Join-Path $script:Root 'compose.yml') up -d --wait
    if ($LASTEXITCODE -ne 0) { throw 'docker compose up завершился с ошибкой.' }
}

function Ensure-EnvFile {
    $envFile = Join-Path $script:Backend '.env'
    if (-not (Test-Path $envFile)) {
        Copy-Item (Join-Path $script:Backend '.env.example') $envFile
        Write-Host "Создан $envFile из .env.example"
    }
}
