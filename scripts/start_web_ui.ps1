$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python is not available on PATH. Install Python or activate the correct environment first.'
}

python -m streamlit run src/testcode/web_ui.py
