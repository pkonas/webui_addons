# VUT AI Tutor Universal Installer 2.3.3

Tutor runtime **1.26.4**, API engine **2.0.5**, e-INFRA adaptér **2.1.7**.

Úplný nástupce balíku **2.3.2 / runtime 1.26.3**, včetně dřívější opravy přenosu PDF a všech původních platforem. Jde o úpravu dodaného instalátoru, nikoli oficiální vydání Open WebUI nebo PDF.js. PDF.js zůstává **6.2.108** a databázové schéma Tutora **14**.

## Oprava chybějícího originálu a opakovaného nahrání

Runtime 1.26.3 dokázal oznámit `file_path_missing` místo původního HTTP 500, ale při opětovném nahrání totožných bajtů mohl deduplikací vybrat původní nefunkční záznam. Nová kopie přitom existovala pod jiným UUID. Verze 1.26.4 odděluje stabilní identitu studia od dostupné kopie originálu:

- Pokud původní záznam nemá dostupný soubor, hledá se **pouze kopie stejného vlastníka**. Musí existovat původní raw SHA-256 reference a hash skutečných bajtů kandidáta musí souhlasit. Název knihy, hash extrahovaného textu ani starý odkaz na kanonickou knihu nejsou důkazem shodných PDF.
- Ověřená kopie může být použita pro čtení i indexaci pod původním ID. Při tomto dohledání se nepřepisují Open WebUI cesty ani nepřesouvají relace, výběry, aktivity, mastery a studijní cesty. Deduplikace již automaticky neznamená úspěšně dokončenou indexaci.
- Pokud původní raw identita chybí, automatická záměna se odmítne. Nové nahrání nezachytí neověřený historický hash: vznikne použitelná nová kniha, původní studijní záznam zůstane uložen. Historické nesprávné sloučení nelze bez dalších podkladů automaticky rozdělit.

Běžný originál a dosavadní přesné UUID dohledání mají přednost. Oprava neobchází chyby oprávnění, nejednoznačné původní cesty ani selhání poskytovatele úložiště. Pro S3/GCS/Azure se používá příslušný Storage provider, ne globální prohledávání disku. Opakovaná indexace nedostupného zdroje má prodlevu 300 sekund; explicitní nové nahrání může zkusit obnovu ihned. Diagnostika čtečky ukazuje stav obnovy a další postup.

## Aktualizace stávajícího Desktopu

ZIP rozbalte **do nové samostatné složky**. Zachovejte celou adresářovou strukturu: i e-INFRA a Desktop adaptéry mají vlastní komprimované payloady. Nekopírujte jednotlivý nový runtime do starého instalátoru. Uložte práci; adaptér může Desktop při aktualizaci restartovat.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\install-vut-ai-tutor-universal-v2.3.3.ps1 `
  -Action Repair `
  -Platform Desktop `
  -PromptForCredential `
  -ReportPath .\vut-ai-tutor-install-v2.3.3.json
```

Vlastní `DesktopInstallRoot`, `DesktopDataRoot`, `DesktopConfigRoot` a `PythonPath` přidejte se stejnými hodnotami jako při poslední úspěšné instalaci. Běžný `Repair` nadále používá **TutorOnly**, nikoli přeinstalaci Open WebUI nebo opravu jeho hlavní databáze. `BackendRecovery` a `DesktopDatabaseRepair` zůstávají oddělenými explicitními akcemi.

Po aktualizaci zavřete starý panel Tutora a otevřete nový. Nejprve otevřete původní knihu. Když není dostupná ověřitelná kopie, nahrajte **totožný původní PDF soubor přímo v Tutoru**. Původní knihu ani studijní historii nemažte. Při `original_raw_hash_missing` se nový upload otevře jako nová kniha, bez automatického připojení staré historie. PDF není potřeba tisknout, převádět nebo zbavovat obrázků.

Instalátor kontroluje SHA-256 manifest. Záloha `vut-pdf-hotfix-functions-before-*.json` může obsahovat citlivé nastavení Functions; uchovejte ji soukromě. Desktop manager zálohu vytváří, ale automatický rollback nemá; transakční rollback API enginu a e-INFRA zůstává zachován.

Podrobné zdůvodnění a meze: `docs/PDF-SOURCE-RECOVERY-v2.3.3.md`. Výsledky ověření: `TEST-RESULTS.md`. Staré protokoly 2.3.2 jsou výslovně historické v `docs/history/v2.3.2/`.

## Podporované varianty

| Platforma | Windows PowerShell | Linux/macOS Bash/Python | Instalační větev |
|---|---:|---:|---|
| Open WebUI Desktop pro Windows | ano | ne | zachovaný Desktop lifecycle + Tutor runtime 1.26.4 |
| e-INFRA Windows Server | ano | vzdáleně přes `Remote` | specializovaný adaptér 2.1.7 |
| Docker / Podman | ano | ano | API engine 2.0.5 |
| Obecný bare-metal | ano | ano | API engine 2.0.5 |
| Vzdálené webové rozhraní | ano | ano | API engine 2.0.5 |

Alias `Server` záměrně neexistuje, protože nerozlišuje e-INFRA Scheduled Tasks, obecnou službu, Docker a vzdálené API. Použijte jednoznačnou platformu.

## Co bylo opraveno proti 2.2.0

- Generic API větev již nepoužívá Engine 2.0.1; všechny API platformy používají Engine 2.0.5 s opraveným health kontraktem `asgi-prefix-gateway-v7`.
- Přidány jsou nativní Bash a Python vstupy pro Linux a macOS.
- Desktop `Repair` používá bezpečný režim `TutorOnly`; oprava databáze je dostupná pouze explicitní akcí `DesktopDatabaseRepair`.
- Neexistuje zavádějící platforma `Server`.
- Součástí vydání jsou E2E testy `Install → Verify → Uninstall` pro Remote, Docker a BareMetal, rollback po vynucené chybě, Docker port discovery, start zastaveného kontejneru a reverse-proxy prefix.
- Neznámá budoucí verze Open WebUI projde pouze tehdy, když skutečně splní Functions API, health, Canvas a CORS kontrakt; test obsahuje syntetickou verzi 0.12.7.
- Distribuce je jediný archiv; neexistuje paralelní self-contained balíček se stejným číslem verze a jiným obsahem.
- Desktop `Verify` nyní při chybějícím lokálním backendu spustí oficiální Electron aplikaci stejně jako instalace; `-NoAutoStartDesktop` zachovává striktně read-only procesní režim.
- Verifikátor spouští kořenový dispatcher v novém PowerShell procesu s `ExecutionPolicy Bypass` pouze pro přesný soubor uvnitř již zvoleného balíčku, takže nevzniká druhý Mark-of-the-Web dialog.

## Windows: odblokování a bezpečný test

```powershell
Get-ChildItem -LiteralPath . -Recurse -File | Unblock-File

.\test-vut-ai-tutor-universal-v2.3.3-windows.ps1 `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe'
```

Test nemění produkční Functions, databázi ani procesy Open WebUI. Používá izolovaný mock server.

## Linux/macOS: bezpečný test

```bash
chmod +x ./*.sh ./*.py tests/*.py
PYTHON_BIN=python3 bash ./test-vut-ai-tutor-universal-v2.3.3.sh
```

## Detekce bez změn

Windows:

```powershell
.\install-vut-ai-tutor-universal-v2.3.3.ps1 -Action Detect
```

Linux/macOS:

```bash
bash ./install-vut-ai-tutor-universal-v2.3.3.sh --action detect
```

Při současné přítomnosti Desktopu a e-INFRA serveru automatická detekce skončí bez změny a vyžádá explicitní platformu.

## Open WebUI Desktop pro Windows

Tato platforma označuje oficiální aplikaci `open-webui/desktop`. Konfigurace se čte z Electron `userData` (`%APPDATA%\open-webui` a kompatibilní názvy), `installDir` určuje vestavěný Python a `dataDir` při prázdné hodnotě přechází na `<installDir>\data`. Skutečný port se ověřuje podle aktuálního logu, živých loopback listenerů a `/api/version`; pevný port 8080 se nepovažuje za jedinou možnou adresu. Podrobný kontrakt je v `docs/OFFICIAL-DESKTOP-CONTRACT.md`.

Při `Repair` i `Verify` se nejprve hledá již běžící backend. Není-li dostupný, spustí se oficiální Electron executable, instalátor znovu načítá aktuální URL z logu a kontroluje omezený rozsah `localServer.port` až `port+100`. Pro kontrolu, která nesmí spustit žádný proces, přidejte `-NoAutoStartDesktop`; backend pak musí již běžet. Pokud Desktop používá jako výchozí vzdálenou connection, instalátor tuto volbu nemění a v reportu vysvětlí, proč lokální backend nenaběhl.

```powershell
.\install-vut-ai-tutor-universal-v2.3.3.ps1 `
  -Action Repair `
  -Platform Desktop `
  -DesktopInstallRoot 'D:\web-ui' `
  -PromptForCredential `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe' `
  -StartupTimeout 300 `
  -RouteTimeout 180 `
  -ReportPath '.\vut-ai-tutor-desktop-install.json'
```

Verifikace, která v případě potřeby sama spustí oficiální Desktop:

```powershell
.\verify-vut-ai-tutor-universal-v2.3.3.ps1 `
  -Platform Desktop `
  -DesktopInstallRoot 'D:\web-ui' `
  -PromptForCredential `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe' `
  -StartupTimeout 300 `
  -ReportPath '.\vut-ai-tutor-desktop-verify.json'
```

Databázová oprava je záměrně oddělená:

```powershell
.\install-vut-ai-tutor-universal-v2.3.3.ps1 `
  -Action DesktopDatabaseRepair `
  -Platform Desktop `
  -DesktopInstallRoot 'D:\web-ui' `
  -StopDesktopProcesses `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe'
```

## e-INFRA Windows Server

```powershell
.\install-vut-ai-tutor-universal-v2.3.3.ps1 `
  -Action Repair `
  -Platform EInfraWindows `
  -InstallRoot 'C:\ProgramData\EInfra-OpenWebUI' `
  -TokenFile 'C:\Users\admin\Documents\AI\openwebui-apikey.txt' `
  -PythonPath 'C:\Python314\python.exe' `
  -RestartPolicy OnFailure `
  -PublicVerification BestEffort `
  -ReportPath '.\vut-ai-tutor-einfra-install.json'
```

## Docker / Podman

Windows:

```powershell
.\install-vut-ai-tutor-universal-v2.3.3.ps1 `
  -Action Repair `
  -Platform Docker `
  -ContainerName 'open-webui' `
  -TokenFile '.\openwebui-admin-token.txt' `
  -PythonPath 'C:\Python312\python.exe'
```

Linux/macOS:

```bash
bash ./install-vut-ai-tutor-universal-v2.3.3.sh \
  --action repair \
  --platform docker \
  --container-name open-webui \
  --token-file ./openwebui-admin-token.txt
```

Zastavený explicitně vybraný kontejner může instalátor spustit. Není-li port kontejneru publikovaný na hostu, zadejte také `--base-url` / `-BaseUrl` dosažitelného Open WebUI endpointu.

## Obecný bare-metal

Linux se systemd:

```bash
bash ./install-vut-ai-tutor-universal-v2.3.3.sh \
  --action repair \
  --platform baremetal \
  --base-url http://127.0.0.1:8080 \
  --service-name open-webui \
  --restart-policy on-failure \
  --token-file ./openwebui-admin-token.txt
```

Vlastní správce služby:

```bash
bash ./install-vut-ai-tutor-universal-v2.3.3.sh \
  --action repair \
  --platform baremetal \
  --base-url http://127.0.0.1:8080 \
  --restart-command 'supervisorctl restart open-webui' \
  --token-file ./openwebui-admin-token.txt
```

## Vzdálené webové rozhraní a reverse-proxy prefix

```bash
bash ./install-vut-ai-tutor-universal-v2.3.3.sh \
  --action repair \
  --platform remote \
  --base-url https://portal.example.edu/openwebui \
  --token-file ./openwebui-admin-token.txt \
  --ca-certificate ./organization-root-ca.pem
```

Cestový prefix `/openwebui` se zachová pro API, Canvas i health endpointy.

## Přihlašování

Doporučen je token uložený v jednorázkovém souboru s omezenými oprávněními. Interaktivní přihlášení:

PowerShell:

```powershell
-PromptForCredential
```

Bash/Python:

```bash
--prompt-for-credential
```

Heslo se nevkládá do příkazového řádku ani do reportu.

## Verifikace

Windows:

```powershell
.\verify-vut-ai-tutor-universal-v2.3.3.ps1 `
  -Platform Remote `
  -BaseUrl 'https://webui.example.edu' `
  -TokenFile '.\openwebui-admin-token.txt' `
  -PythonPath 'C:\Python312\python.exe'
```

Linux/macOS:

```bash
bash ./verify-vut-ai-tutor-universal-v2.3.3.sh \
  --platform remote \
  --base-url https://webui.example.edu \
  --token-file ./openwebui-admin-token.txt
```

Za úspěch se považuje pouze současně:

- aktivní `study_tutor_gateway_bootstrap` typu `event`;
- aktivní `study_tutor_pipe` typu `pipe`;
- přesná shoda zdrojových hashů;
- JSON z `/study-tutor/health` s runtime 1.26.4;
- strategie `asgi-prefix-gateway-v7`;
- `gateway_active=true`, `main_router_mutated=false`;
- skutečné Tutor HTML z `/study-tutor/canvas`, nikoli SPA fallback;
- funkční CORS preflight pro `Origin: null`.

## Bezpečnost a aktualizace

Obecný API engine ani API část e-INFRA při instalaci nemění přímo databázi Open WebUI. Před změnou Functions vytvoří snapshot a při selhání provede rollback. Desktop `TutorOnly` používá svůj manager: ukládá zálohu Functions, ale automatický rollback zde není implementován. Neznámé budoucí vydání Open WebUI není přijato pouze podle čísla verze; rozhodují capability probes a závěrečný runtime acceptance test.

Podrobnosti jsou v `docs/ARCHITECTURE.md`, `docs/COMPATIBILITY.md`, `docs/SECURITY.md` a `docs/UPGRADE-RUNBOOK.md`.

## Ověření PDF opravy po instalaci

Použijte skutečnou adresu a port z instalačního reportu. Pro backend na portu 8080:

```powershell
$h = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/study-tutor/health'
$h.version
$h.pdf_delivery
```

Očekává se verze `1.26.4` a `pdf_delivery.revision` rovna `pdf-delivery-r2`.
`live_document_verified: false` je záměrné: health ani instalátor neověřuje
vykreslení konkrétní knihy. Zavřete starý panel Tutora, otevřete nový a načtěte
původní PDF. Při stále starém runtime aplikaci zcela ukončete a znovu spusťte.
U proxy nasazení zachovejte také prefix před `/study-tutor`.

PDF endpoint vyžaduje token studijní relace. Samostatný požadavek bez něj může
správně vrátit 401; administrátorský API token jej nenahrazuje. Chybějící PDF nelze vytvořit z pouhého extrahovaného textu. Obnovu čtení umožní pouze dostupná kopie s ověřenou bajtovou identitou. Při přetrvání chyby použijte nový kód a ID
chyby ze čtečky a odpovídající serverový traceback; nesdílejte tokeny ani zálohy.

## Rozšířené vývojové testy

Základní package testy používají pouze standardní knihovnu Pythonu a izolované mock
API. Volitelná PDF sada navíc potřebuje FastAPI, httpx, python-multipart a Node.js.
Testovací závislosti **neinstalujte do vestavěného Pythonu Desktopu**. Použijte
samostatné prostředí mimo adresář rozbaleného balíku; zaznamenané verze jsou
v `BUILD-TEST-REPORT.json` a v `tests/requirements-test.txt`.

```bash
VUT_RUN_PDF_TESTS=1 PYTHON_BIN=/cesta/k/test-venv/bin/python \
  bash ./test-vut-ai-tutor-universal-v2.3.3.sh
```

```powershell
.\test-vut-ai-tutor-universal-v2.3.3-windows.ps1 `
  -PythonPath 'C:\test-venv\Scripts\python.exe' `
  -IncludePdfTests
```

Výsledky skutečně provedených testů a hranice ověření: `TEST-RESULTS.md`.

## Opakování regresních testů s vlastním PDF

Do izolovaného testovacího prostředí lze doplnit `pypdf` a použít existující PDF:

```bash
VUT_CASE_PDF=/absolutni/cesta/k/souboru.pdf \
  python tests/test_pdf_source_recovery.py
```

Bez `VUT_CASE_PDF` se používá generovaný testovací PDF; jeden test skutečné extrakce se přeskočí. Soukromé PDF a původní aplikační logy nejsou součástí univerzálního balíku. Testy Files/Storage používají izolované náhrady Open WebUI API, ne přístup do skutečné uživatelské databáze.
