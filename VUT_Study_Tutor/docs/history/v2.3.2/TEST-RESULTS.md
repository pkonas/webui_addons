# Výsledky ověření — Universal 2.3.2 / runtime 1.26.3

Sestavení: 18. září 2026. Hostitel: Linux, Python 3.13.5, Node.js 22.16.0.

## Jednotlivé testy

| Sada | Výsledek | Co se skutečně provádí |
|---|---:|---|
| PDF backend | 41 / 41 | Izolovaná reálná ASGI brána, dočasné SQLite, HMAC relace; Files/Storage jsou test doubles |
| Desktop manager a payloady | 3 / 3 | Mock API instalace/verify, záloha Functions, zachování valves, self-test |
| Univerzální integrace | 12 / 12 | Všechny vrstvy payloadů, shodné verze/markery, zachování zdrojových funkcí, manifest a odmítnutí poškození |
| JavaScript diagnostika | 6 / 6 | Node.js testy chybového JSON, korelace ID, autorizace a omezení diagnostického stahování |
| **Celkem** | **62 / 62** | Bez neúspěšných dokončených testů |

## Původní regresní sady

Prošly také původní sady package contract, PowerShell lexical/CmdletBinding contract,
Bash syntaxe, kompilace Pythonu, dispatcher/engine self-test, detekce platforem,
start zastaveného kontejneru (simulace) a Desktop lifecycle/autostart/dynamický port
(simulace). Pro Remote, Docker a BareMetal prošly cykly Install → Verify → Uninstall
proti mock API. Ověřen byl rollback po vynuceném selhání, reverse-proxy prefix,
Bash/Python vstupy a capability gate pro syntetickou verzi Open WebUI 0.12.7.
Tyto scénáře nejsou započítány jako další jednotlivé unittest testy do čísla 62.

## Kontrola zachování původního balíku

Všech 37 původních souborů má odpovídající soubor v novém vydání; mapování je
v `docs/INTEGRATION-PROVENANCE.json`. Žádná z 383 původních runtime funkcí/metod
nebyla odstraněna: 359 má identický AST, 24 je změněno hotfixem a přibyly čtyři.
Zachováno je všech 186 pojmenovaných JavaScriptových funkcí, Canvas HTML/CSS jsou
bajtově shodné, PDF.js zůstává 6.2.108 a databázové schéma Tutora zůstává 14.
Strukturální inventář není důkazem funkčního průchodu každým výukovým scénářem.

Všechny přímé i vnořené payloady Desktop/e-INFRA mají obsah i SHA-256 shodný
s kanonickými zdroji. PowerShell soubory jsou UTF-8 BOM + CRLF. Vložený Pipe je
shodný se samostatným Pipe, testovaný JS je shodný s nasazovaným Canvas JS.

## Archiv

Testovací sady byly znovu spuštěny z čistého rozbalení sestaveného ZIPu.
Ověřeny byly ZIP CRC, manifest a SHA256SUMS; archiv neobsahuje __pycache__ ani .pyc.
Podrobné protokoly a strojový souhrn jsou v `docs/test-logs/` a
`BUILD-TEST-REPORT.json`. Závislosti zaznamenává také `tests/requirements-test.txt`.

## Co zde nebylo živě ověřeno

Windows PowerShell 5.1 ani nativní PowerShell parser, Windows filesystem/ACL,
spuštění a restart skutečné Electron aplikace, e-INFRA Scheduled Tasks a Caddy,
reálný Docker/Podman daemon, systemd/služby, macOS, produkční Open WebUI a storage
providery, pixelové vykreslování PDF.js v Electronu ani konkrétní uživatelovo PDF.

Health potvrzuje nasazený runtime a revizi brány, nikoli otevření knihy.
`live_document_verified: false` je proto záměrné. Na cílové instalaci je nutné
otevřít původní dokument v novém panelu Tutora. Chybějící originál hotfix neobnoví.
