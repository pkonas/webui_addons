# Bezpečnost

- Tokeny a hesla se nezapisují do reportů; secret-like pole jsou redigována.
- Loopback požadavky obcházejí systémovou HTTP proxy.
- TLS ověření je výchozí; privátní CA se předává explicitně.
- `--insecure-tls` / `-InsecureTls` je pouze diagnostická volba.
- API instalace nemění databázi Open WebUI.
- Desktop databázová oprava vyžaduje explicitní akci.
- Restart Dockeru, služby nebo příkazu je možný pouze pro explicitně vybranou platformu a podle `RestartPolicy`.
- Package manifest chrání adaptéry a runtime proti nechtěnému smíchání verzí.

- PDF fallback kontroluje autorizaci a přesné UUID, nikoli pouze název souboru.
- Desktop záloha `vut-pdf-hotfix-functions-before-*.json` obsahuje i valves a může
  obsahovat tajné hodnoty; nejde o redigovaný instalační report.
- Desktop `TutorOnly` automaticky nevrací změny zpět. API rollback zůstává zachován.
- SHA-256 není kryptografický podpis vydavatele.
