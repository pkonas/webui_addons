# Architektura 2.3.4

Kořenový dispatcher vybírá specializovaný adaptér. Tutor Event a Pipe runtime 1.26.5 jsou společné všem platformám.

- **Desktop Windows:** lifecycle adaptér `2.3.1-official-desktop-lifecycle-r1`, který vychází z funkčního Desktop manageru 1.26.5, ale opravuje `Verify` autostart. Používá Electron `userData`, dynamický port, oficiální executable, bezpečný process tree a explicitní DB recovery.
- **e-INFRA Windows:** adaptér 2.1.8, `runtime.json`, Caddy a vlastnicky ověřené Scheduled Tasks.
- **Docker/Podman/BareMetal/Remote:** API engine 2.0.6.

## Desktop lifecycle

1. načte `%APPDATA%\open-webui\config.json` a kompatibilní historické názvy;
2. vezme `installDir`, `dataDir` a `localServer.port`;
3. nejprve ověří aktuální URL z logu a živé loopback listenery;
4. není-li backend dostupný, `Repair` i `Verify` standardně spustí oficiální Electron executable;
5. opakovaně načte nové logy a souběžně prohledá omezený rozsah portů;
6. přijme pouze endpoint, který vrátí podporovaný JSON z `/api/version`;
7. `-NoAutoStartDesktop` launch zakáže.

Spuštění Electron aplikace není databázová oprava. Databázová migrace je dostupná pouze explicitní akcí `DesktopDatabaseRepair`.

## API transakce

API engine provádí:

1. `/api/version` a Functions capability probe;
2. autentizaci;
3. snapshot managed Functions a Valves;
4. instalaci Pipe a Event;
5. kontrolu typu, aktivity a source SHA-256;
6. health, Canvas a CORS acceptance test;
7. odstranění legacy IDs;
8. rollback při chybě.

Canvas používá ASGI prefix gateway a nemění hlavní FastAPI router Open WebUI.

## Jednotný PDF runtime

Revize `pdf-delivery-r2` je ve všech větvích včetně vnořených payloadů e-INFRA.
Desktop repair/verify/recovery obsahují přesně stejné zdroje jako `runtime/`.
e-INFRA vnitřní wrapper používá stejný API engine 2.0.6 jako `engine/`.
Desktop manager před aktualizací navíc zálohuje managed Functions a nastavení;
automatický rollback zde není implementován. Viz `PDF-HOTFIX-INTEGRATION-v2.3.2.md`.

## Vlastnictví rozměrů Canvasu

`canvas-layout-r1` ponechává nativní layout výhradně Open WebUI. Pouze náhradní pevný dock rezervuje prostor na jednom známém kořeni chatu. Koordinátor slučuje změny přes requestAnimationFrame a zruší předchozí pokus o otevření; nemá trvalý layout polling. Viz `CANVAS-LAYOUT-FIX-v2.3.4.md`.
