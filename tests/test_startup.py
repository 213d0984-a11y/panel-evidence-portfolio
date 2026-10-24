from pathlib import Path
import tomllib

def test_default_startup_is_local_noninteractive_and_without_telemetry():
    config=tomllib.loads((Path(__file__).resolve().parents[1]/'.streamlit/config.toml').read_text(encoding='utf-8'))
    assert config['server']['address']=='127.0.0.1'
    assert config['server']['headless'] is True
    assert config['server']['fileWatcherType']=='none'
    assert config['browser']['gatherUsageStats'] is False


def test_startup_accepts_existing_python_and_stops_on_bootstrap_failure():
    root=Path(__file__).resolve().parents[1]
    script=(root/'run_demo.ps1').read_text(encoding='utf-8')
    assert '[string]$PythonExecutable' in script and '[switch]$PrepareOnly' in script
    assert '-I -m venv .venv' in script
    assert 'if ($LASTEXITCODE -ne 0)' in script
    assert 'Set-ExecutionPolicy' not in script and 'ExecutionPolicy Bypass' not in script
    assert 'ExecutionPolicy Bypass' not in (root/'README.md').read_text(encoding='utf-8')
