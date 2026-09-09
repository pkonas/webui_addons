# VUT AI Tutor – e-INFRA Windows Server Adapter 2.1.5

**Adaptér:** 2.1.5  
**Universal Engine:** 2.0.2  
**Neměněný Tutor runtime:** 1.26.2

Tato kompletní sada je určena pro Open WebUI instalované skriptem
`Install-EInfraOpenWebUI-v2.4.5.ps1`. Autoritativní konfigurace je
`%ProgramData%\EInfra-OpenWebUI\config\runtime.json`, interní backend je
standardně `127.0.0.1:18080` a veřejné HTTPS zajišťuje Caddy.

## Oprava v 2.1.5 – segmentace jednotlivých běhů backendového logu

Self-test 2.1.4 používal platnou syntetickou hlavičku:

```text
--- new start: open-webui.exe serve --port 18080 ---
```

Regulární výraz však vyžadoval alespoň jeden další znak nebo část cesty před
`open-webui.exe`. Proto holý název executable nerozpoznal, ponechal v řezu i
chybu z předchozího běhu a `Log segmentation self-test` skončil chybou.

Verze 2.1.5 zavádí jedinou funkci `Test-BackendRunStartLine` a sdílený pattern,
který přijímá:

- holý `open-webui.exe` i `open-webui`;
- úplnou nequoted cestu;
- úplnou cestu v uvozovkách, včetně mezer;
- pouze příkaz `serve`, nikoli jiný executable nebo subcommand.

Segmentace vždy vybírá poslední rozpoznaný běh. Při omezení počtu řádků zachová
hlavičku posledního běhu a nejnovější část jeho tailu. Starší Tutor traceback
se proto nemůže zaměnit za chybu nového startu.

## Zachované opravy

Sada zachovává bezpečné zpracování nullable Task Scheduler hodnot, file-based
Python probe bez `python -c`, úplný vlastnicky omezený restart backendu,
selektivní SQLite recovery pouze známých Tutor Functions, Universal Engine
2.0.2 a bajtově nezměněný Tutor runtime 1.26.2.

## Doporučený postup na serveru Pelton

### 1. Offline test

```powershell
.\test-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1 `
  -PythonPath 'C:\Python314\python.exe' `
  -InstallRoot 'C:\ProgramData\EInfra-OpenWebUI'
```

Test nemění databázi, Functions ani stav plánovaných úloh. Rozhodující nové
řádky jsou:

```text
[PASS] backend log segmentation contract
[PASS] Adapter self-test: vlastnictvi procesu, ochrana Caddy/manageru a izolace posledniho behu logu.
[PASS] Self-test kompletni e-INFRA sady prosel.
```

### 2. Oprava Tutoru

```powershell
.\install-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1 `
  -Action Repair `
  -InstallRoot 'C:\ProgramData\EInfra-OpenWebUI' `
  -TokenFile 'C:\Users\admin\Documents\AI\openwebui-apikey.txt' `
  -PythonPath 'C:\Python314\python.exe' `
  -RestartPolicy OnFailure `
  -TutorStartupRecovery Auto `
  -PublicVerification BestEffort `
  -StartupTimeout 300 `
  -RouteTimeout 180 `
  -ReportPath '.\vut-ai-tutor-einfra-install.json'
```

### 3. Verifikace

```powershell
.\verify-vut-ai-tutor-einfra-windows-server-v2.1.5.ps1 `
  -InstallRoot 'C:\ProgramData\EInfra-OpenWebUI' `
  -TokenFile 'C:\Users\admin\Documents\AI\openwebui-apikey.txt' `
  -PythonPath 'C:\Python314\python.exe' `
  -PublicVerification Required `
  -RouteTimeout 180 `
  -ReportPath '.\vut-ai-tutor-einfra-verify.json'
```

## Diagnostika

Read-only collector:

```powershell
.\collect-vut-ai-tutor-einfra-diagnostics-v2.1.5.ps1 `
  -InstallRoot 'C:\ProgramData\EInfra-OpenWebUI' `
  -OutputPath '.\vut-ai-tutor-einfra-diagnostics.json'
```
