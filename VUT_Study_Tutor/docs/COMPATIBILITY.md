# Kompatibilita

| Platforma | Stav |
|---|---|
| Oficiální Open WebUI Desktop Windows | adaptér 2.3.4 pro Electron `open-webui/desktop`; `Repair` i `Verify` umí spustit aplikaci a zjistit dynamický port |
| e-INFRA Windows Server | adaptér 2.1.8 |
| Docker/Podman | API engine 2.0.6, běžící i zastavený explicitně vybraný kontejner, publikovaný port nebo explicitní URL |
| Bare-metal Linux/Windows/macOS | API engine 2.0.6, explicitní URL; restart pouze explicitní službou/příkazem |
| Remote/web | API engine 2.0.6, HTTP/HTTPS a reverse-proxy prefix |

## Desktop hranice podpory

Desktop větev je určena pro oficiální repozitář `open-webui/desktop`, jehož Windows build používá Electron `userData`, `config.json`, `installDir`, vestavěný Python a executable `open-webui.exe`. Nejde o obecný Python server s podobnou adresářovou strukturou.

Je-li `defaultConnectionId` vzdálený, spuštění aplikace nemusí automaticky nastartovat lokální backend. Adaptér tuto volbu nepřepisuje; stav uloží do reportu a skončí s konkrétní diagnostikou. Pro striktní kontrolu již běžící instance je k dispozici `-NoAutoStartDesktop`.

## Budoucí vydání Open WebUI

Číslo verze není povolenka ke změně. Neznámá verze projde pouze po úspěšné autentizaci Functions API, přesné kontrole uložených Function zdrojů a ověření health, Canvas a CORS. Integrační test používá také syntetickou budoucí verzi 0.12.7.
