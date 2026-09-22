# Anonymizovat 7.1 — chování a hranice

## Opravená chyba

V7 volala blokující `_check()` ještě před otevřením vybraného Toolu. Citlivý text
proto vůbec nemohl dojít do dialogu. V7.1 nejdříve rozliší vybraný Tool, ověří jeho
přístupová oprávnění a předá vstup dialogu. Blokující kontrola se tím **nevypíná**:
proběhne po očištění a schválení a znovu v hooku `request`.

## Běžné použití

Zapněte Anonymizovat mezi nástroji a odešlete své zadání. Text může obsahovat
rozpoznatelné citlivé údaje. Dialog jej předvyplní; nemusíte text vkládat podruhé.

Je-li v požadavku podporovaná příloha, dialog nabídne její zahrnutí. Originální
bajty se přečtou pod ověřeným vlastníkem po potvrzení souhlasu. Původní název,
extrahovaný text ani hash předaný klientem se nepoužívají jako důkaz bezpečnosti.
Přílohy lze v dialogu vynechat; jejich původní reference se potom modelu nepředají.
Nové soubory lze vybrat také přímo v dialogu. Celkový limit se vztahuje na obě skupiny.

Potvrďte souhlas a klikněte **Anonymizovat a zobrazit náhled**. Náhled obsahuje
všechny očištěné zprávy modelového kontextu, včetně dřívější historie zahrnuté v
aktuálním požadavku. Stejný údaj v historii, promptu a souboru používá stejné náhrady.
Očišťuje se pracovní kopie, nikoli databáze.

Po schválení náhledu klikněte **Předat očištěné zadání LLM**. Očištěná pracovní kopie
nahradí původní zprávy v právě běžícím modelovém požadavku. Neotevírá se jiný chat,
nekliká se programově na tlačítko odeslat a neposílá se druhá zpráva přes `postMessage`.

Zrušení, nedostupný dialog, chybějící oprávnění, změna politiky, chybný parser nebo
neúspěšná závěrečná kontrola znamenají blokaci, nikoli návrat k originálu.
Zaškrtnutí Toolu samo dialog stále neotevírá; aktivuje jej následující odeslání.

## Cesta bez běžného uploadu nových originálů

Zůstává dostupná varianta s necitlivou větou **Otevřít anonymizátor.**. S vybraným
Toolem otevře prázdný dialog. Originální text a soubory vložte teprve do něj. Nové
soubory z dialogu tento doplněk neposílá do běžného souborového úložiště WebUI.
Nejde již o jedinou povolenou cestu; opravená 7.1 podporuje i již odeslané zadání.

## Důležité omezení ukládání

**Text odeslaný běžným editorem a soubory přidané běžným uploadem již mohou být
uložené ve WebUI dříve, než se otevře dialog. Oprava je nemaže, nezpětně nepřepisuje
a nedokládá nulovou retenci.** Totéž platí pro dřívější historii. Varování a dialog
to výslovně uvádějí. Pro odstranění originálů je nutné ruční smazání vlákna a uploadů.

Uložena může zůstat původní uživatelská bublina, nikoli její očištěná pracovní kopie.
Při dalším požadavku proto historie znovu prochází kontrolou; se zapnutým nástrojem
se znovu očišťuje. Bez zapnutého nástroje může být citlivá historie znovu zablokována.

## Rozsah detekce a formátů

Detekční a dokumentové jádro je převzaté z v7. Pravidla pokrývají 14 jazyků a
rozpoznatelné strukturované údaje; neznámé jméno ve volném textu, citlivý kontext nebo
nový nestandardní zápis mohou uniknout. Povinný náhled není certifikací anonymity.

Dialog předává očištěnou textovou reprezentaci dokumentů, nikoli nový binární
DOCX/PDF. Textové a kontrolovatelné dokumenty zůstávají podporované jako ve v7.
Samostatná média, skeny bez čitelného textu, šifrované či jinak nezkontrolovatelné
soubory se nepropustí. OCR a přepis zvuku tato oprava nepřidává. Obrazové části
převáděných dokumentů se mohou vynechat; uživatel tento převod schvaluje.

Výchozí limit: 5 souborů, 5 000 000 bajtů na soubor, 10 000 000 bajtů celkem a
400 000 znaků pro kontrolované texty. Započítává se celý modelový kontext.

Kontrolované přílohy musí patřit přihlášenému uživateli. Sdílené soubory jiného
vlastníka tato konzervativní verze nepřebírá. Neprůhledné multimodální bloky nebo
nástrojová historie s `tool_calls` jsou stále nepodporované.

Parametry modelu či dodatečné zdroje mimo předané zprávy nejsou v dialogu
libovolně přepisovány. Obsah přidaný po schválení znovu kontroluje `request` a při
nálezu se požadavek zastaví. Modelové systémové prompty či alternativní integrace
mimo tyto hooky, pomocné úlohy a předchozí uploadové zpracování nejsou touto opravou
prokazatelně chráněné.

Python parsery běží lokálně v backendu. Časový limit neukončuje násilně parserové
vlákno. Některé raw hodnoty existují v paměti procesu a prohlížeče. Doplněk sám
nezapisuje originály do DB ani nespouští úklid; neovládá však obsahové logování
WebUI, proxy, socketů, tracing, cache poskytovatele úložiště nebo zálohy.

## Kompatibilita

Cílový backend je 0.11.3; jiné verze se odmítají. Jsou potřeba obě Functions/Tool
součásti 7.1 a funkční interaktivní callback `execute`. Neproběhla instalace do
živé instance WebUI ani ověření Windows, Docker či Desktop. Formou instalace jde
výhradně o Workspace Tool a globální Filter, bez úprav aplikace.
