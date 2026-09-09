# Universal Engine 2.0.2 – výsledky opravného testu

- Python syntax/compile: PASS
- Runtime payload Event/Pipe hash a frontmatter: PASS
- Strategie deklarovaná bootstrapem: `asgi-prefix-gateway-v7`
- Strategie přijímaná validátorem: `asgi-prefix-gateway-v7`
- Architektonický popis: `asgi-prefix-gateway-v7-no-main-router-mutation`
- `wait_for_runtime` proti JSON health + Canvas + CORS mocku: PASS
- Nesprávná záměna architektonického popisu za API hodnotu: správně odmítnuta
- Runtime bootstrap a Pipe 1.26.2: bajtově nezměněny
