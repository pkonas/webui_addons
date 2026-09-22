#requires -Version 5.1
[CmdletBinding()]
param([string]$PythonPath = '', [switch]$IncludePdfTests)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python {
    if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
        $full=[IO.Path]::GetFullPath($PythonPath)
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { throw ('Python nebyl nalezen: {0}' -f $full) }
        return $full
    }
    foreach ($name in @('python.exe','python','python3.exe','python3','py.exe','py')) {
        $command=Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) { return $command.Source }
    }
    throw 'Python nebyl nalezen; zadejte -PythonPath.'
}
function Invoke-PythonTest([string]$Path) {
    $python=Find-Python
    $old=$ErrorActionPreference
    try { $ErrorActionPreference='Continue'; & $python $Path; $code=[int]$LASTEXITCODE } finally { $ErrorActionPreference=$old }
    if ($code -ne 0) { throw ('Test {0} skončil kódem {1}.' -f (Split-Path -Leaf $Path),$code) }
    Write-Host ('[PASS] {0}' -f (Split-Path -Leaf $Path)) -ForegroundColor Green
}

$psFiles=@(Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.ps1')
foreach ($file in $psFiles) {
    $tokens=$null; $errors=$null
    [void][System.Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$errors)
    if (@($errors).Count -gt 0) { throw ('PowerShell parser odmítl {0}: {1}' -f $file.FullName,((@($errors)|ForEach-Object{$_.Message}) -join '; ')) }
    $command=Get-Command -Name $file.FullName
    $names=@($command.Parameters.Keys)
    if ($names.Count -ne (@($names|Sort-Object -Unique)).Count) { throw ('Duplicitní parametry v {0}' -f $file.FullName) }
    Write-Host ('[PASS] PowerShell parser a metadata: {0}' -f $file.Name) -ForegroundColor Green
}

$manifest=Get-Content -LiteralPath (Join-Path $Root 'PACKAGE-MANIFEST.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($entry in @($manifest.files)) {
    $path=Join-Path $Root ([string]$entry.path)
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Manifestový soubor chybí: {0}' -f $path) }
    $actual=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne ([string]$entry.sha256).ToLowerInvariant()) { throw ('SHA-256 nesouhlasí: {0}' -f $entry.path) }
}
Write-Host '[PASS] PACKAGE-MANIFEST SHA-256' -ForegroundColor Green

Invoke-PythonTest (Join-Path $Root 'tests\test_package_contract_v2.3.4.py')
Invoke-PythonTest (Join-Path $Root 'tests\test_powershell_lexical_v2.3.4.py')
Invoke-PythonTest (Join-Path $Root 'tests\test_platform_detection_v2.3.4.py')
Invoke-PythonTest (Join-Path $Root 'tests\test_desktop_official_lifecycle_v2.3.4.py')
Invoke-PythonTest (Join-Path $Root 'tests\test_api_platforms_e2e_v2.3.4.py')

$installer=Join-Path $Root 'install-vut-ai-tutor-universal-v2.3.4.ps1'
$selfReport=Join-Path $env:TEMP ('vut-universal-selftest-' + [Guid]::NewGuid().ToString('N') + '.json')
try {
    & $installer -Action SelfTest -PythonPath (Find-Python) -ReportPath $selfReport
    if ($LASTEXITCODE -ne 0) { throw ('Installer SelfTest skončil kódem {0}.' -f $LASTEXITCODE) }
} finally { Remove-Item -LiteralPath $selfReport -Force -ErrorAction SilentlyContinue }
Write-Host '[PASS] root installer SelfTest' -ForegroundColor Green

$temp=Join-Path $env:TEMP ('vut-detect-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -Force | Out-Null
try {
    $desktopOutput=& $installer -Action Detect -Platform Desktop -DesktopInstallRoot (Join-Path $temp 'desktop') 6>&1 | Out-String
    if ($desktopOutput -notmatch '"selected_platform"\s*:\s*"Desktop"') { throw 'Explicitní Desktop detekce selhala.' }
    $runtime=Join-Path $temp 'runtime.json'
    @{ProductId='EInfra-OpenWebUI';BackendPort=18080;PrimaryUrl='https://example.invalid'} | ConvertTo-Json | Set-Content -LiteralPath $runtime -Encoding UTF8
    $serverOutput=& $installer -Action Detect -Platform EInfraWindows -InstallRoot $temp -RuntimeConfigPath $runtime 6>&1 | Out-String
    if ($serverOutput -notmatch '"selected_platform"\s*:\s*"EInfraWindows"') { throw 'Explicitní e-INFRA detekce selhala.' }
    $remoteOutput=& $installer -Action Detect -Platform Remote -BaseUrl 'https://example.invalid/openwebui' 6>&1 | Out-String
    if ($remoteOutput -notmatch '"selected_platform"\s*:\s*"Remote"') { throw 'Explicitní Remote detekce selhala.' }
} finally { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
Write-Host '[PASS] non-mutating platform detection' -ForegroundColor Green
Invoke-PythonTest (Join-Path $Root 'tests\test_universal_pdf_integration.py')
Invoke-PythonTest (Join-Path $Root 'tests\test_pdf_installer.py')
if ($IncludePdfTests) {
    Invoke-PythonTest (Join-Path $Root 'tests\test_pdf_delivery.py')
    Invoke-PythonTest (Join-Path $Root 'tests\test_pdf_source_recovery.py')
    $node = Get-Command 'node' -ErrorAction Stop
    & $node.Source '--check' (Join-Path $Root 'docs\canvas.pdf-hotfix.js')
    if ($LASTEXITCODE -ne 0) { throw 'Canvas JavaScript syntax check failed.' }
    & $node.Source '--test' (Join-Path $Root 'tests\test_pdf_diagnostic.mjs')
    if ($LASTEXITCODE -ne 0) { throw 'PDF JavaScript diagnostic tests failed.' }
}
Write-Host '[PASS] VUT AI Tutor Universal Installer 2.3.4 Windows-safe test completed.' -ForegroundColor Green
