# Diagnóza: Scheduled Task skončí ve stavu Ready

Výpis `stav ulohy: Ready` znamená, že dlouhodobý runner backendu již neběží. Adaptér 2.1.1 čekal až do timeoutu, ale nečetl `Get-ScheduledTaskInfo.LastTaskResult` ani konec `open-webui.log`.

Druhý ověřený rozdíl proti původnímu e-INFRA instalátoru je restartovací sekvence. Původní instalátor po `Stop-ScheduledTask` volá `Stop-ManagedProcesses -RequireStopped`; adaptér 2.1.1 tento krok vynechal. Osiřelý proces tak mohl zabránit novému startu.

Adaptér 2.1.4 kopíruje vlastnický model původního instalátoru, ale zastavuje pouze backendovou větev a ponechává Caddy v provozu. Pokud úloha skončí před readiness, selže rychle a uloží diagnostický JSON. Offline změnu databáze provede jen tehdy, pokud poslední startovací log současně obsahuje Tutor identifikátor a chybu, nebo pokud je recovery výslovně nastavena na `Required`.
