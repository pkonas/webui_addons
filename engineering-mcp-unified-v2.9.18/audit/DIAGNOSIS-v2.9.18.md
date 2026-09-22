# Diagnóza v2.9.18: čekání na model, nikoli potvrzená chyba disku nebo JSON

## Doloženo dodanými soubory

`physnemo-native-tools-preflight(3).json` z 21. září 2026, začátek kontroly 13:59:31 UTC (15:59:31 Europe/Prague), uvádí:

```text
local_probe.success = true
local_probe.tool_summary = attempts 7, succeeded 7, failed 0
local_probe.execution_summary = attempts 1, succeeded 1, failed 0, returncode 0
model_probe.tool_summary = attempts 3, succeeded 3, last_tool workspace_list
model_probe.model_summary = requests 5, responses 4, tool_calls 0, json_actions 3
model_probe.execution_summary = attempts 0
failed_stage = model_probe.workspace_write
exception_type = OpenAITimeoutError
error = PHYSNEMO_NATIVE_PREFLIGHT_FAILED
```

`last_response` patří předchozímu `workspace_list`, nikoli selhavšímu požadavku. Její epoch 1789999206 odpovídá 14:00:06 UTC (16:00:06 českého času). Konec příslušného WSL příkazu je zapsán v `physnemo-wsl-install(20260921-155516).log` pod 14:01:37 UTC (16:01:37 českého času). Rozdíl je 91 sekund. Hlavička této části WSL logu je zapisována po dokončení příkazu; nelze ji zaměnit za začátek modelového čekání.

Kontrola bridge (`physnemo-agent-bridge-preflight(3).json`) prošla pro JSON, SSE i LangChain. MCP kontrola našla pět veřejných nástrojů. Synchronizace (`openwebui-native-sync(4).json`) potvrzuje registraci, nikoli provedení: `chat_tool_registration_ready=true`, `chat_tool_execution_ready=false`.

Lokální zápis a Python fungovaly. Fáze `model_probe.workspace_write` nejprve požaduje modelovou odpověď s příkazem, poté ji ověřuje a až pak zapisuje. Z reportu nelze tento timeout označit za selhání zápisu na disk. Modelový skript v tomto pokusu nevznikl.

## Ověřeno ve skutečném zdroji v2.9.17

V samostatném i vloženém kontrolním klientovi je:

```python
ChatOpenAI(..., timeout=90, max_retries=0)
```

`native_tool_preflight` má pro všechny modelové kroky společný limit 240 sekund. Windows obal spouští kontrolní WSL proces s limitem 300 sekund. Bridge pro upstream HTTP používá až 900 sekund, ale klient kontrolující instalaci může přestat čekat mnohem dříve. Zvýšení pouze vnějšího WSL/startup limitu proto nemění vnitřní SDK limit.

Časování a typ výjimky silně odpovídají vypršení 90sekundového klientského limitu. Konkrétní délka pátého požadavku nebyla ve staré diagnostice přímo měřena.

## Co podklady nedokazují

Není doloženo, proč se upstream odpověď zdržela nebo nedoručila: fronta modelu, jeho generování, vlastní Pipe/proxy, síť ani jiná příčina nejsou z těchto reportů rozlišitelné. Není doložena nová validační chyba JSON v tomto pokusu. Není důvod z těchto údajů měnit API klíče, vypínat DLP nebo mazat WSL.

Počáteční `curl: (7)` při startu NAT není závěrečným selháním: stejný krok skončil `EXIT: 0` a vrátil seznam pěti nástrojů. `AuthlibDeprecationWarning` je varování; závěrečný report označuje jinou výjimku. Historické chyby na začátku kumulativních logů se nesmí vydávat za události tohoto pokusu.

## Změna v2.9.18

Časové rozpočty instalační kontroly jsou explicitní: SDK 300 s, aplikační dohled požadavku 305 s, modelová fáze 1 800 s, WSL obal 1 920 s. Uživatelská přenastavení jsou konečná a validovaná. Kontrola měří jednotlivá čekání a eviduje poslední požadavek odděleně od poslední odpovědi.

Rozlišuje SDK/request timeout, celkový modelový deadline a běžnou provider chybu. Přidává metadata-only heartbeat. Timeout nic automaticky neopakuje a nezměkčuje kontroly souborů, přesného skriptu ani Python návratového kódu. Runtime výpočetní algoritmus, JSON parser, model a ochranné filtry se záměrně nemění.

## Reprodukce a omezení

`executed-tests/v2917-timeout-reproduction.json` obsahuje reprodukci na nezměněném pluginu v2.9.17: testovací model vrátí tři platné JSON akce a při přípravě čtvrté vyvolá syntetický `OpenAITimeoutError`. Výsledek odpovídá kombinaci 5 požadavků / 4 odpovědí / 3 operací / 0 modelových běhů Pythonu / obecné chyby. Toto není zachycená odpověď vašeho backendu ani fyzické měření 90 sekund.

Nové síťové testy používají skutečný HTTPX klient a lokální TCP server: odpověď na zápis je zpožděna o 0,18 s. Limit 0,05 s vyvolá skutečný `ReadTimeout`; limit 0,6 s dovolí provést všechny nástroje, spustit skutečný Python a ověřit přesné soubory. Další testy kontrolují aplikační deadline, celkový limit, zrušení, ochranu citlivého obsahu a zachování readiness=false při chybě.

Tyto testy nepotvrzují dostupnost vašeho modelu, správnost Windows instalace ani vědeckou kvalitu budoucí simulace. Konkrétní verze SDK se zde nepodařilo stáhnout kvůli DNS; proto jsou SDK/NAT rozhraní označené testovací náhrady.
