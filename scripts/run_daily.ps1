# Daily batch run for Windows Task Scheduler (the Windows equivalent of cron).
# Register it (one time) with:
#   schtasks /Create /TN "OlistETL" /SC DAILY /ST 02:00 /TR "powershell -ExecutionPolicy Bypass -File <full path>\scripts\run_daily.ps1"
# Linux cron equivalent:   0 2 * * *  cd /path/to/repo && python -m sc_etl.pipeline >> logs/cron.log 2>&1
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$env:Path = "$env:USERPROFILE\miniconda3\envs\de;$env:USERPROFILE\miniconda3\envs\de\Library\bin;$env:Path"
Set-Location $repo

python scripts\setup_local_postgres.py --start-only
python -m sc_etl.pipeline --source-dir data\source
if ($LASTEXITCODE -ne 0) {
    Write-Error "ETL pipeline failed - see logs\pipeline.log"
    exit $LASTEXITCODE
}
python scripts\run_analytics.py
