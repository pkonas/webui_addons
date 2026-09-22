# VUT AI Tutor Universal Installer 2.3.4

Tutor runtime **1.26.5**, API engine **2.0.6**, e-INFRA adaptér **2.1.8**.

Úplný nástupce balíku **2.3.3 / runtime 1.26.4**, včetně dřívější opravy přenosu PDF a všech původních platforem. Jde o úpravu dodaného instalátoru, nikoli oficiální vydání Open WebUI nebo PDF.js. PDF.js zůstává **6.2.108** a databázové schéma Tutora **14**.

## Oprava rozkmitání Canvasu při znovuotevření

Oprava `canvas-layout-r1` mění **parent-page bridge** v `StudyRuntime._canvas_open_panel_code`, nikoli PDF.js. Nativní panel Open WebUI nyní spravuje jeho vlastní layout. Tutor nepřepisuje šířku ani okraje chatu nebo composeru na základě rozměrů nativního iframe a nesleduje tyto prvky pro další přepis rozměrů.

Pouze náhradní pevný pravý dock rezervuje prostor na jednom známém kořenovém prvku chatu; používá vlastní explicitní šířku omezenou viewportem. Neznámá struktura dostane overlay bez spekulativní změny `<main>`. Změny se slučují do jednoho `requestAnimationFrame`, žádný trvalý 700ms layout polling nezůstává. Uzavřený dock odpojí vlastní resize target, zruší drag a obnoví jen vlastněné CSS vlastnosti. Pozdější příchod nativního panelu zavře náhradní dock. Nové otevření ruší starý pokus a jeho timeout, aby se starý dock neobjevil znovu.

Úplné HTML/CSS/JS uvnitř Canvasu, PDF.js **6.2.108**, PDF opravy **pdf-delivery-r2** a schéma **14** zůstávají zachovány. Detail opravy a omezení reprodukce: `docs/CANVAS-LAYOUT-FIX-v2.3.4.md`. Rozbalená skutečně vložená parent šablona: `docs/canvas-panel-bridge.js`.

Dřívější oprava chybějícího originálu, raw SHA-256 identity a opakovaného uploadu z runtime 1.26.4 zůstává zachována. Nemění se oprávnění, DLP, databázové cesty ani studijní historie; při chybějící raw identitě se nadále odmítá přiřazení podle pouhého názvu nebo textového hashe.

## Aktualizace stávajícího Desktopu

ZIP rozbalte **do nové samostatné složky**. Zachovejte celou adresářovou strukturu: i e-INFRA a Desktop adaptéry mají vlastní komprimované payloady. Nekopírujte jednotlivý nový runtime do starého instalátoru. Uložte práci; adaptér může Desktop při aktualizaci restartovat.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\install-vut-ai-tutor-universal-v2.3.4.ps1 `
  -Action Repair `
  -Platform Desktop `
  -PromptForCredential `
  -ReportPath .\vut-ai-tutor-install-v2.3.4.json
```

Vlastní `DesktopInstallRoot`, `DesktopDataRoot`, `DesktopConfigRoot` a `PythonPath` přidejte se stejnými hodnotami jako při poslední úspěšné instalaci. Běžný `Repair` nadále používá **TutorOnly**, nikoli přeinstalaci Open WebUI nebo opravu jeho hlavní databáze. `BackendRecovery` a `DesktopDatabaseRepair` zůstávají oddělenými explicitními akcemi.

**Po aktualizaci úplně ukončete Open WebUI Desktop, včetně běhu v oznamovací oblasti, a znovu jej spusťte.** Pouhé zavření iframe nestačí: starý parent-page JavaScript může v hlavním okně zůstávat aktivní. Ve webovém prohlížeči obnovte celé Open WebUI, ne pouze iframe Canvasu. Historii, knihy, PDF ani uložené uživatelské layouty není třeba mazat.

Potom otevřete Tutora, zavřete Canvas a několikrát jej znovu otevřete, také po změně šířky nativního dělicího panelu. Ověřte současně chat, vstupní pole a boční nástroje. Při přetrvání potíží je potřeba klientská diagnostika a přesný čas reprodukce, nikoli další převod PDF.

Instalátor kontroluje SHA-256 manifest. Záloha `vut-pdf-hotfix-functions-before-*.json` může obsahovat citlivé nastavení Functions; uchovejte ji soukromě. Desktop manager zálohu vytváří, ale automatický rollback nemá; transakční rollback API enginu a e-INFRA zůstává zachován.

Podrobné zdůvodnění a meze: `docs/PDF-SOURCE-RECOVERY-v2.3.3.md`. Výsledky ověření: `TEST-RESULTS.md`. Staré protokoly jsou historické v `docs/history/v2.3.2/` a `docs/history/v2.3.3/`.

## Podporované varianty

| Platforma | Windows PowerShell | Linux/macOS Bash/Python | Instalační větev |
|---|---:|---:|---|
| Open WebUI Desktop pro Windows | ano | ne | zachovaný Desktop lifecycle + Tutor runtime 1.26.5 |
| e-INFRA Windows Server | ano | vzdáleně přes `Remote` | specializovaný adaptér 2.1.8 |
| Docker / Podman | ano | ano | API engine 2.0.6 |
| Obecný bare-metal | ano | ano | API engine 2.0.6 |
| Vzdálené webové rozhraní | ano | ano | API engine 2.0.6 |

Alias `Server` záměrně neexistuje, protože nerozlišuje e-INFRA Scheduled Tasks, obecnou službu, Docker a vzdálené API. Použijte jednoznačnou platformu.

## Co bylo opraveno proti 2.2.0

- Generic API větev již nepoužívá Engine 2.0.1; všechny API platformy používají Engine 2.0.6 s opraveným health kontraktem `asgi-prefix-gateway-v7`.
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

.\test-vut-ai-tutor-universal-v2.3.4-windows.ps1 `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe'
```

Test nemění produkční Functions, databázi ani procesy Open WebUI. Používá izolovaný mock server.

## Linux/macOS: bezpečný test

```bash
chmod +x ./*.sh ./*.py tests/*.py
PYTHON_BIN=python3 bash ./test-vut-ai-tutor-universal-v2.3.4.sh
```

## Detekce bez změn

Windows:

```powershell
.\install-vut-ai-tutor-universal-v2.3.4.ps1 -Action Detect
```

Linux/macOS:

```bash
bash ./install-vut-ai-tutor-universal-v2.3.4.sh --action detect
```

Při současné přítomnosti Desktopu a e-INFRA serveru automatická detekce skončí bez změny a vyžádá explicitní platformu.

## Open WebUI Desktop pro Windows

Tato platforma označuje oficiální aplikaci `open-webui/desktop`. Konfigurace se čte z Electron `userData` (`%APPDATA%\open-webui` a kompatibilní názvy), `installDir` určuje vestavěný Python a `dataDir` při prázdné hodnotě přechází na `<installDir>\data`. Skutečný port se ověřuje podle aktuálního logu, živých loopback listenerů a `/api/version`; pevný port 8080 se nepovažuje za jedinou možnou adresu. Podrobný kontrakt je v `docs/OFFICIAL-DESKTOP-CONTRACT.md`.

Při `Repair` i `Verify` se nejprve hledá již běžící backend. Není-li dostupný, spustí se oficiální Electron executable, instalátor znovu načítá aktuální URL z logu a kontroluje omezený rozsah `localServer.port` až `port+100`. Pro kontrolu, která nesmí spustit žádný proces, přidejte `-NoAutoStartDesktop`; backend pak musí již běžet. Pokud Desktop používá jako výchozí vzdálenou connection, instalátor tuto volbu nemění a v reportu vysvětlí, proč lokální backend nenaběhl.

```powershell
.\install-vut-ai-tutor-universal-v2.3.4.ps1 `
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
.\verify-vut-ai-tutor-universal-v2.3.4.ps1 `
  -Platform Desktop `
  -DesktopInstallRoot 'D:\web-ui' `
  -PromptForCredential `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe' `
  -StartupTimeout 300 `
  -ReportPath '.\vut-ai-tutor-desktop-verify.json'
```

Databázová oprava je záměrně oddělená:

```powershell
.\install-vut-ai-tutor-universal-v2.3.4.ps1 `
  -Action DesktopDatabaseRepair `
  -Platform Desktop `
  -DesktopInstallRoot 'D:\web-ui' `
  -StopDesktopProcesses `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe'
```

## e-INFRA Windows Server

```powershell
.\install-vut-ai-tutor-universal-v2.3.4.ps1 `
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
.\install-vut-ai-tutor-universal-v2.3.4.ps1 `
  -Action Repair `
  -Platform Docker `
  -ContainerName 'open-webui' `
  -TokenFile '.\openwebui-admin-token.txt' `
  -PythonPath 'C:\Python312\python.exe'
```

Linux/macOS:

```bash
bash ./install-vut-ai-tutor-universal-v2.3.4.sh \
  --action repair \
  --platform docker \
  --container-name open-webui \
  --token-file ./openwebui-admin-token.txt
```

Zastavený explicitně vybraný kontejner může instalátor spustit. Není-li port kontejneru publikovaný na hostu, zadejte také `--base-url` / `-BaseUrl` dosažitelného Open WebUI endpointu.

## Obecný bare-metal

Linux se systemd:

```bash
bash ./install-vut-ai-tutor-universal-v2.3.4.sh \
  --action repair \
  --platform baremetal \
  --base-url http://127.0.0.1:8080 \
  --service-name open-webui \
  --restart-policy on-failure \
  --token-file ./openwebui-admin-token.txt
```

Vlastní správce služby:

```bash
bash ./install-vut-ai-tutor-universal-v2.3.4.sh \
  --action repair \
  --platform baremetal \
  --base-url http://127.0.0.1:8080 \
  --restart-command 'supervisorctl restart open-webui' \
  --token-file ./openwebui-admin-token.txt
```

## Vzdálené webové rozhraní a reverse-proxy prefix

```bash
bash ./install-vut-ai-tutor-universal-v2.3.4.sh \
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
.\verify-vut-ai-tutor-universal-v2.3.4.ps1 `
  -Platform Remote `
  -BaseUrl 'https://webui.example.edu' `
  -TokenFile '.\openwebui-admin-token.txt' `
  -PythonPath 'C:\Python312\python.exe'
```

Linux/macOS:

```bash
bash ./verify-vut-ai-tutor-universal-v2.3.4.sh \
  --platform remote \
  --base-url https://webui.example.edu \
  --token-file ./openwebui-admin-token.txt
```

Za úspěch se považuje pouze současně:

- aktivní `study_tutor_gateway_bootstrap` typu `event`;
- aktivní `study_tutor_pipe` typu `pipe`;
- přesná shoda zdrojových hashů;
- JSON z `/study-tutor/health` s runtime 1.26.5;
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

Očekává se verze `1.26.5` a `pdf_delivery.revision` rovna `pdf-delivery-r2`.
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
  bash ./test-vut-ai-tutor-universal-v2.3.4.sh
```

```powershell
.\test-vut-ai-tutor-universal-v2.3.4-windows.ps1 `
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

## Ověření opravy Canvas layoutu

```powershell
$h = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/study-tutor/health'
$h.version
$h.canvas_layout
```

Očekává se `1.26.5`, `revision: canvas-layout-r1`, `native_layout_owner: open-webui`, `fallback_only_reservation: true`. `live_window_verified: false` je úmyslné: server nemůže health odpovědí potvrdit geometrii aktuálního desktopového okna.

V konzoli **hlavního okna Open WebUI**, ne iframe, lze po otevření Tutora získat pouze lokální diagnostiku bez tokenů:

```javascript
JSON.stringify(window.__VUT_AI_TUTOR_UI_COORDINATOR_V1220__?.snapshot() ?? {
  status: 'coordinator-not-installed-in-this-page',
  note: 'Open Tutor through a fresh chat action; a historical native citation may not install the bridge.'
}, null, 2)
```

Nativní režim má `mode: native`, `ownedElements: 0`, `observedResizeTargets: 0`. `styleWrites` je kumulativní čítač (po předchozím fallbacku nemusí být nula); v klidu nemá samovolně přibývat. Diagnostika se automaticky neposílá na server a neloguje chat ani přihlašovací údaje.

## Volitelné prohlížečové regresní testy

Testy používají skutečný Chromium a skutečnou vloženou parent šablonu, ale zjednodušené DOM prostředí bez běžícího Open WebUI. Prohlížeč a Playwright jsou testovací závislosti, nikoli součást instalace Tutora:

```bash
python -m pip install -r tests/requirements-browser-test.txt
VUT_CHROMIUM=/usr/bin/chromium python tests/test_canvas_layout_browser.py
# Nebo společně se zbytkem regresí:
VUT_RUN_PDF_TESTS=1 VUT_RUN_CANVAS_BROWSER_TESTS=1 VUT_CHROMIUM=/usr/bin/chromium \
  bash test-vut-ai-tutor-universal-v2.3.4.sh
```

Ve Windows nastavte `VUT_CHROMIUM` na existující Chromium/Chrome a spusťte testovací Python přímo. Chromium v testu běží headless; `--no-sandbox` je pouze argument tohoto izolovaného testu, ne změna nastavení vašeho Desktopu. Původní vadná šablona je výhradně testovací fixture a neinstaluje se do Open WebUI.
