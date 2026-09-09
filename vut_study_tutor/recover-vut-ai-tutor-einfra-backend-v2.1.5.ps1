#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:ProgramData\EInfra-OpenWebUI",
    [string]$RuntimeConfigPath,
    [string]$PythonPath,
    [double]$StartupTimeout = 300,
    [ValidateSet('Disabled','Auto','Required')]
    [string]$TutorStartupRecovery = 'Auto',
    [ValidateRange(3,120)]
    [int]$CrashGraceSeconds = 12,
    [ValidateRange(20,500)]
    [int]$DiagnosticTailLines = 120,
    [string]$ReportPath = '.\vut-ai-tutor-einfra-backend-recovery.json',
    [switch]$KeepPayloadDirectory
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1'
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw ('Chybi kompletni instalacni skript: {0}' -f $installer)
}
$arguments = @(
    '-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$installer,
    '-Action','BackendRecovery',
    '-InstallRoot',$InstallRoot,
    '-StartupTimeout',[string]$StartupTimeout,
    '-TutorStartupRecovery',$TutorStartupRecovery,
    '-CrashGraceSeconds',[string]$CrashGraceSeconds,
    '-DiagnosticTailLines',[string]$DiagnosticTailLines,
    '-ReportPath',$ReportPath
)
if (-not [string]::IsNullOrWhiteSpace($RuntimeConfigPath)) { $arguments += @('-RuntimeConfigPath',$RuntimeConfigPath) }
if (-not [string]::IsNullOrWhiteSpace($PythonPath)) { $arguments += @('-PythonPath',$PythonPath) }
if ($KeepPayloadDirectory) { $arguments += '-KeepPayloadDirectory' }
if ($PSBoundParameters.ContainsKey('Debug') -and [bool]$PSBoundParameters['Debug']) { $arguments += '-Debug' }

& powershell.exe @arguments
exit $LASTEXITCODE
