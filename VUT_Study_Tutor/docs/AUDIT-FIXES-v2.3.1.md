# Opravy po auditu 2.2.0 a Desktop lifecycle oprava

- odstraněna paralelní distribuce se stejným číslem verze a jinými payloady;
- Generic Engine 2.0.1 nahrazen Engine 2.0.3;
- health API hodnota `asgi-prefix-gateway-v7` je oddělena od architektonického popisu;
- přidán native Bash/Python vstup;
- odstraněn alias `Server`;
- přidány E2E testy Remote, Docker, BareMetal, reverse-proxy prefix a rollback;
- Desktop Repair je mapován na `TutorOnly`, nikoli na implicitní databázovou opravu;
- Docker/Podman autodetekce zahrnuje i zastavené kontejnery;
- přidán capability-gated test neznámé budoucí verze Open WebUI;
- Desktop platforma byla znovu porovnána s oficiálním `open-webui/desktop`;
- opraveno: `Verify` již nepoužívá jednorázový pasivní backend probe, ale stejnou oficiální Electron autostart/reprobe větev jako `TutorOnly`;
- doplněny aktuální názvy Electron `userData` adresářů, logová URL a omezený dynamický port scan;
- odstraněn druhý Mark-of-the-Web dialog při použití kořenového verifikátoru;
- Tutor Event a Pipe 1.26.2 zůstaly bajtově beze změny, Desktop manager/wrappery jsou záměrně aktualizované.
