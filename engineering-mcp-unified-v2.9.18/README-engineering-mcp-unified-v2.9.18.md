# Engineering MCP Unified v2.9.18

Kompletní samonosný instalátor pro Windows + WSL2. Základ: v2.9.17; PhysicsNeMo/NAT komponenta a plugin: **1.2.10**. Hlavní `.ps1` obsahuje celý Python program i komponentu. Žádný patch ani externí auditní zdroj není pro instalaci potřeba. Externí závislosti se nadále mohou stahovat z internetu.

## Co tato verze opravuje

Nový report v2.9.17 skončil `OpenAITimeoutError` v `model_probe.workspace_write`. Lokální část provedla sedm operací a Python úspěšně; modelová část provedla tři operace, ale pátý modelový požadavek už nevrátil odpověď. Zápis testovacího skriptu v modelové části ještě nebyl proveden.

Ve v2.9.17 měl kontrolní ChatOpenAI klient pevný timeout 90 sekund. Celá modelová fáze měla další limit 240 sekund a vnější WSL proces 300 sekund. Poslední zaznamenanou úspěšnou modelovou odpověď a konec kontroly v dodaném logu dělí přibližně 91 sekund. To odpovídá vypršení klientského limitu; příčinu pomalé nebo nedoručené upstream odpovědi podklady neobsahují.

V2.9.18 mění **instalační ověření**, nikoli model, poskytovatele, klíče nebo fyzikální zadání:

| Vrstva | v2.9.17 | v2.9.18 — výchozí limit |
|---|---:|---:|
| SDK požadavek na model | 90 s | 300 s |
| Dodatečný aplikační dohled jednoho požadavku | nebyl samostatný | 305 s |
| Celá modelová fáze | 240 s | 1 800 s |
| Vnější WSL proces instalátoru | 300 s | 1 920 s |

Pětisekundová rezerva umožňuje nejprve zachytit vlastní chybu SDK. WSL rezerva 120 sekund slouží načtení, lokálním kontrolám a úklidu. Modelová fáze se při vyčerpání svého celkového limitu zastaví i tehdy, když jednotlivé požadavky dosud své limity nepřekročily. Nejde o odhad délky instalace, ale o konečné maximální rozpočty jednotlivých vrstev.

Timeout **nevede k automatickému opakování** modelového požadavku, k přepnutí na jiný model ani k opakování dokončených nástrojů. SDK v kontrolním klientovi má `max_retries=0`. Případná upstream práce může již spotřebovat prostředky; zrušení místního čekání nezaručuje zrušení vzdálené inference.

Během čekání kontrola vypisuje přibližně každých 15 sekund `PHYSNEMO_PREFLIGHT_PROGRESS` s názvem čekající operace a uplynulým časem. Neobsahuje tělo odpovědi, kód, argumenty ani klíče. Stejná metadata jsou v `model-events.jsonl`.

Zůstává zachován striktní JSON parser, nejvýše dva dodatečné pokusy o opravu formátu, kontrola přesného skriptu, oddělená lokální/modelová pracoviště a požadavek na skutečný Python i skutečné soubory. Ochranné filtry, automatický průběh jobů a galerie se nemění. Limity běžných výpočetních jobů a jejich modelové konfigurace se touto úpravou nepřepisují.

## Instalace přes existující verzi

Rozbalte celý ZIP. V PowerShellu přejděte do `engineering-mcp-unified-v2.9.18`. Použijte stejný Windows účet a případnou vlastní hodnotu `ENGINEERING_MCP_HOME` jako dosud. Open WebUI musí být dostupné pro synchronizaci a modelové testy. Dokončete rozpracované joby před aktualizací.

```powershell
Unblock-File .\verify-engineering-mcp-unified-v2.9.18.ps1
Unblock-File .\install-engineering-mcp-unified-v2.9.18.ps1

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\verify-engineering-mcp-unified-v2.9.18.ps1
if ($LASTEXITCODE -ne 0) { throw "Kontrola balicku neprosla." }

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-engineering-mcp-unified-v2.9.18.ps1 -Resume
if ($LASTEXITCODE -ne 0) { throw "Instalace nebo preflight neprosly; zkontrolujte novy report." }
```

Použijte `-Resume`, nikoli `-Force` nebo odinstalaci. Nemažte virtuální prostředí, WSL distro, konfiguraci ani joby. Všech 46 původních parametrů hlavního instalátoru zůstává zachováno. Auditní zdroje nejsou konfigurační soubory a jejich ruční úprava neaktualizuje instalaci.

Po úspěšné instalaci restartujte Open WebUI a otevřete nový chat. Neúspěšné starší joby se automaticky nepřepočítají.

## Ověření úspěchu

V `logs\physnemo-native-tools-preflight.json` musí být současně:

```json
{"success": true, "model_tool_execution_verified": true}
```

`selected_tool_transport: json_actions_v1` a `native_tool_calls_verified: false` mohou být při úspěšné kompatibilní cestě v pořádku. Samotný úspěšný lokální test nebo registrace nástrojů nestačí. `chat_tool_execution_ready` se při neúspěšné kontrole nesmí nastavit na `true`.

Nové chyby:

- `PHYSNEMO_MODEL_REQUEST_TIMEOUT`: vypršel limit jednoho modelového požadavku. `timeout_error.outcome` rozliší `sdk_timeout` a `request_deadline`; `origin_exception_type` uchovává bezpečný název původní výjimky.
- `PHYSNEMO_MODEL_PREFLIGHT_TOTAL_TIMEOUT`: vypršel rozpočet celé modelové fáze, ne nutně konkrétní SDK timeout.
- `PHYSNEMO_MODEL_TIMEOUT_CONFIG_INVALID`: neplatné časové nastavení, kontrola se nesmí spustit s nekonečným či záporným limitem.

`failed_stage` označuje čekající fázi. `model_summary.last_request` se odlišuje od `last_response`, která může patřit předchozímu úspěšnému nástroji. `timeout_error` a `last_request_timing` mají časové údaje, nikoli citlivou odpověď. `pending_operation_dispatched: false` popisuje stav při modelovém čekání; netvrdí, že žádná dřívější operace neběžela.

## Samostatná kontrola po nasazení v2.9.18

Není nutné při každém ověření znovu instalovat závislosti:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\check-installed-physnemo-v2.9.18.ps1
```

Volitelné explicitní limity samostatné kontroly:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\check-installed-physnemo-v2.9.18.ps1 -ModelRequestTimeoutSeconds 600 -ModelPreflightTimeoutSeconds 3600
```

Kontrola používá nainstalovaný plugin **1.2.10 / V5**; starý odmítne jako nekompatibilní. Neinstaluje závislosti ani nemění konfiguraci/readiness. Vytváří nová diagnostická pracoviště a výsledek `logs\physnemo-model-tools-recheck.json`, volá model a při úspěchu spouští dva malé Python procesy (lokální a modelový). Čistě nativní cesta má sedm modelových požadavků; cesta s prvním neúspěšným nativním pokusem má osm. Opravy JSON mohou přidat další požadavky. Nespouští fyzikální simulaci.

Pro plný instalátor lze ve stávajícím PowerShell procesu před jeho spuštěním nastavit `ENGINEERING_MCP_PHYSNEMO_REQUEST_TIMEOUT_SECONDS` a `ENGINEERING_MCP_PHYSNEMO_PREFLIGHT_TIMEOUT_SECONDS`. Tato nastavení se nepersistují do klíčů ani modelové konfigurace. Rozsahy: požadavek 1–900 sekund; celá modelová fáze nejméně limit požadavku, nejvýše 7 200 sekund. Samostatný `.ps1` používá vlastní výše uvedené parametry.

## Rozsah ověření

Výsledky aktuálně provedených testů jsou v `audit/TEST-RESULTS-engineering-mcp-unified-v2.9.18.txt`, jejich výstupy v `audit/executed-tests`. Testy používají skutečné místní soubory, Python podprocesy a HTTPX/TCP spojení proti testovacímu serveru. NAT/LangChain/modelová rozhraní jsou testovací náhrady. Zpoždění síťových testů jsou zmenšená; nejsou měřením vašeho backendu.

Pokus nainstalovat přesné SDK verze v tomto prostředí selhal na překladu DNS. Windows PowerShell, WSL, skutečný NAT/LangChain klient, e-infra model ani vykreslení v Open WebUI zde nejsou ověřené. Vyšší limit neopraví nefunkční nebo neodpovídající upstream službu. Úspěšný preflight navíc neprokazuje konvergenci ani fyzikální správnost PINN.
