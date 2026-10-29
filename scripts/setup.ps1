<#
.SYNOPSIS
    Однократная подготовка: .env, Docker-сервисы, зависимости Python, модели.
.PARAMETER SkipModels
    Не скачивать модели (они скачаются сами при первом использовании).
#>
param([switch]$SkipModels)

. "$PSScriptRoot\common.ps1"

$uv = Get-Uv
Write-Host "uv: $uv"

Ensure-EnvFile
Start-Infra

Write-Host 'Устанавливаю зависимости Python (uv sync) ...'
Push-Location $script:Backend
try {
    & $uv sync
    if ($LASTEXITCODE -ne 0) { throw 'uv sync завершился с ошибкой.' }

    if (-not $SkipModels) {
        Write-Host 'Скачиваю модели (CLIP и PaddleOCR) ...'
        & $uv run --env-file .env python scripts/download_models.py
        if ($LASTEXITCODE -ne 0) { throw 'Загрузка моделей завершилась с ошибкой.' }
    }
}
finally {
    Pop-Location
}

if (Get-Command npm.cmd -ErrorAction SilentlyContinue) {
    Write-Host 'Устанавливаю зависимости фронтенда (npm install) ...'
    Push-Location $script:Frontend
    try {
        & npm.cmd install --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'npm install завершился с ошибкой.' }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host 'Node.js не найден: фронтенд не установлен (https://nodejs.org). API работает и без него.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Готово. Запуск сервиса: .\scripts\start.ps1' -ForegroundColor Green
