#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PythonPath,
    [string]$InstallRoot = "$env:ProgramData\EInfra-OpenWebUI"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

function Resolve-TestPython {
    param([string]$Requested)
    if (-not [string]::IsNullOrWhiteSpace($Requested)) {
        return (Resolve-Path -LiteralPath $Requested -ErrorAction Stop).Path
    }
    foreach ($candidate in @('py.exe','python.exe','python3.exe','python3','python')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $command) { return $command.Source }
    }
    throw 'Python 3.11 nebo novejsi nebyl nalezen. Pouzijte -PythonPath.'
}

$scripts = @(
    (Join-Path $root 'install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1'),
    (Join-Path $root 'recover-vut-ai-tutor-einfra-backend-v2.1.5.ps1'),
    (Join-Path $root 'collect-vut-ai-tutor-einfra-diagnostics-v2.1.5.ps1'),
    (Join-Path $root 'verify-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1'),
    (Join-Path $root 'test-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1'),
    (Join-Path $root 'engine\install-vut-ai-tutor-universal-v2.0.2.ps1'),
    (Join-Path $root 'engine\verify-vut-ai-tutor-universal-v2.0.2.ps1')
)
foreach ($path in $scripts) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Chybi soubor: {0}' -f $path) }
    $tokens = $null; $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)
    if (@($errors).Count -gt 0) {
        $details = @($errors | ForEach-Object { $_.Message }) -join '; '
        throw ('PowerShell parser odmitl soubor {0}: {1}' -f $path,$details)
    }
    $command = Get-Command -Name $path -ErrorAction Stop
    if ($null -eq $command -or $command.Parameters.Keys -notcontains 'Debug') {
        throw ('Skript {0} nema korektni CmdletBinding metadata/common parametr Debug.' -f $path)
    }
    Write-Host ('[PASS] PowerShell parser a metadata: {0}' -f (Split-Path $path -Leaf))
}

$expected = @{
    'runtime\vut_ai_tutor_bootstrap_v1.26.2_server_desktop_windows_mock_transport_complete.py' = '0110a99c6736301c66122121f7da67c8271bb71db7e81b3cc6c5bcae97521892'
    'runtime\vut_ai_tutor_pipe_v1.26.2_server_desktop_windows_mock_transport_complete.py' = 'd7809efd8b046bd6dd4f127aaf8500c0568d783b6c1befe51b3ac3dc5167a76e'
    'engine\vut_ai_tutor_universal_installer_v2.0.2.py' = 'dbc9cde8c5f4f3830c15861c5ca111e50c82a48539e9209d4bcd6beb9578d4cc'
    'engine\install-vut-ai-tutor-universal-v2.0.2.ps1' = '6531e22d4163f4c7e448aa2d97ae04b5ba7f7d5a4c62fa366a11fe68d93f903f'
}
foreach ($relative in $expected.Keys) {
    $path = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Chybi soubor: {0}' -f $path) }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected[$relative]) { throw ('SHA-256 nesouhlasi pro {0}: {1}' -f $relative,$actual) }
    Write-Host ('[PASS] SHA-256: {0}' -f $relative)
}

$installerSourcePath = Join-Path $root 'install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1'
$installerSource = Get-Content -LiteralPath $installerSourcePath -Raw -Encoding UTF8
$requiredRecoverySymbols = @(
    'Stop-EInfraBackendCompletely',
    'Stop-EInfraBackendProcesses',
    'Wait-BackendPortReleased',
    'Wait-EInfraBackendTaskQuiescent',
    'Get-ScheduledTaskInfo',
    'LastTaskResultHex',
    'Save-BackendFailureDiagnostics',
    'Invoke-OfflineTutorFunctionDeactivation',
    'Test-RestartUsefulAfterEngineFailure',
    'BackendRecovery'
)
foreach ($symbol in $requiredRecoverySymbols) {
    if ($installerSource -notmatch [regex]::Escape($symbol)) { throw ('Instalator neobsahuje povinnou recovery logiku: {0}' -f $symbol) }
}
$stopFunction = [regex]::Match($installerSource,'(?s)function Stop-EInfraBackendCompletely\s*\{.*?\n\}')
if (-not $stopFunction.Success) { throw 'Nelze izolovat Stop-EInfraBackendCompletely.' }
$stopText = $stopFunction.Value
$order = @(
    $stopText.IndexOf('Stop-ScheduledTask'),
    $stopText.IndexOf('Stop-EInfraBackendProcesses'),
    $stopText.IndexOf('Wait-BackendPortReleased'),
    $stopText.IndexOf('Wait-EInfraBackendTaskQuiescent')
)
if ($order -contains -1 -or $order[0] -ge $order[1] -or $order[1] -ge $order[2] -or $order[2] -ge $order[3]) {
    throw 'Stop sekvence neni task -> procesy -> port -> klidovy stav tasku.'
}
Write-Host '[PASS] Adapter obsahuje uplny stop procesu, uvolneni portu, klidovy stav tasku, fail-fast diagnostiku a selektivni SQLite recovery.'

$python = Resolve-TestPython -Requested $PythonPath
$pythonProbePath = Join-Path $root 'tests\python-host-probe-v2.1.5.py'
if (-not (Test-Path -LiteralPath $pythonProbePath -PathType Leaf)) {
    throw ('Chybi Python host probe: {0}' -f $pythonProbePath)
}
$pythonProbeOutput = @(& $python $pythonProbePath)
$pythonProbeExitCode = $LASTEXITCODE
if ($pythonProbeExitCode -ne 0) {
    throw ('Testovaci Python nelze spustit nebo je prilis stary; probe skoncil kodem {0}.' -f $pythonProbeExitCode)
}
try {
    $pythonProbe = (($pythonProbeOutput -join "`n") | ConvertFrom-Json -ErrorAction Stop)
}
catch {
    throw ('Python host probe nevratil platny JSON: {0}' -f ($pythonProbeOutput -join ' '))
}
if (-not [bool]$pythonProbe.ok) {
    throw ('Python host probe oznamil neuspech: {0}' -f ($pythonProbeOutput -join ' '))
}
$pythonVersion = [string]$pythonProbe.version
Write-Host ('[INFO] Testovaci Python: {0} ({1})' -f $python,$pythonVersion)

$tests = @(
    @{ Label='package static contract'; Path=(Join-Path $root 'tests\test-package-static-v2.1.5.py'); Arguments=@() },
    @{ Label='PowerShell/Python invocation contract'; Path=(Join-Path $root 'tests\test-powershell-python-invocation-contract-v2.1.5.py'); Arguments=@() },
    @{ Label='adapter Python helper execution'; Path=(Join-Path $root 'tests\test-adapter-python-helpers-v2.1.5.py'); Arguments=@() },
    @{ Label='PowerShell here-string contract'; Path=(Join-Path $root 'tests\test-powershell-here-string-contract-v2.1.5.py'); Arguments=@() },
    @{ Label='PowerShell lexical balance'; Path=(Join-Path $root 'tests\test-powershell-lexical-balance-v2.1.5.py'); Arguments=@() },
    @{ Label='adapter recovery contract'; Path=(Join-Path $root 'tests\test-adapter-recovery-contract-v2.1.5.py'); Arguments=@() },
    @{ Label='backend log segmentation contract'; Path=(Join-Path $root 'tests\test-log-segmentation-contract-v2.1.5.py'); Arguments=@() },
    @{ Label='Task Scheduler null timestamp contract'; Path=(Join-Path $root 'tests\test-task-diagnostic-null-contract-v2.1.5.py'); Arguments=@() },
    @{ Label='runtime health contract'; Path=(Join-Path $root 'tests\test-runtime-health-contract-v2.0.2.py'); Arguments=@('--engine',(Join-Path $root 'engine\vut_ai_tutor_universal_installer_v2.0.2.py'),'--bootstrap',(Join-Path $root 'runtime\vut_ai_tutor_bootstrap_v1.26.2_server_desktop_windows_mock_transport_complete.py'),'--pipe',(Join-Path $root 'runtime\vut_ai_tutor_pipe_v1.26.2_server_desktop_windows_mock_transport_complete.py')) }
)
foreach ($entry in $tests) {
    $testPath = [string]$entry.Path
    $testArguments = [string[]]@($entry.Arguments)
    & $python $testPath @testArguments
    if ($LASTEXITCODE -ne 0) { throw ('Test {0} skoncil kodem {1}.' -f $entry.Label,$LASTEXITCODE) }
    Write-Host ('[PASS] {0}' -f $entry.Label)
}

# Main SelfTest runs before runtime.json/task access, therefore it never changes the
# real server. It verifies the embedded engine, process ownership and a synthetic
# SQLite selective-deactivation transaction.
$installer = Join-Path $root 'install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1'
$selfTestReport = Join-Path $env:TEMP ('vut-einfra-selftest-' + [Guid]::NewGuid().ToString('N') + '.json')
$arguments = @('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$installer,'-Action','SelfTest','-ReportPath',$selfTestReport,'-PythonPath',$python)
& powershell.exe @arguments
if ($LASTEXITCODE -ne 0) { throw ('Self-test skoncil kodem {0}.' -f $LASTEXITCODE) }
Write-Host '[PASS] Kompletni offline test e-INFRA balicku 2.1.5 prosel bez restartu produkcni ulohy.'

$runtimeConfig = Join-Path ([IO.Path]::GetFullPath($InstallRoot)) 'config\runtime.json'
if (Test-Path -LiteralPath $runtimeConfig -PathType Leaf) {
    $config = Get-Content -LiteralPath $runtimeConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    Write-Host ('[INFO] Nalezena produkcni konfigurace pouze pro read-only informaci: {0}' -f $runtimeConfig)
    if ($config.PSObject.Properties.Name -contains 'BackendPort') { Write-Host ('[INFO] Konfigurovany backendovy port: {0}' -f $config.BackendPort) }
}
