# Ověření 2.3.3 / runtime 1.26.4

Provedeno 18. 9. 2026 na Linuxu, Python 3.13.5, Node 22.16.0. Jde o výsledky této revize; historické protokoly 2.3.2 jsou oddělené v `docs/history/v2.3.2/`.

## Automatizované testy

| Sada | Úspěšné testy |
|---|---:|
| PDF brána: autorizace, přenos, úložiště, Range/HEAD, chyby | 41 |
| Obnova zdroje, deduplikace, vlastníci, raw/text hash, opakované nahrání, skutečné PDF | 32 |
| Desktop manager: záloha a zachování nastavení přes mock API | 3 |
| Kompletní balík: všechny vložené payloady, platformy, AST inventura, manifest | 13 |
| JavaScriptová diagnostika | 7 |
| **Celkem** | **96** |

V tomto běhu 0 selhání, 0 přeskočených testů. Dále prošly kontroly Bash syntaxe, kompilace všech Python souborů, lexikální kontrola PowerShellu, package contract, self-test dispatcheru/enginu, simulovaná detekce platforem, Desktop lifecycle a dynamický port, instalační cykly Remote/Docker/BareMetal na mock HTTP API, rollback po vynucené chybě a Bash/Python vstupy s reverse-proxy prefixem. Test budoucí verze Open WebUI používá syntetickou hodnotu 0.12.7, není tvrzením o konkrétním upstream vydání.

Protokol: `docs/test-logs/full-regression-v2.3.3.log`. Přesné verze, počty a podklady: `BUILD-TEST-REPORT.json`.

## Skutečně dodané PDF

`numericke_metody_2.pdf`: 1 452 819 bajtů; raw SHA-256 `c134aed0f69bbc6903a9781411b59039cfc6f3dfd5d22a8c7cc998396e90bc40`.

Pypdf strict=True načetl všech 129 stran, 185 778 znaků a text na každé straně. Dokument není šifrovaný. PDFium vykreslil všech 129 stran při scale=1.0 bez chyby. PyMuPDF načetl 129 stran bez strukturální opravy. Kontrolně byly vizuálně prohlédnuty reprezentativní vykreslené strany. PDF nebyl převáděn ani změněn.

Izolovaná reprodukce s původními PDF bajty: runtime 1.26.3 při neplatném kanonickém záznamu a dostupné totožné kopii vrátí 409; runtime 1.26.4 při stejných podmínkách vrátí 200 a přesně původní bajty. Samostatný test potvrzuje zachování řádků sessions, selections, activities, mastery, learning_paths i books při samotném dohledání zdroje. Další testy pokrývají opětovné nahrání multipart a převzetí přílohy chatu.

Regresní test bez původní raw reference neodhaduje identitu podle názvu či extrahovaného textu: kopii jako starou knihu odmítne. Nové nahrání však může otevřít jako novou knihu a zachovat původní historii odděleně.

## Zachování balíku

Ze 387 runtime funkcí/metod 1.26.3 zůstává všech 387 přítomných; 377 má shodný AST, 10 bylo cíleně změněno a 5 přibylo. Historická inventura 383 funkcí 1.26.2 je také zachována. Canvas HTML/CSS, PDF.js 6.2.108 a schema 14 zůstávají. Desktop, EInfraWindows, Docker/Podman, BareMetal, Remote a explicitní recovery akce jsou stále v distribuci. Každý vnořený payload se ověřuje proti zdrojům, nikoli jen podle verze na obalu.

## Meze ověření

ASGI brána, dočasná SQLite a podpis studijní relace jsou skutečné; rozhraní Files/Storage/Knowledge/RAG Open WebUI jsou testovací náhrady. Instalační E2E testy běží proti mock API. Neproběhlo živé spuštění Windows PowerShellu/Electronu, e-INFRA služeb, Docker/Podman daemonu, cloudových storage služeb nebo macOS. PDF.js v Electronu nebyl vykreslovacím testem ověřen. Strukturální inventura není testem každého studijního či ANSYS scénáře.

Logy neprokazují, proč starý záznam původní cestu ztratil, ani neobsahují kompletní produkční metadata. Automatické dohledání potřebuje raw referenci a dostupnou totožnou kopii stejného vlastníka. Bez originálu nebo kopie oprava PDF nevytvoří. Uživatelský PDF a kompletní aplikační logy nejsou součástí balíku.

## Opakování

```bash
VUT_RUN_PDF_TESTS=1 VUT_CASE_PDF=/absolutni/cesta/k/numericke_metody_2.pdf \
  bash ./test-vut-ai-tutor-universal-v2.3.3.sh
```

Bez `VUT_CASE_PDF` se přeskočí jediný test extrakce soukromého dokumentu, ostatní používají generované testovací PDF. Testovací prostředí vytvořte mimo balík a mimo vestavěný Python Desktopu. Pro volitelnou skutečnou extrakci je navíc potřeba pypdf; zde použito 5.9.0.
