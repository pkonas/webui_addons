#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Auto','Desktop','EInfraWindows','Docker','BareMetal','Remote')][string]$Platform='Auto',
    [string]$BaseUrl='', [string]$TokenFile='', [switch]$PromptForCredential, [string]$Email='', [string]$PasswordFile='',
    [string]$CaCertificate='', [switch]$InsecureTls, [double]$RequestTimeout=15, [int]$StartupTimeout=300, [int]$RouteTimeout=180,
    [string]$ReportPath='.\vut-ai-tutor-universal-verify.json', [string]$PythonPath='',
    [string]$DesktopInstallRoot='', [string]$DesktopDataRoot='', [string]$DesktopConfigRoot='', [string]$DesktopExecutable='',
    [switch]$NoAutoStartDesktop, [switch]$KeepPayloadDirectory,
    [string]$InstallRoot="$env:ProgramData\EInfra-OpenWebUI", [string]$RuntimeConfigPath='',
    [ValidateSet('Skip','BestEffort','Required')][string]$PublicVerification='BestEffort',
    [ValidateSet('Auto','Docker','Podman')][string]$ContainerEngine='Auto', [string]$ContainerName='', [string]$ServiceName='', [string]$RestartCommand='',
    [switch]$NoAutoPrompt
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$installer=Join-Path $PSScriptRoot 'install-vut-ai-tutor-universal-v2.3.4.ps1'
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw ('Chybí univerzální instalátor: {0}' -f $installer) }

# Execute the sibling dispatcher in a new PowerShell process.  The user has
# already chosen to run this verified wrapper; using Bypass only for the exact
# sibling file avoids a second Mark-of-the-Web prompt without changing the
# machine execution policy or unblocking unrelated files.
$shell = if (Test-Path -LiteralPath (Join-Path $PSHOME 'powershell.exe')) {
    Join-Path $PSHOME 'powershell.exe'
} elseif (Test-Path -LiteralPath (Join-Path $PSHOME 'pwsh.exe')) {
    Join-Path $PSHOME 'pwsh.exe'
} else {
    $candidate = Get-Command powershell.exe,pwsh.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $candidate) { throw 'Nebyl nalezen powershell.exe ani pwsh.exe.' }
    $candidate.Source
}

$arguments = New-Object Collections.Generic.List[string]
foreach ($item in @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$installer,'-Action','Verify')) { [void]$arguments.Add([string]$item) }
foreach ($entry in $PSBoundParameters.GetEnumerator()) {
    if ($entry.Key -in @('Debug','Verbose','ErrorAction','WarningAction','InformationAction')) { continue }
    $name = '-' + [string]$entry.Key
    $value = $entry.Value
    if ($value -is [Management.Automation.SwitchParameter]) {
        if ([bool]$value) { [void]$arguments.Add($name) }
    } else {
        [void]$arguments.Add($name)
        [void]$arguments.Add([string]$value)
    }
}
if ($PSBoundParameters.ContainsKey('Debug') -and [bool]$PSBoundParameters['Debug']) { [void]$arguments.Add('-Debug') }
& $shell @($arguments.ToArray())
exit [int]$LASTEXITCODE
