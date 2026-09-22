# Výsledky ověření — Universal 2.3.4 / runtime 1.26.5

## Výsledek

**121 jednotlivých automatizovaných testů prošlo; 0 selhání, 0 přeskočených.**
Tento protokol a připojené logy popisují testy v sestavené zdrojové složce před zabalením. Následná kontrola po čistém rozbalení výsledného ZIPu má samostatný protokol vedle archivu; tento vnitřní protokol není důkazem svého vlastního pozdějšího zabalení.

Prostředí: Linux, Python 3.13.5, Node v22.16.0, Chromium **144.0.7559.96**. Nejde o živý Windows Desktop/Electron uživatele.

| Sada | Úspěšné testy |
|---|---:|
| PDF delivery (isolated ASGI) | 41 |
| PDF copy recovery, including supplied-PDF byte test | 32 |
| Desktop Function manager (mock API) | 3 |
| Universal payload integration and preservation | 13 |
| PDF JavaScript diagnostics (Node) | 7 |
| Canvas layout contracts | 6 |
| Canvas lifecycle (Chromium reduced DOM) | 19 |

Dále prošly Bash syntaxe, kompilace Pythonu, integrita balíčku, lexikální PowerShell/CmdletBinding kontrola, self-test dispatcheru a API enginu, detekce platforem, simulované životní cykly Desktopu, mock instalační cykly Remote/Docker/BareMetal včetně rollbacku a Bash/Python vstupy s reverse-proxy prefixem. Tyto scénáře nejsou podruhé započítány do 121 jednotlivých testů.

## Reprodukce závady v prohlížeči

Test používá **původní nezměněnou JS šablonu z runtime 1.26.4**, nikoli nově napsanou napodobeninu jejího algoritmu. Hostitelský DOM je zjednodušený flex layout, kde kořen chatu obsahuje nativní boční panel. Iframe má lokální testovací obsah; síťové požadavky jsou zablokovány. Není to plná reprodukce konkrétní instalované verze Open WebUI.

| Měření v tomto běhu | Původní bridge | Opravený bridge |
|---|---:|---:|
| Šířka kořene chatu při viewportu 1440 px | střídá 749 / 1440 px | stabilně 1440 px |
| Změny atributu style na kořeni chatu | 434 | 0 |
| Události chyby ResizeObserver loop | 81 | 0 |

Počty událostí závisí na načasování daného testu; nejde o hodnoty odečtené z uživatelových logů. Při stejném testovacím rozložení nová verze nepřepisuje nativní šířku ani vstupní pole.

Další browser testy ověřují 12 cyklů odebrání a opětovného připojení nativního panelu, změny viewportu a nativního rozdělení, náhradní dock, mobilní overlay, neznámý hostitelský DOM, zrušení starého pokusu o otevření, pozdní příchod nativního panelu, slučování 400 žádostí do jediného animation frame, drag/close a obnovu kurzoru, zachování cizích CSS změn, odpojení resize targetů, nahrazení starého koordinátoru, jednorázové předání studijního promptu a diagnostiku bez tajných hodnot.

**Životní cyklus:** `dispose()` je v testu spuštěno přímo. Registrace `pagehide` se kontroluje staticky; skutečná navigace pagehide/bfcache zde testována není.

## Zachování předchozích funkcí

Kontrola porovnává skutečný předchozí runtime ze ZIPu 2.3.3 / 1.26.4. Zachováno je všech **392** evidovaných funkcí/metod. Těla **390** z nich mají shodné AST. Změněny jsou pouze `StudyRuntime._canvas_open_panel_code` a `StudyRuntime.register_routes` (přidání health diagnostiky). To není náhrada živého ověření každého výukového scénáře.

Vnitřní Canvas HTML/CSS/JS jsou beze změny. PDF.js zůstává 6.2.108, databázové schéma 14 a PDF opravy pdf-delivery-r2. Testy rozbalují i vložené a vnořené Desktop/e-INFRA payloady a kontrolují jejich přesnou shodu s kanonickými soubory. PowerShell payloady zachovávají BOM/CRLF a podporovaný here-string formát.

Součástí této regrese byl také test s původním `numericke_metody_2.pdf` z předchozího hlášení: ověření odpovědi izolované brány a shody bajtů při obnově dostupné kopie. **PDF není přibaleno** a v této sadě neprobíhalo vykreslování celé knihy v Electronu.

## Health smoke test

Skutečný požadavek přes ASGI transport izolované Tutor brány vrátil HTTP 200, verzi **1.26.5**, `canvas_layout.revision: canvas-layout-r1`, `pdf_delivery.revision: pdf-delivery-r2`. `live_window_verified: false` je záměr: server nemůže takto potvrdit stav konkrétního aktivního okna. Rozhraní Open WebUI v tomto testu nahrazují testovací adaptéry.

## Reprodukce testů

```bash
VUT_RUN_PDF_TESTS=1 VUT_CASE_PDF=/cesta/k/numericke_metody_2.pdf \
  bash ./test-vut-ai-tutor-universal-v2.3.4.sh
VUT_CHROMIUM=/usr/bin/chromium \
  python3 tests/test_canvas_layout_browser.py
```

Backendové závislosti: `tests/requirements-test.txt`. Browser testy potřebují Playwright (`tests/requirements-browser-test.txt`) a samostatně nainstalované Chromium. Bez `VUT_CASE_PDF` se případ s uživatelským PDF přeskočí; výše popsaný ověřený běh tuto proměnnou měl nastavenou. Browser sada je také dostupná přes `VUT_RUN_CANVAS_BROWSER_TESTS=1` v hlavním Bash test runneru. Není součástí běžné instalace.

## Doklady

- `BUILD-TEST-REPORT.json` — strojově čitelný souhrn.
- `docs/test-logs/v2.3.4/full-regression.log` — celý úspěšný regresní běh.
- `docs/test-logs/v2.3.4/canvas-browser.log` — všech 19 browser testů.
- `docs/canvas-browser-metrics.json` — konkrétní měření před/po.
- `docs/canvas-health-smoke.json` — izolovaný health požadavek.
- `docs/CANVAS-LAYOUT-PROVENANCE.json` — kontrolní součty a rozsah změn.
- `docs/canvas-panel-bridge-v1.26.4-to-v1.26.5.patch` — čitelný diff JS šablony.

**Neověřeno živě:** Windows PowerShell, Electron, konkrétní uživatelův Svelte frontend, skutečné e-INFRA služby a Docker/Podman. Oprava neposkytuje důkaz, že v konkrétní instalaci nemůže existovat ještě jiný nezávislý zdroj změn rozměrů. DLP, GPU sandbox, databázové schéma, originální PDF a studijní historie se touto opravou nemění.
