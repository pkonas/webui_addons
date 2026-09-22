# Integrace PDF hotfixu do univerzálního instalátoru 2.3.2

## Původ a rozsah

Vstupem je uživatelem dodaný úplný balík 2.3.1 / runtime 1.26.2 a samostatný Desktop
PDF hotfix 1.26.3. Toto vydání integruje opravu, nikoli nový Open WebUI nebo nový
PDF.js. Neprokazuje příčinu konkrétního produkčního HTTP 500 ani dostupnost
originálního PDF na počítači uživatele.

| Komponenta | Integrovaná verze | Rozsah změny |
|---|---|---|
| Kořenové PS/Bash/Python dispatchery | 2.3.2 | Nové cesty/verze, původní přepínače a platformy |
| Společný Tutor Event a Pipe | 1.26.3 | PDF hotfix a univerzální build marker |
| Desktop manager | 1.26.3 | Hotfix manager se zálohou Functions/valves; původní lifecycle |
| API engine | 2.0.4 | Engine 2.0.3 s novým očekávaným runtime/markerem |
| e-INFRA adaptér | 2.1.6 | Nové payloady; původní Scheduled Tasks/Caddy/recovery logika |
| e-INFRA vnitřní API wrapper | 2.0.4 | Stejný engine, Event, Pipe a Desktop recovery payload jako zbytek balíku |

Desktop lifecycle revision zůstává `2.3.1-official-desktop-lifecycle-r1`, protože
jeho implementace nebyla při této integraci měněna. Jde o revizi komponenty,
nikoli o zastaralou verzi nasazovaného Tutora.

## Zachované větve a funkce

Desktop Windows zachovává dynamickou detekci portu, start oficiální aplikace pro
Repair/Verify, `NoAutoStartDesktop`, předávání vlastních adresářů a Pythonu,
explicitní startup recovery a oddělenou databázovou opravu. e-INFRA zachovává
`runtime.json`, Scheduled Tasks, kontrolu vlastnictví procesů, Caddy,
PublicVerification, TutorStartupRecovery a diagnostické/recovery skripty.

Docker/Podman zachovává detekci publikovaného portu i start explicitně zvoleného
zastaveného kontejneru. Bare-metal zachovává služby i explicitní restartovací
příkaz. Remote zachovává HTTP/HTTPS, privátní CA, reverse-proxy prefix a API
instalaci/ověření/odinstalaci. Všechny původní volby dispatcheru zůstávají;
nejednoznačný alias `Server` do kořenového rozhraní přidán nebyl.

Runtime zachovává knihovnu, studijní cesty, analýzu/retrieval, výběry v dokumentu,
integrované nástrojové a ANSYS scénáře i schéma 14. Porovnání AST proti původnímu
zdroji eviduje 383 původních funkcí/metod: žádná nebyla odstraněna, 359 má identický
AST a změněných 24 patří k PDF/API kompatibilitě, diagnostice a uzavírání SQLite.
Přibyly čtyři funkce/metody. Zachováno je všech 186 pojmenovaných JS funkcí,
Canvas HTML/CSS jsou bajtově shodné, PDF.js je stále 6.2.108.
Samotný inventář nenahrazuje funkční test každého studijního scénáře.

## Proč nestačilo přepsat tři soubory runtime

Desktop repair, verify i recovery mají vlastní gzip/base64 payloady. e-INFRA má
vnořený PowerShell wrapper a v něm API engine, Event, Pipe i další Desktop
repair wrapper. Všechny tyto vrstvy byly přegenerovány z kanonických souborů a
nově mají odpovídající SHA-256. Čitelná kopie e-INFRA vnitřního wrapperu je v
`adapters/einfra/api-wrapper-v2.0.4.ps1`; je bajtově shodná s vloženou kopií.
Nejde o nový uživatelský vstup: používejte kořenový univerzální dispatcher.

## PDF chování

Oprava kontroluje prázdné/nevhodné cesty, podporuje sync i async Files/Storage a
používá společný resolver pro čtečku, obrys, extrakci textu a přiložené studijní
cesty. Náhradní lokální dohledání je pouze v nastaveném uploads, podle přesného
UUID již autorizovaného souboru. Shoda jen názvu se nepoužije, více kandidátů
se odmítne, symlink mimo uploads není povolen a u cloudového provideru se lokální
fallback nepoužije. Databázové cesty se automaticky nepřepisují.

PDF se otevře a zkontroluje se hlavička před odesláním úspěšné odpovědi. Podporuje
GET 200, jeden byte range 206, HEAD a neplatný range 416. Kontrola PDF hlavičky
není plnou validací celého dokumentu. Streamy i SQLite spojení se uzavírají.

| Kód | Význam |
|---|---|
| `file_path_missing` / 409 | Chybí cesta a nelze jednoznačně dohledat autorizovaný originál |
| `file_not_found` / 404 | Originální soubor není dostupný |
| `file_path_ambiguous` / 409 | Více kandidátů stejného UUID; žádný není zvolen |
| `storage_permission_denied` / 503 | Proces nemá potřebná oprávnění |
| `storage_provider_error` / 502 | Výjimka storage provideru |
| `storage_io_error` / 503 | Selhání čtení souboru |
| `pdf_invalid_header` / 422 | Prázdný soubor nebo chybějící základní PDF hlavička |
| `tutor_route_error` / 500 | Jiná neočekávaná chyba; ID odpovídá backendovému logu |

Čtečka zobrazí kód, typ výjimky a ID chyby. Diagnostický autorizovaný požadavek
použije Range 0–1023, chybný JSON čte s limitem a úspěšný stream zruší, aby zbytečně
nestahoval celou knihu. Stacktrace a cesty zůstávají v serverovém logu.

## Aktualizace a bezpečnost

Rozbalte do nové složky a spusťte původní příkaz přes nový kořenový skript 2.3.2.
Zachovejte stejné vlastní adresáře/Python/platformu jako u funkční instalace.
Normální Desktop Repair používá TutorOnly; nevynucuje reinstall Open WebUI ani
opravnou migraci hlavní databáze. Může však restartovat aplikaci. Schéma knihovny
Tutora se tímto hotfixem nemění.

Desktop před změnou ukládá `vut-pdf-hotfix-functions-before-*.json` vedle reportu;
tato záloha může obsahovat citlivá nastavení. Automatický rollback Desktop
manageru není implementován. API engine a e-INFRA zachovávají transakční rollback.
SHA-256 chrání proti náhodnému smíchání souborů, není to digitální podpis autora.

Závěrečné ověření konkrétní knihy musí proběhnout v novém panelu Tutora. Health
`live_document_verified=false` není chyba: instalátor skutečné otevření knihy
netvrdí. Chybějící originál oprava neobnoví.

## Ověřování

Původní regresní sady zůstaly v balíku. Nová sada
`tests/test_universal_pdf_integration.py` kontroluje všechny vrstvy payloadů,
zdrojový inventář, verze, přepínače, kódování i odmítnutí poškozeného souboru.
PDF testy běží na reálné izolované ASGI bráně s dočasným SQLite a nahrazenými
externími Files/Storage rozhraními. Instalační testy používají mock API.
Přesné výsledky a neprovedené živé testy: `TEST-RESULTS.md` a `BUILD-TEST-REPORT.json`.
