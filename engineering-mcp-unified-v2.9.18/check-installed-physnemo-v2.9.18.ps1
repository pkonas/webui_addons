# Engineering MCP v2.9.18: recheck existing installation; no install/update/uninstall.
[CmdletBinding()]
param(
    [string]$AppHome = "",
    [ValidateRange(1,900)][int]$ModelRequestTimeoutSeconds = 300,
    [ValidateRange(1,7200)][int]$ModelPreflightTimeoutSeconds = 1800
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
if ($ModelPreflightTimeoutSeconds -lt $ModelRequestTimeoutSeconds) {
    throw "The total model timeout must be at least the request timeout."
}
if (-not $AppHome) { $AppHome = $env:ENGINEERING_MCP_HOME }
if (-not $AppHome) { $AppHome = Join-Path $env:LOCALAPPDATA "EngineeringMCP" }
$RuntimePath = Join-Path $AppHome "logs\physnemo-runtime-health.json"
$OutputPath = Join-Path $AppHome "logs\physnemo-model-tools-recheck.json"
$Checker = Join-Path $PSScriptRoot "check-physnemo-native-tools-v2.9.18.py"
$ExpectedCheckerSha256 = "1f567a1b4ca7fc5d52a595d44564dad34023f288364d2714ef884505ac6d09ac"
if (-not (Test-Path -LiteralPath $RuntimePath -PathType Leaf)) {
    throw "Runtime report not found: $RuntimePath. Run the complete installer first."
}
if ((Get-FileHash -LiteralPath $Checker -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedCheckerSha256) {
    throw "Checker integrity verification failed. Extract the complete original ZIP."
}
$Runtime = Get-Content -LiteralPath $RuntimePath -Raw -Encoding UTF8 | ConvertFrom-Json
$Root = [string]$Runtime.linux_install_dir
$Distro = [string]$Runtime.distro
if (-not $Runtime.configured -or -not $Root.StartsWith("/") -or -not $Distro -or $Root -match "[\r\n]" -or $Distro -match "[\r\n]") {
    throw "Runtime is not configured. No changes were made."
}
$Payload = [Convert]::ToBase64String([IO.File]::ReadAllBytes($Checker))
$Launcher = "exec(__import__('base64').b64decode('$Payload'))"
Write-Host "Checking installed PhysicsNeMo tools through the existing model. No dependencies or settings will be changed."
$SavedPreference = $ErrorActionPreference
try {
    # PowerShell 5.1 can turn native stderr warnings into ErrorRecord objects.
    # Never print third-party stderr, which may contain provider payloads.
    $ErrorActionPreference = "Continue"
    $Lines = @(& wsl.exe -d $Distro --exec "$Root/.venv-nat/bin/python" -c $Launcher --root $Root --runtime-env "$Root/config/runtime.env" --request-timeout $ModelRequestTimeoutSeconds --total-timeout $ModelPreflightTimeoutSeconds 2>&1 | ForEach-Object {
        $Text = $_.ToString().Trim()
        if ($Text.StartsWith("PHYSNEMO_PREFLIGHT_PROGRESS ")) { Write-Host $Text }
        elseif ($Text.StartsWith("{")) { $Text }
    })
    $NativeExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $SavedPreference
}
$JsonLine = $Lines | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_.StartsWith("{") } | Select-Object -Last 1
if (-not $JsonLine) { throw "Checker returned no JSON report (exit $NativeExitCode). No installation was changed." }
$Report = $JsonLine | ConvertFrom-Json
[IO.File]::WriteAllText($OutputPath, ($Report | ConvertTo-Json -Depth 50), (New-Object Text.UTF8Encoding($false)))
Write-Host "Report: $OutputPath"
Write-Host "Success: $($Report.success)"
if ($Report.PSObject.Properties.Name -contains "failed_stage") { Write-Host "Stage: $($Report.failed_stage)" }
if ($Report.PSObject.Properties.Name -contains "error") { Write-Host "Error: $($Report.error)" }
if ($Report.PSObject.Properties.Name -contains "validation_error") { Write-Host "Validation: $($Report.validation_error.reason)" }
if ($Report.PSObject.Properties.Name -contains "timeout_error") {
    Write-Host "Timeout: $($Report.timeout_error.outcome)"
}
Write-Host "This is a diagnostic recheck only. It does not modify saved installation/readiness state."
if ($NativeExitCode -ne 0 -or -not $Report.success) { exit 2 }
exit 0
