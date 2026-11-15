param(
    [string]$Python = 'E:\Environments\Python\pytorch\Scripts\python.exe',
    [int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python environment missing: $Python. See docs/PC_MIGRATION.md"
}
Push-Location $PSScriptRoot
try {
    & $Python run_pc.py --port $Port
} finally {
    Pop-Location
}
