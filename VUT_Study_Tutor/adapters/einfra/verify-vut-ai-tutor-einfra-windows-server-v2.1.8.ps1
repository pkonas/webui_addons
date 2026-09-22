#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:ProgramData\EInfra-OpenWebUI",
    [string]$RuntimeConfigPath,
    [string]$TokenFile,
    [switch]$PromptForCredential,
    [string]$Email,
    [string]$PasswordFile,
    [string]$CaCertificate,
    [switch]$InsecureTls,
    [double]$RequestTimeout = 15,
    [double]$StartupTimeout = 300,
    [double]$RouteTimeout = 180,
    [ValidateSet('Skip','BestEffort','Required')]
    [string]$PublicVerification = 'BestEffort',
    [string]$ReportPath = '.\vut-ai-tutor-einfra-verify.json',
    [string]$PythonPath,
    [switch]$KeepPayloadDirectory
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'install-vut-ai-tutor-einfra-windows-server-v2.1.8.ps1'
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw ('Chybi instalacni skript: {0}' -f $installer) }
$arguments = @('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$installer,'-Action','Verify','-InstallRoot',$InstallRoot,'-RequestTimeout',[string]$RequestTimeout,'-StartupTimeout',[string]$StartupTimeout,'-RouteTimeout',[string]$RouteTimeout,'-PublicVerification',$PublicVerification,'-ReportPath',$ReportPath)
if ($RuntimeConfigPath) { $arguments += @('-RuntimeConfigPath',$RuntimeConfigPath) }
if ($TokenFile) { $arguments += @('-TokenFile',$TokenFile) }
if ($PromptForCredential) { $arguments += '-PromptForCredential' }
if ($Email) { $arguments += @('-Email',$Email) }
if ($PasswordFile) { $arguments += @('-PasswordFile',$PasswordFile) }
if ($CaCertificate) { $arguments += @('-CaCertificate',$CaCertificate) }
if ($InsecureTls) { $arguments += '-InsecureTls' }
if ($PythonPath) { $arguments += @('-PythonPath',$PythonPath) }
if ($KeepPayloadDirectory) { $arguments += '-KeepPayloadDirectory' }
if ($PSBoundParameters.ContainsKey('Debug') -and [bool]$PSBoundParameters['Debug']) { $arguments += '-Debug' }
& powershell.exe @arguments
exit $LASTEXITCODE
