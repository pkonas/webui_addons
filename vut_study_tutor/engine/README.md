# VUT AI Tutor Universal Installer 2.0.2

> **Engine 2.0.2 route-contract fix:** runtime 1.26.2 publishes `asgi-prefix-gateway-v7` in the health API. The longer `asgi-prefix-gateway-v7-no-main-router-mutation` string is only an architecture label; the installer validates `main_router_mutated=false` separately.

> **PowerShell 2.0.2 hotfix:** `[CmdletBinding()]` already provides the common `-Debug` parameter. The wrappers no longer redeclare `$Debug`; passing `-Debug` remains supported and enables installer diagnostics through the built-in common parameter.


**Instalátor:** 2.0.2  
**Neměněný runtime Tutoru:** 1.26.2  
**Canonical Functions:** `study_tutor_gateway_bootstrap` (`event`) a `study_tutor_pipe` (`pipe`)

Tato sada sjednocuje instalaci VUT AI Tutoru pro:

- Open WebUI Desktop;
- Docker a Podman;
- bare-metal instalaci na Windows nebo Linuxu;
- vzdálenou webovou instalaci dostupnou přes HTTP/HTTPS;
- Open WebUI za reverzní proxy a pod cestovým prefixem.

Známý funkční runtime 1.26.2 je v balíčku převzat **bajtově beze změny**. Univerzální instalační vrstva řeší pouze nalezení backendu, autentizaci, transakční nasazení Functions, verifikaci a platformně omezené restart/recovery operace.

## Zásadní bezpečnostní pravidlo

Normální akce `Install`, `Repair`, `Verify`, `Preflight` a `Uninstall`:

- neimportují Python prostředí Open WebUI;
- neupravují balíčky Open WebUI;
- nemění SQLite/PostgreSQL databázi přímo;
- nemanipulují s interním `app.router.routes`;
- používají pouze veřejné HTTP Functions API Open WebUI;
- ukládají předchozí managed Functions do zálohy a při chybě je obnoví.

Přímá oprava Desktop databáze je zvláštní, výslovně potvrzovaná akce `DesktopDatabaseRepair`. Není dostupná pro Docker, bare metal ani vzdálený server.

---

## Rychlý start – Windows Desktop

Rozbalte ZIP do nové složky a odblokujte všechny soubory:

```powershell
Set-Location 'D:\Downloads\vut-ai-tutor-universal-installer-v2.0.2-runtime-v1.26.2-complete'
Get-ChildItem -LiteralPath . -Recurse -File | Unblock-File
```

Bezpečný offline test:

```powershell
.\test-vut-ai-tutor-universal-v2.0.2-windows.ps1 `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe'
```

Instalace nebo oprava:

```powershell
.\install-vut-ai-tutor-universal-v2.0.2.ps1 `
  -Action Repair `
  -Platform Desktop `
  -DesktopInstallRoot 'D:\web-ui' `
  -PromptForCredential `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe' `
  -ReportPath '.\vut-ai-tutor-desktop-report.json'
```

Instalátor použije běžící lokální backend. Pokud neběží, vyhledá Desktop executable, spustí jej a průběžně znovu načítá skutečnou URL z logu a konfigurace. Neváže se napevno na port 8080.

Verifikace po instalaci nebo po aktualizaci Open WebUI:

```powershell
.\verify-vut-ai-tutor-universal-v2.0.2.ps1 `
  -Platform Desktop `
  -DesktopInstallRoot 'D:\web-ui' `
  -PromptForCredential `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe' `
  -ReportPath '.\vut-ai-tutor-desktop-verify.json'
```

---

## Docker / Podman

Je-li port kontejneru publikovaný na hostu, lze nechat kontejner nalézt automaticky:

```bash
./install-vut-ai-tutor-universal-v2.0.2.sh \
  --action repair \
  --platform docker \
  --container-name open-webui \
  --token-file ./openwebui-admin-token.txt \
  --report-path ./vut-ai-tutor-docker-report.json
```

Za reverzní proxy nebo bez publikovaného portu zadejte veřejnou či interní URL explicitně:

```bash
./install-vut-ai-tutor-universal-v2.0.2.sh \
  --action repair \
  --platform docker \
  --base-url https://webui.example.cz \
  --container-name open-webui \
  --token-file ./openwebui-admin-token.txt
```

Docker/Podman režim nikdy neopravuje databázi a nemění image. Při `--restart-policy on-failure` smí restartovat pouze vybraný kontejner, a to až po neúspěšné API reaktivaci Event Function.

Windows PowerShell varianta:

```powershell
.\install-vut-ai-tutor-universal-v2.0.2.ps1 `
  -Action Repair `
  -Platform Docker `
  -ContainerName 'open-webui' `
  -TokenFile '.\openwebui-admin-token.txt' `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe'
```

---

## Bare metal

Linux se systemd a lokálním backendem:

```bash
./install-vut-ai-tutor-universal-v2.0.2.sh \
  --action repair \
  --platform baremetal \
  --base-url http://127.0.0.1:8080 \
  --service-name open-webui \
  --restart-policy on-failure \
  --token-file ./openwebui-admin-token.txt
```

Bez explicitního `--service-name` nebo `--restart-command` se bare-metal služba automaticky nerestartuje. Vzdálená URL je vždy bezpečnější než odhad lokálního portu.

Windows Server / vlastní služba:

```powershell
.\install-vut-ai-tutor-universal-v2.0.2.ps1 `
  -Action Repair `
  -Platform BareMetal `
  -BaseUrl 'https://server.example.cz' `
  -ServiceName 'OpenWebUI' `
  -RestartPolicy OnFailure `
  -TokenFile '.\openwebui-admin-token.txt' `
  -PythonPath 'C:\Python312\python.exe'
```

---

## Vzdálené webové rozhraní

Webový prohlížeč není samostatný typ backendu. Instalátor se připojuje k URL serveru, který webové rozhraní obsluhuje:

```bash
./install-vut-ai-tutor-universal-v2.0.2.sh \
  --action repair \
  --platform remote \
  --base-url https://webui.example.cz/openwebui \
  --token-file ./openwebui-admin-token.txt
```

Podporován je cestový prefix. Z uvedeného příkladu se API volá jako:

```text
https://webui.example.cz/openwebui/api/version
https://webui.example.cz/openwebui/api/v1/functions/...
```

Soukromá certifikační autorita:

```powershell
.\install-vut-ai-tutor-universal-v2.0.2.ps1 `
  -Action Repair `
  -Platform Remote `
  -BaseUrl 'https://webui.example.cz' `
  -CaCertificate '.\organization-root-ca.pem' `
  -TokenFile '.\openwebui-admin-token.txt'
```

`-InsecureTls` / `--insecure-tls` je pouze explicitní diagnostická výjimka.

---

## Akce instalátoru

| Akce | Zápis | Účel |
|---|---:|---|
| `Preflight` | ne | ověří `/api/version`, platformu, TLS a volitelně Functions API |
| `Install` | ano | aktualizuje/vytvoří canonical Pipe a Event bez zbytečného smazání |
| `Repair` | ano | před instalací canonical dvojici smaže a vytvoří znovu; vhodné při stale cache |
| `Verify` | ne | kontroluje Functions, hash, health, Canvas a CORS |
| `Uninstall` | ano | zazálohuje a odstraní všechny canonical i historické Tutor Functions |
| `SelfTest` | ne | ověří pouze vložené payloady a lokální kontrakty |
| `DesktopDatabaseRepair` | ano | výslovná Desktop-only obnova známého schématu; vyžaduje `-AllowPlatformMutation` |

### Desktop database repair

Použijte pouze při prokázané chybě migrace, například chybějícím `chat.timer_at`, a nejprve ukončete práci v Desktopu:

```powershell
.\install-vut-ai-tutor-universal-v2.0.2.ps1 `
  -Action DesktopDatabaseRepair `
  -Platform Desktop `
  -DesktopInstallRoot 'D:\web-ui' `
  -AllowPlatformMutation `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe' `
  -ReportPath '.\desktop-database-repair.json'
```

Tato akce deleguje na přesnou, známou Desktop recovery větev runtime 1.26.2. Ostatní platformy ji nemohou spustit.

---

## Transakční instalace

Instalace probíhá v tomto pořadí:

1. ověření JSON odpovědi z `/api/version`; HTML SPA fallback se odmítne;
2. autentizace administrátora a ověření Functions API;
3. úplná záloha všech canonical a historických Tutor Function záznamů;
4. deaktivace všech starých Event/Pipe aliasů;
5. vytvoření nebo aktualizace `study_tutor_pipe`;
6. vytvoření nebo aktualizace `study_tutor_gateway_bootstrap`;
7. kontrola typu, aktivity a normalizovaného SHA-256 obou zdrojů;
8. kontrola přesného runtime markeru přes `/study-tutor/health`;
9. kontrola skutečného Tutor HTML z `/study-tutor/canvas`;
10. CORS preflight s `Origin: null` pro sandboxovaný Canvas;
11. odstranění historických aliasů až po úspěchu;
12. automatický rollback při chybě.

Při stale Function cache provede instalátor nejprve bezpečný API cyklus delete/create Eventu. Restartuje platformu pouze podle `RestartPolicy` a pouze pokud příslušný adaptér umí restart omezit na zvolenou instanci.

## Canonical a historické Function ID

Po úspěchu musí být aktivní:

```text
study_tutor_gateway_bootstrap   event
study_tutor_pipe                pipe
```

Instalátor čistí tyto historické aliasy:

```text
study_tutor_bootstrap
study_tutor_canvas_bootstrap
vut_ai_tutor_bootstrap
vut_ai_tutor_pipe
study_tutor_pipe_managed
```

## Robustnost vůči aktualizacím Open WebUI

Instalátor záměrně nepoužívá samotné číslo verze jako rozhodnutí o kompatibilitě. Provede capability probes:

- platný JSON z `/api/version`;
- dostupnost administrátorského Functions API;
- create/update/toggle/delete/read konkrétních Function;
- přesný uložený source hash;
- runtime health contract;
- skutečný Canvas obsah;
- CORS preflight.

Neznámou budoucí verzi Open WebUI nezablokuje pouze kvůli číslu. Pokračuje jen tehdy, když všechny potřebné schopnosti skutečně fungují. Jakmile se veřejný API kontrakt změní, skončí před přijetím instalace a obnoví předchozí Function záznamy.

Po každé aktualizaci Open WebUI doporučujeme nejprve:

```text
Preflight → Verify → teprve při neúspěchu Repair
```

Normální instalační tok nikdy automaticky neaktualizuje Open WebUI ani jeho Python závislosti.

## Autentizace a tajné údaje

Preferované možnosti:

1. administrátorský token v souboru čitelném jen vlastníkem;
2. interaktivní `-PromptForCredential` / `--prompt-credentials`;
3. proměnné prostředí `VUT_INSTALL_TOKEN`, `VUT_INSTALL_EMAIL`, `VUT_INSTALL_PASSWORD`.

Token ani heslo se neukládají do reportu. Report je před zápisem rekurzivně redigován.

## Reporty a zálohy

Každá operace vytvoří auditní JSON. Záloha Functions vzniká před prvním zápisem typicky v:

```text
./vut-ai-tutor-backups/functions-before-YYYYMMDD-HHMMSS.json
```

Report obsahuje:

- vybranou platformu a backend URL;
- všechny sondované kandidáty a jejich chyby;
- Open WebUI verzi jako informativní údaj;
- způsob autentizace bez tajných hodnot;
- source hash obou canonical Function;
- runtime health, Canvas a CORS receipt;
- platformní restart/recovery operace;
- rollback receipt.

## Návratové kódy

| Kód | Význam |
|---:|---|
| 0 | úspěch |
| 2 | chybná konfigurace/payload |
| 3 | backend nenalezen nebo nelze spustit/restartovat |
| 4 | autentizace |
| 5 | Functions API |
| 6 | instalační transakce |
| 7 | verifikace runtime/Canvas/CORS |
| 8 | neúplný rollback |
| 130 | zrušeno uživatelem |

## Přímé spuštění Python manageru

PowerShell a Bash wrappery jsou self-contained, ale všechny zdroje jsou v balíčku také samostatně:

```bash
python3 vut_ai_tutor_universal_installer_v2.0.2.py \
  --action preflight \
  --platform remote \
  --base-url https://webui.example.cz \
  --bootstrap-path runtime/vut_ai_tutor_bootstrap_v1.26.2_server_desktop_windows_mock_transport_complete.py \
  --pipe-path runtime/vut_ai_tutor_pipe_v1.26.2_server_desktop_windows_mock_transport_complete.py \
  --report-path preflight.json
```

## Ověřený a neověřený rozsah

- Runtime 1.26.2 byl prakticky potvrzen v Open WebUI Desktop po opravě všech popsaných problémů.
- Univerzální API transakce, rollback, HTML fallback, Windows reset transportu, Docker port mapping a platformní výběr jsou testovány hermetickými mocky.
- Docker, Podman, systemd a vzdálený server nebyly v tomto sestavovacím prostředí připojeny k vaší produkční instanci. Proto instalátor používá stejný veřejný API tok, capability probes a fail-safe rollback místo platformních předpokladů.

Další podrobnosti jsou v `docs/ARCHITECTURE.md`, `docs/PLATFORM-MATRIX.md`, `docs/UPGRADE-RUNBOOK.md` a `docs/SECURITY.md`.
