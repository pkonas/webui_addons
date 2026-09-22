#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:ProgramData\EInfra-OpenWebUI",
    [string]$RuntimeConfigPath,
    [ValidateRange(20,1000)]
    [int]$TailLines = 200,
    [string]$OutputPath = '.\vut-ai-tutor-einfra-diagnostics.json'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-AbsolutePath {
    param([Parameter(Mandatory=$true)][string]$Path)
    $candidate = if ([IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path (Get-Location) $Path }
    return [IO.Path]::GetFullPath($candidate)
}

function ConvertTo-TaskResultHex {
    param([AllowNull()]$Value)
    if ($null -eq $Value) { return '' }
    $signed = [int64]$Value
    $unsigned = $signed % 4294967296
    if ($unsigned -lt 0) { $unsigned += 4294967296 }
    return ('0x{0:X8}' -f [uint64]$unsigned)
}

function Get-PropertyValue {
    param($Object,[string[]]$Names,$DefaultValue=$null)
    if ($null -eq $Object) { return $DefaultValue }
    foreach ($name in $Names) {
        foreach ($property in @($Object.PSObject.Properties)) {
            if ([string]::Equals([string]$property.Name,$name,[StringComparison]::OrdinalIgnoreCase)) { return $property.Value }
        }
    }
    return $DefaultValue
}

function ConvertTo-NullableTaskResult {
    param([AllowNull()]$Value)
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) { return $null }
    try { return [int64]$Value } catch { return $null }
}

function ConvertTo-TaskDateTimeText {
    param([AllowNull()]$Value)
    if ($null -eq $Value) { return '' }
    try {
        if ($Value -is [DateTimeOffset]) {
            $dateTimeOffset = [DateTimeOffset]$Value
            if ($dateTimeOffset -eq [DateTimeOffset]::MinValue) { return '' }
            return $dateTimeOffset.ToString('o',[Globalization.CultureInfo]::InvariantCulture)
        }
        $dateTime = [DateTime]$Value
        if ($dateTime -eq [DateTime]::MinValue) { return '' }
        return $dateTime.ToString('o',[Globalization.CultureInfo]::InvariantCulture)
    }
    catch {
        $text = [string]$Value
        if ([string]::IsNullOrWhiteSpace($text)) { return '' }
        return $text
    }
}

function Get-TaskSnapshot {
    param([Parameter(Mandatory=$true)][string]$TaskName)
    $task = $null
    $info = $null
    $taskQueryError = ''
    $taskInfoQueryError = ''
    try { $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop }
    catch { $taskQueryError = $_.Exception.Message }
    try { $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction Stop }
    catch { $taskInfoQueryError = $_.Exception.Message }

    $result = ConvertTo-NullableTaskResult -Value (Get-PropertyValue -Object $info -Names @('LastTaskResult') -DefaultValue $null)
    $lastRun = ConvertTo-TaskDateTimeText -Value (Get-PropertyValue -Object $info -Names @('LastRunTime') -DefaultValue $null)
    $nextRun = ConvertTo-TaskDateTimeText -Value (Get-PropertyValue -Object $info -Names @('NextRunTime') -DefaultValue $null)
    $missedRuns = 0
    $missedRaw = Get-PropertyValue -Object $info -Names @('NumberOfMissedRuns') -DefaultValue $null
    if ($null -ne $missedRaw -and -not [string]::IsNullOrWhiteSpace([string]$missedRaw)) {
        try { $missedRuns = [int]$missedRaw } catch { $missedRuns = 0 }
    }
    $actions = @()
    if ($null -ne $task) {
        $actions = @(Get-PropertyValue -Object $task -Names @('Actions') -DefaultValue @() | ForEach-Object {
            if ($null -ne $_) {
                [pscustomobject][ordered]@{
                    Execute=[string](Get-PropertyValue -Object $_ -Names @('Execute') -DefaultValue '')
                    Arguments=[string](Get-PropertyValue -Object $_ -Names @('Arguments') -DefaultValue '')
                    WorkingDirectory=[string](Get-PropertyValue -Object $_ -Names @('WorkingDirectory') -DefaultValue '')
                }
            }
        })
    }
    $state = if ($null -ne $task) { [string](Get-PropertyValue -Object $task -Names @('State') -DefaultValue 'Unknown') } elseif (-not [string]::IsNullOrWhiteSpace($taskQueryError)) { 'Unavailable' } else { 'Missing' }
    return [pscustomobject][ordered]@{
        Name = $TaskName
        Exists = $null -ne $task
        State = $state
        LastTaskResult = $result
        LastTaskResultHex = ConvertTo-TaskResultHex -Value $result
        LastRunTime = $lastRun
        NextRunTime = $nextRun
        NumberOfMissedRuns = $missedRuns
        TaskQueryError = $taskQueryError
        TaskInfoQueryError = $taskInfoQueryError
        Actions = $actions
    }
}

$root = [IO.Path]::GetFullPath($InstallRoot)
$configPath = if ([string]::IsNullOrWhiteSpace($RuntimeConfigPath)) { Join-Path $root 'config\runtime.json' } else { Resolve-AbsolutePath -Path $RuntimeConfigPath }
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw ('Runtime konfigurace nebyla nalezena: {0}' -f $configPath) }
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$backendPort = [int](Get-PropertyValue -Object $config -Names @('BackendPort','backend_port') -DefaultValue 18080)
$logDirectory = [string](Get-PropertyValue -Object $config -Names @('LogDirectory','log_directory') -DefaultValue (Join-Path $root 'logs'))
$publicUrl = [string](Get-PropertyValue -Object $config -Names @('PrimaryUrl','PublicUrl','public_url') -DefaultValue '')
$backendLog = Join-Path $logDirectory 'open-webui.log'

$portOwners = @()
try {
    $portOwners = @(Get-NetTCPConnection -State Listen -LocalPort $backendPort -ErrorAction Stop | ForEach-Object {
        $process = Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId={0}' -f $_.OwningProcess) -ErrorAction SilentlyContinue
        [pscustomobject][ordered]@{
            ProcessId=[int]$_.OwningProcess
            LocalAddress=[string]$_.LocalAddress
            Name=if ($null -ne $process) { [string]$process.Name } else { '' }
            ExecutablePath=if ($null -ne $process) { [string]$process.ExecutablePath } else { '' }
            CommandLine=if ($null -ne $process) { [string]$process.CommandLine } else { '' }
        }
    })
}
catch { }

$managedProcesses = @()
try {
    $rootPrefix = $root.TrimEnd('\').ToLowerInvariant() + '\'
    $managedProcesses = @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop | Where-Object {
        $path = ([string]$_.ExecutablePath).ToLowerInvariant()
        $command = ([string]$_.CommandLine).ToLowerInvariant()
        $path.StartsWith($rootPrefix) -or $command.Contains($rootPrefix)
    } | ForEach-Object {
        [pscustomobject][ordered]@{ ProcessId=[int]$_.ProcessId; ParentProcessId=[int]$_.ParentProcessId; Name=[string]$_.Name; ExecutablePath=[string]$_.ExecutablePath; CommandLine=[string]$_.CommandLine }
    })
}
catch { }

$apiProbe = [pscustomobject][ordered]@{ Url=('http://127.0.0.1:{0}/api/version' -f $backendPort); Ok=$false; Version=''; Error='' }
try {
    $response = Invoke-RestMethod -UseBasicParsing -Uri $apiProbe.Url -Method Get -TimeoutSec 10
    $apiProbe.Ok = $null -ne $response -and $response.PSObject.Properties.Name -contains 'version'
    if ($apiProbe.Ok) { $apiProbe.Version = [string]$response.version }
}
catch { $apiProbe.Error = $_.Exception.Message }

$report = [pscustomobject][ordered]@{
    TimestampUtc = [DateTimeOffset]::UtcNow.ToString('o')
    AdapterDiagnosticVersion = '2.1.8'
    InstallRoot = $root
    RuntimeConfigPath = $configPath
    InternalUrl = ('http://127.0.0.1:{0}' -f $backendPort)
    PublicUrl = $publicUrl
    ApiVersionProbe = $apiProbe
    BackendTask = Get-TaskSnapshot -TaskName 'e-INFRA Open WebUI Backend'
    ProxyTask = Get-TaskSnapshot -TaskName 'e-INFRA Open WebUI HTTPS'
    PortOwners = $portOwners
    ManagedProcesses = $managedProcesses
    BackendLogPath = $backendLog
    BackendLogTail = if (Test-Path -LiteralPath $backendLog -PathType Leaf) { @(Get-Content -LiteralPath $backendLog -Tail $TailLines -ErrorAction SilentlyContinue) } else { @() }
}

$output = Resolve-AbsolutePath -Path $OutputPath
$parent = Split-Path -Parent $output
if (-not [string]::IsNullOrWhiteSpace($parent)) { [IO.Directory]::CreateDirectory($parent) | Out-Null }
$json = $report | ConvertTo-Json -Depth 12
[IO.File]::WriteAllText($output,$json + "`r`n",(New-Object Text.UTF8Encoding($false)))
Write-Host ('[PASS] Read-only diagnostika byla ulozena do {0}' -f $output)
