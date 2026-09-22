# Aktualizace na Anonymizovat 7.1 — pouze přes rozhraní WebUI

Balíček obsahuje náhradu **obou** existujících součástí: Workspace Tool a globální
Filter Function. Integrační cíl je backend Open WebUI **0.11.3**. Nepotřebujete
terminál, instalaci balíčků, změnu repozitáře, Action ani Event Function.

## 1. Nahraďte Workspace Tool

Otevřete **Workspace → Tools → Anonymizovat → Edit**. Nahraďte celý zdrojový kód
obsahem `anonymizovat_tool.py` z tohoto balíčku. Zachovejte ID stávajícího Toolu
(obvykle `anonymizovat`) a jeho přístupová oprávnění. Uložte změnu.

Ve Valves Toolu ponechte `guard_filter_id` rovné skutečnému ID vašeho DLP filtru.
Pokud se filtr jmenuje `dlp_guard_v6`, použijte `dlp_guard_v6`; kvůli číslu vydání
ID nepřejmenovávejte. Výchozí `dlp_guard_v7` je jen návrh pro novou instalaci.

## 2. Nahraďte globální filtr

Otevřete **Admin Panel → Functions → váš DLP Guard → Edit**. Nahraďte celý zdrojový
kód obsahem `dlp_guard_filter.py`. Zachovejte jeho ID a uložte změnu.

Ponechte **Active** a **Global** zapnuté. Ve Valves zkontrolujte pouze přiřazení:

| Nastavení filtru | Hodnota |
| --- | --- |
| `anonymizer_tool_id` | Skutečné ID Toolu z kroku 1, obvykle `anonymizovat`. |
| `hmac_key` | Váš původní náhodný tajný klíč, nejméně 32 znaků. |
| `tenant`, `key_id`, `aliases_json`, `default_phone_country` | Zachovejte dosavadní hodnoty. |

Nevytvářejte druhou současně aktivní kopii DLP Guardu. Starý filtr v6 nebo v7 může
požadavek stále zablokovat dříve, než se spustí nová větev 7.1. Staré Action a cleanup
Event Functions ponechte neaktivní. HMAC klíč nikdy nevkládejte do promptu.

## 3. Dokončete aktualizaci

Po uložení **obou** součástí obnovte stránku. V oblasti editoru vyberte v
**Integrace → Nástroje** Workspace Tool **Anonymizovat**. Jeho ID musí odpovídat
nastavení filtru a uživatel musí mít oprávnění nástroj používat.

V nové dvojici je interní protokol `dlp-workspace/7.1`. Kombinaci staré a nové součásti
filtr odmítne. Aktualizace nemění detekční politiku HMAC; se stejnou konfigurací a
identitou zůstávají dosavadní pseudonymy stejné.
