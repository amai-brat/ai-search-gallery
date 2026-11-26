<#
.SYNOPSIS
    Останавливает приложение, запущенное через start.ps1.
.PARAMETER WipeData
    Дополнительно УДАЛИТЬ базу (все проиндексированные картинки и история задач).
    Сами картинки на диске не трогаются; загруженные через сайт файлы и миниатюры остаются.
#>
param([switch]$WipeData)

. "$PSScriptRoot\common.ps1"

$pidFile = Join-Path $script:RunDir 'pids.txt'
if (Test-Path $pidFile) {
    foreach ($id in Get-Content $pidFile) {
        if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
            # /T убивает и дочерние процессы (uv -> python -> индексатор).
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
    $uv = Get-Uv
    Push-Location $script:Backend
    try {
        $db = (& $uv run python -c "import sys; sys.path.insert(0, 'src'); from utils.config import DATABASE_PATH; print(DATABASE_PATH)").Trim()
    }
    finally {
        Pop-Location
    }
    foreach ($f in @($db, "$db-wal", "$db-shm")) {
        if (Test-Path $f) { Remove-Item $f -Force; Write-Host "Удалён $f" }
    }
}
