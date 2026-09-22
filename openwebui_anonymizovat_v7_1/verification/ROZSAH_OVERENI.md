# Provedené lokální ověření

49 Python komponentových testů a 12 testů se skutečným Chromium. WebUI resolver,
oprávnění, socketové propojení a poskytovatel modelu byly nahrazené testovacími
adaptéry. Samostatná komponentová kontrola načetla skutečný dočasný TXT soubor a
ověřila jeho nezměněnost. Nebyla použita žádná uživatelská data ani skutečný LLM.

Ověřena především regresní situace: již odeslaný citlivý prompt se zapnutým Toolem
otevře předvyplněný dialog; stará citlivá historie i soubor dostanou pseudonymy;
do schválení je počet volání simulovaného příjemce nula. Zrušení v obou fázích,
cizí příloha, změna politiky a nepodporovaný soubor zůstávají blokované.

Ověřeno rovněž dávkování dlouhého předvyplnění a náhledu, povinný souhlas, zachování
původního testovacího požadavku, neprovedení HTML vloženého v promptu, závěrečné
kontroly a zamítnutí nekompatibilního protokolu 7.0.

Zdrojové testy jsou přiložené pro audit. Jejich výsledek není instalací do živé
instance Open WebUI. Screenshot je z Chromium harnessu, nikoli z aplikace WebUI.
