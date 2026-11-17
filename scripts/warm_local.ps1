<#
  Onbellek isitmasini BU bilgisayardan (Turk IP'si) calistirir.

  Neden: GitHub Actions runner'i yurt disi veri merkezi IP'si kullaniyor; N11,
  MediaMarkt, Vatan gibi Turk magazalari buradan cogu terimde sonuc vermiyor
  (120 terimin 114'unde tek magaza). Ayni betik Turk Telekom IP'sinden cok
  magazali sonuc veriyor.

  Kurulum: bkz. docs/warm_local.md. Anahtarlar repoya GIRMEZ; proje kokundeki
  .env.warm dosyasindan okunur (.gitignore'da).
#>
param(
    [int]$Limit = 400,
    [int]$TtlHours = 48,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$EnvFile = Join-Path $Root ".env.warm"
if (-not (Test-Path $EnvFile)) {
    Write-Error ".env.warm bulunamadi. Icine SUPABASE_URL=... ve SUPABASE_SERVICE_KEY=... yaz (docs/warm_local.md)."
    exit 2
}
Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $i = $line.IndexOf("=")
        [Environment]::SetEnvironmentVariable($line.Substring(0, $i).Trim(), $line.Substring($i + 1).Trim().Trim('"'), "Process")
    }
}
foreach ($required in "SUPABASE_URL", "SUPABASE_SERVICE_KEY") {
    if (-not [Environment]::GetEnvironmentVariable($required, "Process")) {
        Write-Error "$required .env.warm icinde tanimli degil."
        exit 2
    }
}

# Ilk calismada proje icinde sanal ortam kurulur (sistem Python'una dokunmaz).
$Venv = Join-Path $Root ".venv-warm"
$Py = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Base = (Get-Command py -ErrorAction SilentlyContinue)
    if ($Base) { & py -3 -m venv $Venv } else { & python -m venv $Venv }
    & $Py -m pip install --quiet -r (Join-Path $Root "requirements.txt")
}

$LogDir = Join-Path $Root "app_logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Log = Join-Path $LogDir "warm_local.log"

$Args = @("scripts\warm_price_cache.py", "--limit", $Limit, "--ttl", $TtlHours)
if ($DryRun) { $Args += "--dry-run" }

"=== $(Get-Date -Format s) basladi (limit=$Limit, dry_run=$($DryRun.IsPresent)) ===" | Add-Content $Log -Encoding UTF8
$env:PYTHONIOENCODING = "utf-8"
& $Py @Args 2>&1 | Tee-Object -FilePath $Log -Append
exit $LASTEXITCODE
