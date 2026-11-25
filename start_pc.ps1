param(
    [string]$Python = '',
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
if (-not $Python) {
    $Python = Join-Path $PSScriptRoot '.venv-run\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment missing: $Python. Create .venv-run or pass -Python with a valid python.exe path. See docs/PC_MIGRATION.md"
}
Push-Location $PSScriptRoot
try {
    & $Python run_pc.py --port $Port
} finally {
    Pop-Location
}
