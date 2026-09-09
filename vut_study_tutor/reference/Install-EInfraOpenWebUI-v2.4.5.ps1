#requires -Version 5.1
# EINFRA-OPENWEBUI-INSTALLER; VERSION=2.4.5; CLI=PARSER-GNU-AND-POWERSHELL
# 2.4.5: Caddy smeruje /zaverecne-prace a podcesty na 127.0.0.1:9871 bez odebrani prefixu.
# 2.4.4: Launcher preflight pouziva --help; nevyzaduje runtime WEBUI_SECRET_KEY.
# 2.4.3: Oprava PowerShell interpolace pred dvojteckou v chybovych hlaskach aktualizace.
# 2.4.2: Venv se nikdy nepresouva; po preflightu se nova verze vytvori primo v cilove ceste.
# 2.4.1: Oprava transakcni zalohy: long-path SHA-256, kratke backup cesty a vylouceni regenerovatelne cache.
# 2.4.0: Bezpecna automaticka kontrola a transakcni aktualizace Open WebUI se zalohou a rollbackem.
# 2.3.2: Vychozi profil pelton.ofivk.fme.vutbr.cz a pozadovane funkcni volby Open WebUI.
# 2.3.1: Oprava syntaxe Caddy tls force_automate pro migraci z LocalCA na verejny ACME certifikat.
# 2.3.0: --fqdn implicitne vyzaduje verejne duveryhodny ACME certifikat; verejna validace odmita Caddy LocalCA.
# 2.2.6: Oprava rozliseni chybejici inline hodnoty od prazdne hodnoty v PowerShell 5.1.
# 2.2.5: Oprava spotrebovani samostatne zadanych hodnot CLI voleb (napr. -LocalAccessName JMENO).
# 2.2.4: Oprava parser chyby pri vypisu TCP listeneru (promenna nasledovana dvojteckou).

<#
.SYNOPSIS
    Nainstaluje Open WebUI na Windows a vystavi jej pres HTTPS pomoci Caddy.

.DESCRIPTION
    - Nativni instalace pro Windows x64/ARM64 bez Dockeru.
    - Open WebUI bezi pouze na 127.0.0.1; verejne/LAN rozhrani obsluhuje Caddy.
    - Caddy smeruje /zaverecne-prace a /zaverecne-prace/* na lokalni sluzbu
      127.0.0.1:9871; puvodni URI prefix zustava zachovan. Ostatni pozadavky
      smeruji na nakonfigurovany backend Open WebUI (vychozi 127.0.0.1:18080).
    - LocalCA: Caddy vytvori soukromou lokalni CA. Bez importu jejiho korene na
      kazdem klientovi budou prohlizece hlasit ERR_CERT_AUTHORITY_INVALID.
    - PublicACME: Caddy ziska verejne duveryhodny certifikat pro zadanou DNS domenu.
    - Volba --fqdn bez explicitniho --certificate-mode implicitne pouzije PublicACME;
      instalator nikdy tise nespadne z verejneho certifikatu zpet na LocalCA.
    - Vychozi profil pouziva PublicACME pro pelton.ofivk.fme.vutbr.cz.
    - ENABLE_PERSISTENT_CONFIG=True umoznuje nasledne zmeny z Admin UI.
    - Pri --install, --resume a --update kontroluje oficialni stabilni vydani
      Open WebUI. Vychozi politika automaticky instaluje jen patch aktualizace
      ve stejne major.minor rade a az po bezpecnostnim odkladu.
    - Aktualizace je transakcni: kandidat se nejprve otestuje v oddelenem
      preflight venv. Pri zastavenem backendu se vytvori overena zaloha trvalych
      dat DATA_DIR a nova verze se znovu vytvori primo v kanonicke ceste venv.
      Virtualni prostredi se nikdy nepresouva, protoze jeho Windows launchery
      obsahuji vazby na puvodni cestu. Regenerovatelna cache a runtime-temp se
      nezalohuji; po startu se overi /ready a SQLite. Pri chybe se automaticky
      obnovi trvala data i puvodni venv.

    DULEZITE:
    1) Zmente vychozi FAKE API klic nize PRED prvnim spustenim, nebo jej predejte
       parametrem -ApiKey.
    2) API klic e-INFRA CZ je osobni. Nepouzivejte jeden osobni klic jako sdileny
       klic pro vice osob bez souhlasu/provereni podminek poskytovatele.
    3) Lokalni CA odstrani varovani jen na zarizenich, kde je jeji korenovy
       certifikat duveryhodny. Pro klienty bez instalace CA pouzijte --fqdn nebo
       PublicACME a verejne overitelne DNS jmeno.

.EXAMPLE
    .\Install-EInfraOpenWebUI.ps1 --resume

.EXAMPLE
    .\Install-EInfraOpenWebUI.ps1 `
      -CertificateMode LocalCA `
      -LocalAccessName webui.intranet.example.cz `
      -ApiKey 'sk-SEM-VLOZTE-SKUTECNY-KLIC'

.EXAMPLE
    .\Install-EInfraOpenWebUI.ps1 `
      -CertificateMode PublicACME `
      -PublicDomain webui.example.cz `
      -AcmeEmail admin@example.cz `
      -ApiKey 'sk-SEM-VLOZTE-SKUTECNY-KLIC'

.EXAMPLE
    .\Install-EInfraOpenWebUI.ps1 --resume --fqdn pelton.ofivk.fme.vutbr.cz

.EXAMPLE
    .\Install-EInfraOpenWebUI.ps1 --uninstall

.EXAMPLE
    .\Install-EInfraOpenWebUI.ps1 -Action Status
#>

# Tento skript zamerne nepouziva standardni param() blok. Windows PowerShell
# pouziva pro vlastni parametry jeden spojovnik, zatimco tento instalator ma
# podporovat i presne pozadovane GNU-style volby --resume a --uninstall.
# Vsechny argumenty proto zpracovava vlastni parser; soucasne zachovava
# kompatibilitu s puvodnimi tvary -Action, -ApiKey, -LocalAccessName atd.
# Pokud PowerShell hlasi NamedParameterNotFound jeste pred vypisem verze, spousti
# se jina/starsi kopie souboru, protoze tato verze nema top-level param() blok.

$OriginalArguments = @($args)
$CliSpecified = @{}
$Action = 'Install'
$ResumeRequested = $false
$UninstallRequested = $false
$ShowHelpRequested = $false
$ShowVersionRequested = $false

# Pevny vychozi konfiguracni profil pozadovany pro tento server.
$ProfileCertificateMode = 'PublicACME'
$ProfilePublicDomain = 'pelton.ofivk.fme.vutbr.cz'
$ProfileApiBaseUrl = 'https://llm.ai.e-infra.cz/v1'
$ProfileDefaultModel = 'kimi-k3'
$ProfileOpenWebUIVersion = '0.11.0'
$ProfileWebUiSecret = '3d380eb4ad5f5f46d4dff0922742f5d3f4ad9c8cdb7078b85d765e0afeb29cec'
$ProfileLocalAddresses = @(
    '147.229.83.12',
    '172.25.240.1',
    '172.22.64.1'
)
$FakeApiKeyPlaceholder = 'fake e-infra api key'

$CertificateMode = $ProfileCertificateMode
$PublicDomain = $ProfilePublicDomain
$AcmeEmail = ''
$LocalAccessName = ''
$RequestedFqdn = ''

# ================================================================
# ZMENTE TENTO FAKE KLIC, nebo pouzijte --api-key.
# Pri --resume se bez explicitniho --api-key zachova skutecny klic z runtime.json.
# ================================================================
$ApiKey = $FakeApiKeyPlaceholder
$ApiBaseUrl = $ProfileApiBaseUrl
$DefaultModel = $ProfileDefaultModel
$OpenWebUIVersion = $ProfileOpenWebUIVersion

$BackendPort = 18080
$HttpPort = 80
$HttpsPort = 443
$InstallRoot = "$env:ProgramData\EInfra-OpenWebUI"

$AdminEmail = 'admin@webui.local'
$AdminName = 'Administrator'
$AdminPassword = ''
# Zalozni kopie WEBUI_SECRET_KEY pro obnovu pri poskozenem runtime.json.
# Hodnota je ulozena jen v administratorsky chranenem resume-config.json.
$ResumeWebUiSecret = $ProfileWebUiSecret

$DisableSignup = $false
$AllowAdminUiOverrides = $true
$EnableDirectConnections = $true
$ForceDownload = $false
$PreserveData = $false
$SkipFirewallChange = $false

# Bezpecna automaticka aktualizace Open WebUI.
# Patch = pouze stabilni verze ve stejne major.minor rade.
# Stable = libovolna novejsi stabilni verze (vyzaduje explicitni volbu).
# Off = bez online kontroly; explicitni --open-webui-version stale plati.
$OpenWebUIUpdatePolicy = 'Patch'
$MinimumReleaseAgeHours = 48
$AllowOpenWebUIDowngrade = $false
$script:InstalledOpenWebUIVersion = ''
$script:LatestAvailableOpenWebUIVersion = ''
$script:LastOpenWebUIUpdateCheckUtc = ''
$script:OpenWebUIReleaseUrl = ''
$script:OpenWebUIReleasePublishedAtUtc = ''
$script:OpenWebUIUpdateDecision = ''

# Tyto podadresare DATA_DIR jsou podle konfigurace tohoto instalatoru pouze
# regenerovatelna cache a docasne soubory. Nejsou soucasti transakcni zalohy,
# aby nestabilni Hugging Face cache ani velmi dlouhe modelove cesty nemohly
# zablokovat aktualizaci nebo zvetsovat zalohu uzivatelskych dat.
$OpenWebUIUpdateExcludedDataPaths = @(
    'cache',
    'runtime-temp'
)

# Parser pouziva jediny explicitni kurzor ve script scope. Vnejsi smycka i
# funkce nacitajici hodnotu tak posouvaji stejnou promennou a samostatne zadana
# hodnota volby se spotrebuje prave jednou.
$script:CliArgumentIndex = 0

function Get-RequiredCliValue {
    param(
        [Parameter(Mandatory = $true)][string]$OptionName,
        [Parameter(Mandatory = $true)][bool]$HasInlineValue,
        [AllowNull()][object]$InlineValue,
        [Parameter(Mandatory = $true)][object[]]$AllArguments
    )

    # Nepouzivame test $null -ne $InlineValue nad parametrem typu [string].
    # Windows PowerShell 5.1 pri vazbe parametru prevadi $null na prazdny
    # retezec. Samostatny priznak proto jednoznacne rozlisuje tvary
    # --volba=HODNOTA a --volba HODNOTA.
    if ($HasInlineValue) {
        $inlineText = if ($null -eq $InlineValue) { '' } else { [string]$InlineValue }
        if ([string]::IsNullOrWhiteSpace($inlineText)) {
            throw "Volba --$OptionName vyzaduje neprazdnou hodnotu."
        }
        return $inlineText
    }

    $nextIndex = $script:CliArgumentIndex + 1
    if ($nextIndex -ge $AllArguments.Count) {
        throw "Volba --$OptionName vyzaduje hodnotu."
    }

    $candidate = [string]$AllArguments[$nextIndex]
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        throw "Volba --$OptionName vyzaduje neprazdnou hodnotu."
    }

    $script:CliArgumentIndex = $nextIndex
    return $candidate
}

function ConvertTo-CliInt {
    param(
        [Parameter(Mandatory = $true)][string]$OptionName,
        [Parameter(Mandatory = $true)][string]$Value,
        [Parameter(Mandatory = $true)][int]$Minimum,
        [Parameter(Mandatory = $true)][int]$Maximum
    )

    $parsed = 0
    if (-not [int]::TryParse($Value, [ref]$parsed) -or $parsed -lt $Minimum -or $parsed -gt $Maximum) {
        throw "Neplatna hodnota --$OptionName '$Value'; povoleny rozsah je $Minimum az $Maximum."
    }
    return $parsed
}

function Set-CliCommand {
    param([Parameter(Mandatory = $true)][string]$Command)

    if ($script:CliSpecified.ContainsKey('Command') -and $script:Action -ne $Command) {
        throw "Nelze kombinovat prikazy '$($script:Action)' a '$Command'."
    }
    $script:Action = $Command
    $script:CliSpecified['Command'] = $true
}

try {
    while ($script:CliArgumentIndex -lt $OriginalArguments.Count) {
        $rawToken = ([string]$OriginalArguments[$script:CliArgumentIndex]).Trim()
        if ([string]::IsNullOrWhiteSpace($rawToken)) {
            $script:CliArgumentIndex++
            continue
        }

        if ($rawToken.StartsWith('--')) {
            $body = $rawToken.Substring(2)
        }
        elseif ($rawToken.StartsWith('-')) {
            $body = $rawToken.Substring(1)
        }
        elseif ($rawToken.StartsWith('/')) {
            $body = $rawToken.Substring(1)
        }
        else {
            throw "Neznamy argument '$rawToken'. Pouzijte --help."
        }

        $hasInlineValue = $false
        $inlineValue = $null
        $equalsIndex = $body.IndexOf('=')
        if ($equalsIndex -ge 0) {
            $hasInlineValue = $true
            $inlineValue = $body.Substring($equalsIndex + 1)
            $body = $body.Substring(0, $equalsIndex)
        }
        $option = $body.Trim().ToLowerInvariant()

        switch ($option) {
            'resume' {
                Set-CliCommand -Command 'Install'
                $ResumeRequested = $true
                $CliSpecified['Resume'] = $true
            }
            { $_ -in @('uninstall', 'uninstal') } {
                Set-CliCommand -Command 'Uninstall'
                $UninstallRequested = $true
            }
            'install' { Set-CliCommand -Command 'Install' }
            'update' { Set-CliCommand -Command 'Update' }
            'start' { Set-CliCommand -Command 'Start' }
            'stop' { Set-CliCommand -Command 'Stop' }
            'restart' { Set-CliCommand -Command 'Restart' }
            'status' { Set-CliCommand -Command 'Status' }
            'version' { $ShowVersionRequested = $true }
            'help' { $ShowHelpRequested = $true }
            'h' { $ShowHelpRequested = $true }
            '?' { $ShowHelpRequested = $true }

            'action' {
                $value = Get-RequiredCliValue -OptionName 'action' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                switch ($value.Trim().ToLowerInvariant()) {
                    'install' { Set-CliCommand -Command 'Install' }
                    'resume' { Set-CliCommand -Command 'Install'; $ResumeRequested = $true; $CliSpecified['Resume'] = $true }
                    'update' { Set-CliCommand -Command 'Update' }
                    'start' { Set-CliCommand -Command 'Start' }
                    'stop' { Set-CliCommand -Command 'Stop' }
                    'restart' { Set-CliCommand -Command 'Restart' }
                    'status' { Set-CliCommand -Command 'Status' }
                    { $_ -in @('uninstall', 'uninstal') } { Set-CliCommand -Command 'Uninstall'; $UninstallRequested = $true }
                    default { throw "Neplatna hodnota --action '$value'." }
                }
            }

            { $_ -in @('certificate-mode', 'certificatemode', 'tls-mode', 'tlsmode') } {
                $value = Get-RequiredCliValue -OptionName 'certificate-mode' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                switch ($value.Trim().ToLowerInvariant()) {
                    'localca' { $CertificateMode = 'LocalCA' }
                    'publicacme' { $CertificateMode = 'PublicACME' }
                    default { throw "Neplatny rezim certifikatu '$value'; pouzijte LocalCA nebo PublicACME." }
                }
                $CliSpecified['CertificateMode'] = $true
            }
            { $_ -in @('fqdn', 'hostname') } {
                $RequestedFqdn = Get-RequiredCliValue -OptionName 'fqdn' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['Fqdn'] = $true
            }
            { $_ -in @('local-access-name', 'localaccessname') } {
                $LocalAccessName = Get-RequiredCliValue -OptionName 'local-access-name' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['LocalAccessName'] = $true
            }
            { $_ -in @('public-domain', 'publicdomain') } {
                $PublicDomain = Get-RequiredCliValue -OptionName 'public-domain' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['PublicDomain'] = $true
            }
            { $_ -in @('acme-email', 'acmeemail') } {
                $AcmeEmail = Get-RequiredCliValue -OptionName 'acme-email' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['AcmeEmail'] = $true
            }
            { $_ -in @('api-key', 'apikey') } {
                $ApiKey = Get-RequiredCliValue -OptionName 'api-key' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['ApiKey'] = $true
            }
            { $_ -in @('api-base-url', 'apibaseurl') } {
                $ApiBaseUrl = Get-RequiredCliValue -OptionName 'api-base-url' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['ApiBaseUrl'] = $true
            }
            { $_ -in @('model', 'default-model', 'defaultmodel') } {
                $DefaultModel = Get-RequiredCliValue -OptionName 'model' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['DefaultModel'] = $true
            }
            { $_ -in @('open-webui-version', 'openwebuiversion') } {
                $OpenWebUIVersion = Get-RequiredCliValue -OptionName 'open-webui-version' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['OpenWebUIVersion'] = $true
            }
            { $_ -in @('backend-port', 'backendport') } {
                $value = Get-RequiredCliValue -OptionName 'backend-port' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $BackendPort = ConvertTo-CliInt -OptionName 'backend-port' -Value $value -Minimum 1024 -Maximum 65535
                $CliSpecified['BackendPort'] = $true
            }
            { $_ -in @('http-port', 'httpport') } {
                $value = Get-RequiredCliValue -OptionName 'http-port' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $HttpPort = ConvertTo-CliInt -OptionName 'http-port' -Value $value -Minimum 1 -Maximum 65535
                $CliSpecified['HttpPort'] = $true
            }
            { $_ -in @('https-port', 'httpsport') } {
                $value = Get-RequiredCliValue -OptionName 'https-port' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $HttpsPort = ConvertTo-CliInt -OptionName 'https-port' -Value $value -Minimum 1 -Maximum 65535
                $CliSpecified['HttpsPort'] = $true
            }
            { $_ -in @('install-root', 'installroot') } {
                $InstallRoot = Get-RequiredCliValue -OptionName 'install-root' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['InstallRoot'] = $true
            }
            { $_ -in @('admin-email', 'adminemail') } {
                $AdminEmail = Get-RequiredCliValue -OptionName 'admin-email' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['AdminEmail'] = $true
            }
            { $_ -in @('admin-name', 'adminname') } {
                $AdminName = Get-RequiredCliValue -OptionName 'admin-name' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['AdminName'] = $true
            }
            { $_ -in @('admin-password', 'adminpassword') } {
                $AdminPassword = Get-RequiredCliValue -OptionName 'admin-password' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $CliSpecified['AdminPassword'] = $true
            }
            { $_ -in @('disable-signup', 'disablesignup') } { $DisableSignup = $true; $CliSpecified['DisableSignup'] = $true }
            { $_ -in @('allow-admin-ui-overrides', 'allowadminuioverrides') } { $AllowAdminUiOverrides = $true; $CliSpecified['AllowAdminUiOverrides'] = $true }
            { $_ -in @('enable-direct-connections', 'enabledirectconnections') } { $EnableDirectConnections = $true; $CliSpecified['EnableDirectConnections'] = $true }
            { $_ -in @('update-policy', 'updatepolicy', 'open-webui-update-policy', 'openwebuiupdatepolicy') } {
                $value = Get-RequiredCliValue -OptionName 'update-policy' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                switch ($value.Trim().ToLowerInvariant()) {
                    'patch' { $OpenWebUIUpdatePolicy = 'Patch' }
                    'stable' { $OpenWebUIUpdatePolicy = 'Stable' }
                    'off' { $OpenWebUIUpdatePolicy = 'Off' }
                    default { throw "Neplatna politika aktualizaci '$value'; pouzijte Patch, Stable nebo Off." }
                }
                $CliSpecified['OpenWebUIUpdatePolicy'] = $true
            }
            { $_ -in @('minimum-release-age-hours', 'minimumreleaseagehours', 'min-release-age-hours', 'minreleaseagehours') } {
                $value = Get-RequiredCliValue -OptionName 'minimum-release-age-hours' -HasInlineValue $hasInlineValue -InlineValue $inlineValue -AllArguments $OriginalArguments
                $MinimumReleaseAgeHours = ConvertTo-CliInt -OptionName 'minimum-release-age-hours' -Value $value -Minimum 0 -Maximum 8760
                $CliSpecified['MinimumReleaseAgeHours'] = $true
            }
            { $_ -in @('no-update-check', 'noupdatecheck', 'disable-auto-update', 'disableautoupdate') } {
                $OpenWebUIUpdatePolicy = 'Off'
                $CliSpecified['OpenWebUIUpdatePolicy'] = $true
            }
            { $_ -in @('allow-downgrade', 'allowdowngrade') } {
                $AllowOpenWebUIDowngrade = $true
                $CliSpecified['AllowOpenWebUIDowngrade'] = $true
            }
            { $_ -in @('force-download', 'forcedownload') } { $ForceDownload = $true; $CliSpecified['ForceDownload'] = $true }
            { $_ -in @('preserve-data', 'keep-data', 'preservedata', 'keepdata') } { $PreserveData = $true; $CliSpecified['PreserveData'] = $true }
            { $_ -in @('purge-data', 'purgedata') } { $PreserveData = $false; $CliSpecified['PreserveData'] = $true }
            { $_ -in @('skip-firewall-change', 'skipfirewallchange') } { $SkipFirewallChange = $true; $CliSpecified['SkipFirewallChange'] = $true }
            default { throw "Neznama volba '$rawToken'. Pouzijte --help." }
        }

        $script:CliArgumentIndex++
    }

    # --fqdn vyjadruje pozadavek na certifikat duveryhodny bez instalace
    # soukrome CA. Neni-li rezim explicitne zadan, zvoli se PublicACME. Pro
    # zamerne soukromou CA pouzijte --certificate-mode LocalCA --fqdn JMENO
    # nebo explicitni --local-access-name JMENO.
    if ($CliSpecified.ContainsKey('Fqdn')) {
        $fqdnValue = ([string]$RequestedFqdn).Trim().TrimEnd('.')
        if ([string]::IsNullOrWhiteSpace($fqdnValue)) {
            throw 'Volba --fqdn vyzaduje neprazdne DNS jmeno.'
        }

        if ($CliSpecified.ContainsKey('CertificateMode') -and $CertificateMode -eq 'LocalCA') {
            if ($CliSpecified.ContainsKey('PublicDomain')) {
                throw 'Nelze kombinovat --certificate-mode LocalCA s --public-domain.'
            }
            if ($CliSpecified.ContainsKey('LocalAccessName') -and
                -not [string]::Equals(([string]$LocalAccessName).Trim().TrimEnd('.'), $fqdnValue, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Hodnoty --fqdn a --local-access-name si odporuji.'
            }
            $LocalAccessName = $fqdnValue
            $CliSpecified['LocalAccessName'] = $true
        }
        else {
            if ($CliSpecified.ContainsKey('LocalAccessName')) {
                throw 'Volbu --fqdn nelze kombinovat s --local-access-name, pokud neni explicitne zvolen LocalCA.'
            }
            if ($CliSpecified.ContainsKey('PublicDomain') -and
                -not [string]::Equals(([string]$PublicDomain).Trim().TrimEnd('.'), $fqdnValue, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Hodnoty --fqdn a --public-domain si odporuji.'
            }
            $CertificateMode = 'PublicACME'
            $PublicDomain = $fqdnValue
            $CliSpecified['CertificateMode'] = $true
            $CliSpecified['PublicDomain'] = $true
        }
    }

    if ($CliSpecified.ContainsKey('PublicDomain') -and -not $CliSpecified.ContainsKey('CertificateMode')) {
        $CertificateMode = 'PublicACME'
        $CliSpecified['CertificateMode'] = $true
    }
    if ($CliSpecified.ContainsKey('LocalAccessName') -and -not $CliSpecified.ContainsKey('CertificateMode')) {
        $CertificateMode = 'LocalCA'
        $CliSpecified['CertificateMode'] = $true
    }
    if ($CertificateMode -eq 'PublicACME' -and $CliSpecified.ContainsKey('LocalAccessName')) {
        throw 'LocalAccessName lze pouzit pouze s --certificate-mode LocalCA.'
    }
    if ($CertificateMode -eq 'LocalCA' -and $CliSpecified.ContainsKey('PublicDomain')) {
        throw 'PublicDomain lze pouzit pouze s --certificate-mode PublicACME.'
    }

    if ($CliSpecified.ContainsKey('PreserveData') -and $Action -ne 'Uninstall') {
        throw 'Volby --preserve-data a --purge-data lze pouzit pouze s --uninstall.'
    }
}
catch {
    Write-Host "CHYBA ARGUMENTU: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'Pouzijte --help.' -ForegroundColor Yellow
    exit 2
}

# Zachovani kompatibility se zbytkem puvodni implementace.
$PurgeData = -not $PreserveData


Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ScriptVersion = '2.4.5'
$ProductId = 'EInfra-OpenWebUI'
$BackendTaskName = 'e-INFRA Open WebUI Backend'
$ProxyTaskName = 'e-INFRA Open WebUI HTTPS'
$FirewallRulePrefix = 'e-INFRA Open WebUI'

$InstallRoot = [IO.Path]::GetFullPath($InstallRoot)
$BinDir = Join-Path $InstallRoot 'bin'
$UvDir = Join-Path $BinDir 'uv'
$CaddyDir = Join-Path $BinDir 'caddy'
$VenvDir = Join-Path $InstallRoot 'venv'
$PythonInstallDir = Join-Path $InstallRoot 'python'
$PythonBinDir = Join-Path $BinDir 'python-shims'
$UvCacheDir = Join-Path $InstallRoot 'uv-cache'
$DataDir = Join-Path $InstallRoot 'data'
$RuntimeTempDir = Join-Path $DataDir 'runtime-temp'
$CacheDir = Join-Path $DataDir 'cache'
$HfCacheDir = Join-Path $CacheDir 'huggingface'
$StaticDir = Join-Path $DataDir 'static'
$ConfigDir = Join-Path $InstallRoot 'config'
$RuntimeConfigPath = Join-Path $ConfigDir 'runtime.json'
$RuntimeScriptPath = Join-Path $ConfigDir 'Run-Component.ps1'
$CaddyfilePath = Join-Path $ConfigDir 'Caddyfile'
$CaddyDataBase = Join-Path $InstallRoot 'caddy-data'
$CaddyConfigBase = Join-Path $InstallRoot 'caddy-config'
$LogDir = Join-Path $InstallRoot 'logs'
$DownloadDir = Join-Path $InstallRoot 'downloads'
$BackupDir = Join-Path $InstallRoot 'backups'
$ClientCaDir = Join-Path $InstallRoot 'client-ca'
$AdminDir = Join-Path $InstallRoot 'admin-only'
$CredentialsPath = Join-Path $AdminDir 'ADMIN-CREDENTIALS.txt'
$InstallerStateDir = Join-Path $InstallRoot '.installer'
$InstallerStatePath = Join-Path $InstallerStateDir 'state.json'
$InstallerSnapshotDir = Join-Path $InstallerStateDir 'original-state'
$InstallerResumeConfigPath = Join-Path $InstallerStateDir 'resume-config.json'
$OpenWebUIUpdateTransactionPath = Join-Path $InstallerStateDir 'open-webui-update-transaction.json'
$OpenWebUIStagingVenvDir = Join-Path $InstallerStateDir 'open-webui-venv-staging'
$OpenWebUIRollbackVenvDir = Join-Path $InstallerStateDir 'open-webui-venv-rollback'
# Posledni odinstalacni checkpoint je mimo mazany strom. Umoznuje dokoncit
# --uninstall i po vypadku mezi smazanim .installer a smazanim InstallRoot.
$UninstallRecoveryStatePath = "$InstallRoot.uninstall-recovery.json"
$InstallerMutexName = 'Global\EInfra-OpenWebUI-Installer-v2'
$ManagedTopLevelNames = @(
    'bin', 'venv', 'python', 'uv-cache', 'data', 'config',
    'caddy-data', 'caddy-config', 'logs', 'downloads', 'backups',
    'client-ca', 'admin-only', '.installer'
)
$script:InstallerState = $null
$script:InstallerMutex = $null
$script:CurrentPhase = ''
$script:InstallContext = $null
$script:InstallerStateSourcePath = ''
$script:InstallerStateCanQuarantine = $false


$UvExe = Join-Path $UvDir 'uv.exe'
$CaddyExe = Join-Path $CaddyDir 'caddy.exe'
$PythonExe = Join-Path $VenvDir 'Scripts\python.exe'
$OpenWebUIExe = Join-Path $VenvDir 'Scripts\open-webui.exe'
$VenvLayoutMarker = Join-Path $VenvDir '.einfra-uv-link-mode-copy-v1'

function Write-Step {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Write-Ok {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-Notice {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor DarkCyan
}

function Write-Caution {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Warning $Message
}


function Show-Usage {
    $usage = @'
E-INFRA Open WebUI - jednotny instalator pro Windows

Pouziti:
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\Install-EInfraOpenWebUI.ps1 [prikaz] [volby]

Hlavni prikazy:
  --install                 Nova instalace (vychozi prikaz).
  --resume                  Navaze na prerusenou instalaci nebo opravi existujici
                            instalaci. Zachova databazi, certifikaty, API klic,
                            WEBUI_SECRET_KEY a uzivatelska data.
  --uninstall               Odstrani program, ulohy, firewall pravidla, serverovou
                            duveru lokalni CA a instalacni adresar. Odinstalace ma
                            vlastni checkpointy a po preruseni se stejnym prikazem
                            bezpecne pokracuje. Vychozi je odstraneni vcetne dat.

Provozni prikazy:
  --status | --start | --stop | --restart | --update

Nejdulezitejsi volby:
  --fqdn JMENO              FQDN pouzivane klienty. Bez explicitniho rezimu
                            znamena PublicACME a vyzaduje verejne duveryhodny
                            certifikat; pri neuspechu instalace skonci chybou.
  --certificate-mode MODE   LocalCA nebo PublicACME. LocalCA je soukroma CA a
                            klienti ji musi importovat; neni verejne duveryhodna.
  --public-domain JMENO     Verejna domena pro PublicACME (alternativa k --fqdn).
  --local-access-name JMENO Soukrome DNS jmeno/IP pro LocalCA.
  --acme-email EMAIL        Volitelny kontakt pro ACME.
  --api-key KLIC            API klic e-INFRA CZ.
  --api-base-url URL        Vychozi: https://llm.ai.e-infra.cz/v1
  --model MODEL             Vychozi: kimi-k3
  --open-webui-version VERZE Explicitni cilova verze; obchazi automaticky vyber.
  --update-policy POLICY    Patch (vychozi), Stable nebo Off. Patch automaticky
                            instaluje jen stabilni aktualizace ve stejne rade.
  --minimum-release-age-hours N
                            Vychozi 48 hodin; cerstvejsi vydani se odlozi.
  --allow-downgrade         Povoluje explicitni prechod na starsi verzi. Bez teto
                            volby je downgrade zablokovan kvuli databazovemu schematu.
  --no-update-check         Alias pro --update-policy Off.
  --install-root CESTA      Vychozi: %ProgramData%\EInfra-OpenWebUI
  --force-download          Vynuti nove stazeni uv a Caddy.
  --preserve-data           Jen s --uninstall: presune data do samostatne zalohy.
  --skip-firewall-change    Pri instalaci nemeni Windows Firewall.
  --version                 Vypise verzi instalatoru a skonci.
  --help                    Tato napoveda.

Priklady:
  .\Install-EInfraOpenWebUI.ps1 --resume --fqdn pelton.ofivk.fme.vutbr.cz
  .\Install-EInfraOpenWebUI.ps1 --certificate-mode LocalCA --local-access-name webui.intranet.example.cz
  .\Install-EInfraOpenWebUI.ps1 --uninstall
  .\Install-EInfraOpenWebUI.ps1 --uninstall --preserve-data

Podporovan je take zapis s jednim spojovnikem, napr. -Resume -Fqdn JMENO,
-Action Status, -Action Uninstall nebo -LocalAccessName JMENO. Skript nema
param() blok; vsechny volby zpracovava vlastni parser, aby fungovaly oba tvary.
'@
    Write-Host $usage
}

function Acquire-InstallerMutex {
    $createdNew = $false
    $mutex = [Threading.Mutex]::new($false, $InstallerMutexName, [ref]$createdNew)
    try {
        if (-not $mutex.WaitOne(0, $false)) {
            $mutex.Dispose()
            throw 'Jina instance instalatoru prave bezi. Dokoncete ji nebo ji ukoncete a potom pouzijte --resume.'
        }
    }
    catch [Threading.AbandonedMutexException] {
        # Predchozi proces skoncil neocekavane; mutex nyni vlastnime a --resume
        # muze bezpecne pokracovat ze stavoveho souboru.
    }
    $script:InstallerMutex = $mutex
}

function Release-InstallerMutex {
    if ($null -ne $script:InstallerMutex) {
        try { $script:InstallerMutex.ReleaseMutex() } catch { }
        $script:InstallerMutex.Dispose()
        $script:InstallerMutex = $null
    }
}

function Add-StatePropertyIfMissing {
    param(
        [Parameter(Mandatory = $true)]$State,
        [Parameter(Mandatory = $true)][string]$Name,
        [AllowNull()]$DefaultValue
    )
    if ($State.PSObject.Properties.Name -notcontains $Name) {
        Add-Member -InputObject $State -MemberType NoteProperty -Name $Name -Value $DefaultValue
    }
}

function Normalize-CertificateThumbprint {
    param([AllowNull()][string]$Thumbprint)
    if ([string]::IsNullOrWhiteSpace($Thumbprint)) { return '' }
    return $Thumbprint.Replace(' ', '').ToUpperInvariant()
}

function Get-CertificateTrustRecord {
    param([Parameter(Mandatory = $true)][string]$Thumbprint)

    if ($null -eq $script:InstallerState) { return $null }
    Add-StatePropertyIfMissing -State $script:InstallerState -Name 'CertificateTrustRecords' -DefaultValue @()
    $normalized = Normalize-CertificateThumbprint -Thumbprint $Thumbprint
    foreach ($record in @($script:InstallerState.CertificateTrustRecords)) {
        if ($null -eq $record) { continue }
        Add-StatePropertyIfMissing -State $record -Name 'Thumbprint' -DefaultValue ''
        Add-StatePropertyIfMissing -State $record -Name 'PresentBefore' -DefaultValue $false
        Add-StatePropertyIfMissing -State $record -Name 'ImportedByInstaller' -DefaultValue $false
        Add-StatePropertyIfMissing -State $record -Name 'RemoveOnUninstall' -DefaultValue $false
        Add-StatePropertyIfMissing -State $record -Name 'Reason' -DefaultValue ''
        Add-StatePropertyIfMissing -State $record -Name 'UpdatedAt' -DefaultValue ''
        if ((Normalize-CertificateThumbprint -Thumbprint ([string]$record.Thumbprint)) -eq $normalized) {
            return $record
        }
    }
    return $null
}

function Set-CertificateTrustRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Thumbprint,
        [Parameter(Mandatory = $true)][bool]$PresentBefore,
        [Parameter(Mandatory = $true)][bool]$ImportedByInstaller,
        [Parameter(Mandatory = $true)][bool]$RemoveOnUninstall,
        [Parameter(Mandatory = $true)][string]$Reason
    )

    if ($null -eq $script:InstallerState) { return $null }
    Add-StatePropertyIfMissing -State $script:InstallerState -Name 'CertificateTrustRecords' -DefaultValue @()
    $normalized = Normalize-CertificateThumbprint -Thumbprint $Thumbprint
    $record = Get-CertificateTrustRecord -Thumbprint $normalized
    if ($null -eq $record) {
        $record = [pscustomobject][ordered]@{
            Thumbprint = $normalized
            PresentBefore = $PresentBefore
            ImportedByInstaller = $ImportedByInstaller
            RemoveOnUninstall = $RemoveOnUninstall
            Reason = $Reason
            UpdatedAt = [DateTimeOffset]::Now.ToString('o')
        }
        $records = [Collections.Generic.List[object]]::new()
        foreach ($existingRecord in @($script:InstallerState.CertificateTrustRecords)) {
            if ($null -ne $existingRecord) { [void]$records.Add($existingRecord) }
        }
        [void]$records.Add($record)
        $script:InstallerState.CertificateTrustRecords = $records.ToArray()
    }
    else {
        $record.PresentBefore = $PresentBefore
        $record.ImportedByInstaller = $ImportedByInstaller
        $record.RemoveOnUninstall = $RemoveOnUninstall
        $record.Reason = $Reason
        $record.UpdatedAt = [DateTimeOffset]::Now.ToString('o')
    }
    Write-InstallerState
    return $record
}

function Read-InstallerState {
    if (-not (Test-Path -LiteralPath $InstallerStatePath -PathType Leaf)) {
        return $null
    }
    try {
        return Get-Content -LiteralPath $InstallerStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "Stavovy soubor instalace je poskozeny: $InstallerStatePath. Detail: $($_.Exception.Message)"
    }
}

function Read-UninstallState {
    $script:InstallerStateSourcePath = ''
    $script:InstallerStateCanQuarantine = $false
    foreach ($candidatePath in @($InstallerStatePath, $UninstallRecoveryStatePath)) {
        if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) { continue }
        $script:InstallerStateSourcePath = $candidatePath
        try {
            $state = Get-Content -LiteralPath $candidatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        catch {
            # Primarni stav uvnitr instalacniho adresare lze pri poskozeni
            # odlozit a zkusit obnovit z externiho checkpointu. Externi stav
            # se karantenuje jen tehdy, kdyz nema konkurencni platny stav.
            $script:InstallerStateCanQuarantine = $true
            throw "Stavovy soubor odinstalace je poskozeny: $candidatePath. Detail: $($_.Exception.Message)"
        }

        $stateProperties = @($state.PSObject.Properties.Name)
        if ($stateProperties -contains 'ProductId' -and
            -not [string]::Equals([string]$state.ProductId, $ProductId, [StringComparison]::Ordinal)) {
            $script:InstallerStateCanQuarantine = $false
            throw "Stavovy soubor $candidatePath patri jinemu produktu ('$($state.ProductId)') a nebude zmenen."
        }
        if ([string]::Equals($candidatePath, $UninstallRecoveryStatePath, [StringComparison]::OrdinalIgnoreCase)) {
            if ($stateProperties -notcontains 'ProductId' -or
                -not [string]::Equals([string]$state.ProductId, $ProductId, [StringComparison]::Ordinal)) {
                $script:InstallerStateCanQuarantine = $false
                throw "Externi checkpoint $candidatePath nema platne vlastnictvi produktu $ProductId a nebude zmenen."
            }
        }
        return $state
    }
    return $null
}

function Write-UninstallRecoveryState {
    if ($null -eq $script:InstallerState) { return }

    $stateProperties = @($script:InstallerState.PSObject.Properties.Name)
    if ($stateProperties -notcontains 'ProductId' -or
        -not [string]::Equals([string]$script:InstallerState.ProductId, $ProductId, [StringComparison]::Ordinal)) {
        throw 'Odinstalacni stav nema platny identifikator produktu; externi checkpoint nebude zapsan.'
    }
    $installationId = [string]$script:InstallerState.InstallationId
    if ([string]::IsNullOrWhiteSpace($installationId)) {
        throw 'Odinstalacni stav nema InstallationId; externi checkpoint nebude zapsan.'
    }

    if (Test-Path -LiteralPath $UninstallRecoveryStatePath -PathType Leaf) {
        try {
            $existingRecovery = Get-Content -LiteralPath $UninstallRecoveryStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        catch {
            throw "Existujici externi checkpoint $UninstallRecoveryStatePath nelze overit a nebude prepsan. Detail: $($_.Exception.Message)"
        }
        $existingProperties = @($existingRecovery.PSObject.Properties.Name)
        if ($existingProperties -notcontains 'ProductId' -or
            -not [string]::Equals([string]$existingRecovery.ProductId, $ProductId, [StringComparison]::Ordinal) -or
            $existingProperties -notcontains 'InstallationId' -or
            -not [string]::Equals([string]$existingRecovery.InstallationId, $installationId, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Existujici externi checkpoint $UninstallRecoveryStatePath nepatri teto instalaci a nebude prepsan."
        }
    }

    $json = $script:InstallerState | ConvertTo-Json -Depth 20
    $temporaryPath = "$UninstallRecoveryStatePath.tmp"
    Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue
    Write-Utf8NoBom -Path $temporaryPath -Content ($json + "`r`n")
    Set-AdminOnlyFileAcl -Path $temporaryPath
    Move-Item -LiteralPath $temporaryPath -Destination $UninstallRecoveryStatePath -Force
    Set-AdminOnlyFileAcl -Path $UninstallRecoveryStatePath
}

function Write-InstallerState {
    if ($null -eq $script:InstallerState) { return }
    Ensure-Directory $InstallerStateDir
    $script:InstallerState.UpdatedAt = [DateTimeOffset]::Now.ToString('o')
    $json = $script:InstallerState | ConvertTo-Json -Depth 20
    $temporaryPath = "$InstallerStatePath.tmp"
    Write-Utf8NoBom -Path $temporaryPath -Content ($json + "`r`n")
    Move-Item -LiteralPath $temporaryPath -Destination $InstallerStatePath -Force
    Set-AdminOnlyFileAcl -Path $InstallerStatePath
}

function Initialize-InstallerState {
    if ($Action -in @('Install', 'Update') -and (Test-Path -LiteralPath $UninstallRecoveryStatePath -PathType Leaf)) {
        try {
            $pendingRecovery = Get-Content -LiteralPath $UninstallRecoveryStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        catch {
            throw "Vedle instalacniho adresare existuje necitelny odinstalacni checkpoint $UninstallRecoveryStatePath. Z bezpecnostnich duvodu nejprve spustte --uninstall."
        }
        $pendingProperties = @($pendingRecovery.PSObject.Properties.Name)
        if ($pendingProperties -notcontains 'ProductId' -or
            -not [string]::Equals([string]$pendingRecovery.ProductId, $ProductId, [StringComparison]::Ordinal)) {
            throw "Soubor $UninstallRecoveryStatePath nema vlastnictvi produktu $ProductId. Instalator jej nebude menit; pred pokracovanim konflikt vyreste rucne."
        }
        throw "Odinstalace teto instalace je v zaverecne fazi. Dokoncete ji prikazem --uninstall; --resume ani --update nesmi obnovit soubory po destruktivni fazi."
    }

    $existingState = Read-InstallerState
    if ($null -ne $existingState) {
        Add-StatePropertyIfMissing -State $existingState -Name 'SchemaVersion' -DefaultValue 5
        $existingState.SchemaVersion = 5
        Add-StatePropertyIfMissing -State $existingState -Name 'InstallerVersion' -DefaultValue $ScriptVersion
        Add-StatePropertyIfMissing -State $existingState -Name 'ProductId' -DefaultValue $ProductId
        if (-not [string]::Equals([string]$existingState.ProductId, $ProductId, [StringComparison]::Ordinal)) {
            throw "Stavovy soubor $InstallerStatePath patri jinemu produktu ('$($existingState.ProductId)') a nebude pouzit."
        }
        Add-StatePropertyIfMissing -State $existingState -Name 'InstallationId' -DefaultValue ([Guid]::NewGuid().ToString('D'))
        Add-StatePropertyIfMissing -State $existingState -Name 'Status' -DefaultValue 'Interrupted'
        Add-StatePropertyIfMissing -State $existingState -Name 'CurrentPhase' -DefaultValue ''
        Add-StatePropertyIfMissing -State $existingState -Name 'CompletedPhases' -DefaultValue @()
        Add-StatePropertyIfMissing -State $existingState -Name 'UninstallCompletedPhases' -DefaultValue @()
        Add-StatePropertyIfMissing -State $existingState -Name 'LastError' -DefaultValue ''
        Add-StatePropertyIfMissing -State $existingState -Name 'StartedAt' -DefaultValue ([DateTimeOffset]::Now.ToString('o'))
        Add-StatePropertyIfMissing -State $existingState -Name 'UpdatedAt' -DefaultValue ([DateTimeOffset]::Now.ToString('o'))
        Add-StatePropertyIfMissing -State $existingState -Name 'RootExistedBeforeInstaller' -DefaultValue $true
        Add-StatePropertyIfMissing -State $existingState -Name 'RootOriginalSddl' -DefaultValue ''
        Add-StatePropertyIfMissing -State $existingState -Name 'RootChildrenBeforeInstaller' -DefaultValue @()
        Add-StatePropertyIfMissing -State $existingState -Name 'AdoptedLegacyInstallation' -DefaultValue $false
        Add-StatePropertyIfMissing -State $existingState -Name 'ManagedTaskNames' -DefaultValue @()
        Add-StatePropertyIfMissing -State $existingState -Name 'FirewallRuleNames' -DefaultValue @()
        Add-StatePropertyIfMissing -State $existingState -Name 'AddedRootCertificates' -DefaultValue @()
        Add-StatePropertyIfMissing -State $existingState -Name 'PendingRootCertificateImports' -DefaultValue @()
        Add-StatePropertyIfMissing -State $existingState -Name 'PreexistingRootCertificates' -DefaultValue @()
        Add-StatePropertyIfMissing -State $existingState -Name 'LegacyRootCertificates' -DefaultValue @()
        Add-StatePropertyIfMissing -State $existingState -Name 'CertificateTrustRecords' -DefaultValue @()
        Add-StatePropertyIfMissing -State $existingState -Name 'PreserveDataRequested' -DefaultValue $false
        Add-StatePropertyIfMissing -State $existingState -Name 'PreservedDataPath' -DefaultValue ''
        $existingState.InstallerVersion = $ScriptVersion
        $script:InstallerState = $existingState
        Write-InstallerState

        if ($Action -in @('Install', 'Update') -and ([string]$existingState.Status).StartsWith('Uninstall', [StringComparison]::OrdinalIgnoreCase)) {
            throw "Odinstalace jiz byla zahajena (faze '$($existingState.CurrentPhase)'). Dokoncete ji prikazem --uninstall; instalaci nelze bezpecne obnovit po destruktivni odinstalacni fazi."
        }
        if ($Action -eq 'Install' -and -not $ResumeRequested -and [string]$existingState.Status -ne 'Installed') {
            throw "Predchozi instalace nebyla dokoncena (faze '$($existingState.CurrentPhase)'). Spustte stejny skript s --resume, nebo --uninstall."
        }
        if ($Action -eq 'Install' -and -not $ResumeRequested -and [string]$existingState.Status -eq 'Installed') {
            throw 'Instalace jiz existuje. Pro opravu nebo zmenu konfigurace pouzijte --resume; pro aktualizaci --update.'
        }
        return
    }

    $rootExisted = Test-Path -LiteralPath $InstallRoot -PathType Container
    $rootOriginalSddl = ''
    $rootAclCaptureError = ''
    $itemsBeforeInstaller = @()
    if ($rootExisted) {
        $itemsBeforeInstaller = @(Get-ChildItem -LiteralPath $InstallRoot -Force -ErrorAction SilentlyContinue)
        try {
            $sections = [Security.AccessControl.AccessControlSections]::Access -bor
                        [Security.AccessControl.AccessControlSections]::Owner -bor
                        [Security.AccessControl.AccessControlSections]::Group
            $rootOriginalSddl = (Get-Acl -LiteralPath $InstallRoot).GetSecurityDescriptorSddlForm($sections)
        }
        catch {
            $rootAclCaptureError = $_.Exception.Message
            Write-Caution "Puvodni ACL korenoveho adresare nelze zaznamenat: $rootAclCaptureError"
        }
    }

    $legacyMarkers = @(
        $RuntimeConfigPath,
        $VenvDir,
        $CaddyDataBase,
        $CaddyExe,
        $OpenWebUIExe
    ) | Where-Object { Test-Path -LiteralPath $_ }
    $looksLikeLegacyInstallation = @($legacyMarkers).Count -gt 0

    if ($rootExisted -and -not $looksLikeLegacyInstallation -and
        [string]::IsNullOrWhiteSpace($rootOriginalSddl) -and $Action -ne 'Uninstall') {
        throw "Puvodni ACL adresare $InstallRoot nelze zaznamenat, proto nelze garantovat vratnou instalaci. Detail: $rootAclCaptureError"
    }

    if ($rootExisted -and -not $looksLikeLegacyInstallation -and $itemsBeforeInstaller.Count -gt 0 -and $Action -ne 'Uninstall') {
        throw "Adresar $InstallRoot jiz existuje a neni prazdny ani rozpoznanou instalaci e-INFRA Open WebUI. Zvolte jiny --install-root."
    }

    if ($looksLikeLegacyInstallation -and $Action -eq 'Install' -and -not $ResumeRequested) {
        throw 'Byla nalezena instalace z drivejsi verze bez stavoveho souboru. Spustte tento skript s --resume.'
    }
    if ($looksLikeLegacyInstallation -and $ResumeRequested) {
        Write-Caution 'Prebiram instalaci 1.2.x bez puvodniho rollback snapshotu. Od teto chvile budou nove zmeny evidovany; --uninstall odstrani jednoznacne artefakty starsi instalace, ale nemuze rekonstruovat nezaznamenane zmeny, ktere provedla predchozi verze pred vznikem state.json.'
    }

    Ensure-Directory $InstallerStateDir
    Ensure-Directory $InstallerSnapshotDir
    $script:InstallerState = [pscustomobject][ordered]@{
        SchemaVersion = 5
        InstallerVersion = $ScriptVersion
        ProductId = $ProductId
        InstallationId = [Guid]::NewGuid().ToString('D')
        Status = 'Installing'
        CurrentPhase = 'initialization'
        CompletedPhases = @()
        UninstallCompletedPhases = @()
        LastError = ''
        StartedAt = [DateTimeOffset]::Now.ToString('o')
        UpdatedAt = [DateTimeOffset]::Now.ToString('o')
        RootExistedBeforeInstaller = [bool]$rootExisted
        RootOriginalSddl = $rootOriginalSddl
        RootChildrenBeforeInstaller = @($itemsBeforeInstaller | ForEach-Object { $_.Name })
        AdoptedLegacyInstallation = [bool]$looksLikeLegacyInstallation
        ManagedTaskNames = @()
        FirewallRuleNames = @()
        AddedRootCertificates = @()
        PendingRootCertificateImports = @()
        PreexistingRootCertificates = @()
        LegacyRootCertificates = @()
        CertificateTrustRecords = @()
        PreserveDataRequested = $false
        PreservedDataPath = ''
    }

    if ($looksLikeLegacyInstallation -and (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf)) {
        try {
            $legacyConfiguration = Read-RuntimeConfig
            if ($legacyConfiguration.PSObject.Properties.Name -contains 'LocalCaThumbprint') {
                $legacyThumbprint = Normalize-CertificateThumbprint -Thumbprint ([string]$legacyConfiguration.LocalCaThumbprint)
                if (-not [string]::IsNullOrWhiteSpace($legacyThumbprint)) {
                    $script:InstallerState.LegacyRootCertificates = @($legacyThumbprint)
                }
            }
        }
        catch {
            Write-Caution "Informace o lokalni CA ze starsi instalace nelze nacist: $($_.Exception.Message)"
        }
    }

    Write-InstallerState
}

function Invoke-InstallPhase {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Operation
    )

    $script:CurrentPhase = $Name
    if ($null -ne $script:InstallerState) {
        $script:InstallerState.Status = 'Installing'
        $script:InstallerState.CurrentPhase = $Name
        $script:InstallerState.LastError = ''
        $script:InstallerState.InstallerVersion = $ScriptVersion
        Write-InstallerState
    }

    try {
        & $Operation
        if ($null -ne $script:InstallerState) {
            $completed = @($script:InstallerState.CompletedPhases)
            if ($completed -notcontains $Name) {
                $script:InstallerState.CompletedPhases = @($completed + $Name)
            }
            Write-InstallerState
        }
    }
    catch {
        if ($null -ne $script:InstallerState) {
            $script:InstallerState.Status = 'Interrupted'
            $script:InstallerState.CurrentPhase = $Name
            $script:InstallerState.LastError = $_.Exception.Message
            Write-InstallerState
        }
        throw
    }
}

function Clear-ResumeBootstrapPassword {
    if (-not (Test-Path -LiteralPath $InstallerResumeConfigPath -PathType Leaf)) { return }
    try {
        $saved = Get-Content -LiteralPath $InstallerResumeConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($saved.PSObject.Properties.Name -contains 'AdminPassword' -and
            -not [string]::IsNullOrWhiteSpace([string]$saved.AdminPassword)) {
            $saved.AdminPassword = ''
            $json = $saved | ConvertTo-Json -Depth 10
            $temporaryPath = "$InstallerResumeConfigPath.tmp"
            Write-Utf8NoBom -Path $temporaryPath -Content ($json + "`r`n")
            Set-AdminOnlyFileAcl -Path $temporaryPath
            Move-Item -LiteralPath $temporaryPath -Destination $InstallerResumeConfigPath -Force
            Set-AdminOnlyFileAcl -Path $InstallerResumeConfigPath
        }
    }
    catch {
        Write-Caution "Docasne bootstrap heslo se nepodarilo odstranit z resume konfigurace: $($_.Exception.Message)"
    }
}

function Invoke-UninstallPhase {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Operation
    )

    $script:CurrentPhase = $Name
    if ($null -ne $script:InstallerState) {
        Add-StatePropertyIfMissing -State $script:InstallerState -Name 'UninstallCompletedPhases' -DefaultValue @()
        $completed = @($script:InstallerState.UninstallCompletedPhases)
        if ($completed -contains $Name) {
            Write-Notice "Odinstalacni faze '$Name' byla jiz dokoncena; znovu ji idempotentne overuji."
        }
        $script:InstallerState.Status = 'Uninstalling'
        $script:InstallerState.CurrentPhase = $Name
        $script:InstallerState.LastError = ''
        $script:InstallerState.InstallerVersion = $ScriptVersion
        Write-InstallerState
    }

    try {
        & $Operation
        if ($null -ne $script:InstallerState) {
            $completed = @($script:InstallerState.UninstallCompletedPhases)
            if ($completed -notcontains $Name) {
                $script:InstallerState.UninstallCompletedPhases = @($completed + $Name)
            }
            Write-InstallerState
        }
    }
    catch {
        if ($null -ne $script:InstallerState) {
            $script:InstallerState.Status = 'UninstallInterrupted'
            $script:InstallerState.CurrentPhase = $Name
            $script:InstallerState.LastError = $_.Exception.Message
            Write-InstallerState
        }
        throw
    }
}

function Set-InstallerCompleted {
    if ($null -eq $script:InstallerState) { return }
    $script:InstallerState.Status = 'Installed'
    $script:InstallerState.CurrentPhase = 'completed'
    $script:InstallerState.LastError = ''
    $script:InstallerState.InstallerVersion = $ScriptVersion
    $script:InstallerState.UninstallCompletedPhases = @()
    $script:InstallerState.PreserveDataRequested = $false
    $script:InstallerState.PreservedDataPath = ''
    Write-InstallerState
    Clear-ResumeBootstrapPassword
}

function Set-InstallerFailed {
    param([Parameter(Mandatory = $true)]$ErrorRecord)
    if ($null -eq $script:InstallerState) { return }
    if (([string]$script:InstallerState.Status).StartsWith('Uninstall', [StringComparison]::OrdinalIgnoreCase)) {
        # Pokus o --resume nesmi prepsat checkpoint rozpracovane odinstalace.
        return
    }
    try {
        $script:InstallerState.Status = 'Interrupted'
        if (-not [string]::IsNullOrWhiteSpace($script:CurrentPhase)) {
            $script:InstallerState.CurrentPhase = $script:CurrentPhase
        }
        $script:InstallerState.LastError = [string]$ErrorRecord.Exception.Message
        Write-InstallerState
    }
    catch { }
}

function ConvertFrom-EnvironmentBoolean {
    param([AllowNull()]$Value, [bool]$DefaultValue)
    if ($null -eq $Value) { return $DefaultValue }
    switch (([string]$Value).Trim().ToLowerInvariant()) {
        'true' { return $true }
        '1' { return $true }
        'yes' { return $true }
        'false' { return $false }
        '0' { return $false }
        'no' { return $false }
        default { return $DefaultValue }
    }
}

function Apply-RequestedConfigurationProfile {
    # Explicitni CLI volby maji prednost. Bez nich je profil z tohoto skriptu
    # autoritativni i pri --resume, aby stara runtime/resume konfigurace
    # nevratila LocalCA nebo predchozi omezujici hodnoty.
    $certificateWasExplicit =
        $CliSpecified.ContainsKey('CertificateMode') -or
        $CliSpecified.ContainsKey('PublicDomain') -or
        $CliSpecified.ContainsKey('LocalAccessName') -or
        $CliSpecified.ContainsKey('Fqdn')

    if (-not $certificateWasExplicit) {
        $script:CertificateMode = $ProfileCertificateMode
        $script:PublicDomain = $ProfilePublicDomain
        $script:LocalAccessName = ''
    }
    if (-not $CliSpecified.ContainsKey('AcmeEmail')) {
        $script:AcmeEmail = ''
    }

    if (-not $CliSpecified.ContainsKey('ApiBaseUrl')) {
        $script:ApiBaseUrl = $ProfileApiBaseUrl
    }
    if (-not $CliSpecified.ContainsKey('DefaultModel')) {
        $script:DefaultModel = $ProfileDefaultModel
    }
    if (-not $CliSpecified.ContainsKey('OpenWebUIVersion')) {
        # Nevracej automaticky jiz aktualizovanou instalaci na profilovou
        # minimalni verzi. Skutecny cil se jeste urci online kontrolou vydani.
        $currentVersion = ConvertTo-OpenWebUIVersionObject -Value $script:OpenWebUIVersion
        $profileVersion = ConvertTo-OpenWebUIVersionObject -Value $ProfileOpenWebUIVersion
        if ($null -eq $currentVersion -or $currentVersion -lt $profileVersion) {
            $script:OpenWebUIVersion = $ProfileOpenWebUIVersion
        }
    }
    if (-not $CliSpecified.ContainsKey('OpenWebUIUpdatePolicy') -and
        $script:OpenWebUIUpdatePolicy -notin @('Patch', 'Stable', 'Off')) {
        $script:OpenWebUIUpdatePolicy = 'Patch'
    }
    if (-not $CliSpecified.ContainsKey('MinimumReleaseAgeHours') -and
        ($script:MinimumReleaseAgeHours -lt 0 -or $script:MinimumReleaseAgeHours -gt 8760)) {
        $script:MinimumReleaseAgeHours = 48
    }
    if (-not $CliSpecified.ContainsKey('BackendPort')) { $script:BackendPort = 18080 }
    if (-not $CliSpecified.ContainsKey('HttpPort')) { $script:HttpPort = 80 }
    if (-not $CliSpecified.ContainsKey('HttpsPort')) { $script:HttpsPort = 443 }
    if (-not $CliSpecified.ContainsKey('DisableSignup')) { $script:DisableSignup = $false }
    if (-not $CliSpecified.ContainsKey('AllowAdminUiOverrides')) { $script:AllowAdminUiOverrides = $true }
    if (-not $CliSpecified.ContainsKey('EnableDirectConnections')) { $script:EnableDirectConnections = $true }

    # Hodnota byla uzivatelem vyslovne dodana. Pouziva se i pri migraci, aby
    # nedoslo k nahodne rotaci JWT/OAuth klice.
    $script:ResumeWebUiSecret = $ProfileWebUiSecret
}

function Import-ExistingConfigurationForResume {
    if (-not (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf)) { return }

    try {
        $configuration = Read-RuntimeConfig
    }
    catch {
        # Resume konfigurace je zapisovana atomicky a obsahuje vstupni hodnoty
        # i WEBUI_SECRET_KEY. Poskozeny runtime.json tedy nesmi zablokovat opravu.
        Write-Caution "Stavajici runtime.json nelze pri --resume nacist; bude znovu vytvoren z chranene resume konfigurace. Detail: $($_.Exception.Message)"
        return
    }

    $configProperties = @($configuration.PSObject.Properties.Name)
    $environmentProperties = @()
    if ($configProperties -contains 'Environment' -and $null -ne $configuration.Environment) {
        $environmentProperties = @($configuration.Environment.PSObject.Properties.Name)
    }

    if (-not $CliSpecified.ContainsKey('CertificateMode') -and $configProperties -contains 'CertificateMode') {
        $script:CertificateMode = [string]$configuration.CertificateMode
    }
    if (-not $CliSpecified.ContainsKey('PublicDomain') -and $configProperties -contains 'PublicDomain') {
        $script:PublicDomain = [string]$configuration.PublicDomain
    }
    if (-not $CliSpecified.ContainsKey('AcmeEmail') -and $configProperties -contains 'AcmeEmail') {
        $script:AcmeEmail = [string]$configuration.AcmeEmail
    }
    if (-not $CliSpecified.ContainsKey('LocalAccessName') -and
        $script:CertificateMode -eq 'LocalCA' -and
        $configProperties -contains 'LocalAccessName') {
        $script:LocalAccessName = [string]$configuration.LocalAccessName
    }
    if (-not $CliSpecified.ContainsKey('BackendPort') -and $configProperties -contains 'BackendPort') {
        $script:BackendPort = [int]$configuration.BackendPort
    }
    if (-not $CliSpecified.ContainsKey('HttpPort') -and $configProperties -contains 'HttpPort') {
        $script:HttpPort = [int]$configuration.HttpPort
    }
    if (-not $CliSpecified.ContainsKey('HttpsPort') -and $configProperties -contains 'HttpsPort') {
        $script:HttpsPort = [int]$configuration.HttpsPort
    }
    if (-not $CliSpecified.ContainsKey('OpenWebUIVersion') -and
        $configProperties -contains 'RequestedOpenWebUIVersion' -and
        -not [string]::IsNullOrWhiteSpace([string]$configuration.RequestedOpenWebUIVersion)) {
        $script:OpenWebUIVersion = [string]$configuration.RequestedOpenWebUIVersion
    }
    if (-not $CliSpecified.ContainsKey('OpenWebUIUpdatePolicy') -and
        $configProperties -contains 'OpenWebUIUpdatePolicy' -and
        [string]$configuration.OpenWebUIUpdatePolicy -in @('Patch', 'Stable', 'Off')) {
        $script:OpenWebUIUpdatePolicy = [string]$configuration.OpenWebUIUpdatePolicy
    }
    if (-not $CliSpecified.ContainsKey('MinimumReleaseAgeHours') -and
        $configProperties -contains 'MinimumReleaseAgeHours') {
        $savedAge = [int]$configuration.MinimumReleaseAgeHours
        if ($savedAge -ge 0 -and $savedAge -le 8760) {
            $script:MinimumReleaseAgeHours = $savedAge
        }
    }

    if (-not $CliSpecified.ContainsKey('ApiBaseUrl') -and $environmentProperties -contains 'OPENAI_API_BASE_URL') {
        $script:ApiBaseUrl = [string]$configuration.Environment.OPENAI_API_BASE_URL
    }
    if (-not $CliSpecified.ContainsKey('ApiKey') -and $environmentProperties -contains 'OPENAI_API_KEY') {
        $script:ApiKey = [string]$configuration.Environment.OPENAI_API_KEY
    }
    if ($environmentProperties -contains 'WEBUI_SECRET_KEY' -and
        -not [string]::IsNullOrWhiteSpace([string]$configuration.Environment.WEBUI_SECRET_KEY)) {
        $script:ResumeWebUiSecret = [string]$configuration.Environment.WEBUI_SECRET_KEY
    }
    if (-not $CliSpecified.ContainsKey('DefaultModel') -and $environmentProperties -contains 'DEFAULT_MODELS') {
        $script:DefaultModel = [string]$configuration.Environment.DEFAULT_MODELS
    }
    if (-not $CliSpecified.ContainsKey('DisableSignup') -and $environmentProperties -contains 'ENABLE_SIGNUP') {
        $script:DisableSignup = -not (ConvertFrom-EnvironmentBoolean -Value $configuration.Environment.ENABLE_SIGNUP -DefaultValue $true)
    }
    if (-not $CliSpecified.ContainsKey('AllowAdminUiOverrides') -and $environmentProperties -contains 'ENABLE_PERSISTENT_CONFIG') {
        $script:AllowAdminUiOverrides = ConvertFrom-EnvironmentBoolean -Value $configuration.Environment.ENABLE_PERSISTENT_CONFIG -DefaultValue $false
    }
    if (-not $CliSpecified.ContainsKey('EnableDirectConnections') -and $environmentProperties -contains 'ENABLE_DIRECT_CONNECTIONS') {
        $script:EnableDirectConnections = ConvertFrom-EnvironmentBoolean -Value $configuration.Environment.ENABLE_DIRECT_CONNECTIONS -DefaultValue $false
    }
    if (-not $CliSpecified.ContainsKey('AdminEmail') -and $environmentProperties -contains 'WEBUI_ADMIN_EMAIL') {
        $script:AdminEmail = [string]$configuration.Environment.WEBUI_ADMIN_EMAIL
    }
    if (-not $CliSpecified.ContainsKey('AdminName') -and $environmentProperties -contains 'WEBUI_ADMIN_NAME') {
        $script:AdminName = [string]$configuration.Environment.WEBUI_ADMIN_NAME
    }

    if ($script:CertificateMode -eq 'LocalCA' -and
        -not $CliSpecified.ContainsKey('LocalAccessName') -and
        [string]::IsNullOrWhiteSpace($script:LocalAccessName) -and
        $configProperties -contains 'SiteHosts') {
        foreach ($candidate in @($configuration.SiteHosts)) {
            $text = ([string]$candidate).Trim().TrimEnd('.').ToLowerInvariant()
            $parsedAddress = $null
            if ($text -like '*.*' -and
                $text -ne 'localhost' -and
                -not [Net.IPAddress]::TryParse($text, [ref]$parsedAddress)) {
                $script:LocalAccessName = $text
                break
            }
        }
    }

    if ($script:CertificateMode -eq 'PublicACME' -and -not $CliSpecified.ContainsKey('LocalAccessName')) {
        $script:LocalAccessName = ''
    }

    Write-Notice 'Pro --resume byla prevzata stavajici konfigurace a tajne hodnoty z runtime.json; explicitni volby prikazoveho radku maji prednost.'
}

function Write-ResumeConfiguration {
    $resumeConfiguration = [ordered]@{
        SchemaVersion = 1
        InstallerVersion = $ScriptVersion
        ProductId = $ProductId
        RequestedOpenWebUIVersion = $OpenWebUIVersion
        PythonVersion = '3.11'
        CertificateMode = $CertificateMode
        PublicDomain = $PublicDomain
        AcmeEmail = $AcmeEmail
        LocalAccessName = $LocalAccessName
        ApiKey = $ApiKey
        ApiBaseUrl = $ApiBaseUrl
        DefaultModel = $DefaultModel
        OpenWebUIVersion = $OpenWebUIVersion
        OpenWebUIUpdatePolicy = $OpenWebUIUpdatePolicy
        MinimumReleaseAgeHours = $MinimumReleaseAgeHours
        AllowOpenWebUIDowngrade = [bool]$AllowOpenWebUIDowngrade
        BackendPort = $BackendPort
        HttpPort = $HttpPort
        HttpsPort = $HttpsPort
        AdminEmail = $AdminEmail
        AdminName = $AdminName
        AdminPassword = $AdminPassword
        WebUiSecret = $ResumeWebUiSecret
        DisableSignup = [bool]$DisableSignup
        AllowAdminUiOverrides = [bool]$AllowAdminUiOverrides
        EnableDirectConnections = [bool]$EnableDirectConnections
    }
    $json = $resumeConfiguration | ConvertTo-Json -Depth 10
    $temporaryPath = "$InstallerResumeConfigPath.tmp"
    Write-Utf8NoBom -Path $temporaryPath -Content ($json + "`r`n")
    Set-AdminOnlyFileAcl -Path $temporaryPath
    Move-Item -LiteralPath $temporaryPath -Destination $InstallerResumeConfigPath -Force
    Set-AdminOnlyFileAcl -Path $InstallerResumeConfigPath
}

function Import-ResumeConfiguration {
    if (-not (Test-Path -LiteralPath $InstallerResumeConfigPath -PathType Leaf)) { return }
    try {
        $saved = Get-Content -LiteralPath $InstallerResumeConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $properties = @($saved.PSObject.Properties.Name)
        if ($properties -contains 'ProductId' -and
            -not [string]::Equals([string]$saved.ProductId, $ProductId, [StringComparison]::Ordinal)) {
            throw "Ulozena resume konfigurace patri jinemu produktu ('$($saved.ProductId)')."
        }
        $mappings = @(
            @{ Key='CertificateMode'; Variable='CertificateMode'; Type='String' },
            @{ Key='PublicDomain'; Variable='PublicDomain'; Type='String' },
            @{ Key='AcmeEmail'; Variable='AcmeEmail'; Type='String' },
            @{ Key='LocalAccessName'; Variable='LocalAccessName'; Type='String' },
            @{ Key='ApiKey'; Variable='ApiKey'; Type='String' },
            @{ Key='ApiBaseUrl'; Variable='ApiBaseUrl'; Type='String' },
            @{ Key='DefaultModel'; Variable='DefaultModel'; Type='String' },
            @{ Key='OpenWebUIVersion'; Variable='OpenWebUIVersion'; Type='String' },
            @{ Key='OpenWebUIUpdatePolicy'; Variable='OpenWebUIUpdatePolicy'; Type='String' },
            @{ Key='MinimumReleaseAgeHours'; Variable='MinimumReleaseAgeHours'; Type='Int' },
            @{ Key='AllowOpenWebUIDowngrade'; Variable='AllowOpenWebUIDowngrade'; Type='Bool' },
            @{ Key='BackendPort'; Variable='BackendPort'; Type='Int' },
            @{ Key='HttpPort'; Variable='HttpPort'; Type='Int' },
            @{ Key='HttpsPort'; Variable='HttpsPort'; Type='Int' },
            @{ Key='AdminEmail'; Variable='AdminEmail'; Type='String' },
            @{ Key='AdminName'; Variable='AdminName'; Type='String' },
            @{ Key='AdminPassword'; Variable='AdminPassword'; Type='String' },
            @{ Key='WebUiSecret'; Variable='ResumeWebUiSecret'; Type='String' },
            @{ Key='DisableSignup'; Variable='DisableSignup'; Type='Bool' },
            @{ Key='AllowAdminUiOverrides'; Variable='AllowAdminUiOverrides'; Type='Bool' },
            @{ Key='EnableDirectConnections'; Variable='EnableDirectConnections'; Type='Bool' }
        )
        foreach ($mapping in $mappings) {
            $key = [string]$mapping.Key
            if ($CliSpecified.ContainsKey($key) -or $properties -notcontains $key) { continue }
            $value = $saved.$key
            switch ([string]$mapping.Type) {
                'Int' { Set-Variable -Scope Script -Name ([string]$mapping.Variable) -Value ([int]$value) }
                'Bool' { Set-Variable -Scope Script -Name ([string]$mapping.Variable) -Value ([bool]$value) }
                default { Set-Variable -Scope Script -Name ([string]$mapping.Variable) -Value ([string]$value) }
            }
        }
        if ($script:CertificateMode -eq 'PublicACME' -and -not $CliSpecified.ContainsKey('LocalAccessName')) {
            $script:LocalAccessName = ''
        }
    }
    catch {
        Write-Caution "Ulozenou konfiguraci pro --resume nelze nacist: $($_.Exception.Message)"
    }
}

function Remove-ManagedPathWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [ValidateRange(1, 20)][int]$Attempts = 6
    )

    if (-not (Test-Path -LiteralPath $Path)) { return }
    $lastError = ''
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        }
        catch {
            $lastError = $_.Exception.Message
            if ($attempt -lt $Attempts) {
                Stop-ManagedProcesses
                Start-Sleep -Milliseconds (500 * $attempt)
            }
        }
    }
    throw "Cestu $Path nelze odebrat ani po $Attempts pokusech. Detail: $lastError"
}

function Restore-OriginalRootAcl {
    param(
        [AllowEmptyString()][string]$Sddl,
        [switch]$ThrowOnFailure
    )
    if ([string]::IsNullOrWhiteSpace($Sddl) -or -not (Test-Path -LiteralPath $InstallRoot -PathType Container)) {
        if ([string]::IsNullOrWhiteSpace($Sddl) -and $ThrowOnFailure) {
            throw 'Puvodni ACL korenoveho adresare nebyla pri instalaci dostupna; nelze ji presne obnovit.'
        }
        return
    }
    try {
        $security = New-Object Security.AccessControl.DirectorySecurity
        $sections = [Security.AccessControl.AccessControlSections]::Access -bor
                    [Security.AccessControl.AccessControlSections]::Owner -bor
                    [Security.AccessControl.AccessControlSections]::Group
        $security.SetSecurityDescriptorSddlForm($Sddl, $sections)
        Set-Acl -LiteralPath $InstallRoot -AclObject $security
        Write-Ok "Puvodni ACL adresare $InstallRoot byla obnovena."
    }
    catch {
        $message = "Puvodni ACL adresare $InstallRoot se nepodarilo obnovit: $($_.Exception.Message)"
        if ($ThrowOnFailure) { throw $message }
        Write-Caution $message
    }
}

function Assert-WindowsAndAdministrator {
    if ($env:OS -ne 'Windows_NT') {
        throw 'Tento skript je urcen pouze pro Windows.'
    }

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Skript musi bezet jako spravce (Run as administrator).'
    }
}

function Write-Utf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Content
    )
    $encoding = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Ensure-Directory {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function ConvertTo-NativeCommandLineArgument {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Value
    )

    # ProcessStartInfo na .NET Frameworku pouzivanem Windows PowerShellem 5.1
    # nema kolekci ArgumentList. Proto sestavujeme prikazovy radek podle pravidel
    # Windows CommandLineToArgvW/CRT, vcetne zpetnych lomitek pred uvozovkami.
    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') {
        return $Value
    }

    $builder = New-Object Text.StringBuilder
    [void]$builder.Append([char]34)
    $backslashCount = 0

    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq [char]92) {
            $backslashCount++
            continue
        }

        if ($character -eq [char]34) {
            for ($index = 0; $index -lt (($backslashCount * 2) + 1); $index++) {
                [void]$builder.Append([char]92)
            }
            [void]$builder.Append([char]34)
            $backslashCount = 0
            continue
        }

        for ($index = 0; $index -lt $backslashCount; $index++) {
            [void]$builder.Append([char]92)
        }
        $backslashCount = 0
        [void]$builder.Append($character)
    }

    # Koncova zpetna lomitka musi byt uvnitr uzaviracich uvozovek zdvojena.
    for ($index = 0; $index -lt ($backslashCount * 2); $index++) {
        [void]$builder.Append([char]92)
    }
    [void]$builder.Append([char]34)
    return $builder.ToString()
}

function New-NativeProcessStartInfo {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @()
    )

    $encodedArguments = foreach ($argument in $Arguments) {
        ConvertTo-NativeCommandLineArgument -Value ([string]$argument)
    }

    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $Executable
    $startInfo.Arguments = ($encodedArguments -join ' ')
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    return $startInfo
}

function Invoke-NativeCommandCapture {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @()
    )

    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw "Spustitelny soubor nebyl nalezen: $Executable"
    }

    # Nepouzivame LASTEXITCODE. Skutecny navratovy kod cteme primo z procesu,
    # cimz se vyhneme rozdilum scope a prevodu stderr na PowerShell ErrorRecord.
    $startInfo = New-NativeProcessStartInfo -Executable $Executable -Arguments $Arguments
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    $stdout = ''
    $stderr = ''
    $exitCode = 1

    try {
        if (-not $process.Start()) {
            throw 'System.Diagnostics.Process.Start vratil hodnotu False.'
        }

        # Oba proudy se ctou soubezne, aby se proces nezablokoval pri zaplneni
        # jednoho z presmerovanych bufferu.
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $stdout = [string]$stdoutTask.GetAwaiter().GetResult()
        $stderr = [string]$stderrTask.GetAwaiter().GetResult()
        $exitCode = [int]$process.ExitCode
    }
    catch {
        throw "Nativni program '$Executable' se nepodarilo spustit nebo dokoncit: $($_.Exception.Message)"
    }
    finally {
        $process.Dispose()
    }

    $stdout = $stdout.TrimEnd([char[]]"`r`n")
    $stderr = $stderr.TrimEnd([char[]]"`r`n")
    $outputParts = @()
    if (-not [string]::IsNullOrWhiteSpace($stdout)) {
        $outputParts += $stdout
    }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        $outputParts += $stderr
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($outputParts -join [Environment]::NewLine)
        StdOut = $stdout
        StdErr = $stderr
    }
}

function Invoke-NativeCommandPassthrough {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @()
    )

    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw "Spustitelny soubor nebyl nalezen: $Executable"
    }

    $startInfo = New-NativeProcessStartInfo -Executable $Executable -Arguments $Arguments
    $startInfo.CreateNoWindow = $false
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo

    try {
        if (-not $process.Start()) {
            throw 'System.Diagnostics.Process.Start vratil hodnotu False.'
        }
        $process.WaitForExit()
        return [int]$process.ExitCode
    }
    catch {
        throw "Nativni program '$Executable' se nepodarilo spustit nebo dokoncit: $($_.Exception.Message)"
    }
    finally {
        $process.Dispose()
    }
}

function Set-PrivateAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    # SIDy jsou nezavisle na jazyku Windows:
    # S-1-5-18 = LOCAL SYSTEM, S-1-5-19 = LOCAL SERVICE,
    # S-1-5-32-544 = BUILTIN\Administrators.
    # Sluzby maji na koreni pouze cteni/spousteni. Zapis dostanou jen do
    # datovych, logovacich a Caddy runtime adresaru.
    $icaclsExe = "$env:SystemRoot\System32\icacls.exe"
    $rootAclResult = Invoke-NativeCommandCapture -Executable $icaclsExe -Arguments @(
        $Path,
        '/inheritance:r',
        '/grant:r',
        '*S-1-5-18:(OI)(CI)F',
        '*S-1-5-32-544:(OI)(CI)F',
        '*S-1-5-19:(OI)(CI)RX'
    )
    if ($rootAclResult.ExitCode -ne 0) {
        throw "Nepodarilo se nastavit ACL adresare $Path (exit code $($rootAclResult.ExitCode)): $($rootAclResult.Output)"
    }

    foreach ($writablePath in @($DataDir, $LogDir, $CaddyDataBase, $CaddyConfigBase)) {
        $writableAclResult = Invoke-NativeCommandCapture -Executable $icaclsExe -Arguments @(
            $writablePath,
            '/inheritance:r',
            '/grant:r',
            '*S-1-5-18:(OI)(CI)F',
            '*S-1-5-32-544:(OI)(CI)F',
            '*S-1-5-19:(OI)(CI)M'
        )
        if ($writableAclResult.ExitCode -ne 0) {
            throw "Nepodarilo se nastavit zapisova ACL adresare $writablePath (exit code $($writableAclResult.ExitCode)): $($writableAclResult.Output)"
        }
    }

    foreach ($adminOnlyPath in @($AdminDir, $BackupDir, $DownloadDir, $UvCacheDir, $InstallerStateDir)) {
        $adminAclResult = Invoke-NativeCommandCapture -Executable $icaclsExe -Arguments @(
            $adminOnlyPath,
            '/inheritance:r',
            '/grant:r',
            '*S-1-5-18:(OI)(CI)F',
            '*S-1-5-32-544:(OI)(CI)F'
        )
        if ($adminAclResult.ExitCode -ne 0) {
            throw "Nepodarilo se nastavit administratorska ACL adresare $adminOnlyPath (exit code $($adminAclResult.ExitCode)): $($adminAclResult.Output)"
        }
    }
}

function Set-AdminOnlyFileAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    $icaclsExe = "$env:SystemRoot\System32\icacls.exe"
    $fileAclResult = Invoke-NativeCommandCapture -Executable $icaclsExe -Arguments @(
        $Path,
        '/inheritance:r',
        '/grant:r',
        '*S-1-5-18:F',
        '*S-1-5-32-544:F'
    )
    if ($fileAclResult.ExitCode -ne 0) {
        throw "Nepodarilo se nastavit administratorska ACL souboru $Path (exit code $($fileAclResult.ExitCode)): $($fileAclResult.Output)"
    }
}

function Reset-TreeToInheritedAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    # /reset nahradi ACL vsech polozek vychozimi zdedenymi ACL z aktualniho
    # rodice. Pouziva se az po instalaci balicku, aby runtime soubory zdedily
    # read/execute pro LOCAL SERVICE a nezustaly svazane s ACL uv cache.
    $icaclsExe = "$env:SystemRoot\System32\icacls.exe"
    $aclResult = Invoke-NativeCommandCapture -Executable $icaclsExe -Arguments @(
        $Path,
        '/reset',
        '/T',
        '/C',
        '/Q'
    )
    if ($aclResult.ExitCode -ne 0) {
        throw "Nepodarilo se obnovit zdedena ACL stromu $Path (exit code $($aclResult.ExitCode)): $($aclResult.Output)"
    }
}

function Assert-LocalServiceReadAccess {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Soubor pro kontrolu runtime opravneni nebyl nalezen: $Path"
    }

    $localServiceSid = New-Object Security.Principal.SecurityIdentifier -ArgumentList 'S-1-5-19'
    $acl = Get-Acl -LiteralPath $Path
    $rules = $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])

    $requiredMask = [int][Security.AccessControl.FileSystemRights]::ReadAndExecute
    $allowMask = 0
    $denyMask = 0

    foreach ($rule in $rules) {
        if ([string]$rule.IdentityReference.Value -ne $localServiceSid.Value) {
            continue
        }

        $ruleMask = [int]$rule.FileSystemRights
        if ($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow) {
            $allowMask = $allowMask -bor $ruleMask
        }
        else {
            $denyMask = $denyMask -bor $ruleMask
        }
    }

    if (($denyMask -band $requiredMask) -ne 0 -or
        ($allowMask -band $requiredMask) -ne $requiredMask) {
        throw "Ucet LOCAL SERVICE nema read/execute k runtime souboru: $Path"
    }
}

function Get-NativeArchitecture {
    $architecture = $env:PROCESSOR_ARCHITEW6432
    if ([string]::IsNullOrWhiteSpace($architecture)) {
        $architecture = $env:PROCESSOR_ARCHITECTURE
    }

    switch ($architecture.ToUpperInvariant()) {
        'AMD64' { return 'amd64' }
        'ARM64' { return 'arm64' }
        default { throw "Nepodporovana architektura Windows: $architecture. Vyzaduje se x64 nebo ARM64." }
    }
}

function New-RandomHex {
    param([ValidateRange(16, 128)][int]$Bytes = 32)
    $buffer = New-Object byte[] $Bytes
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($buffer)
    }
    finally {
        $rng.Dispose()
    }
    return (-join ($buffer | ForEach-Object { $_.ToString('x2') }))
}

function New-RandomPassword {
    param([ValidateRange(16, 72)][int]$Length = 28)

    # Heslo vzdy obsahuje vsechny kategorie pozadovane validacnim regexem.
    # Bez uvozovek a zpetnych apostrofu, aby bylo snadno pouzitelne v shellu.
    $upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
    $lower = 'abcdefghijkmnopqrstuvwxyz'
    $digits = '23456789'
    $special = '!@#%-+='
    $alphabet = $upper + $lower + $digits + $special
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()

    function Get-CryptoIndex {
        param(
            [Parameter(Mandatory = $true)]$Generator,
            [ValidateRange(1, 65535)][int]$Maximum
        )
        $buffer = New-Object byte[] 4
        $Generator.GetBytes($buffer)
        $number = [BitConverter]::ToUInt32($buffer, 0)
        return [int]($number % [uint32]$Maximum)
    }

    try {
        $characters = [Collections.Generic.List[char]]::new()
        foreach ($group in @($upper, $lower, $digits, $special)) {
            $characters.Add($group[(Get-CryptoIndex -Generator $rng -Maximum $group.Length)])
        }
        while ($characters.Count -lt $Length) {
            $characters.Add($alphabet[(Get-CryptoIndex -Generator $rng -Maximum $alphabet.Length)])
        }

        # Fisher-Yates shuffle, aby povinne znaky nebyly vzdy na zacatku.
        for ($i = $characters.Count - 1; $i -gt 0; $i--) {
            $j = Get-CryptoIndex -Generator $rng -Maximum ($i + 1)
            $temporary = $characters[$i]
            $characters[$i] = $characters[$j]
            $characters[$j] = $temporary
        }
        return -join $characters.ToArray()
    }
    finally {
        $rng.Dispose()
    }
}

function Invoke-DownloadFile {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Destination,
        [switch]$AlwaysDownload
    )

    Ensure-Directory (Split-Path -Parent $Destination)
    if ((Test-Path -LiteralPath $Destination) -and -not $AlwaysDownload) {
        return
    }

    $temporary = "$Destination.partial"
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue

    $headers = @{ 'User-Agent' = "EInfra-OpenWebUI-Installer/$ScriptVersion" }
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Uri -Headers $headers -OutFile $temporary
        Move-Item -LiteralPath $temporary -Destination $Destination -Force
    }
    catch {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        throw "Stazeni selhalo: $Uri`n$($_.Exception.Message)"
    }
}

function Assert-FileHash {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedHash
    )

    $hash = $ExpectedHash.Trim().ToLowerInvariant()
    if ($hash.Length -eq 64) {
        $algorithm = 'SHA256'
    }
    elseif ($hash.Length -eq 128) {
        $algorithm = 'SHA512'
    }
    else {
        throw "Nepodporovana delka kontrolniho souctu pro $Path."
    }

    $actual = (Get-FileHash -LiteralPath $Path -Algorithm $algorithm).Hash.ToLowerInvariant()
    if ($actual -ne $hash) {
        throw "Kontrolni soucet nesouhlasi pro $Path. Ocekavano: $hash; zjisteno: $actual"
    }
}

function Expand-ZipClean {
    param(
        [Parameter(Mandatory = $true)][string]$ZipPath,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }
    Ensure-Directory $Destination
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $Destination -Force
}

function Install-Uv {
    Write-Step 'Stahuji a overuji spravce Pythonu uv'

    if ($ResumeRequested -and -not $ForceDownload -and (Test-Path -LiteralPath $UvExe -PathType Leaf)) {
        try {
            $existingUv = Invoke-NativeCommandCapture -Executable $UvExe -Arguments @('--version')
            if ($existingUv.ExitCode -eq 0) {
                Write-Ok "Pouzivam existujici $($existingUv.Output); pri --resume se funkcni komponenta zbytecne nestahuje."
                return
            }
            Write-Caution "Existujici uv neproslo kontrolou a bude nainstalovano znovu: $($existingUv.Output)"
        }
        catch {
            Write-Caution "Existujici uv nelze overit a bude nainstalovano znovu: $($_.Exception.Message)"
        }
    }

    $arch = Get-NativeArchitecture
    if ($arch -eq 'amd64') {
        $assetName = 'uv-x86_64-pc-windows-msvc.zip'
    }
    else {
        $assetName = 'uv-aarch64-pc-windows-msvc.zip'
    }

    $baseUri = 'https://github.com/astral-sh/uv/releases/latest/download'
    $zipPath = Join-Path $DownloadDir $assetName
    $checksumPath = "$zipPath.sha256"

    Invoke-DownloadFile -Uri "$baseUri/$assetName" -Destination $zipPath -AlwaysDownload:($ForceDownload -or $Action -eq 'Update')
    Invoke-DownloadFile -Uri "$baseUri/$assetName.sha256" -Destination $checksumPath -AlwaysDownload:($ForceDownload -or $Action -eq 'Update')

    $checksumText = [IO.File]::ReadAllText($checksumPath)
    $match = [regex]::Match($checksumText, '(?i)\b[0-9a-f]{64}\b')
    if (-not $match.Success) {
        throw "V souboru $checksumPath nebyl nalezen SHA-256 soucet."
    }
    Assert-FileHash -Path $zipPath -ExpectedHash $match.Value

    $tempDir = Join-Path $DownloadDir 'uv-extracted'
    Expand-ZipClean -ZipPath $zipPath -Destination $tempDir
    $downloadedExe = Get-ChildItem -Path $tempDir -Filter 'uv.exe' -File -Recurse | Select-Object -First 1
    if ($null -eq $downloadedExe) {
        throw 'V archivu uv nebyl nalezen uv.exe.'
    }

    Ensure-Directory $UvDir
    Copy-Item -LiteralPath $downloadedExe.FullName -Destination $UvExe -Force
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue

    $uvVersionResult = Invoke-NativeCommandCapture -Executable $UvExe -Arguments @('--version')
    if ($uvVersionResult.ExitCode -ne 0) {
        throw "uv se nepodarilo spustit (exit code $($uvVersionResult.ExitCode)): $($uvVersionResult.Output)"
    }
    Write-Ok $uvVersionResult.Output
}

function Get-LatestCaddyRelease {
    $headers = @{
        'User-Agent' = "EInfra-OpenWebUI-Installer/$ScriptVersion"
        'Accept' = 'application/vnd.github+json'
    }

    try {
        $release = Invoke-RestMethod `
            -Uri 'https://api.github.com/repos/caddyserver/caddy/releases/latest' `
            -Headers $headers
    }
    catch {
        throw "Nelze zjistit posledni vydani Caddy z oficialniho GitHub API: $($_.Exception.Message)"
    }

    $tag = ([string]$release.tag_name).Trim()
    $tagMatch = [regex]::Match(
        $tag,
        '^v(?<Version>[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?)$',
        [Text.RegularExpressions.RegexOptions]::CultureInvariant
    )
    if ([string]::IsNullOrWhiteSpace($tag) -or -not $tagMatch.Success) {
        throw "GitHub API vratilo neocekavany tag vydani Caddy: '$tag'."
    }

    return [pscustomobject]@{
        Metadata = $release
        Tag = $tag
        Version = [string]$tagMatch.Groups['Version'].Value
    }
}

function Install-Caddy {
    Write-Step 'Stahuji a overuji Caddy HTTPS reverse proxy'

    if ($ResumeRequested -and -not $ForceDownload -and (Test-Path -LiteralPath $CaddyExe -PathType Leaf)) {
        try {
            $existingCaddy = Invoke-NativeCommandCapture -Executable $CaddyExe -Arguments @('version')
            if ($existingCaddy.ExitCode -eq 0) {
                Write-Ok "Pouzivam existujici Caddy $($existingCaddy.Output); pri --resume se funkcni komponenta zbytecne nestahuje."
                return
            }
            Write-Caution "Existujici Caddy neproslo kontrolou a bude nainstalovano znovu: $($existingCaddy.Output)"
        }
        catch {
            Write-Caution "Existujici Caddy nelze overit a bude nainstalovano znovu: $($_.Exception.Message)"
        }
    }

    $arch = Get-NativeArchitecture
    $releaseInfo = Get-LatestCaddyRelease
    $release = $releaseInfo.Metadata
    $tag = [string]$releaseInfo.Tag
    $version = [string]$releaseInfo.Version

    # Caddy ma vice nez 100 release artefaktu. Nektere kombinace GitHub API a
    # Windows PowerShellu vraceji pri strankovani nekompletni seznam, proto archiv
    # nevyhledavame v kolekci assets. Oficialni nazvy sestavime primo z overeneho
    # tagu posledniho vydani a nasledne archiv overime publikovanym checksumem.
    $assetName = "caddy_${version}_windows_${arch}.zip"
    $checksumsName = "caddy_${version}_checksums.txt"
    $downloadBase = "https://github.com/caddyserver/caddy/releases/download/$tag"
    $zipUri = "$downloadBase/$assetName"
    $checksumsUri = "$downloadBase/$checksumsName"

    Write-Notice "Caddy $tag; archiv $assetName"

    $zipPath = Join-Path $DownloadDir $assetName
    $checksumsPath = Join-Path $DownloadDir $checksumsName
    $alwaysDownload = ($ForceDownload -or $Action -eq 'Update')

    # Checksum stahujeme jako prvni. Pokud GitHub zmeni konvenci nazvu, chyba bude
    # obsahovat presnou sestavenou URL namisto nepravdive informace, ze archiv chybi.
    Invoke-DownloadFile -Uri $checksumsUri -Destination $checksumsPath -AlwaysDownload:$alwaysDownload
    Invoke-DownloadFile -Uri $zipUri -Destination $zipPath -AlwaysDownload:$alwaysDownload

    # Je-li digest checksum souboru soucasti odpovedi GitHub API, overime nejprve
    # i tento soubor. Samotny ZIP je vzdy povinne overen hodnotou v checksums.txt.
    $checksumsMetadata = $null
    if ($release.PSObject.Properties.Name -contains 'assets') {
        $checksumsMetadata = $release.assets |
            Where-Object { [string]$_.name -eq $checksumsName } |
            Select-Object -First 1
    }

    if ($null -ne $checksumsMetadata -and
        $checksumsMetadata.PSObject.Properties.Name -contains 'digest') {
        $checksumsDigest = [string]$checksumsMetadata.digest
        if ($checksumsDigest -match '(?i)^sha256:([0-9a-f]{64})$') {
            Assert-FileHash -Path $checksumsPath -ExpectedHash $Matches[1]
        }
    }

    $expectedHash = $null
    $escapedAssetName = [regex]::Escape($assetName)
    foreach ($line in Get-Content -LiteralPath $checksumsPath) {
        if ($line -match "(?i)^\s*([0-9a-f]{64}|[0-9a-f]{128})\s+\*?${escapedAssetName}\s*$") {
            $expectedHash = $Matches[1]
            break
        }
    }

    if ([string]::IsNullOrWhiteSpace($expectedHash)) {
        throw "V $checksumsName nebyl nalezen kontrolni soucet pro $assetName."
    }
    Assert-FileHash -Path $zipPath -ExpectedHash $expectedHash

    $tempDir = Join-Path $DownloadDir 'caddy-extracted'
    Expand-ZipClean -ZipPath $zipPath -Destination $tempDir
    $downloadedExe = Get-ChildItem -Path $tempDir -Filter 'caddy.exe' -File -Recurse | Select-Object -First 1
    if ($null -eq $downloadedExe) {
        throw 'V archivu Caddy nebyl nalezen caddy.exe.'
    }

    Ensure-Directory $CaddyDir
    Copy-Item -LiteralPath $downloadedExe.FullName -Destination $CaddyExe -Force
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue

    $caddyVersionResult = Invoke-NativeCommandCapture -Executable $CaddyExe -Arguments @('version')
    if ($caddyVersionResult.ExitCode -ne 0) {
        throw "Caddy se nepodarilo spustit (exit code $($caddyVersionResult.ExitCode)): $($caddyVersionResult.Output)"
    }
    Write-Ok "Caddy $($caddyVersionResult.Output)"
}

function ConvertTo-OpenWebUIVersionObject {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) { return $null }
    $text = ([string]$Value).Trim()
    if ($text.StartsWith('v', [StringComparison]::OrdinalIgnoreCase)) {
        $text = $text.Substring(1)
    }
    if ($text -notmatch '^\d+\.\d+\.\d+(?:\.\d+)?$') {
        return $null
    }
    try {
        return [Version]::Parse($text)
    }
    catch {
        return $null
    }
}

function ConvertTo-OpenWebUIVersionText {
    param([Parameter(Mandatory = $true)][Version]$Version)
    return $Version.ToString()
}

function Get-InstalledOpenWebUIVersion {
    param(
        [string]$PythonPath = $PythonExe,
        [switch]$Quiet
    )

    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        return ''
    }

    try {
        $result = Invoke-NativeCommandCapture `
            -Executable $PythonPath `
            -Arguments @('-c', "import importlib.metadata; print(importlib.metadata.version('open-webui'))")
        if ($result.ExitCode -ne 0) {
            if (-not $Quiet) {
                Write-Caution "Verzi Open WebUI nelze zjistit: $($result.Output)"
            }
            return ''
        }
        $parsed = ConvertTo-OpenWebUIVersionObject -Value $result.StdOut.Trim()
        if ($null -eq $parsed) {
            if (-not $Quiet) {
                Write-Caution "Open WebUI vratilo neocekavany format verze '$($result.StdOut.Trim())'."
            }
            return ''
        }
        return (ConvertTo-OpenWebUIVersionText -Version $parsed)
    }
    catch {
        if (-not $Quiet) {
            Write-Caution "Verzi Open WebUI nelze zjistit: $($_.Exception.Message)"
        }
        return ''
    }
}

function Get-OpenWebUIStableReleases {
    $headers = @{
        Accept = 'application/vnd.github+json'
        'User-Agent' = "EInfra-OpenWebUI-Installer/$ScriptVersion"
        'X-GitHub-Api-Version' = '2022-11-28'
    }
    $uri = 'https://api.github.com/repos/open-webui/open-webui/releases?per_page=100'
    $response = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get -TimeoutSec 25
    $items = [Collections.Generic.List[object]]::new()

    foreach ($release in @($response)) {
        if ([bool]$release.draft -or [bool]$release.prerelease) { continue }
        $version = ConvertTo-OpenWebUIVersionObject -Value ([string]$release.tag_name)
        if ($null -eq $version) { continue }

        $publishedAt = [DateTimeOffset]::MinValue
        if (-not [DateTimeOffset]::TryParse([string]$release.published_at, [ref]$publishedAt)) {
            continue
        }

        [void]$items.Add([pscustomobject]@{
            Version = $version
            VersionText = (ConvertTo-OpenWebUIVersionText -Version $version)
            PublishedAt = $publishedAt.ToUniversalTime()
            Url = [string]$release.html_url
            Name = [string]$release.name
        })
    }

    return @($items.ToArray() | Sort-Object -Property @{ Expression = { $_.Version }; Descending = $true })
}

function Resolve-OpenWebUIVersionForRun {
    Write-Step 'Kontroluji dostupne stabilni aktualizace Open WebUI'

    $installedText = Get-InstalledOpenWebUIVersion -Quiet
    $installedVersion = ConvertTo-OpenWebUIVersionObject -Value $installedText
    if ($null -ne $installedVersion) {
        $script:InstalledOpenWebUIVersion = ConvertTo-OpenWebUIVersionText -Version $installedVersion
    }
    else {
        $script:InstalledOpenWebUIVersion = ''
    }

    $requestedVersion = ConvertTo-OpenWebUIVersionObject -Value $OpenWebUIVersion
    $explicitVersion = $CliSpecified.ContainsKey('OpenWebUIVersion')
    $requiresReleaseLookup = $OpenWebUIVersion -eq 'latest'

    if ($explicitVersion -and -not $requiresReleaseLookup) {
        if ($null -eq $requestedVersion) {
            throw "Neplatny format OpenWebUIVersion: $OpenWebUIVersion"
        }
        if ($null -ne $installedVersion -and $requestedVersion -lt $installedVersion -and -not $AllowOpenWebUIDowngrade) {
            throw "Pozadovana verze $requestedVersion je starsi nez nainstalovana $installedVersion. Databazove migrace mohou byt jednosmerne; pro vedomy downgrade pouzijte --allow-downgrade a obnovte kompatibilni zalohu dat."
        }
        $script:OpenWebUIVersion = ConvertTo-OpenWebUIVersionText -Version $requestedVersion
        $script:OpenWebUIUpdateDecision = 'Explicitne zadana verze.'
        Write-Notice "Pouziji explicitne zadanou verzi Open WebUI $script:OpenWebUIVersion."
        return
    }

    if (-not $explicitVersion -and $OpenWebUIUpdatePolicy -eq 'Off') {
        if ($null -ne $installedVersion) {
            $script:OpenWebUIVersion = ConvertTo-OpenWebUIVersionText -Version $installedVersion
        }
        elseif ($null -eq $requestedVersion) {
            $script:OpenWebUIVersion = $ProfileOpenWebUIVersion
        }
        $script:OpenWebUIUpdateDecision = 'Online kontrola je vypnuta.'
        Write-Notice "Online kontrola aktualizaci je vypnuta; cilova verze je $script:OpenWebUIVersion."
        return
    }

    $releases = @()
    try {
        $releases = @(Get-OpenWebUIStableReleases)
        $script:LastOpenWebUIUpdateCheckUtc = [DateTimeOffset]::UtcNow.ToString('o')
    }
    catch {
        if ($null -ne $installedVersion) {
            $script:OpenWebUIVersion = ConvertTo-OpenWebUIVersionText -Version $installedVersion
        }
        elseif ($null -eq $requestedVersion) {
            $script:OpenWebUIVersion = $ProfileOpenWebUIVersion
        }
        $script:OpenWebUIUpdateDecision = "Kontrola vydani selhala: $($_.Exception.Message)"
        Write-Caution "Oficialni seznam vydani Open WebUI nelze nacist. Zachovavam verzi $script:OpenWebUIVersion. Detail: $($_.Exception.Message)"
        return
    }

    if ($releases.Count -eq 0) {
        if ($null -ne $installedVersion) {
            $script:OpenWebUIVersion = ConvertTo-OpenWebUIVersionText -Version $installedVersion
        }
        elseif ($null -eq $requestedVersion) {
            $script:OpenWebUIVersion = $ProfileOpenWebUIVersion
        }
        $script:OpenWebUIUpdateDecision = 'Oficialni API nevratilo zadne stabilni vydani.'
        Write-Caution "Oficialni API nevratilo zadne pouzitelne stabilni vydani; zachovavam $script:OpenWebUIVersion."
        return
    }

    $latest = $releases[0]
    $script:LatestAvailableOpenWebUIVersion = [string]$latest.VersionText
    $script:OpenWebUIReleaseUrl = [string]$latest.Url
    $script:OpenWebUIReleasePublishedAtUtc = ([DateTimeOffset]$latest.PublishedAt).ToString('o')

    if ($requiresReleaseLookup) {
        $targetVersion = [Version]$latest.Version
        if ($null -ne $installedVersion -and $targetVersion -lt $installedVersion -and -not $AllowOpenWebUIDowngrade) {
            throw "Posledni stabilni verze $targetVersion je starsi nez nainstalovana $installedVersion; automaticky downgrade je zablokovan."
        }
        $script:OpenWebUIVersion = ConvertTo-OpenWebUIVersionText -Version $targetVersion
        $script:OpenWebUIUpdateDecision = 'Explicitni hodnota latest zvolila posledni stabilni vydani.'
        Write-Notice "Explicitni 'latest' zvolilo Open WebUI $script:OpenWebUIVersion."
        return
    }

    $baselineVersion = if ($null -ne $installedVersion) {
        $installedVersion
    }
    elseif ($null -ne $requestedVersion) {
        $requestedVersion
    }
    else {
        ConvertTo-OpenWebUIVersionObject -Value $ProfileOpenWebUIVersion
    }

    $eligible = [Collections.Generic.List[object]]::new()
    foreach ($release in $releases) {
        if ([Version]$release.Version -le $baselineVersion) { continue }
        $ageHours = ([DateTimeOffset]::UtcNow - ([DateTimeOffset]$release.PublishedAt)).TotalHours
        if ($ageHours -lt $MinimumReleaseAgeHours) { continue }
        if ($OpenWebUIUpdatePolicy -eq 'Patch' -and
            (([Version]$release.Version).Major -ne $baselineVersion.Major -or
             ([Version]$release.Version).Minor -ne $baselineVersion.Minor)) {
            continue
        }
        [void]$eligible.Add($release)
    }

    if ($eligible.Count -gt 0) {
        $selected = $eligible.ToArray()[0]
        $script:OpenWebUIVersion = [string]$selected.VersionText
        $script:OpenWebUIReleaseUrl = [string]$selected.Url
        $script:OpenWebUIReleasePublishedAtUtc = ([DateTimeOffset]$selected.PublishedAt).ToString('o')
        if ($null -ne $installedVersion) {
            $script:OpenWebUIUpdateDecision = "Bezpecna aktualizace $installedVersion -> $($selected.VersionText)."
            Write-Notice "Je dostupna bezpecna aktualizace Open WebUI $installedVersion -> $($selected.VersionText). Bude provedena transakcne."
        }
        else {
            $script:OpenWebUIUpdateDecision = "Nova instalace pouzije stabilni verzi $($selected.VersionText)."
            Write-Notice "Nova instalace pouzije stabilni verzi Open WebUI $($selected.VersionText)."
        }
    }
    else {
        $script:OpenWebUIVersion = ConvertTo-OpenWebUIVersionText -Version $baselineVersion
        $script:OpenWebUIUpdateDecision = 'Nebyla nalezena zpusobila bezpecna aktualizace.'
        Write-Ok "Open WebUI $script:OpenWebUIVersion je pro politiku $OpenWebUIUpdatePolicy aktualni."
    }

    if ([Version]$latest.Version -gt $baselineVersion) {
        $latestAgeHours = ([DateTimeOffset]::UtcNow - ([DateTimeOffset]$latest.PublishedAt)).TotalHours
        if ($latestAgeHours -lt $MinimumReleaseAgeHours) {
            Write-Notice ("Nejnovejsi vydani {0} je stare jen {1:N1} h; automaticka instalace ceka minimalne {2} h." -f $latest.VersionText, $latestAgeHours, $MinimumReleaseAgeHours)
        }
        elseif ($OpenWebUIUpdatePolicy -eq 'Patch' -and
                (([Version]$latest.Version).Major -ne $baselineVersion.Major -or
                 ([Version]$latest.Version).Minor -ne $baselineVersion.Minor)) {
            Write-Caution "Je dostupna nova funkcni rada Open WebUI $($latest.VersionText). Kvuli moznym jednosmernym migracim nebyla automaticky nainstalovana. Po kontrole release notes ji lze povolit volbou --update-policy stable."
        }
    }
}

function Read-OpenWebUIUpdateTransaction {
    if (-not (Test-Path -LiteralPath $OpenWebUIUpdateTransactionPath -PathType Leaf)) {
        return $null
    }
    try {
        $transaction = Get-Content -LiteralPath $OpenWebUIUpdateTransactionPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not [string]::Equals([string]$transaction.ProductId, $ProductId, [StringComparison]::Ordinal)) {
            throw "Transakcni soubor patri jinemu produktu ('$($transaction.ProductId)')."
        }
        return $transaction
    }
    catch {
        throw "Transakcni stav aktualizace $OpenWebUIUpdateTransactionPath nelze bezpecne nacist: $($_.Exception.Message)"
    }
}

function Write-OpenWebUIUpdateTransaction {
    param([Parameter(Mandatory = $true)]$Transaction)

    Ensure-Directory $InstallerStateDir
    if ($Transaction.PSObject.Properties.Name -contains 'UpdatedAt') {
        $Transaction.UpdatedAt = [DateTimeOffset]::UtcNow.ToString('o')
    }
    else {
        $Transaction | Add-Member -NotePropertyName UpdatedAt -NotePropertyValue ([DateTimeOffset]::UtcNow.ToString('o'))
    }
    $temporaryPath = "$OpenWebUIUpdateTransactionPath.tmp"
    Write-Utf8NoBom -Path $temporaryPath -Content (($Transaction | ConvertTo-Json -Depth 12) + "`r`n")
    Set-AdminOnlyFileAcl -Path $temporaryPath
    Move-Item -LiteralPath $temporaryPath -Destination $OpenWebUIUpdateTransactionPath -Force
    Set-AdminOnlyFileAcl -Path $OpenWebUIUpdateTransactionPath
}

function Clear-OpenWebUIUpdateTransaction {
    Remove-Item -LiteralPath $OpenWebUIUpdateTransactionPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "$OpenWebUIUpdateTransactionPath.tmp" -Force -ErrorAction SilentlyContinue
}

function Normalize-UpdateBackupRelativePath {
    param([AllowEmptyString()][string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) { return '' }
    $normalized = $Value.Trim().Replace('\', '/').Trim('/')
    if ([string]::IsNullOrWhiteSpace($normalized)) { return '' }
    if ($normalized -match '(^|/)\.\.?(/|$)') {
        throw "Relativni cesta '$Value' obsahuje nepovoleny segment tecky nebo dvou tecek."
    }
    return $normalized
}

function Get-NormalizedUpdateBackupExclusions {
    param([string[]]$ExcludeRelativePaths = @())

    $normalized = [Collections.Generic.List[string]]::new()
    foreach ($value in @($ExcludeRelativePaths)) {
        $item = Normalize-UpdateBackupRelativePath -Value ([string]$value)
        if (-not [string]::IsNullOrWhiteSpace($item)) {
            [void]$normalized.Add($item)
        }
    }
    return @($normalized.ToArray() | Sort-Object -Unique)
}

function Test-UpdateBackupRelativePathExcluded {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [string[]]$ExcludeRelativePaths = @()
    )

    $candidate = Normalize-UpdateBackupRelativePath -Value $RelativePath
    foreach ($root in @(Get-NormalizedUpdateBackupExclusions -ExcludeRelativePaths $ExcludeRelativePaths)) {
        if ([string]::Equals($candidate, $root, [StringComparison]::OrdinalIgnoreCase) -or
            $candidate.StartsWith($root + '/', [StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function ConvertTo-ExtendedLengthPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = if ($Path.StartsWith('\\?\', [StringComparison]::Ordinal)) {
        $Path
    }
    elseif ([IO.Path]::IsPathRooted($Path)) {
        $Path
    }
    else {
        [IO.Path]::GetFullPath($Path)
    }
    if ($fullPath.StartsWith('\\?\', [StringComparison]::Ordinal)) {
        return $fullPath
    }
    if ($fullPath.StartsWith('\\', [StringComparison]::Ordinal)) {
        return '\\?\UNC\' + $fullPath.Substring(2)
    }
    return '\\?\' + $fullPath
}

function ConvertFrom-ExtendedLengthPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ($Path.StartsWith('\\?\UNC\', [StringComparison]::OrdinalIgnoreCase)) {
        return '\\' + $Path.Substring(8)
    }
    if ($Path.StartsWith('\\?\', [StringComparison]::OrdinalIgnoreCase)) {
        return $Path.Substring(4)
    }
    return $Path
}

function Test-DirectoryExistsLongPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [IO.Directory]::Exists((ConvertTo-ExtendedLengthPath -Path $Path))
}

function Get-LongPathFileIntegrity {
    param([Parameter(Mandatory = $true)][string]$Path)

    $extendedPath = ConvertTo-ExtendedLengthPath -Path $Path
    $share = [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
    $stream = $null
    $sha = $null
    try {
        $stream = [IO.File]::Open($extendedPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, $share)
        $length = [int64]$stream.Length
        $sha = [Security.Cryptography.SHA256]::Create()
        $hashBytes = $sha.ComputeHash($stream)
        $hash = ([BitConverter]::ToString($hashBytes)).Replace('-', '').ToLowerInvariant()
        return [pscustomobject]@{
            Length = $length
            Sha256 = $hash
        }
    }
    catch {
        throw "Soubor '$Path' nelze pri vytvareni integritni zalohy precist: $($_.Exception.Message)"
    }
    finally {
        if ($null -ne $sha) { $sha.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Get-DirectoryFileRecordsLongPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string[]]$ExcludeRelativePaths = @()
    )

    $rootNormal = [IO.Path]::GetFullPath($Path)
    $trimCharacters = [char[]]@([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $rootNormal = $rootNormal.TrimEnd($trimCharacters)
    $rootExtended = (ConvertTo-ExtendedLengthPath -Path $rootNormal).TrimEnd($trimCharacters)
    if (-not [IO.Directory]::Exists($rootExtended)) {
        throw "Adresar pro integritni kontrolu neexistuje: $Path"
    }

    $normalPrefix = $rootNormal + [IO.Path]::DirectorySeparatorChar
    $excluded = @(Get-NormalizedUpdateBackupExclusions -ExcludeRelativePaths $ExcludeRelativePaths)
    $stack = [Collections.Generic.Stack[string]]::new()
    $records = [Collections.Generic.List[object]]::new()
    $stack.Push($rootExtended)

    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        $entries = $null
        try {
            $entries = [IO.Directory]::EnumerateFileSystemEntries($current)
        }
        catch {
            $displayCurrent = ConvertFrom-ExtendedLengthPath -Path $current
            throw "Adresar '$displayCurrent' nelze pri vytvareni integritni zalohy vyjmenovat: $($_.Exception.Message)"
        }

        foreach ($entryValue in $entries) {
            $entryExtended = [string]$entryValue
            if (-not $entryExtended.StartsWith('\\?\', [StringComparison]::Ordinal)) {
                $entryExtended = ConvertTo-ExtendedLengthPath -Path $entryExtended
            }
            $entryNormal = ConvertFrom-ExtendedLengthPath -Path $entryExtended
            if (-not $entryNormal.StartsWith($normalPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Polozka '$entryNormal' nelezi uvnitr kontrolovaneho adresare '$rootNormal'."
            }
            $relativePath = $entryNormal.Substring($normalPrefix.Length).Replace('\', '/')
            if (Test-UpdateBackupRelativePathExcluded -RelativePath $relativePath -ExcludeRelativePaths $excluded) {
                continue
            }

            try {
                $attributes = [IO.File]::GetAttributes($entryExtended)
            }
            catch {
                throw "Polozku '$entryNormal' nelze pri vytvareni integritni zalohy nacist: $($_.Exception.Message)"
            }

            if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Trvala data obsahuji reparse point '$entryNormal'. Aktualizace jej z bezpecnostnich duvodu nebude nasledovat ani tise vynechavat. Presunte jej mimo DATA_DIR nebo jej nahradte skutecnym souborem/adresarem."
            }
            if (($attributes -band [IO.FileAttributes]::Directory) -ne 0) {
                $stack.Push($entryExtended)
                continue
            }

            [void]$records.Add([pscustomobject]@{
                RelativePath = $relativePath
                FullPath = $entryNormal
            })
        }
    }

    return @($records.ToArray() | Sort-Object -Property RelativePath)
}

function Get-DirectoryStatistics {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string[]]$ExcludeRelativePaths = @()
    )

    $count = [int64]0
    $bytes = [int64]0
    foreach ($record in @(Get-DirectoryFileRecordsLongPath -Path $Path -ExcludeRelativePaths $ExcludeRelativePaths)) {
        $integrity = Get-LongPathFileIntegrity -Path ([string]$record.FullPath)
        $count++
        $bytes += [int64]$integrity.Length
    }
    return [pscustomobject]@{ FileCount = $count; Bytes = $bytes }
}

function Get-DirectoryIntegrityManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string[]]$ExcludeRelativePaths = @()
    )

    if (-not (Test-DirectoryExistsLongPath -Path $Path)) {
        throw "Adresar pro integritni manifest neexistuje: $Path"
    }

    $entries = [Collections.Generic.List[object]]::new()
    foreach ($record in @(Get-DirectoryFileRecordsLongPath -Path $Path -ExcludeRelativePaths $ExcludeRelativePaths)) {
        $integrity = Get-LongPathFileIntegrity -Path ([string]$record.FullPath)
        [void]$entries.Add([pscustomobject][ordered]@{
            RelativePath = [string]$record.RelativePath
            Length = [int64]$integrity.Length
            Sha256 = [string]$integrity.Sha256
        })
    }

    return $entries.ToArray()
}

function Write-DirectoryIntegrityManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string[]]$ExcludeRelativePaths = @()
    )

    $excluded = @(Get-NormalizedUpdateBackupExclusions -ExcludeRelativePaths $ExcludeRelativePaths)
    $entries = @(Get-DirectoryIntegrityManifest -Path $Path -ExcludeRelativePaths $excluded)
    $totalBytes = [int64]0
    foreach ($entry in $entries) { $totalBytes += [int64]$entry.Length }
    $manifest = [ordered]@{
        SchemaVersion = 2
        Algorithm = 'SHA256'
        DataKind = 'PersistentOpenWebUIData'
        CreatedAtUtc = [DateTimeOffset]::UtcNow.ToString('o')
        ExcludedRelativePaths = $excluded
        FileCount = [int64]$entries.Count
        TotalBytes = $totalBytes
        Entries = $entries
    }
    Write-Utf8NoBom -Path $Destination -Content (($manifest | ConvertTo-Json -Depth 8) + "`r`n")
    return [pscustomobject]$manifest
}

function Read-DirectoryIntegrityManifest {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Integritni manifest neexistuje: $Path"
    }
    $manifest = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    $schemaVersion = [int]$manifest.SchemaVersion
    if ($schemaVersion -notin @(1, 2) -or [string]$manifest.Algorithm -ne 'SHA256') {
        throw "Integritni manifest '$Path' ma nepodporovany format."
    }
    if (-not ($manifest.PSObject.Properties.Name -contains 'ExcludedRelativePaths')) {
        $manifest | Add-Member -NotePropertyName ExcludedRelativePaths -NotePropertyValue @()
    }
    return $manifest
}

function Assert-DirectoryMatchesIntegrityManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ManifestPath
    )

    $manifest = Read-DirectoryIntegrityManifest -Path $ManifestPath
    $expected = @($manifest.Entries)
    $excluded = @($manifest.ExcludedRelativePaths)
    $actual = @(Get-DirectoryIntegrityManifest -Path $Path -ExcludeRelativePaths $excluded)
    if ($actual.Count -ne $expected.Count) {
        throw "Integritni kontrola '$Path' selhala: ocekavano $($expected.Count) souboru, nalezeno $($actual.Count)."
    }

    for ($index = 0; $index -lt $expected.Count; $index++) {
        $expectedEntry = $expected[$index]
        $actualEntry = $actual[$index]
        if (-not [string]::Equals([string]$expectedEntry.RelativePath, [string]$actualEntry.RelativePath, [StringComparison]::OrdinalIgnoreCase) -or
            [int64]$expectedEntry.Length -ne [int64]$actualEntry.Length -or
            -not [string]::Equals([string]$expectedEntry.Sha256, [string]$actualEntry.Sha256, [StringComparison]::OrdinalIgnoreCase)) {
            throw ("Integritni kontrola '$Path' selhala u polozky {0}: ocekavano '{1}', nalezeno '{2}'." -f $index, [string]$expectedEntry.RelativePath, [string]$actualEntry.RelativePath)
        }
    }

    $actualBytes = [int64]0
    foreach ($entry in $actual) { $actualBytes += [int64]$entry.Length }
    if ([int64]$manifest.TotalBytes -ne $actualBytes) {
        throw "Integritni kontrola '$Path' selhala: nesouhlasi celkova velikost souboru."
    }
}

function Invoke-RobocopyDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [switch]$Mirror,
        [string[]]$ExcludeRelativePaths = @()
    )

    if (-not (Test-DirectoryExistsLongPath -Path $Source)) {
        throw "Zdrojovy adresar pro zalohu/obnovu neexistuje: $Source"
    }
    Ensure-Directory $Destination
    $robocopy = Join-Path $env:SystemRoot 'System32\robocopy.exe'
    $mode = if ($Mirror) { '/MIR' } else { '/E' }
    $arguments = [Collections.Generic.List[string]]::new()
    foreach ($argument in @(
        $Source,
        $Destination,
        $mode,
        '/COPY:DAT',
        '/DCOPY:DAT',
        '/R:2',
        '/W:1',
        '/XJ',
        '/XJD',
        '/XJF',
        '/NFL',
        '/NDL',
        '/NJH',
        '/NJS',
        '/NP'
    )) {
        [void]$arguments.Add([string]$argument)
    }

    $excluded = @(Get-NormalizedUpdateBackupExclusions -ExcludeRelativePaths $ExcludeRelativePaths)
    if ($excluded.Count -gt 0) {
        [void]$arguments.Add('/XD')
        foreach ($relativePath in $excluded) {
            $nativeRelativePath = $relativePath.Replace('/', '\')
            [void]$arguments.Add((Join-Path $Source $nativeRelativePath))
        }
        [void]$arguments.Add('/XF')
        foreach ($relativePath in $excluded) {
            $nativeRelativePath = $relativePath.Replace('/', '\')
            [void]$arguments.Add((Join-Path $Source $nativeRelativePath))
        }
    }

    $result = Invoke-NativeCommandCapture -Executable $robocopy -Arguments $arguments.ToArray()
    # Robocopy 0-7 znamena uspech nebo uspech s rozdily; 8+ je chyba.
    if ($result.ExitCode -ge 8) {
        throw "Robocopy selhalo kodem $($result.ExitCode): $($result.Output)"
    }
}

function Remove-DirectoryTreeRobust {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [ValidateRange(1, 10)][int]$Attempts = 4
    )

    if (-not (Test-DirectoryExistsLongPath -Path $Path)) {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
        }
        return
    }

    Ensure-Directory $InstallerStateDir
    $emptyDirectory = Join-Path $InstallerStateDir ("empty-delete-{0}" -f ([Guid]::NewGuid().ToString('N')))
    Ensure-Directory $emptyDirectory
    $robocopy = Join-Path $env:SystemRoot 'System32\robocopy.exe'
    $lastError = ''

    try {
        for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
            try {
                # Robocopy umi odstranit i potomky s cestami nad MAX_PATH. Zdroj
                # je pro kazde volani novy prazdny adresar, takze do cile nelze
                # omylem pridat zadny soubor.
                $result = Invoke-NativeCommandCapture -Executable $robocopy -Arguments @(
                    $emptyDirectory,
                    $Path,
                    '/MIR',
                    '/R:1',
                    '/W:1',
                    '/XJ',
                    '/XJD',
                    '/XJF',
                    '/NFL',
                    '/NDL',
                    '/NJH',
                    '/NJS',
                    '/NP'
                )
                if ($result.ExitCode -ge 8) {
                    throw "Robocopy purge skoncil kodem $($result.ExitCode): $($result.Output)"
                }

                $extendedPath = ConvertTo-ExtendedLengthPath -Path $Path
                if ([IO.Directory]::Exists($extendedPath)) {
                    [IO.Directory]::Delete($extendedPath, $true)
                }
                if (-not [IO.Directory]::Exists($extendedPath)) { return }
                throw 'Adresar po vycisteni stale existuje.'
            }
            catch {
                $lastError = $_.Exception.Message
                if ($attempt -lt $Attempts) {
                    Stop-ManagedProcesses
                    Start-Sleep -Milliseconds (500 * $attempt)
                }
            }
        }
    }
    finally {
        Remove-Item -LiteralPath $emptyDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }

    throw "Adresar '$Path' nelze bezpecne odebrat ani po $Attempts pokusech. Detail: $lastError"
}

function Assert-FreeSpaceForUpdateBackup {
    param([Parameter(Mandatory = $true)][int64]$RequiredDataBytes)

    $root = [IO.Path]::GetPathRoot($BackupDir)
    $drive = New-Object IO.DriveInfo -ArgumentList $root
    $reserve = [int64](512MB)
    $required = $RequiredDataBytes + $reserve
    if ($drive.AvailableFreeSpace -lt $required) {
        throw ("Pro bezpecnou aktualizaci neni dost volneho mista. Volno: {0:N0} B, potreba nejmene: {1:N0} B (data + rezerva)." -f $drive.AvailableFreeSpace, $required)
    }
}

function Test-OpenWebUISqliteIntegrity {
    param(
        [string]$PythonPath = $PythonExe,
        [switch]$Checkpoint
    )

    $databasePath = Join-Path $DataDir 'webui.db'
    if (-not (Test-Path -LiteralPath $databasePath -PathType Leaf)) { return }
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
        throw "Pro kontrolu SQLite chybi Python: $PythonPath"
    }

    $checkpointFlag = if ($Checkpoint) { '1' } else { '0' }
    $code = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1], timeout=30); c.execute('PRAGMA wal_checkpoint(FULL)') if sys.argv[2]=='1' else None; r=c.execute('PRAGMA quick_check').fetchall(); print(r); c.close(); sys.exit(0 if len(r)==1 and str(r[0][0]).lower()=='ok' else 2)"
    $result = Invoke-NativeCommandCapture -Executable $PythonPath -Arguments @('-c', $code, $databasePath, $checkpointFlag)
    if ($result.ExitCode -ne 0) {
        throw "Kontrola integrity SQLite selhala (exit code $($result.ExitCode)): $($result.Output)"
    }
}

function Copy-OpenWebUIUpdateConfigSnapshot {
    param([Parameter(Mandatory = $true)][string]$Destination)

    Ensure-Directory $Destination
    foreach ($path in @($RuntimeConfigPath, $RuntimeScriptPath, $CaddyfilePath)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Copy-Item -LiteralPath $path -Destination (Join-Path $Destination ([IO.Path]::GetFileName($path))) -Force
        }
    }
}

function Restore-OpenWebUIUpdateConfigSnapshot {
    param([Parameter(Mandatory = $true)][string]$Source)

    if (-not (Test-Path -LiteralPath $Source -PathType Container)) { return }
    Ensure-Directory $ConfigDir
    foreach ($name in @('runtime.json', 'Run-Component.ps1', 'Caddyfile')) {
        $sourcePath = Join-Path $Source $name
        if (Test-Path -LiteralPath $sourcePath -PathType Leaf) {
            Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $ConfigDir $name) -Force
        }
    }
}

function Test-OpenWebUIUpdateBackupDirectoryName {
    param([Parameter(Mandatory = $true)][string]$Name)
    return ($Name -like 'u-*' -or $Name -like 'open-webui-update-*')
}

function Remove-IncompleteOpenWebUIUpdateBackups {
    if (-not (Test-Path -LiteralPath $BackupDir -PathType Container)) { return }

    foreach ($item in @(Get-ChildItem -LiteralPath $BackupDir -Directory -Force -ErrorAction SilentlyContinue)) {
        if (-not (Test-OpenWebUIUpdateBackupDirectoryName -Name $item.Name)) { continue }

        $completionMarker = Join-Path $item.FullName 'backup-complete.json'
        $legacyRuntimeSnapshot = Join-Path $item.FullName 'config\runtime.json'
        $manifestPath = Join-Path $item.FullName 'data-manifest.json'
        $isCompleteNewBackup = Test-Path -LiteralPath $completionMarker -PathType Leaf
        $isCompleteLegacyBackup =
            (Test-Path -LiteralPath $legacyRuntimeSnapshot -PathType Leaf) -and
            (Test-Path -LiteralPath $manifestPath -PathType Leaf)

        if (-not $isCompleteNewBackup -and -not $isCompleteLegacyBackup) {
            Write-Notice "Odstranuji neuplnou aktualizacni zalohu po predchozim preruseni: $($item.FullName)"
            Remove-DirectoryTreeRobust -Path $item.FullName
        }
    }
}

function Remove-OldOpenWebUIUpdateBackups {
    if (-not (Test-Path -LiteralPath $BackupDir -PathType Container)) { return }

    $old = @(Get-ChildItem -LiteralPath $BackupDir -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { Test-OpenWebUIUpdateBackupDirectoryName -Name $_.Name } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 3)
    foreach ($item in $old) {
        Remove-DirectoryTreeRobust -Path $item.FullName
    }
}

function Install-OpenWebUIIntoVenv {
    param(
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$TargetVersion
    )

    $targetVersionObject = ConvertTo-OpenWebUIVersionObject -Value $TargetVersion
    if ($null -eq $targetVersionObject) {
        throw "Neplatna cilova verze Open WebUI: $TargetVersion"
    }
    $normalizedTarget = ConvertTo-OpenWebUIVersionText -Version $targetVersionObject

    Ensure-Directory $PythonInstallDir
    Ensure-Directory $UvCacheDir
    $oldPythonDir = $env:UV_PYTHON_INSTALL_DIR
    $oldPythonBinDir = $env:UV_PYTHON_BIN_DIR
    $oldPythonInstallBin = $env:UV_PYTHON_INSTALL_BIN
    $oldPythonInstallRegistry = $env:UV_PYTHON_INSTALL_REGISTRY
    $oldCacheDir = $env:UV_CACHE_DIR
    $oldLinkMode = $env:UV_LINK_MODE
    $env:UV_PYTHON_INSTALL_DIR = $PythonInstallDir
    $env:UV_PYTHON_BIN_DIR = $PythonBinDir
    $env:UV_PYTHON_INSTALL_BIN = '0'
    $env:UV_PYTHON_INSTALL_REGISTRY = '0'
    $env:UV_CACHE_DIR = $UvCacheDir
    $env:UV_LINK_MODE = 'copy'

    try {
        $pythonInstallExitCode = Invoke-NativeCommandPassthrough `
            -Executable $UvExe `
            -Arguments @('python', 'install', '--no-config', '--no-bin', '--no-registry', '3.11')
        if ($pythonInstallExitCode -ne 0) {
            throw "uv nedokazal nainstalovat Python 3.11 (exit code $pythonInstallExitCode)."
        }

        if (Test-Path -LiteralPath $Destination) {
            Remove-ManagedPathWithRetry -Path $Destination
        }

        $venvExitCode = Invoke-NativeCommandPassthrough `
            -Executable $UvExe `
            -Arguments @('venv', '--no-config', '--managed-python', '--python', '3.11', $Destination)
        if ($venvExitCode -ne 0) {
            throw "uv nedokazal vytvorit virtualni prostredi $Destination (exit code $venvExitCode)."
        }

        $destinationPython = Join-Path $Destination 'Scripts\python.exe'
        $destinationOpenWebUI = Join-Path $Destination 'Scripts\open-webui.exe'
        $package = "open-webui==$normalizedTarget"
        $pipInstallExitCode = Invoke-NativeCommandPassthrough `
            -Executable $UvExe `
            -Arguments @(
                'pip', 'install',
                '--no-config',
                '--python', $destinationPython,
                '--upgrade',
                '--link-mode', 'copy',
                $package
            )
        if ($pipInstallExitCode -ne 0) {
            throw "Instalace balicku $package selhala (exit code $pipInstallExitCode)."
        }

        $testCode = "import importlib.metadata,importlib.util,sys; spec=importlib.util.find_spec('open_webui'); print(importlib.metadata.version('open-webui')) if spec is not None else sys.exit('open_webui module not found')"
        $versionResult = Invoke-NativeCommandCapture -Executable $destinationPython -Arguments @('-c', $testCode)
        if ($versionResult.ExitCode -ne 0) {
            throw "Nova instalace Open WebUI neprosla kontrolou balicku: $($versionResult.Output)"
        }
        $actualVersion = ConvertTo-OpenWebUIVersionObject -Value $versionResult.StdOut.Trim()
        if ($null -eq $actualVersion -or $actualVersion -ne $targetVersionObject) {
            throw "Ve virtualnim prostredi $Destination byla zjistena verze '$($versionResult.StdOut.Trim())', ale pozadovana je $normalizedTarget."
        }

        # Kontrola metadat sama o sobe neoveri Windows console-script launcher vytvoreny
        # uv. Pro test trampoliny pouzivame pouze --help. Volba main --version
        # nacita open_webui.env a pri zapnute autentizaci zamerne vyzaduje
        # WEBUI_SECRET_KEY, coz z ni dela nevhodny a falesne negativni preflight.
        # Presna verze uz byla overena vyse pomoci importlib.metadata.
        $launcherResult = Invoke-NativeCommandCapture -Executable $destinationOpenWebUI -Arguments @('--help')
        if ($launcherResult.ExitCode -ne 0) {
            throw "Launcher Open WebUI ve $Destination nelze spustit (exit code $($launcherResult.ExitCode)): $($launcherResult.Output)"
        }
        if ([string]::IsNullOrWhiteSpace($launcherResult.Output)) {
            throw "Launcher Open WebUI ve $Destination vratil prazdny vystup napovedy."
        }

        Write-Utf8NoBom -Path (Join-Path $Destination '.einfra-uv-link-mode-copy-v1') -Content "layout=copy`ninstaller=$ScriptVersion`nversion=$normalizedTarget`n"
        return $normalizedTarget
    }
    finally {
        $env:UV_PYTHON_INSTALL_DIR = $oldPythonDir
        $env:UV_PYTHON_BIN_DIR = $oldPythonBinDir
        $env:UV_PYTHON_INSTALL_BIN = $oldPythonInstallBin
        $env:UV_PYTHON_INSTALL_REGISTRY = $oldPythonInstallRegistry
        $env:UV_CACHE_DIR = $oldCacheDir
        $env:UV_LINK_MODE = $oldLinkMode
    }
}

function Assert-ActiveOpenWebUIVenv {
    param([Parameter(Mandatory = $true)][string]$ExpectedVersion)

    $initPath = Join-Path $VenvDir 'Lib\site-packages\open_webui\__init__.py'
    foreach ($path in @($PythonExe, $OpenWebUIExe, $initPath, $VenvLayoutMarker)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Aktivni virtualni prostredi je neuplne; chybi $path"
        }
    }
    Reset-TreeToInheritedAcl -Path $VenvDir
    Assert-LocalServiceReadAccess -Path $PythonExe
    Assert-LocalServiceReadAccess -Path $OpenWebUIExe
    Assert-LocalServiceReadAccess -Path $initPath
    $actual = Get-InstalledOpenWebUIVersion
    if (-not [string]::Equals($actual, $ExpectedVersion, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Aktivni virtualni prostredi obsahuje Open WebUI $actual, ale ocekavana je verze $ExpectedVersion."
    }

    # Kontrola presne verze probehla vyse pres importlib.metadata. Zde overujeme
    # pouze spustitelnost Windows console-script launcheru bez inicializace
    # autentizacniho runtime a bez pozadavku na WEBUI_SECRET_KEY.
    $launcherResult = Invoke-NativeCommandCapture -Executable $OpenWebUIExe -Arguments @('--help')
    if ($launcherResult.ExitCode -ne 0) {
        throw "Aktivni launcher Open WebUI nelze spustit (exit code $($launcherResult.ExitCode)): $($launcherResult.Output)"
    }
    if ([string]::IsNullOrWhiteSpace($launcherResult.Output)) {
        throw 'Aktivni launcher Open WebUI vratil prazdny vystup napovedy.'
    }
}

function Invoke-TransactionalOpenWebUIVenvSwap {
    param(
        [Parameter(Mandatory = $true)][string]$FromVersion,
        [Parameter(Mandatory = $true)][string]$ToVersion
    )

    if ($null -ne (Read-OpenWebUIUpdateTransaction)) {
        throw 'Predchozi aktualizacni transakce nebyla uzavrena; musi ji nejprve zpracovat faze obnovy.'
    }

    Write-Step "Pripravuji transakcni aktualizaci Open WebUI $FromVersion -> $ToVersion"
    Remove-IncompleteOpenWebUIUpdateBackups
    Remove-ManagedPathWithRetry -Path $OpenWebUIStagingVenvDir
    if (Test-Path -LiteralPath $OpenWebUIRollbackVenvDir) {
        throw "Neocekavane existuje rollback venv $OpenWebUIRollbackVenvDir bez transakcniho souboru. Z bezpecnostnich duvodu aktualizaci neprovadim."
    }

    $stagedVersion = Install-OpenWebUIIntoVenv -Destination $OpenWebUIStagingVenvDir -TargetVersion $ToVersion
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    # Zamerne kratky nazev. Windows PowerShell 5.1 jinak pri Get-FileHash/Get-Item
    # selhava na zalohovych cestach delsich nez klasicky limit MAX_PATH 260 znaku.
    $backupRoot = Join-Path $BackupDir ("u-{0}" -f $timestamp)
    $dataBackup = Join-Path $backupRoot 'd'
    $configBackup = Join-Path $backupRoot 'c'
    $dataManifest = Join-Path $backupRoot 'data-manifest.json'
    $backupCompletionMarker = Join-Path $backupRoot 'backup-complete.json'
    $backendTask = Get-ScheduledTask -TaskName $BackendTaskName -ErrorAction SilentlyContinue
    $proxyTask = Get-ScheduledTask -TaskName $ProxyTaskName -ErrorAction SilentlyContinue
    $excludedDataPaths = @(Get-NormalizedUpdateBackupExclusions -ExcludeRelativePaths $OpenWebUIUpdateExcludedDataPaths)

    $transaction = [pscustomobject][ordered]@{
        SchemaVersion = 3
        ProductId = $ProductId
        InstallerVersion = $ScriptVersion
        ActivationMethod = 'RecreateAtFinalPath'
        Stage = 'StagingComplete'
        FromVersion = $FromVersion
        ToVersion = $stagedVersion
        StagingVenvPath = $OpenWebUIStagingVenvDir
        RollbackVenvPath = $OpenWebUIRollbackVenvDir
        BackupRoot = $backupRoot
        DataBackupPath = $dataBackup
        ConfigBackupPath = $configBackup
        DataManifestPath = $dataManifest
        BackupCompletionMarkerPath = $backupCompletionMarker
        ExcludedDataPaths = $excludedDataPaths
        DataBackupVerified = $false
        BackendTaskExistedBeforeUpdate = ($null -ne $backendTask -and (Test-ScheduledTaskBelongsToDeployment -Task $backendTask))
        ProxyTaskExistedBeforeUpdate = ($null -ne $proxyTask -and (Test-ScheduledTaskBelongsToDeployment -Task $proxyTask))
        BackendTaskWasRunningBeforeUpdate = ($null -ne $backendTask -and (Test-ScheduledTaskBelongsToDeployment -Task $backendTask) -and [string]$backendTask.State -eq 'Running')
        ProxyTaskWasRunningBeforeUpdate = ($null -ne $proxyTask -and (Test-ScheduledTaskBelongsToDeployment -Task $proxyTask) -and [string]$proxyTask.State -eq 'Running')
        StartedAt = [DateTimeOffset]::UtcNow.ToString('o')
        UpdatedAt = [DateTimeOffset]::UtcNow.ToString('o')
    }
    Write-OpenWebUIUpdateTransaction -Transaction $transaction

    Stop-Deployment -RequireStopped
    Test-OpenWebUISqliteIntegrity -PythonPath $PythonExe -Checkpoint

    Ensure-Directory $backupRoot
    $transaction.Stage = 'BackupInProgress'
    Write-OpenWebUIUpdateTransaction -Transaction $transaction

    Write-Notice "Vytvarim long-path-safe SHA-256 manifest trvalych uzivatelskych dat. Vylouceno: $($excludedDataPaths -join ', ')."
    $sourceManifest = Write-DirectoryIntegrityManifest `
        -Path $DataDir `
        -Destination $dataManifest `
        -ExcludeRelativePaths $excludedDataPaths
    Assert-FreeSpaceForUpdateBackup -RequiredDataBytes ([int64]$sourceManifest.TotalBytes)

    Invoke-RobocopyDirectory `
        -Source $DataDir `
        -Destination $dataBackup `
        -ExcludeRelativePaths $excludedDataPaths

    # Overujeme jak zalohu, tak znovu zdroj. Pokud by se trvala data zmenila
    # i po zastaveni backendu, aktualizace se pred swapem bezpecne prerusi.
    Assert-DirectoryMatchesIntegrityManifest -Path $dataBackup -ManifestPath $dataManifest
    Assert-DirectoryMatchesIntegrityManifest -Path $DataDir -ManifestPath $dataManifest
    Copy-OpenWebUIUpdateConfigSnapshot -Destination $configBackup

    $backupMetadata = [ordered]@{
        SchemaVersion = 1
        ProductId = $ProductId
        InstallerVersion = $ScriptVersion
        FromVersion = $FromVersion
        ToVersion = $stagedVersion
        CreatedAtUtc = [DateTimeOffset]::UtcNow.ToString('o')
        Manifest = [IO.Path]::GetFileName($dataManifest)
        ExcludedDataPaths = $excludedDataPaths
        FileCount = [int64]$sourceManifest.FileCount
        TotalBytes = [int64]$sourceManifest.TotalBytes
    }
    Write-Utf8NoBom -Path $backupCompletionMarker -Content (($backupMetadata | ConvertTo-Json -Depth 6) + "`r`n")
    Set-AdminOnlyFileAcl -Path $backupCompletionMarker

    $transaction.DataBackupVerified = $true
    $transaction.Stage = 'DataBackedUp'
    Write-OpenWebUIUpdateTransaction -Transaction $transaction
    Write-Ok "Zaloha trvalych dat byla overena SHA-256 ($($sourceManifest.FileCount) souboru, $($sourceManifest.TotalBytes) B): $backupRoot"
    Write-Notice 'Adresare cache a runtime-temp nejsou uzivatelska data; pri rollbacku se bezpecne znovu vytvori prazdne.'

    if (-not (Test-Path -LiteralPath $VenvDir -PathType Container)) {
        throw "Pred prepnuti aktualizace chybi aktivni venv $VenvDir."
    }

    # Python virtualni prostredi neni prenosne. Windows console-script launchery
    # vytvorene uv obsahuji vazbu na cestu, ve ktere vznikly. Preflight venv se
    # proto nikdy nepresouva do $VenvDir; cilova verze se po zaloze vytvori znovu
    # primo v kanonicke ceste. Uv cache uz je preflight instalaci zahrata.
    $transaction.Stage = 'SwapPlanned'
    Write-OpenWebUIUpdateTransaction -Transaction $transaction
    Move-Item -LiteralPath $VenvDir -Destination $OpenWebUIRollbackVenvDir

    $transaction.Stage = 'ActiveInstallInProgress'
    Write-OpenWebUIUpdateTransaction -Transaction $transaction
    Remove-ManagedPathWithRetry -Path $OpenWebUIStagingVenvDir
    Write-Notice "Preflight Open WebUI $stagedVersion uspel. Vytvarim cilove venv primo v $VenvDir; venv se nepresouva."
    $activeInstalledVersion = Install-OpenWebUIIntoVenv -Destination $VenvDir -TargetVersion $stagedVersion
    Assert-ActiveOpenWebUIVenv -ExpectedVersion $activeInstalledVersion

    $transaction.Stage = 'VenvSwapped'
    Write-OpenWebUIUpdateTransaction -Transaction $transaction
    $script:InstalledOpenWebUIVersion = $activeInstalledVersion
    Write-Ok "Nova verze $activeInstalledVersion je pripravena primo v kanonicke ceste. Databazove migrace se overi pri startu backendu; do te doby je zachovan rollback."
}

function Wait-OpenWebUIReady {
    param([ValidateRange(10, 900)][int]$TimeoutSeconds = 300)

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $lastError = ''
    $readyEndpointSupported = $true
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($readyEndpointSupported) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/ready" -f $BackendPort) -Method Get -TimeoutSec 10
                if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                    Write-Ok "Open WebUI readiness probe /ready vratila HTTP $($response.StatusCode)."
                    return
                }
                $lastError = "HTTP $($response.StatusCode) z /ready"
            }
            catch {
                $statusCode = 0
                try {
                    if ($null -ne $_.Exception.Response) {
                        $statusCode = [int]$_.Exception.Response.StatusCode
                    }
                }
                catch { $statusCode = 0 }
                if ($statusCode -eq 404) {
                    $readyEndpointSupported = $false
                    Write-Notice 'Tato verze nema /ready; pro kontrolu startu pouziji /health.'
                }
                else {
                    $lastError = $_.Exception.Message
                }
            }
        }

        if (-not $readyEndpointSupported) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/health" -f $BackendPort) -Method Get -TimeoutSec 10
                if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                    Write-Ok "Open WebUI health probe /health vratila HTTP $($response.StatusCode)."
                    return
                }
                $lastError = "HTTP $($response.StatusCode) z /health"
            }
            catch {
                $lastError = $_.Exception.Message
            }
        }
        Start-Sleep -Seconds 3
    }
    throw "Open WebUI nedokoncilo start a databazove migrace do $TimeoutSeconds sekund. Posledni detail: $lastError"
}

function Complete-PendingOpenWebUIUpdate {
    $transaction = Read-OpenWebUIUpdateTransaction
    if ($null -eq $transaction) { return }
    if ([string]$transaction.Stage -eq 'Verified') {
        Remove-ManagedPathWithRetry -Path ([string]$transaction.RollbackVenvPath)
        Remove-ManagedPathWithRetry -Path ([string]$transaction.StagingVenvPath)
        Clear-OpenWebUIUpdateTransaction
        return
    }
    if ([string]$transaction.Stage -ne 'VenvSwapped') {
        throw "Aktualizacni transakce je ve stavu '$($transaction.Stage)', ktery nelze oznacit jako uspesny."
    }

    $actualVersion = Get-InstalledOpenWebUIVersion
    if (-not [string]::Equals($actualVersion, [string]$transaction.ToVersion, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Po startu backendu je aktivni Open WebUI $actualVersion, ocekavana verze je $($transaction.ToVersion)."
    }
    Test-OpenWebUISqliteIntegrity -PythonPath $PythonExe

    $transaction.Stage = 'Verified'
    Write-OpenWebUIUpdateTransaction -Transaction $transaction
    Remove-ManagedPathWithRetry -Path ([string]$transaction.RollbackVenvPath)
    Remove-ManagedPathWithRetry -Path ([string]$transaction.StagingVenvPath)
    $script:InstalledOpenWebUIVersion = $actualVersion
    Clear-OpenWebUIUpdateTransaction
    Remove-OldOpenWebUIUpdateBackups
    Write-Ok "Aktualizace Open WebUI $($transaction.FromVersion) -> $actualVersion byla overena. Zaloha dat zustava v $($transaction.BackupRoot)."
}

function Rollback-PendingOpenWebUIUpdate {
    param([switch]$RestartPreviousDeployment)

    $transaction = Read-OpenWebUIUpdateTransaction
    if ($null -eq $transaction) { return $false }

    Write-Caution "Aktualizace Open WebUI nebyla dokoncena; obnovuji verzi $($transaction.FromVersion) a predaktualizacni trvala data."
    Stop-Deployment -RequireStopped

    if ([bool]$transaction.DataBackupVerified) {
        $dataBackup = [string]$transaction.DataBackupPath
        if (-not (Test-DirectoryExistsLongPath -Path $dataBackup)) {
            throw "Rollback nelze provest: chybi overena zaloha dat $dataBackup. Transakcni stav zustava zachovan."
        }
        $manifestPath = [string]$transaction.DataManifestPath
        Assert-DirectoryMatchesIntegrityManifest -Path $dataBackup -ManifestPath $manifestPath

        # Zaloha je overena pred jakoukoli destruktivni operaci. Cely DATA_DIR
        # potom vytvorime znovu, cimz se odstrani i cache vytvorena novou verzi.
        Remove-DirectoryTreeRobust -Path $DataDir
        Ensure-Directory $DataDir
        Invoke-RobocopyDirectory -Source $dataBackup -Destination $DataDir
        Ensure-Directory $RuntimeTempDir
        Ensure-Directory $CacheDir
        Ensure-Directory $HfCacheDir
        Set-PrivateAcl $InstallRoot
        Assert-DirectoryMatchesIntegrityManifest -Path $DataDir -ManifestPath $manifestPath
        Write-Ok 'Predaktualizacni trvala data byla obnovena; regenerovatelna cache byla vycistena.'
    }
    else {
        # Pred overenim zalohy ani pred swapem se DATA_DIR nemeni. Castecny
        # backup lze proto bezpecne odstranit a puvodni data ponechat nedotcena.
        $partialBackupRoot = [string]$transaction.BackupRoot
        if (-not [string]::IsNullOrWhiteSpace($partialBackupRoot) -and
            (Test-DirectoryExistsLongPath -Path $partialBackupRoot)) {
            Remove-DirectoryTreeRobust -Path $partialBackupRoot
            Write-Notice "Castecna neoverena zaloha byla odstranena: $partialBackupRoot"
        }
    }

    Restore-OpenWebUIUpdateConfigSnapshot -Source ([string]$transaction.ConfigBackupPath)

    $rollbackVenv = [string]$transaction.RollbackVenvPath
    if (Test-Path -LiteralPath $rollbackVenv -PathType Container) {
        Remove-ManagedPathWithRetry -Path $VenvDir
        Move-Item -LiteralPath $rollbackVenv -Destination $VenvDir
        Assert-ActiveOpenWebUIVenv -ExpectedVersion ([string]$transaction.FromVersion)
    }
    elseif ([string]$transaction.Stage -in @('StagingComplete', 'BackupInProgress', 'DataBackedUp', 'SwapPlanned')) {
        # Do prvniho presunu je puvodni venv stale aktivni. Checkpoint SwapPlanned
        # se zapisuje tesne pred Move-Item; pokud proces skoncil mezi checkpointem
        # a presunem, tato kontrola potvrdi puvodni stav.
        $activeVersion = Get-InstalledOpenWebUIVersion -Quiet
        if (-not [string]::Equals($activeVersion, [string]$transaction.FromVersion, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Rollback venv $rollbackVenv chybi a aktivni venv neni puvodni verze $($transaction.FromVersion). Transakcni stav zustava zachovan."
        }
        Assert-ActiveOpenWebUIVenv -ExpectedVersion ([string]$transaction.FromVersion)
    }
    elseif ([string]$transaction.Stage -in @('ActiveInstallInProgress', 'VenvSwapped')) {
        throw "Rollback venv $rollbackVenv chybi, ackoli puvodni venv uz bylo odsunuto. Transakcni stav zustava zachovan."
    }

    Remove-ManagedPathWithRetry -Path ([string]$transaction.StagingVenvPath)
    $script:OpenWebUIVersion = [string]$transaction.FromVersion
    $script:InstalledOpenWebUIVersion = [string]$transaction.FromVersion
    Clear-OpenWebUIUpdateTransaction

    $transactionProperties = @($transaction.PSObject.Properties.Name)
    $backendWasRunning = if ($transactionProperties -contains 'BackendTaskWasRunningBeforeUpdate') {
        [bool]$transaction.BackendTaskWasRunningBeforeUpdate
    }
    else {
        [bool]$transaction.BackendTaskExistedBeforeUpdate
    }
    $proxyWasRunning = if ($transactionProperties -contains 'ProxyTaskWasRunningBeforeUpdate') {
        [bool]$transaction.ProxyTaskWasRunningBeforeUpdate
    }
    else {
        [bool]$transaction.ProxyTaskExistedBeforeUpdate
    }

    if ($RestartPreviousDeployment -and $backendWasRunning) {
        try {
            if (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf) {
                $configuration = Read-RuntimeConfig
                $script:BackendPort = [int]$configuration.BackendPort
                $script:HttpPort = [int]$configuration.HttpPort
                $script:HttpsPort = [int]$configuration.HttpsPort
            }
            Start-TaskIfNeeded -TaskName $BackendTaskName
            Wait-TcpPort -HostName '127.0.0.1' -Port $BackendPort -ComponentName 'Puvodni Open WebUI backend po rollbacku'
            Wait-OpenWebUIReady -TimeoutSeconds 180
            if ($proxyWasRunning) {
                Start-TaskIfNeeded -TaskName $ProxyTaskName
                Wait-TcpPort -HostName '127.0.0.1' -Port $HttpsPort -ComponentName 'Caddy po rollbacku'
            }
            Write-Ok "Puvodni Open WebUI $($transaction.FromVersion) bylo po rollbacku znovu spusteno."
        }
        catch {
            throw "Data a venv byly obnoveny, ale puvodni sluzbu se nepodarilo znovu spustit: $($_.Exception.Message)"
        }
    }

    return $true
}

function Recover-PendingOpenWebUIUpdate {
    $transaction = Read-OpenWebUIUpdateTransaction
    if ($null -eq $transaction) {
        if (Test-Path -LiteralPath $OpenWebUIStagingVenvDir) {
            Remove-ManagedPathWithRetry -Path $OpenWebUIStagingVenvDir
        }
        if (Test-Path -LiteralPath $OpenWebUIRollbackVenvDir) {
            if (-not (Test-Path -LiteralPath $VenvDir)) {
                Move-Item -LiteralPath $OpenWebUIRollbackVenvDir -Destination $VenvDir
                Reset-TreeToInheritedAcl -Path $VenvDir
                Write-Caution 'Byl nalezen osamoceny rollback venv a aktivni venv chybel; puvodni venv byl obnoven.'
            }
            else {
                throw "Existuje osamoceny rollback venv $OpenWebUIRollbackVenvDir bez transakcniho checkpointu. Z bezpecnostnich duvodu jej skript automaticky nesmaze."
            }
        }
        return
    }

    if ([string]$transaction.Stage -eq 'Verified') {
        Remove-ManagedPathWithRetry -Path ([string]$transaction.RollbackVenvPath)
        Remove-ManagedPathWithRetry -Path ([string]$transaction.StagingVenvPath)
        Clear-OpenWebUIUpdateTransaction
        Write-Ok 'Dokoncil jsem uklid jiz overene aktualizacni transakce.'
        return
    }

    [void](Rollback-PendingOpenWebUIUpdate -RestartPreviousDeployment)
    Write-Notice 'Nedokoncena aktualizace byla pred novym pokusem vracena do konzistentniho stavu.'
}

function Install-OpenWebUI {
    Write-Step 'Instaluji nebo bezpecne aktualizuji Python 3.11 a Open WebUI'

    if (-not (Test-Path -LiteralPath $UvExe -PathType Leaf)) {
        throw "Nenalezen uv: $UvExe"
    }

    $targetVersionObject = ConvertTo-OpenWebUIVersionObject -Value $OpenWebUIVersion
    if ($null -eq $targetVersionObject) {
        throw "Cilova verze Open WebUI nebyla po kontrole vydani platna: $OpenWebUIVersion"
    }
    $targetVersion = ConvertTo-OpenWebUIVersionText -Version $targetVersionObject
    $currentVersion = Get-InstalledOpenWebUIVersion -Quiet
    $currentVersionObject = ConvertTo-OpenWebUIVersionObject -Value $currentVersion
    $existingDatabase = Test-Path -LiteralPath (Join-Path $DataDir 'webui.db') -PathType Leaf
    $existingVenv = Test-Path -LiteralPath $VenvDir -PathType Container
    if ($null -eq $currentVersionObject -and ($existingDatabase -or $existingVenv)) {
        throw "Existuje predchozi instalace nebo databaze, ale jeji verzi nelze spolehlive urcit. Automaticka aktualizace proto nebyla provedena. Nejprve opravte/obnovte puvodni venv nebo pouzijte zalohu; data zustala beze zmeny."
    }

    if ($null -ne $currentVersionObject -and $currentVersionObject -gt $targetVersionObject -and -not $AllowOpenWebUIDowngrade) {
        throw "Nainstalovana verze $currentVersion je novejsi nez cilova $targetVersion. Automaticky downgrade je zablokovan."
    }

    if ($null -ne $currentVersionObject -and $currentVersionObject -eq $targetVersionObject) {
        Assert-ActiveOpenWebUIVenv -ExpectedVersion $targetVersion
        $script:InstalledOpenWebUIVersion = $targetVersion
        Write-Ok "Open WebUI $targetVersion je jiz nainstalovano; uzivatelska data ani venv se nemeni."
        return
    }

    if ($null -ne $currentVersionObject) {
        Invoke-TransactionalOpenWebUIVenvSwap -FromVersion $currentVersion -ToVersion $targetVersion
        return
    }

    $installedVersion = Install-OpenWebUIIntoVenv -Destination $VenvDir -TargetVersion $targetVersion
    Assert-ActiveOpenWebUIVenv -ExpectedVersion $installedVersion
    $script:InstalledOpenWebUIVersion = $installedVersion
    Write-Ok "Open WebUI $installedVersion"
}

function Get-LocalHostData {
    $shortName = $env:COMPUTERNAME.Trim().ToLowerInvariant()
    $names = [Collections.Generic.List[string]]::new()

    if ($shortName -match '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$') {
        $names.Add($shortName)
    }

    try {
        $dnsName = ([Net.Dns]::GetHostEntry($env:COMPUTERNAME).HostName).Trim().TrimEnd('.').ToLowerInvariant()
        if ($dnsName -match '^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$') {
            $names.Add($dnsName)
        }
    }
    catch {
        # FQDN neni na kazdem stroji dostupne; kratky nazev/IP adresy staci.
    }

    try {
        $computerSystem = Get-CimInstance -ClassName Win32_ComputerSystem -ErrorAction Stop
        if ($computerSystem.PartOfDomain -and -not [string]::IsNullOrWhiteSpace([string]$computerSystem.Domain)) {
            $domainFqdn = "$shortName.$([string]$computerSystem.Domain)".Trim().TrimEnd('.').ToLowerInvariant()
            if ($domainFqdn -match '^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$') {
                $names.Add($domainFqdn)
            }
        }
    }
    catch {
        # Nepovinne.
    }

    $addresses = [Collections.Generic.List[string]]::new()
    try {
        $ipConfigurations = Get-NetIPConfiguration -ErrorAction Stop | Where-Object {
            $null -ne $_.NetAdapter -and $_.NetAdapter.Status -eq 'Up' -and $null -ne $_.IPv4Address
        }

        # Nejprve rozhrani s vychozi branou, potom vsechna ostatni aktivni
        # rozhrani. Tak se do SAN certifikatu dostanou i adresy vnitrnich siti.
        $preferred = @($ipConfigurations | Where-Object { $null -ne $_.IPv4DefaultGateway })
        $otherConfigurations = @($ipConfigurations | Where-Object { $null -eq $_.IPv4DefaultGateway })
        $orderedConfigurations = @($preferred) + @($otherConfigurations)

        foreach ($configuration in $orderedConfigurations) {
            foreach ($item in @($configuration.IPv4Address)) {
                $ip = [string]$item.IPAddress
                if ($ip -and $ip -notmatch '^127\.' -and $ip -notmatch '^169\.254\.' -and $ip -ne '0.0.0.0') {
                    $addresses.Add($ip)
                }
            }
        }
    }
    catch {
        try {
            foreach ($ipAddress in [Net.Dns]::GetHostAddresses($env:COMPUTERNAME)) {
                if ($ipAddress.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) {
                    $ip = $ipAddress.ToString()
                    if ($ip -notmatch '^127\.' -and $ip -notmatch '^169\.254\.') {
                        $addresses.Add($ip)
                    }
                }
            }
        }
        catch {
            # localhost zustane vzdy dostupny.
        }
    }

    $uniqueNames = @($names.ToArray() | Select-Object -Unique)
    $uniqueAddresses = @($addresses.ToArray() | Select-Object -Unique)

    if ($uniqueNames.Count -gt 0) {
        $fqdnCandidate = @($uniqueNames | Where-Object { $_ -like '*.*' }) | Select-Object -First 1
        if ($null -ne $fqdnCandidate) {
            $primary = [string]$fqdnCandidate
        }
        else {
            $primary = [string]$uniqueNames[0]
        }
    }
    elseif ($uniqueAddresses.Count -gt 0) {
        $primary = [string]$uniqueAddresses[0]
    }
    else {
        $primary = 'localhost'
    }

    $allHosts = [Collections.Generic.List[string]]::new()
    $allHosts.Add($primary)
    foreach ($name in $uniqueNames) { $allHosts.Add([string]$name) }
    foreach ($address in $uniqueAddresses) { $allHosts.Add([string]$address) }
    $allHosts.Add('localhost')
    $allHosts.Add('127.0.0.1')

    return [pscustomobject]@{
        Primary = $primary
        Hosts = @($allHosts.ToArray() | Select-Object -Unique)
        Names = $uniqueNames
        Addresses = $uniqueAddresses
    }
}

function Format-HttpsUrl {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port
    )

    if ($Port -eq 443) {
        return "https://$HostName"
    }
    return "https://${HostName}:$Port"
}

function Normalize-ApiBaseUrl {
    param([Parameter(Mandatory = $true)][string]$Url)
    $trimmed = $Url.Trim().TrimEnd('/')
    $uri = $null
    if (-not [Uri]::TryCreate($trimmed, [UriKind]::Absolute, [ref]$uri)) {
        throw "Neplatne API URL: $Url"
    }
    if ($uri.Scheme -ne 'https') {
        throw 'API endpoint musi pouzivat HTTPS.'
    }
    if (-not [string]::IsNullOrWhiteSpace($uri.UserInfo) -or
        -not [string]::IsNullOrWhiteSpace($uri.Query) -or
        -not [string]::IsNullOrWhiteSpace($uri.Fragment)) {
        throw 'API endpoint nesmi obsahovat prihlasovaci udaje, query parametry ani fragment.'
    }
    return $trimmed
}

function Normalize-LocalAccessName {
    param([Parameter(Mandatory = $true)][string]$Value)

    $candidate = $Value.Trim().TrimEnd('.').ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($candidate) -or $candidate -match '[:/\\]') {
        throw 'LocalAccessName musi byt DNS jmeno nebo IPv4 adresa bez https://, portu a cesty.'
    }

    $parsedAddress = $null
    if ([Net.IPAddress]::TryParse($candidate, [ref]$parsedAddress)) {
        if ($parsedAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
            throw 'LocalAccessName v teto verzi podporuje pouze IPv4 adresu nebo DNS jmeno.'
        }
        return $parsedAddress.ToString()
    }

    $labelPattern = '[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
    if ($candidate.Length -gt 253 -or $candidate -notmatch "^(?:$labelPattern)(?:\.(?:$labelPattern))*$") {
        throw 'LocalAccessName musi byt platne DNS jmeno nebo IPv4 adresa, napr. webui.intranet.example.cz.'
    }
    return $candidate
}

function Validate-InstallParameters {
    if ($BackendPort -eq $HttpPort -or $BackendPort -eq $HttpsPort -or $HttpPort -eq $HttpsPort) {
        throw 'BackendPort, HttpPort a HttpsPort musi byt navzajem odlisne.'
    }

    if ([string]::IsNullOrWhiteSpace($DefaultModel)) {
        throw 'DefaultModel nesmi byt prazdny.'
    }
    $script:DefaultModel = $DefaultModel.Trim()

    if ([string]::IsNullOrWhiteSpace($ApiKey)) {
        throw 'ApiKey nesmi byt prazdny.'
    }
    $trimmedApiKey = $ApiKey.Trim()
    if (-not [string]::Equals($trimmedApiKey, $FakeApiKeyPlaceholder, [StringComparison]::OrdinalIgnoreCase) -and
        $trimmedApiKey -match '\s') {
        throw 'Skutecny ApiKey nesmi obsahovat mezery ani jine bile znaky.'
    }
    $script:ApiKey = $trimmedApiKey

    if (-not [string]::IsNullOrWhiteSpace($LocalAccessName)) {
        if ($CertificateMode -ne 'LocalCA') {
            throw 'LocalAccessName lze pouzit pouze s -CertificateMode LocalCA.'
        }
        $script:LocalAccessName = Normalize-LocalAccessName -Value $LocalAccessName
    }

    if ($CertificateMode -eq 'PublicACME') {
        if ($HttpPort -ne 80 -or $HttpsPort -ne 443) {
            throw 'Rezim PublicACME v tomto skriptu vyzaduje standardni porty 80 a 443.'
        }
        $script:PublicDomain = $PublicDomain.Trim().TrimEnd('.').ToLowerInvariant()
        $publicLabelPattern = '[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
        $publicAddress = $null
        $publicDomainIsIp = [Net.IPAddress]::TryParse($script:PublicDomain, [ref]$publicAddress)
        if ([string]::IsNullOrWhiteSpace($script:PublicDomain) -or
            $script:PublicDomain -match '[:/\\]' -or
            $script:PublicDomain.Length -gt 253 -or
            $script:PublicDomain -notmatch "^(?:$publicLabelPattern)(?:\.(?:$publicLabelPattern))+$" -or
            $publicDomainIsIp) {
            throw 'Pro PublicACME zadejte platnou verejnou DNS domenu bez https:// a bez cesty, napr. webui.example.cz.'
        }
        if (-not [string]::IsNullOrWhiteSpace($AcmeEmail) -and $AcmeEmail -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
            throw 'AcmeEmail musi byt platna e-mailova adresa, nebo muze zustat prazdny.'
        }
    }

    if ([string]::IsNullOrWhiteSpace($AdminEmail) -or $AdminEmail -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') {
        throw 'AdminEmail musi byt platna e-mailova adresa.'
    }
    if ([string]::IsNullOrWhiteSpace($AdminName)) {
        throw 'AdminName nesmi byt prazdny.'
    }
    if (-not [string]::IsNullOrWhiteSpace($AdminPassword) -and
        $AdminPassword -notmatch '^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{12,72}$') {
        throw 'AdminPassword musi mit 12 az 72 znaku a obsahovat velke/male pismeno, cislici a specialni znak.'
    }
    if (-not [string]::IsNullOrWhiteSpace($AdminPassword) -and
        [Text.Encoding]::UTF8.GetByteCount([string]$AdminPassword) -gt 72) {
        throw 'AdminPassword smi mit nejvyse 72 bajtu v UTF-8 kvuli omezeni hashovaciho algoritmu.'
    }

    $script:ApiBaseUrl = Normalize-ApiBaseUrl $ApiBaseUrl
}

function Read-RuntimeConfig {
    if (-not (Test-Path -LiteralPath $RuntimeConfigPath)) {
        throw "Instalace nebyla nalezena: chybi $RuntimeConfigPath"
    }
    $configuration = Get-Content -LiteralPath $RuntimeConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $properties = @($configuration.PSObject.Properties.Name)
    if ($properties -contains 'ProductId' -and
        -not [string]::Equals([string]$configuration.ProductId, $ProductId, [StringComparison]::Ordinal)) {
        throw "Runtime konfigurace $RuntimeConfigPath patri jinemu produktu ('$($configuration.ProductId)')."
    }
    return $configuration
}

function Write-RuntimeConfig {
    param([Parameter(Mandatory = $true)]$Configuration)
    Ensure-Directory $ConfigDir
    $json = $Configuration | ConvertTo-Json -Depth 10
    $temporaryPath = "$RuntimeConfigPath.tmp"
    Write-Utf8NoBom -Path $temporaryPath -Content ($json + "`r`n")
    Move-Item -LiteralPath $temporaryPath -Destination $RuntimeConfigPath -Force
}

function Get-ExistingSecret {
    # Profil obsahuje vyslovne zadanou hodnotu WEBUI_SECRET_KEY. Je pouzita
    # konzistentne pro nove instalace i --resume. Jeji zmena odhlasi uzivatele.
    return $ProfileWebUiSecret
}

function Get-ExistingAdminBootstrap {
    if (-not (Test-Path -LiteralPath $RuntimeConfigPath)) {
        return $null
    }

    try {
        $existing = Read-RuntimeConfig
        $properties = @($existing.Environment.PSObject.Properties.Name)
        if ($properties -notcontains 'WEBUI_ADMIN_PASSWORD' -or
            $properties -notcontains 'WEBUI_ADMIN_EMAIL') {
            return $null
        }

        $password = [string]$existing.Environment.WEBUI_ADMIN_PASSWORD
        $email = [string]$existing.Environment.WEBUI_ADMIN_EMAIL
        if ([string]::IsNullOrWhiteSpace($password) -or [string]::IsNullOrWhiteSpace($email)) {
            return $null
        }

        $name = $AdminName
        if ($properties -contains 'WEBUI_ADMIN_NAME' -and
            -not [string]::IsNullOrWhiteSpace([string]$existing.Environment.WEBUI_ADMIN_NAME)) {
            $name = [string]$existing.Environment.WEBUI_ADMIN_NAME
        }

        return [pscustomobject]@{
            Email = $email
            Name = $name
            Password = $password
        }
    }
    catch {
        Write-Caution "Stavajici bootstrap administratora nelze obnovit: $($_.Exception.Message)"
        return $null
    }
}

function New-RuntimeConfiguration {
    param(
        [Parameter(Mandatory = $true)][string[]]$SiteHosts,
        [Parameter(Mandatory = $true)][string]$PrimaryUrl,
        [Parameter(Mandatory = $true)][string[]]$AllowedOrigins,
        [Parameter(Mandatory = $true)][string]$WebUiSecret,
        [Parameter(Mandatory = $true)][bool]$BootstrapAdmin,
        [string]$BootstrapPassword = ''
    )

    $environment = [ordered]@{
        DATA_DIR = $DataDir
        TEMP = $RuntimeTempDir
        TMP = $RuntimeTempDir
        XDG_CACHE_HOME = $CacheDir
        HF_HOME = $HfCacheDir
        # Open WebUI pri startu kopiruje frontend assets do STATIC_DIR. Vychozi
        # umisteni uvnitr read-only venv neni zapisovatelne pro LOCAL SERVICE.
        STATIC_DIR = $StaticDir
        PYTHONDONTWRITEBYTECODE = '1'
        PYTHONUNBUFFERED = '1'
        ENV = 'prod'
        WEBUI_NAME = 'e-INFRA CZ Open WebUI'
        WEBUI_URL = $PrimaryUrl
        CORS_ALLOW_ORIGIN = ($AllowedOrigins -join ';')
        WEBUI_SECRET_KEY = $WebUiSecret
        WEBUI_AUTH = 'True'
        UVICORN_WORKERS = '1'
        FORWARDED_ALLOW_IPS = '127.0.0.1'

        ENABLE_OPENAI_API = 'True'
        ENABLE_OLLAMA_API = 'False'
        OPENAI_API_BASE_URL = $ApiBaseUrl
        OPENAI_API_KEY = $ApiKey
        DEFAULT_MODELS = $DefaultModel.Trim()

        ENABLE_PERSISTENT_CONFIG = 'True'
        ENABLE_DIRECT_CONNECTIONS = 'True'
        ENABLE_OPENAI_API_PASSTHROUGH = 'True'

        # Funkcni profil pozadovany uzivatelem. Tyto volby umoznuji nahravani
        # a spousteni serverovych pluginu/kodu; pouzivejte pouze pro duveryhodne uzivatele.
        ENABLE_PLUGINS = 'True'
        ENABLE_PIP_INSTALL_FRONTMATTER_REQUIREMENTS = 'True'
        ENABLE_CODE_EXECUTION = 'True'
        ENABLE_CODE_INTERPRETER = 'True'
        ENABLE_API_KEYS = 'True'
        USER_PERMISSIONS_WORKSPACE_TOOLS_ACCESS = 'True'
        USER_PERMISSIONS_WORKSPACE_TOOLS_IMPORT = 'True'
        USER_PERMISSIONS_WORKSPACE_SKILLS_ACCESS = 'True'
        USER_PERMISSIONS_WORKSPACE_SKILLS_IMPORT = 'True'
        USER_PERMISSIONS_CHAT_WEB_UPLOAD = 'True'

        ENABLE_SIGNUP = $(if ($DisableSignup) { 'False' } else { 'True' })
        DEFAULT_USER_ROLE = 'pending'
        ENABLE_PASSWORD_VALIDATION = 'True'
        PASSWORD_VALIDATION_REGEX_PATTERN = '^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).{12,72}$'
        PASSWORD_VALIDATION_HINT = 'Alespon 12 znaku: velke a male pismeno, cislice a specialni znak.'

        WEBUI_SESSION_COOKIE_SECURE = 'True'
        WEBUI_AUTH_COOKIE_SECURE = 'True'
        WEBUI_SESSION_COOKIE_SAME_SITE = 'lax'
        WEBUI_AUTH_COOKIE_SAME_SITE = 'lax'
        JWT_EXPIRES_IN = '7d'
        ENABLE_COMMUNITY_SHARING = 'True'
        ENABLE_ADMIN_CHAT_ACCESS = 'True'
        ENABLE_ADMIN_EXPORT = 'False'
        REQUESTS_VERIFY = 'True'
        AIOHTTP_CLIENT_SESSION_SSL = 'True'
        ENABLE_RAG_LOCAL_WEB_FETCH = 'True'
        GLOBAL_LOG_LEVEL = 'INFO'
    }

    if ($BootstrapAdmin) {
        $environment.WEBUI_ADMIN_EMAIL = $AdminEmail.Trim()
        $environment.WEBUI_ADMIN_NAME = $AdminName.Trim()
        $environment.WEBUI_ADMIN_PASSWORD = $BootstrapPassword
    }

    return [ordered]@{
        SchemaVersion = 1
        InstallerVersion = $ScriptVersion
        ProductId = $ProductId
        RequestedOpenWebUIVersion = $OpenWebUIVersion
        InstalledOpenWebUIVersion = $script:InstalledOpenWebUIVersion
        LatestAvailableOpenWebUIVersion = $script:LatestAvailableOpenWebUIVersion
        OpenWebUIUpdatePolicy = $OpenWebUIUpdatePolicy
        MinimumReleaseAgeHours = $MinimumReleaseAgeHours
        LastOpenWebUIUpdateCheckUtc = $script:LastOpenWebUIUpdateCheckUtc
        OpenWebUIReleaseUrl = $script:OpenWebUIReleaseUrl
        OpenWebUIReleasePublishedAtUtc = $script:OpenWebUIReleasePublishedAtUtc
        OpenWebUIUpdateDecision = $script:OpenWebUIUpdateDecision
        PythonVersion = '3.11'
        CertificateMode = $CertificateMode
        PublicDomain = $PublicDomain
        LocalAccessName = $LocalAccessName
        PrimaryUrl = $PrimaryUrl
        SiteHosts = $SiteHosts
        HttpPort = $HttpPort
        HttpsPort = $HttpsPort
        BackendHost = '127.0.0.1'
        BackendPort = $BackendPort
        InstallRoot = $InstallRoot
        DataDirectory = $DataDir
        WorkingDirectory = $InstallRoot
        OpenWebUIExecutable = $OpenWebUIExe
        CaddyExecutable = $CaddyExe
        Caddyfile = $CaddyfilePath
        CaddyDataBase = $CaddyDataBase
        CaddyConfigBase = $CaddyConfigBase
        LogDirectory = $LogDir
        LocalCaThumbprint = ''
        Environment = $environment
    }
}

function Write-ComponentRunner {
    $content = @'
#requires -Version 5.1
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Backend', 'Caddy')]
    [string]$Component
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$configPath = Join-Path $PSScriptRoot 'runtime.json'
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Rotate-Log {
    param([string]$Path)
    if ((Test-Path -LiteralPath $Path) -and (Get-Item -LiteralPath $Path).Length -gt 52428800) {
        $archive = "$Path.1"
        Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $Path -Destination $archive -Force
    }
}

function ConvertTo-NativeCommandLineArgument {
    param([AllowEmptyString()][string]$Value)

    if ($Value.Length -gt 0 -and $Value -notmatch '[\s"]') {
        return $Value
    }

    $builder = New-Object Text.StringBuilder
    [void]$builder.Append([char]34)
    $backslashCount = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq [char]92) {
            $backslashCount++
            continue
        }
        if ($character -eq [char]34) {
            for ($index = 0; $index -lt (($backslashCount * 2) + 1); $index++) {
                [void]$builder.Append([char]92)
            }
            [void]$builder.Append([char]34)
            $backslashCount = 0
            continue
        }
        for ($index = 0; $index -lt $backslashCount; $index++) {
            [void]$builder.Append([char]92)
        }
        $backslashCount = 0
        [void]$builder.Append($character)
    }
    for ($index = 0; $index -lt ($backslashCount * 2); $index++) {
        [void]$builder.Append([char]92)
    }
    [void]$builder.Append([char]34)
    return $builder.ToString()
}

function Invoke-WithUtf8Log {
    param(
        [string]$Executable,
        [string[]]$Arguments,
        [string]$LogPath
    )

    Rotate-Log -Path $LogPath
    $encoding = New-Object Text.UTF8Encoding($false)
    $header = "`r`n--- $([DateTime]::Now.ToString('o')) start: $Executable $($Arguments -join ' ') ---`r`n"
    [IO.File]::AppendAllText($LogPath, $header, $encoding)

    $encodedArguments = foreach ($argument in $Arguments) {
        ConvertTo-NativeCommandLineArgument -Value ([string]$argument)
    }

    $startInfo = New-Object Diagnostics.ProcessStartInfo
    $startInfo.FileName = $Executable
    $startInfo.Arguments = ($encodedArguments -join ' ')
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    if (($startInfo.PSObject.Properties.Name -contains 'StandardOutputEncoding') -and
        ($startInfo.PSObject.Properties.Name -contains 'StandardErrorEncoding')) {
        $startInfo.StandardOutputEncoding = $encoding
        $startInfo.StandardErrorEncoding = $encoding
    }

    $process = New-Object Diagnostics.Process
    $process.StartInfo = $startInfo
    $exitCode = 1
    $started = $false

    try {
        $started = $process.Start()
        if (-not $started) {
            throw 'System.Diagnostics.Process.Start vratil hodnotu False.'
        }

        # Oba proudy cteme asynchronne, ale zapisujeme je z jednoho vlakna.
        # Tim nevznika PowerShell ErrorRecord ze stderr a logy jsou dostupne
        # prubezne i behem dlouhodobe bezici sluzby.
        $stdoutComplete = $false
        $stderrComplete = $false
        $stdoutTask = $process.StandardOutput.ReadLineAsync()
        $stderrTask = $process.StandardError.ReadLineAsync()

        while (-not ($stdoutComplete -and $stderrComplete)) {
            $madeProgress = $false

            if (-not $stdoutComplete -and $stdoutTask.IsCompleted) {
                $stdoutLine = $stdoutTask.GetAwaiter().GetResult()
                if ($null -eq $stdoutLine) {
                    $stdoutComplete = $true
                }
                else {
                    $line = "$([DateTime]::Now.ToString('o')) $stdoutLine`r`n"
                    [IO.File]::AppendAllText($LogPath, $line, $encoding)
                    $stdoutTask = $process.StandardOutput.ReadLineAsync()
                }
                $madeProgress = $true
            }

            if (-not $stderrComplete -and $stderrTask.IsCompleted) {
                $stderrLine = $stderrTask.GetAwaiter().GetResult()
                if ($null -eq $stderrLine) {
                    $stderrComplete = $true
                }
                else {
                    $line = "$([DateTime]::Now.ToString('o')) $stderrLine`r`n"
                    [IO.File]::AppendAllText($LogPath, $line, $encoding)
                    $stderrTask = $process.StandardError.ReadLineAsync()
                }
                $madeProgress = $true
            }

            if (-not $madeProgress) {
                Start-Sleep -Milliseconds 50
            }
        }

        $process.WaitForExit()
        $exitCode = [int]$process.ExitCode
    }
    catch {
        if ($started) {
            try {
                if (-not $process.HasExited) {
                    $process.Kill()
                    $process.WaitForExit()
                }
            }
            catch {
                # Nejlepsi mozne uklizeni; puvodni chyba se zapise nize.
            }
        }
        $failure = "$([DateTime]::Now.ToString('o')) runner error: $($_.Exception.Message)`r`n"
        [IO.File]::AppendAllText($LogPath, $failure, $encoding)
        $exitCode = 1
    }
    finally {
        $process.Dispose()
    }

    [IO.File]::AppendAllText($LogPath, "--- exit code: $exitCode ---`r`n", $encoding)
    return $exitCode
}

Set-Location -LiteralPath ([string]$config.WorkingDirectory)

if ($Component -eq 'Backend') {
    foreach ($property in $config.Environment.PSObject.Properties) {
        [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value, 'Process')
    }

    $logPath = Join-Path ([string]$config.LogDirectory) 'open-webui.log'
    $arguments = @(
        'serve',
        '--host', [string]$config.BackendHost,
        '--port', [string]$config.BackendPort
    )
    $code = Invoke-WithUtf8Log -Executable ([string]$config.OpenWebUIExecutable) -Arguments $arguments -LogPath $logPath
    exit $code
}

$env:XDG_DATA_HOME = [string]$config.CaddyDataBase
$env:XDG_CONFIG_HOME = [string]$config.CaddyConfigBase
$logPath = Join-Path ([string]$config.LogDirectory) 'caddy-runtime.log'
$arguments = @('run', '--config', [string]$config.Caddyfile, '--adapter', 'caddyfile')
$code = Invoke-WithUtf8Log -Executable ([string]$config.CaddyExecutable) -Arguments $arguments -LogPath $logPath
exit $code
'@
    Write-Utf8NoBom -Path $RuntimeScriptPath -Content $content
}

function Convert-ToCaddyPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return $Path.Replace('\', '/')
}

function Write-CaddyConfiguration {
    param(
        [Parameter(Mandatory = $true)][string[]]$SiteHosts,
        [Parameter(Mandatory = $true)][string]$PrimaryServerName
    )

    $globalLines = [Collections.Generic.List[string]]::new()
    $globalLines.Add('{')
    $globalLines.Add('    admin off')
    $globalLines.Add("    http_port $HttpPort")
    $globalLines.Add("    https_port $HttpsPort")
    if ($CertificateMode -eq 'LocalCA') {
        # Duveru spravuje tento instalator a eviduje thumbprint pro --uninstall.
        # Caddy proto nesmi samovolne menit dalsi systemova/prohlizecova uloziste.
        $globalLines.Add('    skip_install_trust')
    }
    # default_sni je jmeno pro klienty bez SNI. Caddy ocekava DNS jmeno,
    # nikoli IP adresu, proto pri primarni IP zvolime prvni DNS jmeno ze SAN.
    $defaultSni = ''
    foreach ($candidate in (@($PrimaryServerName) + @($SiteHosts))) {
        if ([string]::IsNullOrWhiteSpace([string]$candidate)) { continue }
        $parsedAddress = $null
        if (-not [Net.IPAddress]::TryParse([string]$candidate, [ref]$parsedAddress)) {
            $defaultSni = [string]$candidate
            break
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($defaultSni)) {
        $globalLines.Add("    default_sni $defaultSni")
    }
    if ($CertificateMode -eq 'PublicACME' -and -not [string]::IsNullOrWhiteSpace($AcmeEmail)) {
        $globalLines.Add("    email $AcmeEmail")
    }
    $globalLines.Add('}')
    $globalLines.Add('')

    $siteAddresses = foreach ($siteHost in $SiteHosts) {
        if ($HttpsPort -eq 443) { [string]$siteHost } else { "${siteHost}:$HttpsPort" }
    }
    $siteAddress = @($siteAddresses) -join ', '
    $accessLog = Convert-ToCaddyPath (Join-Path $LogDir 'caddy-access.log')
    $hstsMaxAge = if ($CertificateMode -eq 'PublicACME') { '31536000' } else { '300' }

    $siteLines = [Collections.Generic.List[string]]::new()
    $siteLines.Add("$siteAddress {")
    if ($CertificateMode -eq 'LocalCA') {
        $siteLines.Add('    tls internal')
    }
    elseif ($CertificateMode -eq 'PublicACME') {
        # Pri prechodu ze starsi LocalCA instalace vynuti novou automatizaci
        # verejneho certifikatu i v pripade, ze je ve storage stary certifikat.
        $siteLines.Add('    tls force_automate')
    }
    $siteLines.Add('')
    $siteLines.Add('    encode zstd gzip')
    $siteLines.Add('')
    $siteLines.Add('    @zaverecnePrace path /zaverecne-prace /zaverecne-prace/*')
    $siteLines.Add('')
    $siteLines.Add('    handle @zaverecnePrace {')
    $siteLines.Add('        reverse_proxy 127.0.0.1:9871')
    $siteLines.Add('    }')
    $siteLines.Add('')
    $siteLines.Add('    handle {')
    $siteLines.Add("        reverse_proxy 127.0.0.1:$BackendPort {")
    $siteLines.Add('            flush_interval -1')
    $siteLines.Add('            transport http {')
    $siteLines.Add('                dial_timeout 10s')
    $siteLines.Add('                response_header_timeout 10m')
    $siteLines.Add('                keepalive 2m')
    $siteLines.Add('            }')
    $siteLines.Add('        }')
    $siteLines.Add('    }')
    $siteLines.Add('')
    $siteLines.Add('    header {')
    $siteLines.Add("        Strict-Transport-Security `"max-age=$hstsMaxAge`"")
    $siteLines.Add('        X-Content-Type-Options "nosniff"')
    $siteLines.Add('        X-Frame-Options "SAMEORIGIN"')
    $siteLines.Add('        Referrer-Policy "strict-origin-when-cross-origin"')
    $siteLines.Add('        -Server')
    $siteLines.Add('    }')
    $siteLines.Add('')
    $siteLines.Add('    log {')
    $siteLines.Add("        output file `"$accessLog`" {")
    $siteLines.Add('            roll_size 20MiB')
    $siteLines.Add('            roll_keep 10')
    $siteLines.Add('            roll_keep_for 720h')
    $siteLines.Add('        }')
    $siteLines.Add('        format json')
    $siteLines.Add('    }')
    $siteLines.Add('}')

    $content = (($globalLines.ToArray() + $siteLines.ToArray()) -join "`r`n") + "`r`n"
    Write-Utf8NoBom -Path $CaddyfilePath -Content $content
}

function Test-CaddyConfiguration {
    $oldData = $env:XDG_DATA_HOME
    $oldConfig = $env:XDG_CONFIG_HOME
    $env:XDG_DATA_HOME = $CaddyDataBase
    $env:XDG_CONFIG_HOME = $CaddyConfigBase
    try {
        $validationResult = Invoke-NativeCommandCapture `
            -Executable $CaddyExe `
            -Arguments @('validate', '--config', $CaddyfilePath, '--adapter', 'caddyfile')
        if ($validationResult.ExitCode -ne 0) {
            throw "Caddyfile neni platny (exit code $($validationResult.ExitCode)):`n$($validationResult.Output)"
        }
    }
    finally {
        $env:XDG_DATA_HOME = $oldData
        $env:XDG_CONFIG_HOME = $oldConfig
    }
    Write-Ok 'Caddyfile je syntakticky platny.'
}

function Test-ScheduledTaskBelongsToDeployment {
    param([AllowNull()]$Task)
    if ($null -eq $Task) { return $false }

    $root = $InstallRoot.ToLowerInvariant()
    $runner = $RuntimeScriptPath.ToLowerInvariant()
    foreach ($taskAction in @($Task.Actions)) {
        $description = (([string]$taskAction.Execute) + ' ' + ([string]$taskAction.Arguments) + ' ' + ([string]$taskAction.WorkingDirectory)).ToLowerInvariant()
        if ($description.Contains($runner) -or $description.Contains($root)) { return $true }
    }
    return $false
}

function Stop-ManagedScheduledTask {
    param([Parameter(Mandatory = $true)][string]$TaskName)
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $task) { return }
    if (-not (Test-ScheduledTaskBelongsToDeployment -Task $task)) {
        Write-Caution "Uloha '$TaskName' existuje, ale nepatri teto instalaci; nebude zastavena ani prepsana."
        return
    }
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

function Get-DeploymentTaskNames {
    $names = [Collections.Generic.List[string]]::new()
    foreach ($name in @($BackendTaskName, $ProxyTaskName)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$name) -and -not $names.Contains([string]$name)) {
            [void]$names.Add([string]$name)
        }
    }
    if ($null -ne $script:InstallerState) {
        foreach ($name in @($script:InstallerState.ManagedTaskNames)) {
            $normalized = ([string]$name).Trim()
            if (-not [string]::IsNullOrWhiteSpace($normalized) -and -not $names.Contains($normalized)) {
                [void]$names.Add($normalized)
            }
        }
    }
    return $names.ToArray()
}

function Register-DeploymentTasks {
    Write-Step 'Registruji automaticke spousteni pri startu Windows'

    $managedNames = @($BackendTaskName, $ProxyTaskName)
    foreach ($taskName in $managedNames) {
        $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -ne $existingTask -and -not (Test-ScheduledTaskBelongsToDeployment -Task $existingTask)) {
            throw "Naplanovana uloha '$taskName' jiz existuje a nepatri teto instalaci. Instalator ji z bezpecnostnich duvodu neprepise."
        }
    }

    if ($null -ne $script:InstallerState) {
        # Write-ahead evidence: pokud se proces prerusi po vytvoreni prvni ulohy,
        # --uninstall zna oba rezervovane nazvy a uklidi jen ulohy s nasi cestou.
        $script:InstallerState.ManagedTaskNames = @($managedNames)
        Write-InstallerState
    }

    $powershellExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $principal = New-ScheduledTaskPrincipal -UserId 'LOCALSERVICE' -LogonType ServiceAccount
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew

    $backendArguments = "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$RuntimeScriptPath`" -Component Backend"
    $backendAction = New-ScheduledTaskAction -Execute $powershellExe -Argument $backendArguments -WorkingDirectory $InstallRoot
    $backendTask = New-ScheduledTask -Action $backendAction -Trigger $trigger -Principal $principal -Settings $settings -Description 'Open WebUI backend na loopback rozhrani.'
    Register-ScheduledTask -TaskName $BackendTaskName -InputObject $backendTask -Force | Out-Null

    $proxyArguments = "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$RuntimeScriptPath`" -Component Caddy"
    $proxyAction = New-ScheduledTaskAction -Execute $powershellExe -Argument $proxyArguments -WorkingDirectory $InstallRoot
    $proxyTask = New-ScheduledTask -Action $proxyAction -Trigger $trigger -Principal $principal -Settings $settings -Description 'Caddy HTTPS reverse proxy a sprava certifikatu.'
    Register-ScheduledTask -TaskName $ProxyTaskName -InputObject $proxyTask -Force | Out-Null

    foreach ($taskName in $managedNames) {
        $registered = Get-ScheduledTask -TaskName $taskName -ErrorAction Stop
        if (-not (Test-ScheduledTaskBelongsToDeployment -Task $registered)) {
            throw "Naplanovana uloha '$taskName' po registraci nema ocekavanou cestu k teto instalaci."
        }
    }
    Write-Ok 'Naplanovane ulohy byly zaregistrovany pod omezenym uctem LOCAL SERVICE.'
}

function Remove-DeploymentTasks {
    $failures = [Collections.Generic.List[string]]::new()

    foreach ($taskName in @(Get-DeploymentTaskNames)) {
        try {
            $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if ($null -eq $task) { continue }
            if (-not (Test-ScheduledTaskBelongsToDeployment -Task $task)) {
                Write-Caution "Uloha '$taskName' existuje, ale nepatri teto instalaci; zustala beze zmeny."
                continue
            }

            Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
            Write-Ok "Naplanovana uloha '$taskName' byla odebrana."
        }
        catch {
            [void]$failures.Add("$taskName`: $($_.Exception.Message)")
        }
    }

    foreach ($taskName in @(Get-DeploymentTaskNames)) {
        try {
            $remainingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if ($null -ne $remainingTask -and (Test-ScheduledTaskBelongsToDeployment -Task $remainingTask)) {
                [void]$failures.Add("$taskName`: spravovana uloha po odebrani stale existuje")
            }
        }
        catch {
            [void]$failures.Add("$taskName`: overeni odebrani selhalo: $($_.Exception.Message)")
        }
    }

    if ($failures.Count -gt 0) {
        throw "Nektere spravovane naplanovane ulohy nelze odebrat:`n - $($failures.ToArray() -join "`n - ")"
    }
}

function Get-ManagedProcesses {
    try {
        $caddyLower = $CaddyExe.ToLowerInvariant()
        $venvLower = $VenvDir.ToLowerInvariant()
        $runnerLower = $RuntimeScriptPath.ToLowerInvariant()
        return @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop | Where-Object {
            if ($_.ProcessId -eq $PID) { return $false }
            $commandLine = ([string]$_.CommandLine).ToLowerInvariant()
            $executablePath = ([string]$_.ExecutablePath).ToLowerInvariant()
            ($executablePath -eq $caddyLower) -or
            ($executablePath.StartsWith($venvLower + '\')) -or
            ($commandLine.Contains($runnerLower))
        })
    }
    catch {
        throw "Kontrola spravovanych procesu selhala: $($_.Exception.Message)"
    }
}

function Stop-ManagedProcesses {
    param([switch]$RequireStopped)

    try {
        $processes = @(Get-ManagedProcesses)
    }
    catch {
        if ($RequireStopped) { throw }
        Write-Caution $_.Exception.Message
        return
    }

    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }

    if (-not $RequireStopped) { return }

    $deadline = [DateTime]::UtcNow.AddSeconds(12)
    $remaining = @()
    do {
        Start-Sleep -Milliseconds 500
        $remaining = @(Get-ManagedProcesses)
    } while ($remaining.Count -gt 0 -and [DateTime]::UtcNow -lt $deadline)

    if ($remaining.Count -gt 0) {
        $descriptions = @($remaining | ForEach-Object { "PID $($_.ProcessId) ($($_.Name))" })
        throw "Spravovane procesy se nepodarilo ukoncit: $($descriptions -join ', ')."
    }
}

function Stop-Deployment {
    param([switch]$RequireStopped)

    foreach ($taskName in @($ProxyTaskName, $BackendTaskName)) {
        Stop-ManagedScheduledTask -TaskName $taskName
    }
    Start-Sleep -Seconds 2
    Stop-ManagedProcesses -RequireStopped:$RequireStopped

    if ($RequireStopped) {
        foreach ($taskName in @($ProxyTaskName, $BackendTaskName)) {
            $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            if ($null -ne $task -and (Test-ScheduledTaskBelongsToDeployment -Task $task) -and $task.State -eq 'Running') {
                throw "Spravovana uloha '$taskName' zustala ve stavu Running."
            }
        }
    }
    Start-Sleep -Seconds 1
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port,
        [ValidateRange(100, 10000)][int]$TimeoutMilliseconds = 1000
    )

    $client = New-Object Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-TcpPort {
    param(
        [Parameter(Mandatory = $true)][string]$HostName,
        [Parameter(Mandatory = $true)][int]$Port,
        [ValidateRange(1, 600)][int]$TimeoutSeconds = 180,
        [Parameter(Mandatory = $true)][string]$ComponentName
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-TcpPort -HostName $HostName -Port $Port -TimeoutMilliseconds 750) {
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "$ComponentName nenasloucha na $HostName`:$Port. Zkontrolujte logy v $LogDir."
}

function Get-PortOwnerDescription {
    param([int]$Port)
    try {
        $connections = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop)
        if ($connections.Count -eq 0) { return $null }
        $descriptions = foreach ($connection in $connections) {
            $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
            if ($null -ne $process) {
                "PID $($connection.OwningProcess) ($($process.ProcessName))"
            }
            else {
                "PID $($connection.OwningProcess)"
            }
        }
        return ($descriptions | Select-Object -Unique) -join ', '
    }
    catch {
        return $null
    }
}

function Assert-PortsAvailable {
    foreach ($port in @($BackendPort, $HttpPort, $HttpsPort)) {
        $owner = Get-PortOwnerDescription -Port $port
        if (-not [string]::IsNullOrWhiteSpace($owner)) {
            throw "Port $port je jiz obsazen: $owner"
        }
    }
}

function Get-FirewallDefinitions {
    $id = if ($null -ne $script:InstallerState) {
        $compact = ([string]$script:InstallerState.InstallationId).Replace('-', '')
        if ($compact.Length -gt 12) { $compact.Substring(0, 12) } else { $compact }
    }
    else { 'standalone' }

    return @(
        [pscustomobject]@{ Name="EInfraOpenWebUI-$id-HttpsTcp"; Display="$FirewallRulePrefix HTTPS TCP"; Protocol='TCP'; Port=$HttpsPort },
        [pscustomobject]@{ Name="EInfraOpenWebUI-$id-HttpTcp"; Display="$FirewallRulePrefix HTTP redirect TCP"; Protocol='TCP'; Port=$HttpPort },
        [pscustomobject]@{ Name="EInfraOpenWebUI-$id-HttpsUdp"; Display="$FirewallRulePrefix HTTP3 UDP"; Protocol='UDP'; Port=$HttpsPort }
    )
}

function Test-FirewallRulePortAndDirection {
    param(
        [Parameter(Mandatory = $true)]$Rule,
        [Parameter(Mandatory = $true)][string]$ExpectedProtocol,
        [Parameter(Mandatory = $true)][int]$ExpectedPort
    )

    try {
        if ([string]$Rule.Direction -ne 'Inbound' -or [string]$Rule.Action -ne 'Allow') {
            return $false
        }
        $expectedProtocolAliases = if ($ExpectedProtocol.ToUpperInvariant() -eq 'TCP') { @('TCP', '6') } else { @('UDP', '17') }
        foreach ($portFilter in @($Rule | Get-NetFirewallPortFilter -ErrorAction Stop)) {
            $protocolText = ([string]$portFilter.Protocol).Trim().ToUpperInvariant()
            $portValues = [Collections.Generic.List[string]]::new()
            foreach ($rawPortValue in @($portFilter.LocalPort)) {
                foreach ($part in ([string]$rawPortValue -split ',')) {
                    $trimmedPart = $part.Trim()
                    if (-not [string]::IsNullOrWhiteSpace($trimmedPart)) { [void]$portValues.Add($trimmedPart) }
                }
            }
            if ($expectedProtocolAliases -contains $protocolText -and $portValues.Contains([string]$ExpectedPort)) {
                return $true
            }
        }
        return $false
    }
    catch {
        return $false
    }
}

function Test-FirewallRuleBelongsToDeployment {
    param(
        [Parameter(Mandatory = $true)]$Rule,
        [AllowEmptyString()][string]$ExpectedProtocol = '',
        [int]$ExpectedPort = 0
    )

    try {
        if (-not [string]::IsNullOrWhiteSpace($ExpectedProtocol) -and $ExpectedPort -gt 0 -and
            -not (Test-FirewallRulePortAndDirection -Rule $Rule -ExpectedProtocol $ExpectedProtocol -ExpectedPort $ExpectedPort)) {
            return $false
        }
        if ([string]::IsNullOrWhiteSpace($ExpectedProtocol) -and
            ([string]$Rule.Direction -ne 'Inbound' -or [string]$Rule.Action -ne 'Allow')) {
            return $false
        }

        $expectedProgram = [IO.Path]::GetFullPath($CaddyExe).TrimEnd('\').ToLowerInvariant()
        foreach ($applicationFilter in @($Rule | Get-NetFirewallApplicationFilter -ErrorAction Stop)) {
            $programText = [Environment]::ExpandEnvironmentVariables(([string]$applicationFilter.Program).Trim())
            if ([string]::IsNullOrWhiteSpace($programText) -or $programText -eq 'Any') { continue }
            try { $actualProgram = [IO.Path]::GetFullPath($programText).TrimEnd('\').ToLowerInvariant() }
            catch { continue }
            if ($actualProgram -eq $expectedProgram) { return $true }
        }
        return $false
    }
    catch {
        return $false
    }
}

function Test-LegacyFirewallRuleBelongsToDeployment {
    param(
        [Parameter(Mandatory = $true)]$Rule,
        [Parameter(Mandatory = $true)][string]$ExpectedDisplayName,
        [Parameter(Mandatory = $true)][string]$ExpectedProtocol,
        [Parameter(Mandatory = $true)][int]$ExpectedPort
    )

    if ([string]$Rule.DisplayName -ne $ExpectedDisplayName) { return $false }
    return Test-FirewallRulePortAndDirection -Rule $Rule -ExpectedProtocol $ExpectedProtocol -ExpectedPort $ExpectedPort
}

function Remove-FirewallRuleByIdentity {
    param([Parameter(Mandatory = $true)]$Rule)
    $name = [string]$Rule.Name
    Remove-NetFirewallRule -Name $name -ErrorAction Stop
    if ($null -ne (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue)) {
        throw "Firewall pravidlo '$name' zustalo po pokusu o odebrani aktivni."
    }
}

function Remove-FirewallRuleSafely {
    param(
        [Parameter(Mandatory = $true)]$Rule,
        [AllowEmptyString()][string]$ExpectedProtocol = '',
        [int]$ExpectedPort = 0
    )

    if (-not (Test-FirewallRuleBelongsToDeployment -Rule $Rule -ExpectedProtocol $ExpectedProtocol -ExpectedPort $ExpectedPort)) {
        throw "Firewall pravidlo '$($Rule.DisplayName)' ($($Rule.Name)) nema ocekavany program/protokol/port a nebude z bezpecnostnich duvodu odebrano."
    }
    Remove-FirewallRuleByIdentity -Rule $Rule
}

function Remove-LegacyFirewallRuleSafely {
    param(
        [Parameter(Mandatory = $true)]$Rule,
        [Parameter(Mandatory = $true)][string]$ExpectedDisplayName,
        [Parameter(Mandatory = $true)][string]$ExpectedProtocol,
        [Parameter(Mandatory = $true)][int]$ExpectedPort
    )

    if (-not (Test-LegacyFirewallRuleBelongsToDeployment -Rule $Rule -ExpectedDisplayName $ExpectedDisplayName -ExpectedProtocol $ExpectedProtocol -ExpectedPort $ExpectedPort)) {
        throw "Starsi firewall pravidlo '$($Rule.DisplayName)' ($($Rule.Name)) nema ocekavany smer/protokol/port a nebude odebrano."
    }
    Remove-FirewallRuleByIdentity -Rule $Rule
}

function Configure-Firewall {
    Write-Step 'Nastavuji Windows Defender Firewall'

    if ($SkipFirewallChange) {
        Write-Notice 'Zmena Windows Firewall byla vynechana volbou --skip-firewall-change.'
        return
    }

    foreach ($ruleName in $(if ($null -ne $script:InstallerState) { @($script:InstallerState.FirewallRuleNames) } else { @() })) {
        if ([string]::IsNullOrWhiteSpace([string]$ruleName)) { continue }
        $existingRule = Get-NetFirewallRule -Name ([string]$ruleName) -ErrorAction SilentlyContinue
        if ($null -ne $existingRule) {
            Remove-FirewallRuleSafely -Rule $existingRule
        }
    }

    if ($null -ne $script:InstallerState -and [bool]$script:InstallerState.AdoptedLegacyInstallation) {
        $legacyDefinitions = @(
            [pscustomobject]@{ Display="$FirewallRulePrefix HTTPS TCP"; Protocol='TCP'; Port=$HttpsPort },
            [pscustomobject]@{ Display="$FirewallRulePrefix HTTP redirect TCP"; Protocol='TCP'; Port=$HttpPort },
            [pscustomobject]@{ Display="$FirewallRulePrefix HTTP3 UDP"; Protocol='UDP'; Port=$HttpsPort }
        )
        foreach ($definition in $legacyDefinitions) {
            foreach ($legacyRule in @(Get-NetFirewallRule -DisplayName $definition.Display -ErrorAction SilentlyContinue)) {
                if (Test-FirewallRuleBelongsToDeployment -Rule $legacyRule -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port) {
                    Remove-FirewallRuleSafely -Rule $legacyRule -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port
                }
                elseif (Test-FirewallRuleBelongsToDeployment -Rule $legacyRule) {
                    # Pri poskozenem runtime.json nemusi byt znamy puvodni vlastni port;
                    # cesta programu stale jednoznacne svazuje pravidlo s caddy.exe teto instalace.
                    Remove-FirewallRuleSafely -Rule $legacyRule
                }
                elseif (Test-LegacyFirewallRuleBelongsToDeployment -Rule $legacyRule -ExpectedDisplayName $definition.Display -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port) {
                    Remove-LegacyFirewallRuleSafely -Rule $legacyRule -ExpectedDisplayName $definition.Display -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port
                }
                else {
                    Write-Caution "Stejne pojmenovane firewall pravidlo '$($legacyRule.Name)' nema konfiguraci starsi ani aktualni instalace a zustalo beze zmeny."
                }
            }
        }
    }

    $rules = @(Get-FirewallDefinitions)
    if ($null -ne $script:InstallerState) {
        # Zamyslene nazvy se ulozi pred prvni zmenou, aby --uninstall znal i
        # pravidlo vytvorene tesne pred prerusenim procesu.
        $script:InstallerState.FirewallRuleNames = @($rules | ForEach-Object { $_.Name })
        Write-InstallerState
    }

    try {
        foreach ($definition in $rules) {
            $sameNameRule = Get-NetFirewallRule -Name $definition.Name -ErrorAction SilentlyContinue
            if ($null -ne $sameNameRule) {
                Remove-FirewallRuleSafely -Rule $sameNameRule
            }
            New-NetFirewallRule `
                -Name $definition.Name `
                -DisplayName $definition.Display `
                -Direction Inbound `
                -Action Allow `
                -Protocol $definition.Protocol `
                -LocalPort $definition.Port `
                -Program $CaddyExe `
                -Profile Any | Out-Null

            $createdRule = Get-NetFirewallRule -Name $definition.Name -ErrorAction Stop
            if (-not (Test-FirewallRuleBelongsToDeployment -Rule $createdRule -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port)) {
                throw "Vytvorene firewall pravidlo '$($definition.Name)' nema ocekavanou konfiguraci."
            }
        }
        Write-Ok "Firewall povoluje pouze caddy.exe na TCP $HttpPort/$HttpsPort a UDP $HttpsPort na vsech sitovych profilech."
    }
    catch {
        throw "Nastaveni firewallu selhalo: $($_.Exception.Message)"
    }
}

function Remove-FirewallRules {
    $failures = [Collections.Generic.List[string]]::new()
    $removedNames = [Collections.Generic.List[string]]::new()
    $definitions = @(Get-FirewallDefinitions)
    $definitionByName = @{}
    foreach ($definition in $definitions) { $definitionByName[[string]$definition.Name] = $definition }

    if ($null -ne $script:InstallerState) {
        foreach ($nameValue in @($script:InstallerState.FirewallRuleNames)) {
            $name = ([string]$nameValue).Trim()
            if ([string]::IsNullOrWhiteSpace($name)) { continue }
            $rule = Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
            if ($null -eq $rule) { continue }
            try {
                if ($definitionByName.ContainsKey($name)) {
                    $definition = $definitionByName[$name]
                    if (Test-FirewallRuleBelongsToDeployment -Rule $rule -ExpectedProtocol ([string]$definition.Protocol) -ExpectedPort ([int]$definition.Port)) {
                        Remove-FirewallRuleSafely -Rule $rule -ExpectedProtocol ([string]$definition.Protocol) -ExpectedPort ([int]$definition.Port)
                    }
                    elseif (Test-FirewallRuleBelongsToDeployment -Rule $rule) {
                        # Pravidlo ma nasi cestu k caddy.exe, ale konfigurace mohla
                        # byt rucne zmenena. Vlastnictvi je stale jednoznacne.
                        Remove-FirewallRuleSafely -Rule $rule
                    }
                    else {
                        Write-Caution "Firewall pravidlo '$name' ma rezervovany nazev, ale nepatri teto instalaci; zustalo beze zmeny."
                        continue
                    }
                }
                elseif (Test-FirewallRuleBelongsToDeployment -Rule $rule) {
                    Remove-FirewallRuleSafely -Rule $rule
                }
                else {
                    Write-Caution "Firewall pravidlo '$name' nema cestu k tomuto caddy.exe; zustalo beze zmeny."
                    continue
                }
                if (-not $removedNames.Contains($name)) { [void]$removedNames.Add($name) }
            }
            catch {
                [void]$failures.Add("$name`: $($_.Exception.Message)")
            }
        }
    }

    $legacyEvidence = (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf) -or `
                      (Test-Path -LiteralPath $CaddyExe -PathType Leaf) -or `
                      (Test-Path -LiteralPath $OpenWebUIExe -PathType Leaf)
    $removeLegacy = (($null -eq $script:InstallerState) -and $legacyEvidence) -or `
                    ($null -ne $script:InstallerState -and [bool]$script:InstallerState.AdoptedLegacyInstallation)
    if ($removeLegacy) {
        $legacyDefinitions = @(
            [pscustomobject]@{ Display="$FirewallRulePrefix HTTPS TCP"; Protocol='TCP'; Port=$HttpsPort },
            [pscustomobject]@{ Display="$FirewallRulePrefix HTTP redirect TCP"; Protocol='TCP'; Port=$HttpPort },
            [pscustomobject]@{ Display="$FirewallRulePrefix HTTP3 UDP"; Protocol='UDP'; Port=$HttpsPort }
        )
        foreach ($definition in $legacyDefinitions) {
            foreach ($legacyRule in @(Get-NetFirewallRule -DisplayName $definition.Display -ErrorAction SilentlyContinue)) {
                $legacyName = [string]$legacyRule.Name
                if ($removedNames.Contains($legacyName)) { continue }
                try {
                    if (Test-FirewallRuleBelongsToDeployment -Rule $legacyRule -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port) {
                        Remove-FirewallRuleSafely -Rule $legacyRule -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port
                        [void]$removedNames.Add($legacyName)
                    }
                    elseif (Test-FirewallRuleBelongsToDeployment -Rule $legacyRule) {
                        Remove-FirewallRuleSafely -Rule $legacyRule
                        [void]$removedNames.Add($legacyName)
                    }
                    elseif (Test-LegacyFirewallRuleBelongsToDeployment -Rule $legacyRule -ExpectedDisplayName $definition.Display -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port) {
                        Remove-LegacyFirewallRuleSafely -Rule $legacyRule -ExpectedDisplayName $definition.Display -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port
                        [void]$removedNames.Add($legacyName)
                    }
                    else {
                        Write-Caution "Firewall pravidlo '$legacyName' se stejnym zobrazovanym nazvem nema ocekavanou konfiguraci a zustalo beze zmeny."
                    }
                }
                catch {
                    [void]$failures.Add("$legacyName`: $($_.Exception.Message)")
                }
            }
        }
    }

    foreach ($name in $removedNames.ToArray()) {
        if ($null -ne (Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue)) {
            [void]$failures.Add("$name`: pravidlo po odebrani stale existuje")
        }
    }
    if ($failures.Count -gt 0) {
        throw "Nektera firewall pravidla vytvorena instalatorem nelze odebrat:`n - $($failures.ToArray() -join "`n - ")"
    }
    Write-Ok 'Firewall pravidla vytvorena aktualni nebo prevzatou instalaci byla odebrana.'
}

function Start-TaskIfNeeded {
    param([Parameter(Mandatory = $true)][string]$TaskName)
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    if ($task.State -ne 'Running') {
        Start-ScheduledTask -TaskName $TaskName
    }
}

function Start-Deployment {
    Write-Step 'Spoustim Open WebUI a HTTPS proxy'

    Start-TaskIfNeeded -TaskName $BackendTaskName
    Wait-TcpPort -HostName '127.0.0.1' -Port $BackendPort -ComponentName 'Open WebUI backend'
    Write-Ok "Open WebUI nasloucha pouze lokalne na 127.0.0.1:$BackendPort."

    Start-TaskIfNeeded -TaskName $ProxyTaskName
    Wait-TcpPort -HostName '127.0.0.1' -Port $HttpsPort -ComponentName 'Caddy HTTPS proxy'
    Write-Ok "Caddy nasloucha na HTTPS portu $HttpsPort."
}

function Backup-Database {
    $databasePath = Join-Path $DataDir 'webui.db'
    if (-not (Test-Path -LiteralPath $databasePath)) {
        return
    }

    Ensure-Directory $BackupDir
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $target = Join-Path $BackupDir "webui-$timestamp.db"
    $backupCreated = $false

    # Python sqlite3 backup zahrne i potvrzene transakce z pripadneho WAL a
    # vytvori samostatny konzistentni .db soubor.
    if (Test-Path -LiteralPath $PythonExe) {
        $backupCode = 'import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()'
        try {
            $backupResult = Invoke-NativeCommandCapture `
                -Executable $PythonExe `
                -Arguments @('-c', $backupCode, $databasePath, $target)
            if ($backupResult.ExitCode -eq 0 -and
                (Test-Path -LiteralPath $target) -and
                (Get-Item -LiteralPath $target).Length -gt 0) {
                $backupCreated = $true
            }
            elseif ($backupResult.ExitCode -ne 0) {
                Write-Caution "SQLite online backup skoncil kodem $($backupResult.ExitCode); pouziji souborovou zalohu. $($backupResult.Output)"
            }
        }
        catch {
            Write-Caution "SQLite online backup selhal, pouziji souborovou zalohu: $($_.Exception.Message)"
        }
    }

    if (-not $backupCreated) {
        Copy-Item -LiteralPath $databasePath -Destination $target -Force
        foreach ($suffix in @('-wal', '-shm')) {
            $sourceSidecar = "$databasePath$suffix"
            if (Test-Path -LiteralPath $sourceSidecar) {
                Copy-Item -LiteralPath $sourceSidecar -Destination "$target$suffix" -Force
            }
        }
        Write-Caution 'Zaloha byla vytvorena souborovym kopirovanim; pri rucni obnove zachovejte i pripadne soubory -wal a -shm.'
    }

    $oldBackups = @(Get-ChildItem -Path $BackupDir -Filter 'webui-*.db' -File | Sort-Object LastWriteTime -Descending | Select-Object -Skip 10)
    foreach ($oldBackup in $oldBackups) {
        Remove-Item -LiteralPath $oldBackup.FullName -Force -ErrorAction SilentlyContinue
        foreach ($suffix in @('-wal', '-shm')) {
            Remove-Item -LiteralPath "$($oldBackup.FullName)$suffix" -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Ok "Zaloha databaze: $target"
}

function Get-LocalCaRootPath {
    $expected = Join-Path $CaddyDataBase 'caddy\pki\authorities\local\root.crt'
    if (Test-Path -LiteralPath $expected) {
        return $expected
    }

    $candidate = Get-ChildItem -Path $CaddyDataBase -Filter 'root.crt' -File -Recurse -ErrorAction SilentlyContinue | Where-Object {
        $_.FullName -match '[\\/]pki[\\/]authorities[\\/]local[\\/]root\.crt$'
    } | Select-Object -First 1
    if ($null -ne $candidate) {
        return $candidate.FullName
    }
    return $null
}

function Invoke-InsecureTlsHandshake {
    param(
        [Parameter(Mandatory = $true)][string]$ConnectAddress,
        [Parameter(Mandatory = $true)][string]$ServerName,
        [Parameter(Mandatory = $true)][int]$Port
    )
    try {
        [void](Test-TlsSniHandshake -ConnectAddress $ConnectAddress -ServerName $ServerName -Port $Port -TimeoutMilliseconds 5000)
    }
    catch {
        # Pouze pokus o vyvolani vystaveni certifikatu; nasledna kontrola poskytne detail.
    }
}

function Test-TlsSniHandshake {
    param(
        [Parameter(Mandatory = $true)][string]$ConnectAddress,
        [Parameter(Mandatory = $true)][string]$ServerName,
        [Parameter(Mandatory = $true)][int]$Port,
        [ValidateRange(1000, 60000)][int]$TimeoutMilliseconds = 10000,
        [switch]$RequireTrusted
    )

    $client = New-Object Net.Sockets.TcpClient
    $stream = $null
    try {
        $connect = $client.BeginConnect($ConnectAddress, $Port, $null, $null)
        if (-not $connect.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            throw "TCP timeout na $ConnectAddress`:$Port"
        }
        $client.EndConnect($connect)
        $client.ReceiveTimeout = $TimeoutMilliseconds
        $client.SendTimeout = $TimeoutMilliseconds

        $networkStream = $client.GetStream()
        if ($RequireTrusted) {
            # Bez vlastniho callbacku .NET overi retezec i shodu ServerName/SNI.
            $stream = New-Object Net.Security.SslStream($networkStream, $false)
        }
        else {
            # Pouziva se pouze pri prvotnim vyvolani certifikatu a diagnostice SNI.
            $callback = [Net.Security.RemoteCertificateValidationCallback]{
                param($sender, $certificate, $chain, $sslPolicyErrors)
                return $true
            }
            $stream = New-Object Net.Security.SslStream($networkStream, $false, $callback)
        }
        $stream.ReadTimeout = $TimeoutMilliseconds
        $stream.WriteTimeout = $TimeoutMilliseconds
        $stream.AuthenticateAsClient($ServerName)

        if (-not $stream.IsAuthenticated -or -not $stream.IsEncrypted) {
            throw 'TLS spojeni neni autentizovane a sifrovane.'
        }
        $certificateSubject = ''
        $certificateIssuer = ''
        $certificateThumbprint = ''
        $certificateNotAfterUtc = ''
        $chainRootSubject = ''
        $chainRootThumbprint = ''
        $remoteCertificate = $null
        $chain = $null
        try {
            if ($null -ne $stream.RemoteCertificate) {
                $remoteCertificate = [Security.Cryptography.X509Certificates.X509Certificate2]::new($stream.RemoteCertificate)
                $certificateSubject = [string]$remoteCertificate.Subject
                $certificateIssuer = [string]$remoteCertificate.Issuer
                $certificateThumbprint = Normalize-CertificateThumbprint -Thumbprint ([string]$remoteCertificate.Thumbprint)
                $certificateNotAfterUtc = $remoteCertificate.NotAfter.ToUniversalTime().ToString('o')

                $chain = New-Object Security.Cryptography.X509Certificates.X509Chain
                $chain.ChainPolicy.RevocationMode = [Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck
                [void]$chain.Build($remoteCertificate)
                if ($chain.ChainElements.Count -gt 0) {
                    $rootElement = $chain.ChainElements[$chain.ChainElements.Count - 1].Certificate
                    $chainRootSubject = [string]$rootElement.Subject
                    $chainRootThumbprint = Normalize-CertificateThumbprint -Thumbprint ([string]$rootElement.Thumbprint)
                }
            }
        }
        finally {
            if ($null -ne $chain) { $chain.Dispose() }
            if ($null -ne $remoteCertificate) { $remoteCertificate.Dispose() }
        }

        return [pscustomobject]@{
            ConnectAddress = $ConnectAddress
            ServerName = $ServerName
            Protocol = [string]$stream.SslProtocol
            Cipher = [string]$stream.CipherAlgorithm
            CipherStrength = [int]$stream.CipherStrength
            Trusted = [bool]$RequireTrusted
            CertificateSubject = $certificateSubject
            CertificateIssuer = $certificateIssuer
            CertificateThumbprint = $certificateThumbprint
            CertificateNotAfterUtc = $certificateNotAfterUtc
            ChainRootSubject = $chainRootSubject
            ChainRootThumbprint = $chainRootThumbprint
        }
    }
    finally {
        if ($null -ne $stream) { $stream.Dispose() }
        $client.Dispose()
    }
}

function Assert-PublicCertificateHandshake {
    param(
        [Parameter(Mandatory = $true)]$Handshake,
        [Parameter(Mandatory = $true)][string]$ServerName
    )

    $localRootThumbprint = ''
    $localRootPath = Get-LocalCaRootPath
    if (-not [string]::IsNullOrWhiteSpace([string]$localRootPath) -and
        (Test-Path -LiteralPath $localRootPath -PathType Leaf)) {
        $localRootCertificate = $null
        try {
            $localRootCertificate = [Security.Cryptography.X509Certificates.X509Certificate2]::new($localRootPath)
            $localRootThumbprint = Normalize-CertificateThumbprint -Thumbprint ([string]$localRootCertificate.Thumbprint)
        }
        finally {
            if ($null -ne $localRootCertificate) { $localRootCertificate.Dispose() }
        }
    }

    $rootThumbprint = Normalize-CertificateThumbprint -Thumbprint ([string]$Handshake.ChainRootThumbprint)
    $issuerText = [string]$Handshake.CertificateIssuer
    $rootSubjectText = [string]$Handshake.ChainRootSubject

    if ((-not [string]::IsNullOrWhiteSpace($localRootThumbprint) -and $rootThumbprint -eq $localRootThumbprint) -or
        $issuerText -match '(?i)Caddy Local Authority' -or
        $rootSubjectText -match '(?i)Caddy Local Authority') {
        throw "Caddy pro '$ServerName' stale predklada certifikat vydany soukromou Caddy LocalCA. Verejny ACME certifikat zatim nebyl vystaven."
    }
    if ([string]::IsNullOrWhiteSpace([string]$Handshake.CertificateSubject) -or
        [string]::IsNullOrWhiteSpace([string]$Handshake.CertificateIssuer)) {
        throw "TLS handshake pro '$ServerName' neposkytl dostatek udaju o certifikatu."
    }

    $notAfter = [DateTime]::MinValue
    if (-not [DateTime]::TryParse([string]$Handshake.CertificateNotAfterUtc, [ref]$notAfter) -or
        $notAfter.ToUniversalTime() -le [DateTime]::UtcNow) {
        throw "Certifikat pro '$ServerName' je po platnosti nebo nelze overit jeho dobu platnosti."
    }
}

function Assert-CaddyOwnsExternalListener {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$CaddyExecutable
    )

    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop)
    if ($listeners.Count -eq 0) { throw "Na TCP portu $Port neni zadny listener." }

    $expectedPath = [IO.Path]::GetFullPath($CaddyExecutable).ToLowerInvariant()
    $nonLoopback = $false
    foreach ($listener in $listeners) {
        $process = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        $actualPath = if ($null -ne $process) { [string]$process.ExecutablePath } else { '' }
        if ([string]::IsNullOrWhiteSpace($actualPath) -or [IO.Path]::GetFullPath($actualPath).ToLowerInvariant() -ne $expectedPath) {
            throw "Port $Port obsluhuje neocekavany proces PID $($listener.OwningProcess) ($actualPath), nikoli $CaddyExecutable."
        }
        if ($listener.LocalAddress -in @('0.0.0.0', '::') -or $listener.LocalAddress -notin @('127.0.0.1', '::1')) {
            $nonLoopback = $true
        }
        Write-Notice ('Listener TCP {0}: {1}, PID {2}.' -f $Port, $listener.LocalAddress, $listener.OwningProcess)
    }
    if (-not $nonLoopback) { throw "Caddy na portu $Port nasloucha pouze na loopback rozhrani." }
    Write-Ok "Caddy vlastni TCP port $Port a nasloucha i mimo loopback."
}

function Resolve-AndReportDns {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$LocalAddresses
    )

    $parsedAddress = $null
    if ($Name -eq 'localhost' -or [Net.IPAddress]::TryParse($Name, [ref]$parsedAddress)) { return }
    try {
        $resolved = @([Net.Dns]::GetHostAddresses($Name) | ForEach-Object { $_.ToString() } | Select-Object -Unique)
        Write-Notice "DNS $Name -> $($resolved -join ', ')"
        if ($LocalAddresses.Count -gt 0 -and @($resolved | Where-Object { $LocalAddresses -contains $_ }).Count -eq 0) {
            Write-Caution "DNS $Name nesmeruje na zadnou zjistenou lokalni IPv4 adresu ($($LocalAddresses -join ', ')). Je-li pred serverem NAT nebo load balancer, muze to byt v poradku; jinak opravte DNS."
        }
    }
    catch {
        Write-Caution "DNS $Name nelze prelozit: $($_.Exception.Message)"
    }
}

function Test-DeploymentNetwork {
    param(
        [Parameter(Mandatory = $true)][string]$PrimaryServerName,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$LocalAddresses
    )

    Write-Step 'Overuji listener, TLS SNI a sitova rozhrani'
    Assert-CaddyOwnsExternalListener -Port $HttpsPort -CaddyExecutable $CaddyExe

    $tlsHandshakeTimeoutSeconds = if ($CertificateMode -eq 'PublicACME') { 300 } else { 90 }
    $deadline = [DateTime]::UtcNow.AddSeconds($tlsHandshakeTimeoutSeconds)
    $loopbackTls = $null
    $lastTlsError = ''
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $loopbackTls = Test-TlsSniHandshake -ConnectAddress '127.0.0.1' -ServerName $PrimaryServerName -Port $HttpsPort
            break
        }
        catch {
            $lastTlsError = $_.Exception.Message
            Start-Sleep -Seconds 3
        }
    }
    if ($null -eq $loopbackTls) {
        throw "Caddy nedokazal provest TLS handshake pro SNI '$PrimaryServerName' ani po $tlsHandshakeTimeoutSeconds sekundach. Detail: $lastTlsError"
    }
    Write-Ok "TLS SNI $PrimaryServerName funguje pres 127.0.0.1 ($($loopbackTls.Protocol), $($loopbackTls.Cipher) $($loopbackTls.CipherStrength)-bit)."

    $addresses = @($LocalAddresses | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) } | Select-Object -Unique)
    $successfulInterfaces = [Collections.Generic.List[string]]::new()
    $failedInterfaces = [Collections.Generic.List[string]]::new()
    foreach ($localAddress in $addresses) {
        try {
            $result = Test-TlsSniHandshake -ConnectAddress $localAddress -ServerName $PrimaryServerName -Port $HttpsPort
            $successfulInterfaces.Add([string]$localAddress)
            Write-Ok "TLS SNI $PrimaryServerName funguje i pres rozhrani $localAddress ($($result.Protocol))."
        }
        catch {
            $failedInterfaces.Add("$localAddress`: $($_.Exception.Message)")
            Write-Caution "TLS test pres lokalni rozhrani $localAddress selhal: $($_.Exception.Message)"
        }
    }

    if ($addresses.Count -eq 0) {
        Write-Caution 'Nebyla zjistena zadna aktivni ne-loopback IPv4 adresa; vzdaleny pristup nelze lokalne overit.'
    }
    elseif ($successfulInterfaces.Count -eq 0) {
        throw "TLS nefunguje pres zadne zjistene vnejsi sitove rozhrani. Detaily: $($failedInterfaces -join '; ')"
    }
    elseif ($failedInterfaces.Count -gt 0) {
        Write-Notice "Alespon jedno vnejsi rozhrani proslo; nektera virtualni nebo oddelena rozhrani nejsou z tohoto stroje dosazitelna."
    }

    Resolve-AndReportDns -Name $PrimaryServerName -LocalAddresses $addresses
}

function Write-ClientCaInstaller {
    param(
        [Parameter(Mandatory = $true)][string]$CertificatePath,
        [Parameter(Mandatory = $true)][string]$Thumbprint,
        [Parameter(Mandatory = $true)][string]$Sha256Fingerprint,
        [Parameter(Mandatory = $true)][string[]]$Urls
    )

    Ensure-Directory $ClientCaDir
    $exportedCertificate = Join-Path $ClientCaDir 'e-INFRA-OpenWebUI-Root-CA.crt'
    Copy-Item -LiteralPath $CertificatePath -Destination $exportedCertificate -Force

    $template = @'
#requires -Version 5.1
#requires -RunAsAdministrator

$ErrorActionPreference = 'Stop'
$certificatePath = Join-Path $PSScriptRoot 'e-INFRA-OpenWebUI-Root-CA.crt'
$expectedWindowsThumbprint = '__THUMBPRINT__'
$expectedSha256Fingerprint = '__SHA256__'

if (-not (Test-Path -LiteralPath $certificatePath)) {
    throw "Chybi certifikat: $certificatePath"
}

$certificate = New-Object Security.Cryptography.X509Certificates.X509Certificate2($certificatePath)
try {
    if ($certificate.Thumbprint -ne $expectedWindowsThumbprint) {
        throw "Windows thumbprint certifikatu nesouhlasi. Ocekavano: $expectedWindowsThumbprint; zjisteno: $($certificate.Thumbprint)"
    }

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $actualSha256Fingerprint = -join ($sha256.ComputeHash($certificate.RawData) | ForEach-Object { $_.ToString('X2') })
    }
    finally {
        $sha256.Dispose()
    }

    if ($actualSha256Fingerprint -ne $expectedSha256Fingerprint) {
        throw "SHA-256 otisk certifikatu nesouhlasi. Ocekavano: $expectedSha256Fingerprint; zjisteno: $actualSha256Fingerprint"
    }
}
finally {
    $certificate.Dispose()
}

Import-Certificate -FilePath $certificatePath -CertStoreLocation 'Cert:\LocalMachine\Root' | Out-Null
Write-Host "Korenova CA byla nainstalovana. SHA-256: $expectedSha256Fingerprint" -ForegroundColor Green
Write-Host 'Zavrete a znovu otevrete prohlizec.'
'@
    $installerContent = $template.Replace('__THUMBPRINT__', $Thumbprint).Replace('__SHA256__', $Sha256Fingerprint)
    Write-Utf8NoBom -Path (Join-Path $ClientCaDir 'Install-Client-CA.ps1') -Content $installerContent

    $urlLines = $Urls | ForEach-Object { "  - $_" }
    $instructions = @"
LOKALNI CERTIFIKACNI AUTORITA PRO e-INFRA OPEN WEBUI
===================================================

1. Zkopirujte celou tuto slozku na kazdy klientsky Windows pocitac.
2. Overte si spravnym kanalem SHA-256 otisk DER korenoveho certifikatu:
   $Sha256Fingerprint
   Windows thumbprint (SHA-1 identifikator uloziste):
   $Thumbprint
3. Na klientovi spustte PowerShell jako spravce a provedte:
   .\Install-Client-CA.ps1
4. Zavrete a znovu otevrete prohlizec.
5. Pouzijte presne nekterou z adres obsazenych v certifikatu:
$($urlLines -join "`r`n")

Bez importu teto CA bude vzdaleny klient lokalnimu certifikatu neduverovat.
Pro zarizeni spravovana domenou lze certifikat distribuovat pres Group Policy.
Nikdy nedistribuujte soukromy klic z adresare caddy-data; klientum patri pouze
verejny soubor e-INFRA-OpenWebUI-Root-CA.crt.
"@
    Write-Utf8NoBom -Path (Join-Path $ClientCaDir 'README-CLIENT-CA.txt') -Content $instructions
}

function Trust-AndExportLocalCa {
    param(
        [Parameter(Mandatory = $true)][string[]]$Urls,
        [Parameter(Mandatory = $true)][string]$PrimaryServerName
    )

    Write-Step 'Instaluji lokalni korenovou CA do duveryhodneho uloziste serveru'

    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    $rootPath = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        $rootPath = Get-LocalCaRootPath
        if (-not [string]::IsNullOrWhiteSpace($rootPath)) { break }
        Invoke-InsecureTlsHandshake -ConnectAddress '127.0.0.1' -ServerName $PrimaryServerName -Port $HttpsPort
        Start-Sleep -Seconds 2
    }
    if ([string]::IsNullOrWhiteSpace($rootPath)) {
        throw "Caddy nevytvoril korenovou CA. Zkontrolujte $LogDir\caddy-runtime.log"
    }

    $certificate = New-Object Security.Cryptography.X509Certificates.X509Certificate2($rootPath)
    try {
        $thumbprint = Normalize-CertificateThumbprint -Thumbprint $certificate.Thumbprint
        $sha256 = [Security.Cryptography.SHA256]::Create()
        try { $sha256Fingerprint = -join ($sha256.ComputeHash($certificate.RawData) | ForEach-Object { $_.ToString('X2') }) }
        finally { $sha256.Dispose() }
    }
    finally { $certificate.Dispose() }

    $storePath = "Cert:\LocalMachine\Root\$thumbprint"
    $alreadyTrusted = Test-Path -LiteralPath $storePath
    $record = $null

    if ($null -ne $script:InstallerState) {
        Add-StatePropertyIfMissing -State $script:InstallerState -Name 'AddedRootCertificates' -DefaultValue @()
        Add-StatePropertyIfMissing -State $script:InstallerState -Name 'LegacyRootCertificates' -DefaultValue @()
        Add-StatePropertyIfMissing -State $script:InstallerState -Name 'CertificateTrustRecords' -DefaultValue @()

        $knownAdded = @($script:InstallerState.AddedRootCertificates | ForEach-Object {
            Normalize-CertificateThumbprint -Thumbprint ([string]$_)
        }) -contains $thumbprint
        $knownLegacy = @($script:InstallerState.LegacyRootCertificates | ForEach-Object {
            Normalize-CertificateThumbprint -Thumbprint ([string]$_)
        }) -contains $thumbprint

        $record = Get-CertificateTrustRecord -Thumbprint $thumbprint
        if ($null -eq $record) {
            if ($knownAdded) {
                $record = Set-CertificateTrustRecord -Thumbprint $thumbprint -PresentBefore:$false -ImportedByInstaller:$true -RemoveOnUninstall:$true -Reason 'compatibility-added-array'
            }
            elseif ($knownLegacy -or [bool]$script:InstallerState.AdoptedLegacyInstallation) {
                $record = Set-CertificateTrustRecord -Thumbprint $thumbprint -PresentBefore:$alreadyTrusted -ImportedByInstaller:$false -RemoveOnUninstall:$true -Reason 'adopted-legacy-installation'
            }
            elseif (-not $alreadyTrusted) {
                # Write-ahead zaznam. Pokud proces skonci tesne po importu,
                # --resume i --uninstall poznaji, ze certifikat patri instalaci.
                $record = Set-CertificateTrustRecord -Thumbprint $thumbprint -PresentBefore:$false -ImportedByInstaller:$false -RemoveOnUninstall:$true -Reason 'pending-installer-import'
            }
            else {
                # Certifikat byl duveryhodny jiz pred touto instalaci. Pri
                # --uninstall jej nesmime odstranit.
                $record = Set-CertificateTrustRecord -Thumbprint $thumbprint -PresentBefore:$true -ImportedByInstaller:$false -RemoveOnUninstall:$false -Reason 'preexisting-trust'
            }
        }
        elseif (-not [bool]$record.PresentBefore -and $alreadyTrusted -and -not [bool]$record.ImportedByInstaller) {
            # Obnova po preruseni mezi Import-Certificate a potvrzenim stavu.
            $record = Set-CertificateTrustRecord -Thumbprint $thumbprint -PresentBefore:$false -ImportedByInstaller:$true -RemoveOnUninstall:$true -Reason 'recovered-interrupted-import'
        }
        elseif ([bool]$script:InstallerState.AdoptedLegacyInstallation -and -not [bool]$record.RemoveOnUninstall) {
            $record = Set-CertificateTrustRecord `
                -Thumbprint $thumbprint `
                -PresentBefore ([bool]$record.PresentBefore) `
                -ImportedByInstaller ([bool]$record.ImportedByInstaller) `
                -RemoveOnUninstall:$true `
                -Reason 'adopted-legacy-installation'
        }
    }

    if (-not $alreadyTrusted) {
        Import-Certificate -FilePath $rootPath -CertStoreLocation 'Cert:\LocalMachine\Root' | Out-Null
        if (-not (Test-Path -LiteralPath $storePath)) {
            throw "Import korenove CA $thumbprint do LocalMachine\Root nebyl po dokonceni nalezen."
        }
        $alreadyTrusted = $true
        if ($null -ne $script:InstallerState) {
            $record = Set-CertificateTrustRecord -Thumbprint $thumbprint -PresentBefore:$false -ImportedByInstaller:$true -RemoveOnUninstall:$true -Reason 'imported-by-installer'
        }
    }

    if ($null -ne $script:InstallerState -and $null -ne $record) {
        $added = [Collections.Generic.List[string]]::new()
        foreach ($value in @($script:InstallerState.AddedRootCertificates)) {
            $normalized = Normalize-CertificateThumbprint -Thumbprint ([string]$value)
            if (-not [string]::IsNullOrWhiteSpace($normalized) -and -not $added.Contains($normalized)) { [void]$added.Add($normalized) }
        }
        $legacy = [Collections.Generic.List[string]]::new()
        foreach ($value in @($script:InstallerState.LegacyRootCertificates)) {
            $normalized = Normalize-CertificateThumbprint -Thumbprint ([string]$value)
            if (-not [string]::IsNullOrWhiteSpace($normalized) -and -not $legacy.Contains($normalized)) { [void]$legacy.Add($normalized) }
        }
        if ([bool]$record.ImportedByInstaller -and -not $added.Contains($thumbprint)) {
            [void]$added.Add($thumbprint)
        }
        elseif ([bool]$script:InstallerState.AdoptedLegacyInstallation -and
                [bool]$record.RemoveOnUninstall -and
                -not $legacy.Contains($thumbprint)) {
            [void]$legacy.Add($thumbprint)
        }
        $script:InstallerState.AddedRootCertificates = $added.ToArray()
        $script:InstallerState.LegacyRootCertificates = $legacy.ToArray()
        Write-InstallerState
    }

    $trustedHandshake = $null
    $trustedDeadline = [DateTime]::UtcNow.AddSeconds(45)
    $trustedError = ''
    while ([DateTime]::UtcNow -lt $trustedDeadline) {
        try {
            $trustedHandshake = Test-TlsSniHandshake -ConnectAddress '127.0.0.1' -ServerName $PrimaryServerName -Port $HttpsPort -RequireTrusted
            break
        }
        catch {
            $trustedError = $_.Exception.Message
            Start-Sleep -Seconds 2
        }
    }
    if ($null -eq $trustedHandshake) {
        throw "Koren lokalni CA byl importovan, ale duveryhodny TLS handshake pro '$PrimaryServerName' selhal. Detail: $trustedError"
    }

    Write-ClientCaInstaller -CertificatePath $rootPath -Thumbprint $thumbprint -Sha256Fingerprint $sha256Fingerprint -Urls $Urls

    $configuration = Read-RuntimeConfig
    $configuration.LocalCaThumbprint = $thumbprint
    Write-RuntimeConfig -Configuration $configuration

    Write-Ok "Lokalni CA je duveryhodna na tomto serveru. SHA-256: $sha256Fingerprint"
    Write-Notice "Balicek pro klientske pocitace: $ClientCaDir"
}

function Test-HttpsEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [switch]$Quiet
    )

    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Get -TimeoutSec 20
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
            Write-Ok "HTTPS kontrola uspesna: $Url (HTTP $($response.StatusCode))"
            return $true
        }
    }
    catch {
        if (-not $Quiet) {
            Write-Caution "HTTPS kontrola adresy $Url zatim neuspesna: $($_.Exception.Message)"
        }
    }
    return $false
}

function Test-UpstreamApiIfPossible {
    if ([string]::Equals($ApiKey, $FakeApiKeyPlaceholder, [StringComparison]::OrdinalIgnoreCase) -or
        $ApiKey -match '(?i)FAKE|CHANGE-ME|SEM-VLOZTE') {
        Write-Caution 'Je nastaven FAKE API klic. WebUI bude fungovat, ale dotazy na LLM selzou, dokud klic nezmenite a znovu nespustite instalaci se stejnymi parametry.'
        return
    }

    Write-Step 'Overuji e-INFRA CZ API a dostupnost vychoziho modelu'
    $modelsUrl = "$ApiBaseUrl/models"
    try {
        $headers = @{ Authorization = "Bearer $ApiKey" }
        $response = Invoke-RestMethod -Uri $modelsUrl -Headers $headers -Method Get -TimeoutSec 30
        $ids = @($response.data | ForEach-Object { [string]$_.id })
        if ($ids -contains $DefaultModel) {
            Write-Ok "Endpoint prijal API klic a model '$DefaultModel' je v seznamu modelu."
        }
        else {
            Write-Caution "Endpoint prijal pozadavek, ale model '$DefaultModel' nebyl v seznamu modelu. Dostupnost se muze menit."
        }
    }
    catch {
        Write-Caution "Overeni e-INFRA API selhalo: $($_.Exception.Message)"
    }
}

function Write-AdminCredentialsFile {
    param(
        [Parameter(Mandatory = $true)][string]$Password,
        [Parameter(Mandatory = $true)][string]$PrimaryUrl
    )

    $content = @"
JEDNORAZOVE UDAJE ADMINISTRATORA OPEN WEBUI
===========================================
URL:   $PrimaryUrl
E-mail: $AdminEmail
Heslo: $Password

Po prvnim prihlaseni heslo zmente a tento soubor bezpecne smazte.
Soubor je pristupny pouze LOCAL SYSTEM a mistnim administratorum; sluzba LOCAL SERVICE jej cist nemuze.
"@
    Ensure-Directory $AdminDir
    Write-Utf8NoBom -Path $CredentialsPath -Content $content
    Set-AdminOnlyFileAcl -Path $CredentialsPath
}

function Remove-AdminBootstrapFromRuntime {
    $configuration = Read-RuntimeConfig
    foreach ($name in @('WEBUI_ADMIN_EMAIL', 'WEBUI_ADMIN_NAME', 'WEBUI_ADMIN_PASSWORD')) {
        if ($configuration.Environment.PSObject.Properties.Name -contains $name) {
            $configuration.Environment.PSObject.Properties.Remove($name)
        }
    }
    Write-RuntimeConfig -Configuration $configuration
}

function Confirm-BootstrapAdmin {
    param([Parameter(Mandatory = $true)][string]$Password)

    Write-Step 'Overuji vytvoreni administratorskeho uctu'
    $uri = "http://127.0.0.1:$BackendPort/api/v1/auths/signin"
    $body = @{
        email = $AdminEmail.Trim()
        password = $Password
    } | ConvertTo-Json
    $lastError = 'Neznama chyba.'

    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            $response = Invoke-RestMethod `
                -UseBasicParsing `
                -Uri $uri `
                -Method Post `
                -ContentType 'application/json' `
                -Body $body `
                -TimeoutSec 20

            $responseProperties = @($response.PSObject.Properties.Name)
            $returnedToken = ''
            $returnedEmail = ''
            $returnedRole = ''
            if ($responseProperties -contains 'token') {
                $returnedToken = [string]$response.token
            }
            elseif ($responseProperties -contains 'access_token') {
                $returnedToken = [string]$response.access_token
            }
            if ($responseProperties -contains 'email') {
                $returnedEmail = [string]$response.email
            }
            if ($responseProperties -contains 'role') {
                $returnedRole = [string]$response.role
            }

            if ([string]::Equals($returnedEmail, $AdminEmail.Trim(), [StringComparison]::OrdinalIgnoreCase) -and
                $returnedRole -eq 'admin' -and
                -not [string]::IsNullOrWhiteSpace($returnedToken)) {
                Write-Ok "Administratorsky ucet $AdminEmail byl vytvoren a prihlaseni funguje."
                return
            }
            $lastError = 'API vratilo neocekavanou odpoved bez administratorskeho tokenu.'
        }
        catch {
            $lastError = $_.Exception.Message
        }

        if ($attempt -lt 3) {
            Start-Sleep -Seconds 4
        }
    }

    throw "Administratorsky bootstrap se nepodarilo overit. Jednorazove heslo zustalo v runtime konfiguraci i v chranenem souboru. Detail: $lastError"
}

function Restart-BackendAfterBootstrap {
    Write-Step 'Dokoncuji jednorazove zalozeni administratora'
    Remove-AdminBootstrapFromRuntime
    Stop-ScheduledTask -TaskName $BackendTaskName -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Stop-ManagedProcesses
    Start-ScheduledTask -TaskName $BackendTaskName
    Wait-TcpPort -HostName '127.0.0.1' -Port $BackendPort -ComponentName 'Open WebUI backend po bootstrapu'
    Write-Ok 'Jednorazove administratorske heslo bylo odstraneno z runtime konfigurace.'
}

function Resolve-PublicDomain {
    if ($CertificateMode -ne 'PublicACME') { return }
    Write-Step 'Kontroluji verejnou DNS domenu'
    try {
        $addresses = [Net.Dns]::GetHostAddresses($PublicDomain)
        if ($addresses.Count -eq 0) {
            throw 'DNS nevratilo zadnou adresu.'
        }
        Write-Ok "$PublicDomain se preklada na: $($addresses -join ', ')"
        Write-Notice 'Tento lokalni DNS test nestaci pro ACME: verejna CA musi stejne jmeno prelozit z Internetu a dosahnout na TCP 80 nebo 443.'
    }
    catch {
        throw "DNS domeny $PublicDomain nelze prelozit. Pred instalaci vytvorte A/AAAA zaznam. Detail: $($_.Exception.Message)"
    }
}

function Show-LogTail {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        Write-Host "`n--- Posledni radky: $Path ---" -ForegroundColor Yellow
        Get-Content -LiteralPath $Path -Tail 30 -ErrorAction SilentlyContinue
    }
}

function Show-Status {
    Write-Step 'Stav instalace'

    $state = $null
    try { $state = Read-InstallerState } catch { Write-Caution $_.Exception.Message }
    if ($null -ne $state) {
        Write-Host "Instalator:     $($state.Status)"
        Write-Host "Posledni faze:  $($state.CurrentPhase)"
        if (-not [string]::IsNullOrWhiteSpace([string]$state.LastError)) {
            Write-Host "Posledni chyba: $($state.LastError)" -ForegroundColor Yellow
        }
    }

    if (-not (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf)) {
        Write-Caution "Runtime konfigurace nebyla nalezena v $InstallRoot. Je-li instalace prerusena, pouzijte --resume."
        return
    }

    $configuration = Read-RuntimeConfig
    foreach ($taskName in @($BackendTaskName, $ProxyTaskName)) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -eq $task) {
            Write-Host ("{0,-34} {1}" -f $taskName, 'NENI ZAREGISTROVANA') -ForegroundColor Red
        }
        else {
            $info = Get-ScheduledTaskInfo -TaskName $taskName -ErrorAction SilentlyContinue
            $resultText = if ($null -ne $info) { "LastTaskResult=$($info.LastTaskResult)" } else { '' }
            Write-Host ("{0,-34} {1} {2}" -f $taskName, $task.State, $resultText)
        }
    }

    $backendOpen = Test-TcpPort -HostName '127.0.0.1' -Port ([int]$configuration.BackendPort)
    $httpsOpen = Test-TcpPort -HostName '127.0.0.1' -Port ([int]$configuration.HttpsPort)
    Write-Host "Backend port:  $($configuration.BackendPort) / otevren=$backendOpen"
    Write-Host "HTTPS port:    $($configuration.HttpsPort) / otevren=$httpsOpen"
    Write-Host "URL:           $($configuration.PrimaryUrl)"
    Write-Host "TLS rezim:     $($configuration.CertificateMode)"
    Write-Host "Nazvy/IP SAN:  $(@($configuration.SiteHosts) -join ', ')"
    Write-Host "API endpoint:  $($configuration.Environment.OPENAI_API_BASE_URL)"
    Write-Host "Vychozi model: $($configuration.Environment.DEFAULT_MODELS)"
    $installedVersion = Get-InstalledOpenWebUIVersion -Quiet
    Write-Host "Open WebUI:    $installedVersion"
    if ($configuration.PSObject.Properties.Name -contains 'OpenWebUIUpdatePolicy') {
        Write-Host "Update policy: $($configuration.OpenWebUIUpdatePolicy)"
    }
    if ($configuration.PSObject.Properties.Name -contains 'LatestAvailableOpenWebUIVersion' -and
        -not [string]::IsNullOrWhiteSpace([string]$configuration.LatestAvailableOpenWebUIVersion)) {
        Write-Host "Posledni znam.: $($configuration.LatestAvailableOpenWebUIVersion)"
    }
    Write-Host "Data:          $($configuration.DataDirectory)"
    Write-Host "Logy:          $($configuration.LogDirectory)"

    if ($httpsOpen) {
        $serverName = ''
        if ($configuration.PSObject.Properties.Name -contains 'PrimaryServerName') {
            $serverName = [string]$configuration.PrimaryServerName
        }
        if ([string]::IsNullOrWhiteSpace($serverName)) {
            try { $serverName = ([Uri]$configuration.PrimaryUrl).Host } catch { }
        }
        if (-not [string]::IsNullOrWhiteSpace($serverName)) {
            try {
                $result = Test-TlsSniHandshake -ConnectAddress '127.0.0.1' -ServerName $serverName -Port ([int]$configuration.HttpsPort) -RequireTrusted
                if ([string]$configuration.CertificateMode -eq 'PublicACME') {
                    Assert-PublicCertificateHandshake -Handshake $result -ServerName $serverName
                    Write-Ok "TLS SNI '$serverName' pouziva verejne duveryhodny certifikat ($($result.Protocol))."
                    Write-Notice "Issuer: $($result.CertificateIssuer); platnost do: $($result.CertificateNotAfterUtc); root: $($result.ChainRootSubject)"
                }
                else {
                    Write-Ok "TLS SNI '$serverName' je pres loopback sifrovane a duveryhodne pro tento server ($($result.Protocol))."
                    Write-Caution 'Rezim LocalCA muze byt na tomto serveru duveryhodny, ale vzdaleny klient bez importu korene CA bude hlasit ERR_CERT_AUTHORITY_INVALID.'
                }
            }
            catch {
                Write-Caution "TLS SNI '$serverName' selhalo: $($_.Exception.Message)"
            }
        }
        [void](Test-HttpsEndpoint -Url ([string]$configuration.PrimaryUrl))
    }
}

function Install-Deployment {
    Invoke-InstallPhase -Name 'validate-input' -Operation {
        Validate-InstallParameters
        Resolve-PublicDomain
    }

    Invoke-InstallPhase -Name 'filesystem-and-state' -Operation {
        Write-Step "Pripravuji adresar $InstallRoot"
        foreach ($directory in @(
            $InstallRoot, $BinDir, $UvDir, $CaddyDir, $PythonInstallDir, $UvCacheDir,
            $DataDir, $RuntimeTempDir, $CacheDir, $HfCacheDir, $StaticDir, $ConfigDir,
            $CaddyDataBase, $CaddyConfigBase, $LogDir, $DownloadDir, $BackupDir,
            $ClientCaDir, $AdminDir, $InstallerStateDir, $InstallerSnapshotDir
        )) {
            Ensure-Directory $directory
        }
        Set-PrivateAcl $InstallRoot
        Write-ResumeConfiguration
        Write-Ok 'Instalacni adresar je omezen na administratory; runtime bezi pod uctem LOCAL SERVICE s minimalnimi zapisovymi pravy.'
    }

    Invoke-InstallPhase -Name 'recover-pending-open-webui-update' -Operation {
        Recover-PendingOpenWebUIUpdate
    }

    Invoke-InstallPhase -Name 'open-webui-update-check' -Operation {
        Resolve-OpenWebUIVersionForRun
        Write-ResumeConfiguration
    }

    Invoke-InstallPhase -Name 'install-uv' -Operation { Install-Uv }

    # Nejprve lze pripravit preflight venv bez vypadku. Transakcni aktualizace
    # zastavi backend az pred konzistentni zalohou DATA_DIR, odsune puvodni venv
    # a cilovou verzi znovu vytvori primo v kanonicke ceste.
    Invoke-InstallPhase -Name 'pre-update-database-backup' -Operation {
        Backup-Database
    }
    Invoke-InstallPhase -Name 'install-open-webui' -Operation { Install-OpenWebUI }

    Invoke-InstallPhase -Name 'stop-and-backup' -Operation {
        Write-Step 'Zastavuji spravovane komponenty a overuji porty'
        Stop-Deployment -RequireStopped
        Assert-PortsAvailable
        # Pri skutecne aktualizaci uz existuje silnejsi SHA-256 zaloha trvalych dat
        # DATA_DIR (bez cache a runtime-temp). U bezne opravy/re-konfigurace ponechame SQLite zalohu.
        if ($null -eq (Read-OpenWebUIUpdateTransaction)) {
            Backup-Database
        }
    }

    Invoke-InstallPhase -Name 'install-caddy' -Operation { Install-Caddy }

    Invoke-InstallPhase -Name 'runtime-configuration' -Operation {
        Write-Step 'Vytvarim jednotnou runtime a HTTPS konfiguraci'

        $existingConfiguration = $null
        if (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf) {
            try { $existingConfiguration = Read-RuntimeConfig }
            catch { Write-Caution "Stavajici runtime konfiguraci nelze nacist a bude vytvorena znovu: $($_.Exception.Message)" }
        }

        $freshDatabase = -not (Test-Path -LiteralPath (Join-Path $DataDir 'webui.db') -PathType Leaf)
        $resumableBootstrap = $null
        if (-not $freshDatabase) { $resumableBootstrap = Get-ExistingAdminBootstrap }

        $bootstrapRequired = $freshDatabase -or $null -ne $resumableBootstrap
        $bootstrapPassword = ''
        if ($freshDatabase) {
            $bootstrapPassword = if ([string]::IsNullOrWhiteSpace($AdminPassword)) { New-RandomPassword } else { $AdminPassword }
        }
        elseif ($null -ne $resumableBootstrap) {
            $script:AdminEmail = [string]$resumableBootstrap.Email
            $script:AdminName = [string]$resumableBootstrap.Name
            $bootstrapPassword = [string]$resumableBootstrap.Password
            Write-Notice "Obnovuji nedokonceny bootstrap administratora $AdminEmail."
        }

        $localData = Get-LocalHostData
        $detectedLocalAddresses = @($localData.Addresses | Select-Object -Unique)
        $localAddresses = @($ProfileLocalAddresses | Select-Object -Unique)
        foreach ($profileAddress in $localAddresses) {
            if ($detectedLocalAddresses -notcontains $profileAddress) {
                Write-Caution "Konfigurovana LocalAddress $profileAddress neni mezi aktualne zjistenymi adresami ($($detectedLocalAddresses -join ', '))."
            }
        }
        $primaryServerName = ''
        $siteHosts = @()

        if ($CertificateMode -eq 'PublicACME') {
            $primaryServerName = $PublicDomain
            $siteHosts = @($PublicDomain)
        }
        else {
            if (-not [string]::IsNullOrWhiteSpace($LocalAccessName)) {
                $primaryServerName = Normalize-LocalAccessName -Value $LocalAccessName
            }
            elseif ($null -ne $existingConfiguration -and
                    $existingConfiguration.PSObject.Properties.Name -contains 'PrimaryServerName' -and
                    -not [string]::IsNullOrWhiteSpace([string]$existingConfiguration.PrimaryServerName)) {
                $primaryServerName = Normalize-LocalAccessName -Value ([string]$existingConfiguration.PrimaryServerName)
            }
            elseif ($null -ne $existingConfiguration -and
                    $existingConfiguration.PSObject.Properties.Name -contains 'PrimaryUrl') {
                try {
                    $existingPrimaryUri = $null
                    if ([Uri]::TryCreate([string]$existingConfiguration.PrimaryUrl, [UriKind]::Absolute, [ref]$existingPrimaryUri)) {
                        $primaryServerName = Normalize-LocalAccessName -Value ([string]$existingPrimaryUri.Host)
                    }
                    else {
                        $primaryServerName = ''
                    }
                }
                catch { $primaryServerName = '' }
            }
            if ([string]::IsNullOrWhiteSpace($primaryServerName)) {
                $primaryServerName = Normalize-LocalAccessName -Value ([string]$localData.Primary)
            }

            $hostList = [Collections.Generic.List[string]]::new()
            $candidates = [Collections.Generic.List[string]]::new()
            $candidates.Add($primaryServerName)
            if (-not [string]::IsNullOrWhiteSpace($LocalAccessName)) { $candidates.Add([string]$LocalAccessName) }
            if ($null -ne $existingConfiguration -and $existingConfiguration.PSObject.Properties.Name -contains 'SiteHosts') {
                foreach ($candidate in @($existingConfiguration.SiteHosts)) { $candidates.Add([string]$candidate) }
            }
            foreach ($candidate in @($localData.Hosts)) { $candidates.Add([string]$candidate) }
            $candidates.Add('localhost')
            $candidates.Add('127.0.0.1')

            foreach ($candidate in $candidates) {
                if ([string]::IsNullOrWhiteSpace([string]$candidate)) { continue }
                try { $normalized = Normalize-LocalAccessName -Value ([string]$candidate) }
                catch {
                    Write-Caution "Preskakuji neplatny stary hostname '$candidate': $($_.Exception.Message)"
                    continue
                }
                if (-not $hostList.Contains($normalized)) { $hostList.Add($normalized) }
            }
            $siteHosts = $hostList.ToArray()
            $script:LocalAccessName = $primaryServerName
        }

        $primaryUrl = Format-HttpsUrl -HostName $primaryServerName -Port $HttpsPort
        $allowedOrigins = @($siteHosts | ForEach-Object { Format-HttpsUrl -HostName ([string]$_) -Port $HttpsPort })
        $secret = Get-ExistingSecret
        $script:ResumeWebUiSecret = $secret
        $runtimeConfiguration = New-RuntimeConfiguration `
            -SiteHosts $siteHosts `
            -PrimaryUrl $primaryUrl `
            -AllowedOrigins $allowedOrigins `
            -WebUiSecret $secret `
            -BootstrapAdmin $bootstrapRequired `
            -BootstrapPassword $bootstrapPassword
        $runtimeConfiguration['PrimaryServerName'] = $primaryServerName
        $runtimeConfiguration['AcmeEmail'] = $AcmeEmail
        $runtimeConfiguration['LocalAddresses'] = @($localAddresses)

        Write-RuntimeConfig -Configuration $runtimeConfiguration
        Write-ComponentRunner
        Write-CaddyConfiguration -SiteHosts $siteHosts -PrimaryServerName $primaryServerName
        Test-CaddyConfiguration

        if ($bootstrapRequired) {
            Write-AdminCredentialsFile -Password $bootstrapPassword -PrimaryUrl $primaryUrl
        }

        Write-ResumeConfiguration
        $script:InstallContext = [pscustomobject]@{
            PrimaryUrl = $primaryUrl
            PrimaryServerName = $primaryServerName
            SiteHosts = @($siteHosts)
            AllowedOrigins = @($allowedOrigins)
            LocalAddresses = @($localAddresses)
            BootstrapRequired = [bool]$bootstrapRequired
            BootstrapPassword = $bootstrapPassword
        }
        Write-Ok "HTTPS konfigurace obsahuje: $($siteHosts -join ', ')"
    }

    Invoke-InstallPhase -Name 'firewall' -Operation { Configure-Firewall }
    Invoke-InstallPhase -Name 'scheduled-tasks' -Operation { Register-DeploymentTasks }

    Invoke-InstallPhase -Name 'start-and-bootstrap' -Operation {
        if ($null -eq $script:InstallContext) { throw 'Interni chyba: chybi runtime kontext instalace.' }
        try {
            Start-TaskIfNeeded -TaskName $BackendTaskName
            Wait-TcpPort -HostName '127.0.0.1' -Port $BackendPort -ComponentName 'Open WebUI backend'
            Wait-OpenWebUIReady -TimeoutSeconds 300
            Write-Ok "Open WebUI nasloucha pouze lokalne na 127.0.0.1:$BackendPort a dokoncilo start/migrace."

            if ([bool]$script:InstallContext.BootstrapRequired) {
                Confirm-BootstrapAdmin -Password ([string]$script:InstallContext.BootstrapPassword)
                Restart-BackendAfterBootstrap
                Wait-OpenWebUIReady -TimeoutSeconds 180
            }

            Complete-PendingOpenWebUIUpdate

            Start-TaskIfNeeded -TaskName $ProxyTaskName
            Wait-TcpPort -HostName '127.0.0.1' -Port $HttpsPort -ComponentName 'Caddy HTTPS proxy'
            Write-Ok "Caddy nasloucha na HTTPS portu $HttpsPort."
        }
        catch {
            Show-LogTail -Path (Join-Path $LogDir 'open-webui.log')
            Show-LogTail -Path (Join-Path $LogDir 'caddy-runtime.log')
            throw
        }
    }

    Invoke-InstallPhase -Name 'tls-and-network-validation' -Operation {
        if ($null -eq $script:InstallContext) { throw 'Interni chyba: chybi TLS kontext instalace.' }
        $primaryServerName = [string]$script:InstallContext.PrimaryServerName
        $localAddresses = [string[]]@($script:InstallContext.LocalAddresses)

        if ($CertificateMode -eq 'LocalCA') {
            Trust-AndExportLocalCa `
                -Urls ([string[]]@($script:InstallContext.AllowedOrigins)) `
                -PrimaryServerName $primaryServerName
            Test-DeploymentNetwork -PrimaryServerName $primaryServerName -LocalAddresses $localAddresses
            Start-Sleep -Seconds 2
            if (-not (Test-HttpsEndpoint -Url ([string]$script:InstallContext.PrimaryUrl) -Quiet)) {
                Write-Caution "Prima HTTPS kontrola pres DNS URL selhala, ale lokalni SNI testy prosly. Zkontrolujte DNS preklad jmena '$primaryServerName' a na vzdalenych klientech nainstalujte CA z $ClientCaDir."
            }
        }
        else {
            Test-DeploymentNetwork -PrimaryServerName $primaryServerName -LocalAddresses $localAddresses
            $publicCertificate = $null
            $lastPublicCertificateError = ''
            $deadline = [DateTime]::UtcNow.AddSeconds(300)
            while ([DateTime]::UtcNow -lt $deadline) {
                try {
                    # Pripojeni jde primo na lokalni Caddy, ale SNI i overeni
                    # retezce pouziva verejnou domenu. Test tedy nezavisi na
                    # DNS hairpinu/NAT loopbacku a stale odhali neduveryhodny certifikat.
                    $candidateCertificate = Test-TlsSniHandshake -ConnectAddress '127.0.0.1' -ServerName $primaryServerName -Port $HttpsPort -RequireTrusted
                    Assert-PublicCertificateHandshake -Handshake $candidateCertificate -ServerName $primaryServerName
                    $publicCertificate = $candidateCertificate
                    break
                }
                catch {
                    $lastPublicCertificateError = $_.Exception.Message
                    Start-Sleep -Seconds 5
                }
            }
            if ($null -eq $publicCertificate) {
                Show-LogTail -Path (Join-Path $LogDir 'caddy-runtime.log')
                throw "Verejne duveryhodny certifikat se nepodarilo ziskat ani overit. Skript nepouzil LocalCA jako nahradu. Overte verejne A/AAAA DNS, CAA pravidla a dostupnost TCP 80/443 z Internetu; potom znovu spustte --resume. Detail: $lastPublicCertificateError"
            }
            Write-Ok "Verejny certifikat pro $primaryServerName je duveryhodny a odpovida SNI ($($publicCertificate.Protocol))."
            Write-Notice "Issuer: $($publicCertificate.CertificateIssuer); platnost do: $($publicCertificate.CertificateNotAfterUtc); root: $($publicCertificate.ChainRootSubject)"
            if (-not (Test-HttpsEndpoint -Url ([string]$script:InstallContext.PrimaryUrl) -Quiet)) {
                Write-Caution "Certifikat i lokalni Caddy jsou v poradku, ale DNS URL neni z tohoto serveru dostupna. Zkontrolujte DNS hairpin/NAT; vzdaleny pristup muze presto fungovat."
            }
        }
    }

    Invoke-InstallPhase -Name 'upstream-api-check' -Operation { Test-UpstreamApiIfPossible }

    $context = $script:InstallContext
    Write-Host "`n============================================================" -ForegroundColor Green
    Write-Host 'INSTALACE DOKONCENA' -ForegroundColor Green
    Write-Host "WebUI:          $($context.PrimaryUrl)"
    Write-Host "API endpoint:   $ApiBaseUrl"
    Write-Host "Vychozi model:  $DefaultModel"
    Write-Host "TLS rezim:      $CertificateMode"
    Write-Host "Data:           $DataDir"
    Write-Host "Logy:           $LogDir"
    if ([bool]$context.BootstrapRequired) {
        Write-Host "Admin e-mail:   $AdminEmail" -ForegroundColor Yellow
        Write-Host "Admin heslo:    ulozeno pouze v chranenem souboru" -ForegroundColor Yellow
        Write-Host "Chraneny soubor s udaji: $CredentialsPath" -ForegroundColor Yellow
    }
    if ($CertificateMode -eq 'LocalCA') {
        Write-Host "CA pro klienty: $ClientCaDir" -ForegroundColor Yellow
        Write-Caution 'LocalCA neni verejne duveryhodny certifikat. Bez importu korene CA na kazdem klientovi bude prohlizec hlasit ERR_CERT_AUTHORITY_INVALID.'
    }
    Write-Host '============================================================' -ForegroundColor Green

    if (-not $DisableSignup) {
        Write-Notice 'Nove registrace dostanou roli pending; administrator je musi schvalit.'
    }
    Write-Notice 'ENABLE_PERSISTENT_CONFIG=True: pozdejsi zmeny ConfigVar provedene v Admin UI maji prednost pred hodnotami prostredi.'
    Write-Caution 'Pluginy, import nastroju/skills, pip instalace a spousteni kodu jsou povoleny. Schvalujte pouze duveryhodne uzivatele a obsah.'
    Write-Caution 'API klice e-INFRA CZ jsou osobni. Pro vice osob nepouzivejte jeden sdileny osobni klic v rozporu s podminkami sluzby.'
}

function Update-Deployment {
    if (-not (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf)) {
        throw 'Nejprve provedte instalaci; pro prerusenou instalaci pouzijte --resume.'
    }
    Install-Deployment
    Write-Ok 'Aktualizace a kontrola cele instalace byla dokoncena.'
}

function Test-UninstallEvidence {
    if (Test-Path -LiteralPath $InstallerStatePath -PathType Leaf) { return $true }
    if (Test-Path -LiteralPath $UninstallRecoveryStatePath -PathType Leaf) { return $true }
    foreach ($path in @($RuntimeConfigPath, $CaddyExe, $OpenWebUIExe, $VenvDir, $CaddyDataBase, $InstallerStateDir)) {
        if (Test-Path -LiteralPath $path) { return $true }
    }
    foreach ($taskName in @($BackendTaskName, $ProxyTaskName)) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -ne $task -and (Test-ScheduledTaskBelongsToDeployment -Task $task)) { return $true }
    }
    # Samotna shoda zobrazovaneho nazvu firewall pravidla neni dukazem
    # vlastnictvi. Bez souboru nebo ulohy by odinstalator mohl zasahnout cizi
    # pravidlo se stejnym nazvem; takovou situaci proto nepovazujeme za instalaci.
    return $false
}

function Initialize-UninstallState {
    if ($null -ne $script:InstallerState) {
        foreach ($property in @(
            @{ Name='SchemaVersion'; Value=5 },
            @{ Name='InstallerVersion'; Value=$ScriptVersion },
            @{ Name='ProductId'; Value=$ProductId },
            @{ Name='InstallationId'; Value=([Guid]::NewGuid().ToString('D')) },
            @{ Name='Status'; Value='Uninstalling' },
            @{ Name='CurrentPhase'; Value='uninstall-initialization' },
            @{ Name='CompletedPhases'; Value=@() },
            @{ Name='UninstallCompletedPhases'; Value=@() },
            @{ Name='LastError'; Value='' },
            @{ Name='RootExistedBeforeInstaller'; Value=$false },
            @{ Name='RootOriginalSddl'; Value='' },
            @{ Name='RootChildrenBeforeInstaller'; Value=@() },
            @{ Name='AdoptedLegacyInstallation'; Value=$false },
            @{ Name='ManagedTaskNames'; Value=@() },
            @{ Name='FirewallRuleNames'; Value=@() },
            @{ Name='AddedRootCertificates'; Value=@() },
            @{ Name='PendingRootCertificateImports'; Value=@() },
            @{ Name='PreexistingRootCertificates'; Value=@() },
            @{ Name='LegacyRootCertificates'; Value=@() },
            @{ Name='CertificateTrustRecords'; Value=@() },
            @{ Name='PreserveDataRequested'; Value=$false },
            @{ Name='PreservedDataPath'; Value='' },
            @{ Name='StartedAt'; Value=([DateTimeOffset]::Now.ToString('o')) },
            @{ Name='UpdatedAt'; Value=([DateTimeOffset]::Now.ToString('o')) }
        )) {
            Add-StatePropertyIfMissing -State $script:InstallerState -Name ([string]$property.Name) -DefaultValue $property.Value
        }
        $script:InstallerState.SchemaVersion = 5
        $script:InstallerState.InstallerVersion = $ScriptVersion
        if (-not [string]::Equals([string]$script:InstallerState.ProductId, $ProductId, [StringComparison]::Ordinal)) {
            throw "Odinstalacni stav patri jinemu produktu ('$($script:InstallerState.ProductId)') a nebude pouzit."
        }

        if ($CliSpecified.ContainsKey('PreserveData')) {
            if (-not $PreserveData -and
                -not [string]::IsNullOrWhiteSpace([string]$script:InstallerState.PreservedDataPath)) {
                Write-Caution "Data uz byla presunuta do $($script:InstallerState.PreservedDataPath); --purge-data je nemuze bezpecne vratit zpet ani dodatecne smazat. Zachovana data zustanou na miste."
                $script:InstallerState.PreserveDataRequested = $true
            }
            else {
                $script:InstallerState.PreserveDataRequested = [bool]$PreserveData
            }
        }
        $script:PreserveData = [bool]$script:InstallerState.PreserveDataRequested
        $script:PurgeData = -not $script:PreserveData
        Write-InstallerState
        return $true
    }

    if (-not (Test-UninstallEvidence)) { return $false }

    # Instalace 1.2.x nema state.json. Vytvorime minimalni write-ahead stav,
    # aby se i jeji odinstalace dala po libovolnem preruseni zopakovat.
    Ensure-Directory $InstallerStateDir
    Ensure-Directory $InstallerSnapshotDir
    $script:InstallerState = [pscustomobject][ordered]@{
        SchemaVersion = 5
        InstallerVersion = $ScriptVersion
        ProductId = $ProductId
        InstallationId = [Guid]::NewGuid().ToString('D')
        Status = 'Uninstalling'
        CurrentPhase = 'uninstall-initialization'
        CompletedPhases = @()
        UninstallCompletedPhases = @()
        LastError = ''
        StartedAt = [DateTimeOffset]::Now.ToString('o')
        UpdatedAt = [DateTimeOffset]::Now.ToString('o')
        RootExistedBeforeInstaller = $false
        RootOriginalSddl = ''
        RootChildrenBeforeInstaller = @()
        AdoptedLegacyInstallation = $true
        ManagedTaskNames = @($BackendTaskName, $ProxyTaskName)
        FirewallRuleNames = @()
        AddedRootCertificates = @()
        PendingRootCertificateImports = @()
        PreexistingRootCertificates = @()
        LegacyRootCertificates = @()
        CertificateTrustRecords = @()
        PreserveDataRequested = [bool]$PreserveData
        PreservedDataPath = ''
    }

    if (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf) {
        try {
            $legacyConfiguration = Read-RuntimeConfig
            if ($legacyConfiguration.PSObject.Properties.Name -contains 'LocalCaThumbprint') {
                $thumbprint = Normalize-CertificateThumbprint -Thumbprint ([string]$legacyConfiguration.LocalCaThumbprint)
                if (-not [string]::IsNullOrWhiteSpace($thumbprint)) {
                    $script:InstallerState.LegacyRootCertificates = @($thumbprint)
                }
            }
        }
        catch {
            Write-Caution "Thumbprint lokalni CA ze starsi instalace nelze nacist: $($_.Exception.Message)"
        }
    }
    $script:PreserveData = [bool]$script:InstallerState.PreserveDataRequested
    $script:PurgeData = -not $script:PreserveData
    Write-InstallerState
    return $true
}

function Import-RuntimePortsForUninstall {
    if (-not (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf)) { return }
    try {
        $configuration = Read-RuntimeConfig
        if ($configuration.PSObject.Properties.Name -contains 'BackendPort') { $script:BackendPort = [int]$configuration.BackendPort }
        if ($configuration.PSObject.Properties.Name -contains 'HttpPort') { $script:HttpPort = [int]$configuration.HttpPort }
        if ($configuration.PSObject.Properties.Name -contains 'HttpsPort') { $script:HttpsPort = [int]$configuration.HttpsPort }
    }
    catch {
        Write-Caution "Porty ze stavajici runtime konfigurace nelze nacist; odinstalace pouzije vychozi hodnoty. Detail: $($_.Exception.Message)"
    }
}

function Get-TrackedCertificatesForRemoval {
    $result = [Collections.Generic.List[string]]::new()
    $preexisting = [Collections.Generic.List[string]]::new()
    $adoptedLegacy = $null -eq $script:InstallerState

    if ($null -ne $script:InstallerState) {
        $adoptedLegacy = [bool]$script:InstallerState.AdoptedLegacyInstallation
        foreach ($value in @($script:InstallerState.PreexistingRootCertificates)) {
            $normalized = Normalize-CertificateThumbprint -Thumbprint ([string]$value)
            if (-not [string]::IsNullOrWhiteSpace($normalized) -and -not $preexisting.Contains($normalized)) {
                [void]$preexisting.Add($normalized)
            }
        }
        foreach ($record in @($script:InstallerState.CertificateTrustRecords)) {
            if ($null -eq $record) { continue }
            Add-StatePropertyIfMissing -State $record -Name 'Thumbprint' -DefaultValue ''
            Add-StatePropertyIfMissing -State $record -Name 'RemoveOnUninstall' -DefaultValue $false
            if (-not [bool]$record.RemoveOnUninstall) { continue }
            $normalized = Normalize-CertificateThumbprint -Thumbprint ([string]$record.Thumbprint)
            if (-not [string]::IsNullOrWhiteSpace($normalized) -and
                -not $preexisting.Contains($normalized) -and -not $result.Contains($normalized)) {
                [void]$result.Add($normalized)
            }
        }
        foreach ($collection in @(
            @($script:InstallerState.AddedRootCertificates),
            @($script:InstallerState.PendingRootCertificateImports)
        )) {
            foreach ($value in $collection) {
                $normalized = Normalize-CertificateThumbprint -Thumbprint ([string]$value)
                if (-not [string]::IsNullOrWhiteSpace($normalized) -and
                    -not $preexisting.Contains($normalized) -and -not $result.Contains($normalized)) {
                    [void]$result.Add($normalized)
                }
            }
        }
        if ($adoptedLegacy) {
            foreach ($value in @($script:InstallerState.LegacyRootCertificates)) {
                $normalized = Normalize-CertificateThumbprint -Thumbprint ([string]$value)
                if (-not [string]::IsNullOrWhiteSpace($normalized) -and -not $result.Contains($normalized)) {
                    [void]$result.Add($normalized)
                }
            }
        }
    }

    if ($adoptedLegacy -and (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf)) {
        try {
            $configuration = Read-RuntimeConfig
            if ($configuration.PSObject.Properties.Name -contains 'LocalCaThumbprint') {
                $normalized = Normalize-CertificateThumbprint -Thumbprint ([string]$configuration.LocalCaThumbprint)
                if (-not [string]::IsNullOrWhiteSpace($normalized) -and -not $result.Contains($normalized)) {
                    [void]$result.Add($normalized)
                }
            }
        }
        catch { Write-Caution "Thumbprint CA ze starsi runtime konfigurace nelze nacist: $($_.Exception.Message)" }
    }

    if ($adoptedLegacy) {
        foreach ($candidatePath in @(
            (Get-LocalCaRootPath),
            (Join-Path $ClientCaDir 'e-INFRA-OpenWebUI-Root-CA.crt')
        )) {
            if ([string]::IsNullOrWhiteSpace([string]$candidatePath) -or
                -not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) { continue }
            try {
                $certificate = New-Object Security.Cryptography.X509Certificates.X509Certificate2($candidatePath)
                try { $normalized = Normalize-CertificateThumbprint -Thumbprint $certificate.Thumbprint }
                finally { $certificate.Dispose() }
                if (-not [string]::IsNullOrWhiteSpace($normalized) -and -not $result.Contains($normalized)) {
                    [void]$result.Add($normalized)
                }
            }
            catch { Write-Caution "Certifikat $candidatePath nelze precist: $($_.Exception.Message)" }
        }
    }
    return $result.ToArray()
}

function Remove-TrackedRootCertificates {
    foreach ($thumbprint in @(Get-TrackedCertificatesForRemoval)) {
        $certificatePath = "Cert:\LocalMachine\Root\$thumbprint"
        try {
            if (Test-Path -LiteralPath $certificatePath) {
                Remove-Item -LiteralPath $certificatePath -Force -ErrorAction Stop
            }
            if (Test-Path -LiteralPath $certificatePath) {
                throw 'Certifikat zustal v ulozisti i po pokusu o odstraneni.'
            }
            Write-Ok "Korenovy certifikat $thumbprint pridany touto nebo prevzatou instalaci byl odebran z tohoto serveru."
        }
        catch {
            throw "Korenovy certifikat $thumbprint nelze odebrat: $($_.Exception.Message)"
        }
    }
}

function Remove-ManagedPythonInstallationForUninstall {
    Write-Step 'Odstranuji spravovanou registraci Pythonu'

    if (-not (Test-Path -LiteralPath $UvExe -PathType Leaf)) {
        if (Test-Path -LiteralPath $PythonInstallDir) {
            Write-Caution 'uv.exe neni dostupne; soubory Pythonu budou odebrany s instalacnim adresarem, ale historickou externi registraci instalace 1.2.x nelze automaticky proverit.'
        }
        return
    }

    $oldPythonDir = $env:UV_PYTHON_INSTALL_DIR
    $oldCacheDir = $env:UV_CACHE_DIR
    try {
        $env:UV_PYTHON_INSTALL_DIR = $PythonInstallDir
        $env:UV_CACHE_DIR = $UvCacheDir
        $result = Invoke-NativeCommandCapture -Executable $UvExe -Arguments @(
            'python', 'uninstall', '--no-config', '--all', '--install-dir', $PythonInstallDir
        )

        if ($result.ExitCode -ne 0) {
            if (-not (Test-Path -LiteralPath $PythonInstallDir)) {
                Write-Notice "uv nenaslo aktivni spravovanou instalaci Pythonu; lokalni adresar uz neexistuje. Detail: $($result.Output)"
                return
            }
            throw "uv nedokazalo odebrat spravovanou instalaci Pythonu (exit code $($result.ExitCode)): $($result.Output)"
        }
        Write-Ok 'Spravovana instalace Pythonu a jeji uv registrace byly odebrany.'
    }
    finally {
        $env:UV_PYTHON_INSTALL_DIR = $oldPythonDir
        $env:UV_CACHE_DIR = $oldCacheDir
    }
}

function Protect-PreservedDataDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)
    $icaclsExe = "$env:SystemRoot\System32\icacls.exe"
    $result = Invoke-NativeCommandCapture -Executable $icaclsExe -Arguments @(
        $Path,
        '/inheritance:r',
        '/grant:r',
        '*S-1-5-18:(OI)(CI)F',
        '*S-1-5-32-544:(OI)(CI)F'
    )
    if ($result.ExitCode -ne 0) {
        throw "Nelze zabezpecit zachovana data v $Path`: $($result.Output)"
    }
}

function Preserve-DataForUninstall {
    $effectivePreserveData = [bool]$PreserveData
    $preservedPath = ''
    if ($null -ne $script:InstallerState) {
        Add-StatePropertyIfMissing -State $script:InstallerState -Name 'PreserveDataRequested' -DefaultValue $false
        $effectivePreserveData = [bool]$script:InstallerState.PreserveDataRequested
        if (-not [string]::IsNullOrWhiteSpace([string]$script:InstallerState.PreservedDataPath)) {
            $effectivePreserveData = $true
            $preservedPath = [string]$script:InstallerState.PreservedDataPath
        }
    }
    if (-not $effectivePreserveData) { return }

    if ([string]::IsNullOrWhiteSpace($preservedPath)) {
        $parent = Split-Path -Parent $InstallRoot
        $leaf = Split-Path -Leaf $InstallRoot
        $stamp = [DateTime]::Now.ToString('yyyyMMdd-HHmmss')
        $preservedPath = Join-Path $parent "$leaf-preserved-$stamp"
        if ($null -ne $script:InstallerState) {
            # Write-ahead: opakovane --uninstall pouzije stejny cil.
            $script:InstallerState.PreservedDataPath = $preservedPath
            Write-InstallerState
        }
    }

    Ensure-Directory $preservedPath
    Protect-PreservedDataDirectory -Path $preservedPath
    foreach ($item in @(
        [pscustomobject]@{ Source=$DataDir; Name='data' },
        [pscustomobject]@{ Source=$BackupDir; Name='backups' }
    )) {
        if (-not (Test-Path -LiteralPath $item.Source)) { continue }
        $destination = Join-Path $preservedPath $item.Name
        if (Test-Path -LiteralPath $destination) {
            # Zdroj stale existuje, takze predchozi kopie byla jen castecna.
            Remove-ManagedPathWithRetry -Path $destination
        }
        Copy-Item -LiteralPath $item.Source -Destination $destination -Recurse -Force
        if (-not (Test-Path -LiteralPath $destination)) {
            throw "Zachovani $($item.Source) do $destination se nepodarilo overit."
        }
        Remove-ManagedPathWithRetry -Path $item.Source
    }
    Write-Ok "Uzivatelska data byla pred odinstalaci presunuta do $preservedPath."
}

function Remove-ManagedInstallationFiles {
    $originalNames = @()
    $adoptedLegacy = $false
    if ($null -ne $script:InstallerState) {
        $originalNames = @($script:InstallerState.RootChildrenBeforeInstaller)
        $adoptedLegacy = [bool]$script:InstallerState.AdoptedLegacyInstallation
    }

    foreach ($name in @($ManagedTopLevelNames | Where-Object { $_ -ne '.installer' })) {
        if (-not $adoptedLegacy -and $originalNames -contains $name) {
            Write-Caution "Puvodni polozka '$name' existovala pred instalaci a nebude automaticky odstranena."
            continue
        }
        $path = Join-Path $InstallRoot $name
        if (Test-Path -LiteralPath $path) {
            Remove-ManagedPathWithRetry -Path $path
        }
    }

    $remainingManaged = [Collections.Generic.List[string]]::new()
    foreach ($name in @($ManagedTopLevelNames | Where-Object { $_ -ne '.installer' })) {
        if (-not $adoptedLegacy -and $originalNames -contains $name) { continue }
        if (Test-Path -LiteralPath (Join-Path $InstallRoot $name)) { [void]$remainingManaged.Add($name) }
    }
    if ($remainingManaged.Count -gt 0) {
        throw "Nektere spravovane cesty zustaly po odinstalaci: $($remainingManaged.ToArray() -join ', ')"
    }
}

function Assert-UninstallExternalState {
    $remainingProcesses = @(Get-ManagedProcesses)
    if ($remainingProcesses.Count -gt 0) {
        throw "Po odinstalaci stale bezi spravovane procesy: $(@($remainingProcesses | ForEach-Object { $_.ProcessId }) -join ', ')"
    }

    foreach ($taskName in @(Get-DeploymentTaskNames)) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($null -ne $task -and (Test-ScheduledTaskBelongsToDeployment -Task $task)) {
            throw "Po odinstalaci stale existuje spravovana uloha '$taskName'."
        }
    }

    if ($null -ne $script:InstallerState) {
        foreach ($name in @($script:InstallerState.FirewallRuleNames)) {
            if ([string]::IsNullOrWhiteSpace([string]$name)) { continue }
            $remainingRule = Get-NetFirewallRule -Name ([string]$name) -ErrorAction SilentlyContinue
            if ($null -ne $remainingRule -and (Test-FirewallRuleBelongsToDeployment -Rule $remainingRule)) {
                throw "Po odinstalaci stale existuje firewall pravidlo teto instalace '$name'."
            }
        }

        if ([bool]$script:InstallerState.AdoptedLegacyInstallation) {
            foreach ($definition in @(
                [pscustomobject]@{ Display="$FirewallRulePrefix HTTPS TCP"; Protocol='TCP'; Port=$HttpsPort },
                [pscustomobject]@{ Display="$FirewallRulePrefix HTTP redirect TCP"; Protocol='TCP'; Port=$HttpPort },
                [pscustomobject]@{ Display="$FirewallRulePrefix HTTP3 UDP"; Protocol='UDP'; Port=$HttpsPort }
            )) {
                foreach ($rule in @(Get-NetFirewallRule -DisplayName $definition.Display -ErrorAction SilentlyContinue)) {
                    if ((Test-FirewallRuleBelongsToDeployment -Rule $rule -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port) -or
                        (Test-FirewallRuleBelongsToDeployment -Rule $rule) -or
                        (Test-LegacyFirewallRuleBelongsToDeployment -Rule $rule -ExpectedDisplayName $definition.Display -ExpectedProtocol $definition.Protocol -ExpectedPort $definition.Port)) {
                        throw "Po odinstalaci stale existuje firewall pravidlo prevzate starsi instalaci '$($rule.Name)'."
                    }
                }
            }
        }

        $originalNames = @($script:InstallerState.RootChildrenBeforeInstaller)
        $adoptedLegacy = [bool]$script:InstallerState.AdoptedLegacyInstallation
        foreach ($managedName in @($ManagedTopLevelNames | Where-Object { $_ -ne '.installer' })) {
            if (-not $adoptedLegacy -and $originalNames -contains $managedName) { continue }
            if (Test-Path -LiteralPath (Join-Path $InstallRoot $managedName)) {
                throw "Po odinstalaci stale existuje spravovana cesta '$managedName'."
            }
        }
    }

    foreach ($thumbprint in @(Get-TrackedCertificatesForRemoval)) {
        if (Test-Path -LiteralPath "Cert:\LocalMachine\Root\$thumbprint") {
            throw "Po odinstalaci stale existuje korenovy certifikat $thumbprint."
        }
    }
}

function Finalize-UninstallFilesystem {
    $rootExistedBeforeInstaller = $false
    $rootOriginalSddl = ''
    $adoptedLegacy = $false
    $preservedPath = ''
    if ($null -ne $script:InstallerState) {
        $rootExistedBeforeInstaller = [bool]$script:InstallerState.RootExistedBeforeInstaller
        $rootOriginalSddl = [string]$script:InstallerState.RootOriginalSddl
        $adoptedLegacy = [bool]$script:InstallerState.AdoptedLegacyInstallation
        $preservedPath = [string]$script:InstallerState.PreservedDataPath
        $script:InstallerState.Status = 'UninstallReadyToFinalize'
        $script:InstallerState.CurrentPhase = 'uninstall-finalize-filesystem'
        $script:InstallerState.LastError = ''
        Write-InstallerState
        Write-UninstallRecoveryState
    }

    $leaveOriginalRoot = $rootExistedBeforeInstaller -and -not $adoptedLegacy

    if (Test-Path -LiteralPath $InstallerStateDir) {
        Remove-ManagedPathWithRetry -Path $InstallerStateDir
    }
    if ($leaveOriginalRoot) {
        Restore-OriginalRootAcl -Sddl $rootOriginalSddl -ThrowOnFailure
    }

    if (Test-Path -LiteralPath $InstallRoot -PathType Container) {
        $remaining = @(Get-ChildItem -LiteralPath $InstallRoot -Force -ErrorAction SilentlyContinue)
        if ($leaveOriginalRoot) {
            Write-Ok "Spravovany obsah byl odebran a puvodni adresar $InstallRoot byl ponechan s puvodnim ACL."
            if ($remaining.Count -gt 0) {
                Write-Notice "V puvodnim adresari zustaly nespravovane polozky: $(@($remaining | ForEach-Object { $_.Name }) -join ', ')"
            }
        }
        elseif ($remaining.Count -eq 0) {
            # Pri selhani zustava stavovy objekt v pameti. Vnejsi catch znovu
            # vytvori .installer\state.json, takze dalsi --uninstall muze navazat.
            Remove-ManagedPathWithRetry -Path $InstallRoot
            Write-Ok "Instalacni adresar $InstallRoot byl odebran."
        }
        else {
            Write-Caution "Adresar $InstallRoot nebyl odstranen, protoze obsahuje nespravovane polozky: $(@($remaining | ForEach-Object { $_.Name }) -join ', ')"
        }
    }

    # Externi checkpoint se odstrani az jako posledni spravovany artefakt.
    # Pokud zde dojde k vypadku, dalsi --uninstall jej znovu nacte a overi stav.
    if (Test-Path -LiteralPath $UninstallRecoveryStatePath) {
        Remove-ManagedPathWithRetry -Path $UninstallRecoveryStatePath
    }
    $recoveryTemporaryPath = "$UninstallRecoveryStatePath.tmp"
    if (Test-Path -LiteralPath $recoveryTemporaryPath) {
        Remove-ManagedPathWithRetry -Path $recoveryTemporaryPath
    }
    $recoveryParent = Split-Path -Parent $UninstallRecoveryStatePath
    $recoveryLeaf = Split-Path -Leaf $UninstallRecoveryStatePath
    if (Test-Path -LiteralPath $recoveryParent -PathType Container) {
        foreach ($staleRecovery in @(Get-ChildItem -LiteralPath $recoveryParent -Force -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name.StartsWith("$recoveryLeaf.corrupt-", [StringComparison]::OrdinalIgnoreCase) })) {
            Remove-ManagedPathWithRetry -Path $staleRecovery.FullName
        }
    }

    # Stav je zrusen az po uspesnem dokonceni nebo po zamerne ponechanem
    # puvodnim/nespravovanem adresari. Do te doby musi byt odinstalace obnovitelna.
    $script:InstallerState = $null

    Write-Host "`n============================================================" -ForegroundColor Green
    Write-Host 'ODINSTALACE DOKONCENA' -ForegroundColor Green
    Write-Host 'Byly odebrany spravovane ulohy, procesy, firewall pravidla, serverova duvera CA a programove soubory.'
    if (-not [string]::IsNullOrWhiteSpace($preservedPath)) {
        Write-Host "Zachovana data: $preservedPath" -ForegroundColor Yellow
    }
    Write-Host '============================================================' -ForegroundColor Green
    Write-Caution 'Koren lokalni CA nainstalovany na vzdalenych klientech nebo pres GPO je nutne z techto klientu/GPO odebrat samostatne; server nema opravneni menit jejich uloziste.'
}

function Uninstall-Deployment {
    Write-Step 'Odinstalovavam e-INFRA Open WebUI a vracim lokalni zmeny instalatoru'

    if (-not (Initialize-UninstallState)) {
        Write-Notice "V $InstallRoot nebyla nalezena spravovana instalace; neni co odinstalovat."
        return
    }
    Import-RuntimePortsForUninstall

    Invoke-UninstallPhase -Name 'uninstall-stop-processes' -Operation {
        foreach ($taskName in @(Get-DeploymentTaskNames)) {
            Stop-ManagedScheduledTask -TaskName $taskName
        }
        Start-Sleep -Seconds 1
        Stop-ManagedProcesses -RequireStopped
    }

    Invoke-UninstallPhase -Name 'uninstall-remove-tasks' -Operation {
        Remove-DeploymentTasks
    }

    Invoke-UninstallPhase -Name 'uninstall-remove-firewall' -Operation {
        Remove-FirewallRules
    }

    Invoke-UninstallPhase -Name 'uninstall-remove-certificates' -Operation {
        Remove-TrackedRootCertificates
    }

    Invoke-UninstallPhase -Name 'uninstall-remove-python-registration' -Operation {
        Remove-ManagedPythonInstallationForUninstall
    }

    Invoke-UninstallPhase -Name 'uninstall-preserve-data' -Operation {
        Preserve-DataForUninstall
    }

    Invoke-UninstallPhase -Name 'uninstall-remove-managed-files' -Operation {
        Remove-ManagedInstallationFiles
    }

    Invoke-UninstallPhase -Name 'uninstall-verify-external-state' -Operation {
        Assert-UninstallExternalState
    }

    Finalize-UninstallFilesystem
}

if ($ShowVersionRequested) {
    Write-Host "E-INFRA Open WebUI installer $ScriptVersion"
    exit 0
}

if ($ShowHelpRequested) {
    Show-Usage
    exit 0
}

$exitCode = 0
try {
    Assert-WindowsAndAdministrator
    Acquire-InstallerMutex

    switch ($Action) {
        'Install' {
            Initialize-InstallerState
            $existingDeployment =
                (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf) -or
                (Test-Path -LiteralPath $OpenWebUIExe -PathType Leaf)
            if ($ResumeRequested -or $existingDeployment) {
                # Existujici instalace se prevezme i pri prostem spusteni bez
                # --resume, aby automaticka aktualizace nikdy neprepsala API klic
                # nebo jinou tajnou hodnotu vychozim placeholderem.
                Import-ExistingConfigurationForResume
                Import-ResumeConfiguration
                if ($ResumeRequested) {
                    Write-Notice "Navazuji na fazi '$($script:InstallerState.CurrentPhase)'. Bezpecne idempotentni faze budou znovu overeny."
                }
                else {
                    Write-Notice 'Byla rozpoznana existujici instalace; konfigurace a tajne hodnoty byly bezpecne prevzaty pred kontrolou aktualizaci.'
                }
            }
            Apply-RequestedConfigurationProfile
            Write-ResumeConfiguration
            Install-Deployment
            Set-InstallerCompleted
        }
        'Update' {
            Initialize-InstallerState
            Import-ExistingConfigurationForResume
            Import-ResumeConfiguration
            Apply-RequestedConfigurationProfile
            Write-ResumeConfiguration
            Update-Deployment
            Set-InstallerCompleted
        }
        'Start' {
            $configuration = Read-RuntimeConfig
            $script:BackendPort = [int]$configuration.BackendPort
            $script:HttpsPort = [int]$configuration.HttpsPort
            $script:HttpPort = [int]$configuration.HttpPort
            Start-Deployment
            Show-Status
        }
        'Stop' {
            Stop-Deployment
            Write-Ok 'Open WebUI a Caddy byly zastaveny.'
        }
        'Restart' {
            $configuration = Read-RuntimeConfig
            $script:BackendPort = [int]$configuration.BackendPort
            $script:HttpsPort = [int]$configuration.HttpsPort
            $script:HttpPort = [int]$configuration.HttpPort
            Stop-Deployment
            Start-Deployment
            Show-Status
        }
        'Status' {
            Show-Status
        }
        'Uninstall' {
            try { $script:InstallerState = Read-UninstallState }
            catch {
                if (-not $script:InstallerStateCanQuarantine) { throw }
                $sourcePath = [string]$script:InstallerStateSourcePath
                if ([string]::IsNullOrWhiteSpace($sourcePath)) { $sourcePath = $InstallerStatePath }
                $corruptStatePath = "$sourcePath.corrupt-$([DateTime]::Now.ToString('yyyyMMdd-HHmmss'))"
                try {
                    if (Test-Path -LiteralPath $sourcePath -PathType Leaf) {
                        Move-Item -LiteralPath $sourcePath -Destination $corruptStatePath -Force
                        Write-Caution "Poskozeny stavovy soubor byl docasne odlozen jako $corruptStatePath. Odinstalace zkusi druhy checkpoint nebo vytvori novy stav podle jednoznacnych artefaktu."
                    }
                    $script:InstallerState = Read-UninstallState
                }
                catch {
                    throw "Stavovy soubor je poskozeny a nelze jej bezpecne odlozit nebo nahradit: $($_.Exception.Message)"
                }
            }
            Uninstall-Deployment
        }
    }
}
catch {
    $exitCode = 1
    $caughtError = $_
    $rollbackFailure = ''
    $rollbackSucceeded = $false

    if ($Action -in @('Install', 'Update') -and
        (Test-Path -LiteralPath $OpenWebUIUpdateTransactionPath -PathType Leaf)) {
        try {
            [void](Rollback-PendingOpenWebUIUpdate -RestartPreviousDeployment)
            $rollbackSucceeded = $true
        }
        catch {
            $rollbackFailure = $_.Exception.Message
        }
    }

    if ($Action -in @('Install', 'Update')) { Set-InstallerFailed -ErrorRecord $caughtError }
    elseif ($Action -eq 'Uninstall' -and $null -ne $script:InstallerState) {
        try {
            $script:InstallerState.Status = 'UninstallInterrupted'
            if ([string]::IsNullOrWhiteSpace([string]$script:InstallerState.CurrentPhase)) {
                $script:InstallerState.CurrentPhase = 'uninstall'
            }
            $script:InstallerState.LastError = [string]$caughtError.Exception.Message
            Write-InstallerState
        }
        catch { }
    }

    Write-Host "`nCHYBA: $($caughtError.Exception.Message)" -ForegroundColor Red
    Write-Host "Radek: $($caughtError.InvocationInfo.ScriptLineNumber)" -ForegroundColor DarkRed
    if (-not [string]::IsNullOrWhiteSpace($rollbackFailure)) {
        Write-Host "ROLLBACK SELHAL: $rollbackFailure" -ForegroundColor Red
        Write-Host "Nemente data ani venv rucne; znovu spustte --resume, ktery transakci zkontroluje." -ForegroundColor Yellow
    }
    elseif ($Action -in @('Install', 'Update')) {
        if ($rollbackSucceeded) {
            Write-Host 'Aktualizace selhala, ale puvodni Open WebUI a data byly uspesne obnoveny a sluzba znovu spustena.' -ForegroundColor Yellow
        }
        else {
            Write-Host 'Pokud aktualizace zasahla Open WebUI, puvodni venv a data byly automaticky obnoveny.' -ForegroundColor Yellow
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($script:CurrentPhase)) {
        Write-Host "Faze: $script:CurrentPhase" -ForegroundColor DarkYellow
    }
    Write-Host "Logy (pokud existuji): $LogDir" -ForegroundColor DarkYellow
    if ($Action -in @('Install', 'Update')) {
        Write-Host "Pokracovani: powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" --resume" -ForegroundColor Yellow
    }
    Write-Host "Odinstalace: powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" --uninstall" -ForegroundColor Yellow
}
finally {
    Release-InstallerMutex
}

exit $exitCode
