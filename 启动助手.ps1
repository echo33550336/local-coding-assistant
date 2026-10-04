$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
Set-Location -LiteralPath $projectDir

$pythonCandidates = @()
if ($env:LOCALAPPDATA) {
    $pythonCandidates += @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe')
    )
}
$pythonCandidates += @(
    (Join-Path $projectDir '.runtime\python\python.exe'),
    'C:\Users\LENOVO\AppData\Local\Programs\Python\Python314\python.exe'
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $python) {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & $pyLauncher.Source -3 --version 2>$null
        if ($LASTEXITCODE -eq 0) { $python = $pyLauncher.Source }
    }
}

if (-not $python) {
    throw '找不到 Python 3.10 或更新版本。请先安装 Python，再重新运行本脚本。'
}

$depsDir = Join-Path $projectDir '.deps'
$tempDir = Join-Path $projectDir '.tmp'
if (-not (Test-Path -LiteralPath (Join-Path $depsDir 'fastapi\__init__.py'))) {
    New-Item -ItemType Directory -Force -Path $depsDir,$tempDir | Out-Null
    $env:TEMP = $tempDir
    $env:TMP = $tempDir
    $env:PIP_CACHE_DIR = Join-Path $tempDir 'pip-cache'
    & $python -m pip install --target $depsDir -r (Join-Path $projectDir 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败。' }
}

$env:PYTHONPATH = $depsDir
if (-not $env:OPENAI_API_KEY) {
    Write-Warning 'OPENAI_API_KEY 尚未设置；页面可打开，但发送 AI 请求前需要配置密钥并重新启动。'
}
Write-Host '助手已启动： http://127.0.0.1:8765' -ForegroundColor Green
Start-Process 'http://127.0.0.1:8765/?build=20261003-2'
& $python -m uvicorn app:app --host 127.0.0.1 --port 8765
