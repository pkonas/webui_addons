# Diagnóza: `Log segmentation self-test selhal` (2.1.5)

## Symptom

Všechny statické a Python testy prošly, ale `-Action SelfTest` skončil na
`Log segmentation self-test selhal`.

## Kořenová příčina

Adaptér 2.1.4 hledal začátek běhu výrazem obsahujícím
`\s+.+open-webui`. Část `.+` vyžadovala alespoň jeden znak před názvem
executable. Reálná hlavička s úplnou cestou proto mohla projít, ale validní
self-test hlavička `start: open-webui.exe serve ...` nikoli. Segmentace pak
vrátila řádky obou běhů a starý Tutor `ERROR` způsobil falešně pozitivní
klasifikaci.

## Oprava

Adaptér 2.1.5 používá sdílený `BackendRunStartPattern` a funkci
`Test-BackendRunStartLine`. Regresní sada ověřuje holý executable, úplnou cestu,
quoted cestu, cizí executable, jiný subcommand, izolaci předchozího běhu i
rozpoznání skutečné Tutor chyby v posledním běhu.
