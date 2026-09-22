# Anonymizovat + DLP Guard 7.1

Oprava předčasné blokace citlivého promptu při vybraném nástroji Anonymizovat.

- `anonymizovat_tool.py`: nahradit existující Tool ve Workspace.
- `dlp_guard_filter.py`: nahradit existující globální Filter Function.
- `INSTALACE_CS.md`: pouze instalace, bez testovacích kroků.
- `POUZITI_A_OMEZENI_CS.md`: ovládání a přesná omezení včetně ukládání originálů.
- `verification/`: samostatné podklady lokálního ověření.

**Aktualizujte oba soubory. Zachovejte původní ID, HMAC klíč a jejich vzájemné odkazy.**
Neponechávejte aktivní druhý starý DLP filtr. Cleanup a Action se nepoužívají.

Zapnutý Tool → odeslaný text/přílohy → předvyplněný dialog → očištění celého
předaného kontextu → schválení → opakovaná kontrola → modelová cesta.

Vypnutý Tool → původní blokující kontrola.

Nejde o ochranu před prvním uložením: běžně odeslané originály mohou zůstat uložené.
Nástroj pracuje jen s pracovní kopií aktuálního modelového požadavku.
