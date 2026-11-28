param(
    [string]$Python = '',
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$Open,
    [switch]$ReportApi
)
$ErrorActionPreference = 'Stop'
if (-not $Python) {
    $Python = Join-Path $PSScriptRoot '.venv-run\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        $Python = 'E:\Environments\Python\pytorch\Scripts\python.exe'
    }
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python environment missing: $Python. Create .venv-run or pass -Python with a valid python.exe path. See docs/PC_MIGRATION.md"
}
$Python = (Resolve-Path -LiteralPath $Python).Path

function Set-ReportApi {
    Write-Host 'Report explanation API'
    Write-Host '1. DeepSeek'
    Write-Host '2. OpenAI-compatible API'
    Write-Host '3. Local template'
    $choice = Read-Host 'Choose 1, 2 or 3 [3]'
    if ($choice -in '', '3') {
        $env:ECG_EXPLANATION_PROVIDER = 'template'
        return
    }

    if ($choice -eq '1') {
        $provider = 'deepseek'
        $endpoint = 'https://api.deepseek.com'
        $model = Read-Host 'Model [deepseek-chat]'
        if (-not $model.Trim()) { $model = 'deepseek-chat' }
        $keyName = 'DEEPSEEK_API_KEY'
    } elseif ($choice -eq '2') {
        $provider = 'openai_compatible'
        $endpoint = (Read-Host 'API base URL (include /v1 if required)').Trim().TrimEnd('/')
        $url = $null
        if (-not [Uri]::TryCreate($endpoint, [UriKind]::Absolute, [ref]$url) -or
            ($url.Scheme -ne 'https' -and -not ($url.Scheme -eq 'http' -and $url.IsLoopback)) -or
            $url.UserInfo -or $url.Query -or $url.Fragment) {
            throw 'Enter an HTTPS API base URL or an HTTP loopback URL for a local model.'
        }
        if ($endpoint.EndsWith('/chat/completions')) {
            $endpoint = $endpoint.Substring(0, $endpoint.Length - '/chat/completions'.Length)
        }
        $model = (Read-Host 'Model ID').Trim()
        if (-not $model) { throw 'Model ID is required.' }
        $keyName = 'ECG_LLM_API_KEY'
    } else {
        throw 'Choose 1, 2 or 3.'
    }

    $secret = Read-Host 'API key (hidden, Enter keeps an existing key)' -AsSecureString
    try {
        if ($secret.Length) {
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
            try {
                [Environment]::SetEnvironmentVariable($keyName, [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer))
            } finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
            }
        }
    } finally {
        $secret.Dispose()
    }
    $env:ECG_LLM_ENDPOINT = $endpoint
    $env:ECG_LLM_MODEL = $model.Trim()
    $env:ECG_EXPLANATION_PROVIDER = $provider
}

# A second launcher in this checkout could recover tasks owned by the first one.
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $rootBytes = [Text.Encoding]::UTF8.GetBytes($PSScriptRoot.ToUpperInvariant())
    $checkoutId = [BitConverter]::ToString($sha256.ComputeHash($rootBytes)).Replace('-', '')
} finally {
    $sha256.Dispose()
}
$launcher = [Threading.Mutex]::new($false, "Local\ECG-PC-$checkoutId")
try {
    try {
        $acquired = $launcher.WaitOne(0)
    } catch [Threading.AbandonedMutexException] {
        $acquired = $true
    }
    if (-not $acquired) {
        throw 'This checkout is already running. Use the URL shown in the original launch window.'
    }

    Push-Location $PSScriptRoot
    try {
        $launchArgs = @('run_pc.py', '--port', $Port)
        if ($Open) {
            Push-Location 'frontend'
            try {
                if (-not (Test-Path -LiteralPath 'node_modules/.bin/vite.cmd' -PathType Leaf)) {
                    & npm.cmd ci
                    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
                }
                & npm.cmd run build
                if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
            } finally {
                Pop-Location
            }
            $launchArgs += '--open'
        }
        if ($ReportApi) {
            $reportVariables = 'ECG_EXPLANATION_PROVIDER', 'ECG_LLM_ENDPOINT', 'ECG_LLM_MODEL',
                'DEEPSEEK_API_KEY', 'ECG_LLM_API_KEY'
            $previousValues = @{}
            foreach ($name in $reportVariables) {
                $previousValues[$name] = [Environment]::GetEnvironmentVariable($name)
            }
        }
        try {
            if ($ReportApi) { Set-ReportApi }
            & $Python @launchArgs
            exit $LASTEXITCODE
        } finally {
            if ($ReportApi) {
                foreach ($name in $reportVariables) {
                    [Environment]::SetEnvironmentVariable($name, $previousValues[$name])
                }
            }
        }
    } finally {
        Pop-Location
        $launcher.ReleaseMutex()
    }
} finally {
    $launcher.Dispose()
}
