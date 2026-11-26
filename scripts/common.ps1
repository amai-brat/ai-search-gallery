# Общие функции для scripts\*.ps1 (подключается через dot-sourcing).
# Continue, а не Stop: в Windows PowerShell 5.1 любая строка в stderr нативной команды
# (uv, npm) иначе превращается в ошибку. Коды возврата проверяем явно.
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

function Ensure-EnvFile {
    $envFile = Join-Path $script:Backend '.env'
    if (-not (Test-Path $envFile)) {
        Copy-Item (Join-Path $script:Backend '.env.example') $envFile
        Write-Host "Создан $envFile из .env.example"
    }
}

function Build-Frontend {
    <# npm install (если нужно) и npm run build: собранный сайт раздаёт само приложение. #>
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        Write-Host 'Node.js не найден: сайт не собран (https://nodejs.org). API работает и без него: /docs.' -ForegroundColor Yellow
        return
    }
    Push-Location $script:Frontend
    try {
        if (-not (Test-Path 'node_modules')) {
            Write-Host 'Устанавливаю зависимости сайта (npm install) ...'
            & npm.cmd install --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw 'npm install завершился с ошибкой.' }
        }
        Write-Host 'Собираю сайт (npm run build) ...'
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'npm run build завершился с ошибкой.' }
    }
    finally {
        Pop-Location
    }
}
