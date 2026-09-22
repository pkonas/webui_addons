# Chybějící zdroj PDF: oprava 2.3.3 / runtime 1.26.4

## Co dokládá incident

V dodaném serverovém logu se v 22:38:22 hlásí `file_path_missing` pro staré ID `d81a3f40-8070-4479-b980-eb37f4e6841a` (také pro další ID). Nové nahrání `numericke_metody_2.pdf` se zpracovává jako `4a1a7968-eb9a-467d-8041-4f0d54b067e6`; v 22:39:05 záznam potvrzuje 256 vložených vektorových položek. Čtečka však dále žádá staré ID a dostává 409. Jiný PDF endpoint ve stejném logu vrací 200.

Logy neobsahují kompletní databázové záznamy ani dokazatelnou historii změn původní cesty. Příčina jejího zmizení proto zůstává neprokázaná. V původním runtime lze ovšem reprodukovat druhou závadu: nový upload stejných bajtů je označen jako duplicita a vybere starý kanonický záznam bez cesty. Reprodukce používá oba testovací záznamy stejného vlastníka se shodnou raw referencí; není kopií celé produkční databáze.

## PDF a reprodukce

Soukromě testovaný PDF má 1 452 819 bajtů a SHA-256:

```
c134aed0f69bbc6903a9781411b59039cfc6f3dfd5d22a8c7cc998396e90bc40
```

Pypdf 5.9.0 jej načetl ve strict režimu: 129 stran, 185 778 znaků, text na všech stranách, bez šifrování. PDFium 5.8.0 vykreslil všech 129 stran při scale=1.0. PyMuPDF 1.26.7 potvrdil 129 stran bez opravy struktury. To není test PDF.js v Electronu a neprokazuje shodu každého pixelu mezi renderery.

| Stejný izolovaný scénář s původními bajty PDF | Runtime 1.26.3 | Runtime 1.26.4 |
|---|---|---|
| Výběr původního ID po totožném uploadu | ano | ano |
| Odpověď PDF endpointu | 409 | 200 |
| Odpověď obsahuje přesně původní PDF bajty | ne | ano |
| Nutná konverze PDF nebo změna jeho obsahu | ne | ne |

Samostatný test ověřuje stejné databázové řádky studijních tabulek před/po dohledání kopie. Původní PDF ani kompletní uživatelské logy se s instalátorem nedistribuují.

## Proč nestačí File.hash

Zkontrolovaný upstream Open WebUI při uploadu ukládá raw referenci do `meta.file_hash`. `File.hash` se při retrieval zpracování počítá z extrahovaného textu. Dvě rozdílná PDF mohou mít stejný text; tato hodnota nesmí sloužit jako důkaz bajtové shody. Oprava proto dostupné PDF skutečně hashuje a nepřijímá neúplný či poškozený SHA-256 řetězec. U nedostupného originálu vyžaduje jeho původní `meta.file_hash`; historická hodnota `books.file_sha256` je jen vyhledávací vodítko pro kandidáty, nikoli náhrada důkazu identity originálu.

Primární zdroje zkontrolované 18. 9. 2026:

- https://raw.githubusercontent.com/open-webui/open-webui/main/backend/open_webui/routers/files.py (`upload_file_handler`)
- https://raw.githubusercontent.com/open-webui/open-webui/main/backend/open_webui/routers/retrieval.py (`process_file`)
- https://raw.githubusercontent.com/open-webui/open-webui/main/backend/open_webui/models/files.py (`FileModel`, `get_files_by_user_id`)

Upstream main je pohyblivá větev, nikoli důkaz přesného nainstalovaného zdrojového commitu. Produkční databáze nebyla poskytnuta.

## Rozsah a bezpečnost

Runtime zachovává kanonické ID při doložené bajtové shodě, obnovuje nedokončenou indexaci po explicitním uploadu a omezuje opakované chyby nedostupného souboru. Nemění Open WebUI cesty, nemigruje schéma a neodstraňuje původní knihy. Když chybí raw reference originálu, stará historie zůstává a nový upload se použije jako nová kniha. Staré nesprávné aliasy či již sloučenou historii bez dodatečných podkladů automaticky nerozděluje.

Kontrola vlastníka probíhá i po vyhledání kandidáta. Ověřují se bajty, ne pouze metadata. Jiný vlastník, jiné PDF, nejednoznačná původní UUID cesta a chyba oprávnění nevedou k automatickému náhradnímu otevření. Dosavadní autentizace a rozdělení dat podle uživatele zůstávají zachovány.

Vedlejší hlášení DLP v dodaných logách nejsou tato chyba přenosu. Oprava DLP ani jiné bezpečnostní Functions nevypíná. Kompletní logy mohou obsahovat tajné klíče a nemají se zveřejňovat.

## Distribuce a kontrola změn

Všechny tři Desktop adaptéry obsahují aktualizované Manager/Bootstrap/Pipe payloady. e-INFRA vnější installer obsahuje aktualizovaný api-wrapper, ten nový engine, runtime i DesktopRepair payload. Každá vrstva má nový SHA-256. Kořenové dispatchery, recovery režimy, Docker/Podman, BareMetal a Remote větev jsou zachovány.

`SOURCE-RECOVERY-PROVENANCE.json` zaznamenává SHA-256 původního archivu, původního a upraveného bootstrapu a přesné AST otisky funkcí. Ze 387 funkcí/metod předchozí verze není odstraněna žádná; 377 AST je beze změny, 10 bylo cíleně upraveno, 5 funkcí je nových. Samostatná historická inventura 1.26.2 zůstává v `tests/integration_baseline.json`. Inventura není náhradou funkčního testu každého výukového scénáře.
