#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Install','Repair','Verify','Preflight','Uninstall','SelfTest','Detect','BackendRecovery','DesktopDatabaseRepair')]
    [string]$Action = 'Repair',

    [ValidateSet('Auto','Desktop','EInfraWindows','Docker','BareMetal','Remote')]
    [string]$Platform = 'Auto',

    [string]$BaseUrl = '',
    [string]$TokenFile = '',
    [switch]$PromptForCredential,
    [string]$Email = '',
    [string]$PasswordFile = '',
    [string]$CaCertificate = '',
    [switch]$InsecureTls,

    [double]$RequestTimeout = 15,
    [int]$StartupTimeout = 300,
    [int]$RouteTimeout = 180,
    [ValidateSet('Never','OnFailure','Always')]
    [string]$RestartPolicy = 'OnFailure',

    [string]$ReportPath = '.\vut-ai-tutor-universal-report.json',
    [string]$BackupDir = '',
    [string]$PythonPath = '',

    [string]$DesktopInstallRoot = '',
    [string]$DesktopDataRoot = '',
    [string]$DesktopConfigRoot = '',
    [string]$DesktopExecutable = '',
    [switch]$StopDesktopProcesses,
    [switch]$NoAutoStartDesktop,

    [string]$InstallRoot = "$env:ProgramData\EInfra-OpenWebUI",
    [string]$RuntimeConfigPath = '',
    [ValidateSet('Skip','BestEffort','Required')]
    [string]$PublicVerification = 'BestEffort',
    [ValidateSet('Disabled','Auto','Required')]
    [string]$TutorStartupRecovery = 'Auto',

    [ValidateSet('Auto','Docker','Podman')]
    [string]$ContainerEngine = 'Auto',
    [string]$ContainerName = '',
    [string]$ServiceName = '',
    [string]$RestartCommand = '',

    [switch]$NoStartBackend,
    [switch]$NoRollback,
    [switch]$KeepLegacyDisabled,
    [switch]$KeepPayloadDirectory,
    [switch]$NoAutoPrompt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$InstallerVersion = '2.3.4'
$RuntimeVersion = '1.26.5'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DiagnosticsEnabled = $PSBoundParameters.ContainsKey('Debug') -and [bool]$PSBoundParameters['Debug']
$script:RootBoundParameters = @{}
foreach ($entry in $PSBoundParameters.GetEnumerator()) { $script:RootBoundParameters[$entry.Key] = $entry.Value }

$Paths = [ordered]@{
    DesktopInstall = Join-Path $Root 'adapters\desktop\repair-install-vut-ai-tutor-v1.26.5-server-desktop-windows-mock-transport-complete.ps1'
    DesktopVerify  = Join-Path $Root 'adapters\desktop\verify-vut-ai-tutor-v1.26.5-server-desktop-windows-mock-transport-complete.ps1'
    EInfraInstall  = Join-Path $Root 'adapters\einfra\install-vut-ai-tutor-einfra-windows-server-v2.1.8.ps1'
    EInfraVerify   = Join-Path $Root 'adapters\einfra\verify-vut-ai-tutor-einfra-windows-server-v2.1.8.ps1'
    ApiEngine      = Join-Path $Root 'engine\vut_ai_tutor_universal_installer_v2.0.6.py'
    Bootstrap      = Join-Path $Root 'runtime\vut_ai_tutor_bootstrap_v1.26.5_server_desktop_windows_mock_transport_complete.py'
    Pipe           = Join-Path $Root 'runtime\vut_ai_tutor_pipe_v1.26.5_server_desktop_windows_mock_transport_complete.py'
    DispatcherPy   = Join-Path $Root 'install-vut-ai-tutor-universal-v2.3.4.py'
    Manifest       = Join-Path $Root 'PACKAGE-MANIFEST.json'
}

function Write-Info([string]$Message) { Write-Host ('[INFO] {0}' -f $Message) -ForegroundColor Cyan }
function Write-Pass([string]$Message) { Write-Host ('[PASS] {0}' -f $Message) -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Warning $Message }

function Resolve-AbsolutePath {
    param([string]$Path, [switch]$MustExist, [switch]$Directory)
    if ([string]::IsNullOrWhiteSpace($Path)) { return '' }
    $candidate = if ([IO.Path]::IsPathRooted($Path)) { $Path } else { Join-Path (Get-Location) $Path }
    $full = [IO.Path]::GetFullPath($candidate)
    if ($MustExist) {
        $pathType = if ($Directory) { 'Container' } else { 'Leaf' }
        if (-not (Test-Path -LiteralPath $full -PathType $pathType)) { throw ('Cesta nebyla nalezena: {0}' -f $full) }
    }
    return $full
}

function Get-PropertyValue {
    param([Parameter(Mandatory=$true)]$Object, [Parameter(Mandatory=$true)][string[]]$Names, $DefaultValue = $null)
    if ($null -eq $Object) { return $DefaultValue }
    foreach ($name in $Names) {
        foreach ($property in @($Object.PSObject.Properties)) {
            if ([string]::Equals([string]$property.Name, $name, [StringComparison]::OrdinalIgnoreCase)) { return $property.Value }
        }
    }
    return $DefaultValue
}

function Assert-PackageFiles {
    foreach ($entry in $Paths.GetEnumerator()) {
        if ($entry.Key -eq 'Manifest') { continue }
        if (-not (Test-Path -LiteralPath $entry.Value -PathType Leaf)) { throw ('V balíčku chybí povinný soubor {0}: {1}' -f $entry.Key,$entry.Value) }
    }
    if (-not (Test-Path -LiteralPath $Paths.Manifest -PathType Leaf)) { throw ('V balíčku chybí PACKAGE-MANIFEST.json: {0}' -f $Paths.Manifest) }
    $manifest = Get-Content -LiteralPath $Paths.Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($file in @($manifest.files)) {
        $path = Join-Path $Root ([string]$file.path)
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Manifestový soubor chybí: {0}' -f $path) }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        $expected = ([string]$file.sha256).ToLowerInvariant()
        if ($actual -ne $expected) { throw ('SHA-256 nesouhlasí pro {0}: očekáváno {1}, nalezeno {2}' -f $file.path,$expected,$actual) }
    }
}

function Find-Python {
    if (-not [string]::IsNullOrWhiteSpace($PythonPath)) {
        return Resolve-AbsolutePath -Path $PythonPath -MustExist
    }
    foreach ($name in @('python.exe','python','python3.exe','python3','py.exe','py')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($null -ne $command) { return $command.Source }
    }
    throw 'Nebyl nalezen Python. Zadejte -PythonPath.'
}

function Get-EInfraEvidence {
    $root = [IO.Path]::GetFullPath($InstallRoot)
    $configPath = if (-not [string]::IsNullOrWhiteSpace($RuntimeConfigPath)) { Resolve-AbsolutePath -Path $RuntimeConfigPath } else { Join-Path $root 'config\runtime.json' }
    $reasons = New-Object Collections.Generic.List[string]
    $detected = $false; $productId = ''; $backendPort = $null; $primaryUrl = ''
    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        try {
            $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $productId = [string](Get-PropertyValue -Object $config -Names @('ProductId','product_id') -DefaultValue '')
            $backendPort = Get-PropertyValue -Object $config -Names @('BackendPort','backend_port','port') -DefaultValue $null
            $primaryUrl = [string](Get-PropertyValue -Object $config -Names @('PrimaryUrl','PublicUrl','public_url') -DefaultValue '')
            if ([string]::IsNullOrWhiteSpace($productId) -or $productId -eq 'EInfra-OpenWebUI') {
                $detected = $true; [void]$reasons.Add(('runtime config: {0}' -f $configPath))
            } else { [void]$reasons.Add(('runtime config patří jinému produktu: {0}' -f $productId)) }
        } catch { [void]$reasons.Add(('runtime config nelze načíst: {0}' -f $_.Exception.Message)) }
    }
    return [pscustomobject][ordered]@{ Detected=[bool]$detected; InstallRoot=$root; RuntimeConfigPath=$configPath; ProductId=$productId; BackendPort=$backendPort; PrimaryUrl=$primaryUrl; Reasons=@($reasons) }
}

function Get-DesktopConfigCandidates {
    $items = New-Object Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace($DesktopConfigRoot)) { [void]$items.Add((Resolve-AbsolutePath -Path $DesktopConfigRoot)) }
    if (-not [string]::IsNullOrWhiteSpace($env:APPDATA)) {
        foreach ($name in @('Open WebUI','open-webui','OpenWebUI','open-webui-desktop','com.openwebui.desktop')) { [void]$items.Add((Join-Path $env:APPDATA $name)) }
    }
    $unique = New-Object Collections.Generic.List[string]
    foreach ($item in $items) {
        if ([string]::IsNullOrWhiteSpace($item)) { continue }
        $full = [IO.Path]::GetFullPath($item)
        if (-not $unique.Contains($full)) { [void]$unique.Add($full) }
    }
    return $unique.ToArray()
}

function Get-DesktopEvidence {
    $reasons = New-Object Collections.Generic.List[string]
    $configRoot = ''; $config = $null
    foreach ($candidate in @(Get-DesktopConfigCandidates)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) { continue }
        foreach ($name in @('config.json','settings.json')) {
            $configPath = Join-Path $candidate $name
            if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { continue }
            try { $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json; $configRoot = $candidate; [void]$reasons.Add(('Desktop config: {0}' -f $configPath)); break }
            catch { [void]$reasons.Add(('Desktop config nelze načíst: {0}' -f $_.Exception.Message)) }
        }
        if ($null -ne $config) { break }
        if ((Test-Path -LiteralPath (Join-Path $candidate 'logs\main.log') -PathType Leaf) -or (Test-Path -LiteralPath (Join-Path $candidate 'logs\server.log') -PathType Leaf)) { $configRoot = $candidate; [void]$reasons.Add(('Desktop log directory: {0}' -f $candidate)); break }
    }
    $installRootDetected = ''
    if (-not [string]::IsNullOrWhiteSpace($DesktopInstallRoot)) { $installRootDetected = Resolve-AbsolutePath -Path $DesktopInstallRoot; [void]$reasons.Add(('explicit DesktopInstallRoot: {0}' -f $installRootDetected)) }
    elseif ($null -ne $config) {
        $rawInstall = [string](Get-PropertyValue -Object $config -Names @('installDir','install_dir') -DefaultValue '')
        if (-not [string]::IsNullOrWhiteSpace($rawInstall)) { try { $installRootDetected = [IO.Path]::GetFullPath($rawInstall); [void]$reasons.Add(('Desktop installDir: {0}' -f $installRootDetected)) } catch {} }
    }
    if ([string]::IsNullOrWhiteSpace($installRootDetected)) {
        foreach ($candidate in @('D:\web-ui','C:\web-ui')) { if (Test-Path -LiteralPath $candidate -PathType Container) { $installRootDetected = $candidate; [void]$reasons.Add(('known Desktop root: {0}' -f $candidate)); break } }
    }
    $executableDetected = ''
    if (-not [string]::IsNullOrWhiteSpace($DesktopExecutable)) { $executableDetected = Resolve-AbsolutePath -Path $DesktopExecutable; [void]$reasons.Add(('explicit Desktop executable: {0}' -f $executableDetected)) }
    elseif (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        foreach ($candidate in @((Join-Path $env:LOCALAPPDATA 'Programs\open-webui\open-webui.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\open-webui\Open WebUI.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\Open WebUI\open-webui.exe'),(Join-Path $env:LOCALAPPDATA 'Programs\Open WebUI\Open WebUI.exe'))) {
            if (Test-Path -LiteralPath $candidate -PathType Leaf) { $executableDetected = $candidate; [void]$reasons.Add(('Desktop executable: {0}' -f $candidate)); break }
        }
    }
    $detected = (-not [string]::IsNullOrWhiteSpace($configRoot)) -or (-not [string]::IsNullOrWhiteSpace($installRootDetected)) -or (-not [string]::IsNullOrWhiteSpace($executableDetected))
    return [pscustomobject][ordered]@{ Detected=[bool]$detected; ConfigRoot=$configRoot; InstallRoot=$installRootDetected; Executable=$executableDetected; Reasons=@($reasons) }
}

function Test-DockerOpenWebUI {
    if (-not [string]::IsNullOrWhiteSpace($ContainerName)) { return $true }
    foreach ($engineName in @('docker.exe','docker','podman.exe','podman')) {
        $command = Get-Command $engineName -ErrorAction SilentlyContinue
        if ($null -eq $command) { continue }
        try {
            $output = & $command.Source ps -a --format '{{.Image}} {{.Names}}' 2>$null
            $code = [int]$LASTEXITCODE
            if ($code -ne 0) { $output = & $command.Source ps --format '{{.Image}} {{.Names}}' 2>$null; $code = [int]$LASTEXITCODE }
            if ($code -eq 0 -and (($output -join "`n") -match '(?i)open[-_ ]?webui')) { return $true }
        } catch {}
    }
    return $false
}

function Resolve-TargetPlatform {
    param($EInfraEvidence,$DesktopEvidence)
    if ($Platform -ne 'Auto') { return $Platform }
    $explicitDesktop = $script:RootBoundParameters.ContainsKey('DesktopInstallRoot') -or $script:RootBoundParameters.ContainsKey('DesktopConfigRoot') -or $script:RootBoundParameters.ContainsKey('DesktopExecutable')
    $explicitEInfra = $script:RootBoundParameters.ContainsKey('RuntimeConfigPath') -or $script:RootBoundParameters.ContainsKey('InstallRoot')
    if ($explicitDesktop -and $DesktopEvidence.Detected) { return 'Desktop' }
    if ($explicitEInfra -and $EInfraEvidence.Detected) { return 'EInfraWindows' }
    if (-not [string]::IsNullOrWhiteSpace($BaseUrl)) { return 'Remote' }
    if ($EInfraEvidence.Detected -and $DesktopEvidence.Detected) { throw ('Byly nalezeny současně instalace EInfraWindows a Desktop. Použijte explicitně -Platform. EInfra: {0}; Desktop: {1}' -f $EInfraEvidence.RuntimeConfigPath,$DesktopEvidence.ConfigRoot) }
    if ($EInfraEvidence.Detected) { return 'EInfraWindows' }
    if ($DesktopEvidence.Detected) { return 'Desktop' }
    if (Test-DockerOpenWebUI) { return 'Docker' }
    if (-not [string]::IsNullOrWhiteSpace($ServiceName) -or -not [string]::IsNullOrWhiteSpace($RestartCommand)) { return 'BareMetal' }
    throw 'Nelze automaticky určit typ instalace Open WebUI. Zadejte -Platform a podle potřeby -BaseUrl.'
}

function Get-ChildPowerShellExecutable {
    $candidate = if ($PSVersionTable.PSEdition -eq 'Core') { Join-Path $PSHOME 'pwsh.exe' } else { Join-Path $PSHOME 'powershell.exe' }
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    foreach ($name in @('powershell.exe','pwsh.exe')) { $command = Get-Command $name -ErrorAction SilentlyContinue; if ($null -ne $command) { return $command.Source } }
    throw 'Nebyl nalezen powershell.exe ani pwsh.exe pro spuštění platformního adaptéru.'
}

function Invoke-ChildPowerShell {
    param([Parameter(Mandatory=$true)][string]$ScriptPath,[Parameter(Mandatory=$true)][Collections.Generic.List[string]]$Arguments)
    $shell = Get-ChildPowerShellExecutable
    $nativeArguments = New-Object Collections.Generic.List[string]
    foreach ($item in @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$ScriptPath)) { [void]$nativeArguments.Add($item) }
    foreach ($item in $Arguments) { [void]$nativeArguments.Add([string]$item) }
    if ($DiagnosticsEnabled) { [void]$nativeArguments.Add('-Debug') }
    Write-Info ('Spouštím adaptér: {0}' -f $ScriptPath)
    $oldPreference = $ErrorActionPreference
    try { $ErrorActionPreference = 'Continue'; & $shell @($nativeArguments.ToArray()); $code = [int]$LASTEXITCODE } finally { $ErrorActionPreference = $oldPreference }
    if ($code -ne 0) { throw ('Platformní adaptér skončil kódem {0}: {1}' -f $code,$ScriptPath) }
}

function Add-ValueArgument { param([Collections.Generic.List[string]]$List,[string]$Name,$Value); if ($null -eq $Value) { return }; $text=[string]$Value; if ([string]::IsNullOrWhiteSpace($text)) { return }; [void]$List.Add($Name); [void]$List.Add($text) }
function Add-SwitchArgument { param([Collections.Generic.List[string]]$List,[string]$Name,[bool]$Enabled); if ($Enabled) { [void]$List.Add($Name) } }
function Add-CommonAuthenticationArguments { param([Collections.Generic.List[string]]$List); Add-ValueArgument $List '-TokenFile' $TokenFile; Add-ValueArgument $List '-Email' $Email; Add-ValueArgument $List '-PasswordFile' $PasswordFile; Add-SwitchArgument $List '-PromptForCredential' ([bool]$PromptForCredential) }

function Invoke-DesktopAdapter {
    param($Evidence,[string]$ResolvedReport)
    if ($Action -in @('Uninstall','Preflight')) { return Invoke-ApiEngine -ResolvedPlatform 'Desktop' -ResolvedReport $ResolvedReport -DesktopEvidence $Evidence }
    $scriptPath = if ($Action -eq 'Verify') { $Paths.DesktopVerify } else { $Paths.DesktopInstall }
    $arguments = New-Object Collections.Generic.List[string]
    if ($Action -eq 'DesktopDatabaseRepair') { [void]$arguments.Add('-Mode'); [void]$arguments.Add('DatabaseRepair'); [void]$arguments.Add('-Target'); [void]$arguments.Add('Desktop'); [void]$arguments.Add('-StopDesktopProcesses') }
    elseif ($Action -eq 'BackendRecovery') { [void]$arguments.Add('-Mode'); [void]$arguments.Add('RecoverStartup'); [void]$arguments.Add('-Target'); [void]$arguments.Add('Desktop') }
    elseif ($Action -eq 'Verify') { [void]$arguments.Add('-Target'); [void]$arguments.Add('Desktop') }
    else { [void]$arguments.Add('-Mode'); [void]$arguments.Add('TutorOnly'); [void]$arguments.Add('-Target'); [void]$arguments.Add('Desktop') }
    $desktopRootValue = if (-not [string]::IsNullOrWhiteSpace($DesktopInstallRoot)) { $DesktopInstallRoot } else { [string]$Evidence.InstallRoot }
    $desktopConfigValue = if (-not [string]::IsNullOrWhiteSpace($DesktopConfigRoot)) { $DesktopConfigRoot } else { [string]$Evidence.ConfigRoot }
    $desktopExeValue = if (-not [string]::IsNullOrWhiteSpace($DesktopExecutable)) { $DesktopExecutable } else { [string]$Evidence.Executable }
    Add-ValueArgument $arguments '-DesktopInstallRoot' $desktopRootValue; Add-ValueArgument $arguments '-DesktopDataRoot' $DesktopDataRoot; Add-ValueArgument $arguments '-DesktopConfigRoot' $desktopConfigValue; Add-ValueArgument $arguments '-DesktopExecutable' $desktopExeValue; Add-ValueArgument $arguments '-BaseUrl' $BaseUrl
    Add-CommonAuthenticationArguments $arguments
    Add-ValueArgument $arguments '-PythonPath' $PythonPath; Add-ValueArgument $arguments '-ReportPath' $ResolvedReport; Add-ValueArgument $arguments '-HttpTimeout' ([int][Math]::Ceiling($RequestTimeout)); Add-ValueArgument $arguments '-StartupTimeout' $StartupTimeout; Add-ValueArgument $arguments '-RouteTimeout' $RouteTimeout
    if ($Action -ne 'DesktopDatabaseRepair') { Add-SwitchArgument $arguments '-StopDesktopProcesses' ([bool]$StopDesktopProcesses) }
    Add-SwitchArgument $arguments '-NoAutoStartDesktop' ([bool]$NoAutoStartDesktop); Add-SwitchArgument $arguments '-KeepPayloadDirectory' ([bool]$KeepPayloadDirectory)
    Invoke-ChildPowerShell -ScriptPath $scriptPath -Arguments $arguments
}

function Invoke-EInfraAdapter {
    param($Evidence,[string]$ResolvedReport)
    if ($Action -eq 'DesktopDatabaseRepair') { throw 'DesktopDatabaseRepair nelze použít pro EInfraWindows.' }
    $scriptPath = if ($Action -eq 'Verify') { $Paths.EInfraVerify } else { $Paths.EInfraInstall }
    $arguments = New-Object Collections.Generic.List[string]
    if ($Action -ne 'Verify') {
        $serverAction = if ($Action -eq 'BackendRecovery') { 'BackendRecovery' } elseif ($Action -eq 'Preflight') { 'Preflight' } elseif ($Action -eq 'Uninstall') { 'Uninstall' } elseif ($Action -eq 'Install') { 'Install' } else { 'Repair' }
        Add-ValueArgument $arguments '-Action' $serverAction
    }
    Add-ValueArgument $arguments '-InstallRoot' $Evidence.InstallRoot; Add-ValueArgument $arguments '-RuntimeConfigPath' $Evidence.RuntimeConfigPath; Add-CommonAuthenticationArguments $arguments; Add-ValueArgument $arguments '-CaCertificate' $CaCertificate; Add-SwitchArgument $arguments '-InsecureTls' ([bool]$InsecureTls); Add-ValueArgument $arguments '-RequestTimeout' $RequestTimeout; Add-ValueArgument $arguments '-StartupTimeout' $StartupTimeout; Add-ValueArgument $arguments '-RouteTimeout' $RouteTimeout; Add-ValueArgument $arguments '-PublicVerification' $PublicVerification
    if ($Action -ne 'Verify') { Add-ValueArgument $arguments '-RestartPolicy' $RestartPolicy; Add-ValueArgument $arguments '-TutorStartupRecovery' $TutorStartupRecovery; Add-SwitchArgument $arguments '-NoRollback' ([bool]$NoRollback); Add-SwitchArgument $arguments '-KeepLegacyDisabled' ([bool]$KeepLegacyDisabled); Add-ValueArgument $arguments '-BackupDir' $BackupDir }
    Add-ValueArgument $arguments '-ReportPath' $ResolvedReport; Add-ValueArgument $arguments '-PythonPath' $PythonPath; Add-SwitchArgument $arguments '-KeepPayloadDirectory' ([bool]$KeepPayloadDirectory)
    Invoke-ChildPowerShell -ScriptPath $scriptPath -Arguments $arguments
}

function Invoke-ApiEngine {
    param([string]$ResolvedPlatform,[string]$ResolvedReport,$DesktopEvidence)
    if ($Action -in @('BackendRecovery','DesktopDatabaseRepair')) { throw ('Akce {0} vyžaduje specializovaný adaptér.' -f $Action) }
    $python = Find-Python
    $payloadDir = Join-Path ([IO.Path]::GetTempPath()) ('vut-tutor-universal-2.3.4-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $payloadDir -Force | Out-Null
    try {
        $actionMap = @{ Install='install'; Repair='repair'; Verify='verify'; Preflight='preflight'; Uninstall='uninstall' }
        $platformMap = @{ Desktop='desktop'; Docker='docker'; BareMetal='baremetal'; Remote='remote' }
        $restartMap = @{ Never='never'; OnFailure='on-failure'; Always='always' }
        $engineMap = @{ Auto='auto'; Docker='docker'; Podman='podman' }
        $config = [ordered]@{
            action = $actionMap[$Action]; platform = $platformMap[$ResolvedPlatform]; base_url = $BaseUrl; token_file = $TokenFile; email = $Email; password_file = $PasswordFile; prompt_for_credential = [bool]$PromptForCredential; ca_certificate = $CaCertificate; insecure_tls = [bool]$InsecureTls; request_timeout = $RequestTimeout; startup_timeout = $StartupTimeout; route_timeout = $RouteTimeout; restart_policy = $restartMap[$RestartPolicy]; start_backend = -not [bool]$NoStartBackend; no_rollback = [bool]$NoRollback; keep_legacy_disabled = [bool]$KeepLegacyDisabled; report_path = $ResolvedReport; backup_dir = $BackupDir; bootstrap_path = $Paths.Bootstrap; pipe_path = $Paths.Pipe; container_engine = $engineMap[$ContainerEngine]; container_name = $ContainerName; service_name = $ServiceName; restart_command = $RestartCommand; debug = [bool]$DiagnosticsEnabled
        }
        if ($null -ne $DesktopEvidence) {
            $config.desktop_install_root = if (-not [string]::IsNullOrWhiteSpace($DesktopInstallRoot)) { $DesktopInstallRoot } else { [string]$DesktopEvidence.InstallRoot }
            $config.desktop_config_root = if (-not [string]::IsNullOrWhiteSpace($DesktopConfigRoot)) { $DesktopConfigRoot } else { [string]$DesktopEvidence.ConfigRoot }
            $config.desktop_executable = if (-not [string]::IsNullOrWhiteSpace($DesktopExecutable)) { $DesktopExecutable } else { [string]$DesktopEvidence.Executable }
        }
        $configPath = Join-Path $payloadDir 'config.json'
        [IO.File]::WriteAllText($configPath,($config | ConvertTo-Json -Depth 8),(New-Object Text.UTF8Encoding($false)))
        Write-Info ('Spouštím API engine 2.0.6 pro platformu {0}.' -f $ResolvedPlatform)
        $oldPreference = $ErrorActionPreference
        try { $ErrorActionPreference='Continue'; & $python $Paths.ApiEngine '--config' $configPath; $code=[int]$LASTEXITCODE } finally { $ErrorActionPreference=$oldPreference }
        if ($code -ne 0) { throw ('API engine skončil kódem {0}. Report: {1}' -f $code,$ResolvedReport) }
    } finally {
        if ($KeepPayloadDirectory) { Write-Info ('Dočasná konfigurace ponechána v: {0}' -f $payloadDir) } elseif (Test-Path -LiteralPath $payloadDir) { Remove-Item -LiteralPath $payloadDir -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

if ($PSVersionTable.PSVersion.Major -ge 6 -and -not $IsWindows) { throw 'PowerShell dispatcher je určen pro Windows. Na Linuxu/macOS použijte install-vut-ai-tutor-universal-v2.3.4.sh.' }
Assert-PackageFiles

if ($Action -eq 'SelfTest') {
    $python = Find-Python
    $resolvedReport = Resolve-AbsolutePath -Path $ReportPath
    $oldPreference=$ErrorActionPreference
    try { $ErrorActionPreference='Continue'; & $python $Paths.DispatcherPy '--action' 'self-test' '--report-path' $resolvedReport; $code=[int]$LASTEXITCODE } finally { $ErrorActionPreference=$oldPreference }
    if ($code -ne 0) { throw ('Self-test skončil kódem {0}.' -f $code) }
    Write-Pass ('Self-test univerzální sady {0} prošel.' -f $InstallerVersion)
    exit 0
}

$einfraEvidence = Get-EInfraEvidence
$desktopEvidence = Get-DesktopEvidence
$resolvedPlatform = Resolve-TargetPlatform -EInfraEvidence $einfraEvidence -DesktopEvidence $desktopEvidence
$detection = [ordered]@{ installer_version=$InstallerVersion; runtime_version=$RuntimeVersion; requested_platform=$Platform; selected_platform=$resolvedPlatform; einfra=$einfraEvidence; desktop=$desktopEvidence; base_url=$BaseUrl }
Write-Info ('Univerzální instalátor {0}; Tutor runtime {1}.' -f $InstallerVersion,$RuntimeVersion)
Write-Info ('Detekovaná platforma: {0}' -f $resolvedPlatform)
if ($Action -eq 'Detect') { $detection | ConvertTo-Json -Depth 10; exit 0 }

if (-not $NoAutoPrompt -and $Action -in @('Install','Repair','Verify','Uninstall') -and [string]::IsNullOrWhiteSpace($TokenFile) -and [string]::IsNullOrWhiteSpace($Email) -and [string]::IsNullOrWhiteSpace($PasswordFile) -and -not $PromptForCredential) { $PromptForCredential=$true; Write-Info 'Nebyl zadán token ani účet; vyžádám administrátorské přihlašovací údaje.' }

$resolvedReport = Resolve-AbsolutePath -Path $ReportPath
if (-not [string]::IsNullOrWhiteSpace($TokenFile)) { $TokenFile = Resolve-AbsolutePath -Path $TokenFile -MustExist }
if (-not [string]::IsNullOrWhiteSpace($PasswordFile)) { $PasswordFile = Resolve-AbsolutePath -Path $PasswordFile -MustExist }
if (-not [string]::IsNullOrWhiteSpace($CaCertificate)) { $CaCertificate = Resolve-AbsolutePath -Path $CaCertificate -MustExist }
if (-not [string]::IsNullOrWhiteSpace($PythonPath)) { $PythonPath = Resolve-AbsolutePath -Path $PythonPath -MustExist }

switch ($resolvedPlatform) {
    'Desktop' { Invoke-DesktopAdapter -Evidence $desktopEvidence -ResolvedReport $resolvedReport }
    'EInfraWindows' { Invoke-EInfraAdapter -Evidence $einfraEvidence -ResolvedReport $resolvedReport }
    'Docker' { Invoke-ApiEngine -ResolvedPlatform 'Docker' -ResolvedReport $resolvedReport -DesktopEvidence $null }
    'BareMetal' { Invoke-ApiEngine -ResolvedPlatform 'BareMetal' -ResolvedReport $resolvedReport -DesktopEvidence $null }
    'Remote' { Invoke-ApiEngine -ResolvedPlatform 'Remote' -ResolvedReport $resolvedReport -DesktopEvidence $null }
    default { throw ('Interní chyba: neznámá platforma {0}.' -f $resolvedPlatform) }
}
Write-Pass ('Akce {0} byla dokončena pro platformu {1}. Report: {2}' -f $Action,$resolvedPlatform,$resolvedReport)
