<#
.SYNOPSIS
    Останавливает воркер и API, запущенные через start.ps1.
.PARAMETER Docker
    Дополнительно остановить контейнеры Postgres и Redis (данные сохраняются).
.PARAMETER WipeData
    Остановить контейнеры и УДАЛИТЬ тома с данными (вся база и очередь будут стёрты).
#>
param(
    [switch]$Docker,
    [switch]$WipeData
)

. "$PSScriptRoot\common.ps1"

$pidFile = Join-Path $script:RunDir 'pids.txt'
if (Test-Path $pidFile) {
    foreach ($id in Get-Content $pidFile) {
        if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
            # /T убивает и дочерние процессы (uv -> python -> celery/fastapi).
            & taskkill /PID $id /T /F | Out-Null
            Write-Host "Остановлен процесс $id"
        }
    }
    Remove-Item $pidFile
}
else {
    Write-Host 'Файл .run\pids.txt не найден: нечего останавливать.'
}

if ($WipeData) {
    Wait-Docker
    & docker compose -f (Join-Path $script:Root 'compose.yml') down -v
}
elseif ($Docker) {
    Wait-Docker
    & docker compose -f (Join-Path $script:Root 'compose.yml') down
}
