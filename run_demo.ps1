param(
    [string]$PythonExecutable,
    [ValidateRange(1024,65535)][int]$Port=8765,
    [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$demoPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) {
    # Use an already installed interpreter. Never install Python or change
    # execution policy, ACLs, UAC, registry or pip bootstrap after a failure.
    if ($PythonExecutable) {
        if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) { throw '指定されたPython実行ファイルがありません。' }
        & $PythonExecutable -I -c "import sys; raise SystemExit(sys.version_info[:2] != (3,12))"
        if ($LASTEXITCODE -ne 0) { throw '既存のPython 3.12を指定してください。新規インストールは自動実行しません。' }
        & $PythonExecutable -I -m venv .venv
    } else {
        if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Python 3.12が必要です。既存の実行ファイルは -PythonExecutable で指定できます。' }
        & py -3.12 -I -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) { throw 'venv/ensurepipの準備に失敗しました。権限や実行環境を確認してください。別のブートストラップや権限変更は自動実行しません。' }
}
# Recover from an interrupted first install instead of treating an existing
# but incomplete virtual environment as ready.
& $demoPython -I -c "import importlib.metadata as m,tomllib; p=tomllib.load(open('pyproject.toml','rb')); v=next((d.version for d in m.distributions(name=p['project']['name'])),None); raise SystemExit(v != p['project']['version'])"
$demoNeedsInstall = $LASTEXITCODE -ne 0
if (-not $demoNeedsInstall) {
    & $demoPython -I -m pip check | Out-Null
    $demoNeedsInstall = $LASTEXITCODE -ne 0
}
if ($demoNeedsInstall) {
    & $demoPython -I -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw '依存パッケージを準備できませんでした。' }
}
if ($PrepareOnly) { Write-Output '準備完了（アプリは起動していません）。'; return }
$env:RAG_DATA_DIR = Join-Path $PSScriptRoot 'data/demo'
$env:RAG_LLM_PROVIDER = 'extractive'
& $demoPython -I -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port $Port --server.headless true --browser.gatherUsageStats false
