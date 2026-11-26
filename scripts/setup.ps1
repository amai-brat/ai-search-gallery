<#
.SYNOPSIS
    Однократная подготовка: .env, зависимости Python, модели, сборка сайта.
.PARAMETER SkipModels
    Не скачивать модели (они скачаются сами при первом использовании).
#>
param([switch]$SkipModels)

. "$PSScriptRoot\common.ps1"

$uv = Get-Uv
Write-Host "uv: $uv"

Ensure-EnvFile

Write-Host 'Устанавливаю зависимости Python (uv sync) ...'
Push-Location $script:Backend
try {
    & $uv sync
    if ($LASTEXITCODE -ne 0) { throw 'uv sync завершился с ошибкой.' }

    if (-not $SkipModels) {
        Write-Host 'Скачиваю модели (CLIP ~1.5 ГБ и OCR) ...'
        & $uv run python scripts/download_models.py
        if ($LASTEXITCODE -ne 0) { throw 'Загрузка моделей завершилась с ошибкой.' }
    }
}
finally {
    Pop-Location
}

Build-Frontend

Write-Host ''
Write-Host 'Готово. Запуск: .\scripts\start.ps1' -ForegroundColor Green
