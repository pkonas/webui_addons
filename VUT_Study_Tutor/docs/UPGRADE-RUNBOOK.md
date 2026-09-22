# Postup po aktualizaci Open WebUI

1. Spusťte bezpečný package test.
2. Proveďte `Preflight` proti cílové instanci.
3. Spusťte `Verify`.
4. Pouze při neúspěchu spusťte `Repair`.
5. Zkontrolujte instalační JSON report a health kontrakt.
6. Databázové recovery používejte pouze pro Desktop a jen při prokázané chybě schématu.

## Desktop

Běžné `Verify` může spustit oficiální Electron aplikaci, pokud lokální backend neběží. To odpovídá lifecycle Desktopu a nemění databázi ani Functions. Pro čistě pasivní sondu použijte:

```powershell
.\verify-vut-ai-tutor-universal-v2.3.4.ps1 `
  -Platform Desktop `
  -DesktopInstallRoot 'D:\web-ui' `
  -NoAutoStartDesktop `
  -PromptForCredential `
  -PythonPath 'D:\Anaconda\envs\ai_services\python.exe'
```

Pokud pasivní sonda selže, spusťte Desktop ručně nebo zopakujte příkaz bez `-NoAutoStartDesktop`.

## Remote příklad

```bash
./install-vut-ai-tutor-universal-v2.3.4.sh --action preflight --platform remote --base-url https://webui.example.edu --token-file ./token.txt
./verify-vut-ai-tutor-universal-v2.3.4.sh --platform remote --base-url https://webui.example.edu --token-file ./token.txt
```

## Přechod z univerzálního 2.3.1 nebo samostatného PDF hotfixu

Nový kompletní ZIP rozbalte samostatně. Proveďte `Repair` přes kořenový skript
2.3.4 se stejnou platformou, vlastními cestami a Pythonem jako dříve. Samostatný
Desktop PDF hotfix již není nutné spouštět. U Desktopu nejprve uložte práci.
`DesktopDatabaseRepair` není součástí běžné PDF opravy.

Po instalaci ověřte runtime `1.26.5`, `pdf_delivery.revision=pdf-delivery-r2` a
otevřete stejnou knihu v novém panelu Tutora. Health neověřuje skutečný dokument.
Zálohy Functions uchovejte soukromě; neposílejte je jako diagnostický report.

## Přechod na opravu Canvas layoutu 2.3.4

Po `Repair` plně obnovte hlavní stránku Open WebUI; na Desktopu aplikaci ukončete včetně oznamovací oblasti a znovu spusťte. Pouhé zavření iframe nenahradí dříve zavedený parent-page JavaScript. Ověřte `canvas_layout.revision=canvas-layout-r1`. Hodnota `live_window_verified=false` je záměrná: health nepotvrzuje geometrii aktuálního okna. Vyzkoušejte opakované zavření/znovuotevření a změnu nativního dělicího panelu. Není potřeba mazat studijní historii, PDF ani nastavení.
