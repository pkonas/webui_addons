# Diagnóza: falešné odmítnutí zdravé ASGI gateway

Chyba byla v instalátoru, nikoli v serverovém runtime.

- Bootstrap runtime 1.26.2 publikuje ve health JSON hodnotu `asgi-prefix-gateway-v7`.
- Engine 2.0.1 očekával `asgi-prefix-gateway-v7-no-main-router-mutation`.
- Delší řetězec byl interní architektonický popis, nikoli hodnota pole `registration_strategy`.
- Restart nemohl výsledek změnit, protože po každém restartu zdravý runtime znovu publikoval stejnou správnou API hodnotu.

Engine 2.0.2 má oddělené konstanty pro health API a dokumentační architekturu. Regresní test načte strategii přímo z dodaného bootstrapu a spustí celý `wait_for_runtime` proti lokálnímu mock endpointu.
