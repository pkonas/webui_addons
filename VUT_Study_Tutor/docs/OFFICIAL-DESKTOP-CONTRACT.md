# Official Open WebUI Desktop contract used by installer 2.3.4

The Desktop platform means the official Electron application from
`https://github.com/open-webui/desktop`, not a generic Python, Docker or
server deployment.

The adapter follows the public source layout of that application:

- Electron `userData` contains `config.json` and `logs/main.log` / `logs/server.log`.
- `config.json.installDir` identifies the heavyweight runtime root.
- `config.json.dataDir`, when empty, resolves to `<installDir>/data`.
- the bundled Python executable is `<installDir>/python/python.exe` on Windows.
- `localServer.port` is only the requested initial port; the application can move
  to the next available port, up to `port + 100`.
- the authoritative runtime URL is taken from the most recent `Server started:`
  or `Server started with PID ... URL:` log entry and must still answer with JSON
  from `/api/version`.
- the standard Windows executable is searched as
  `%LOCALAPPDATA%/Programs/open-webui/open-webui.exe` (plus product-name variants).

The official Electron app starts its local backend when it connects to the
virtual local connection. Consequently both `Repair` and `Verify` may launch the
Desktop executable when no live local backend exists. This is process startup,
not database mutation. Pass `-NoAutoStartDesktop` to require an already-running
backend.

If `defaultConnectionId` selects a remote connection, launching the Desktop may
not start the local backend. The report records that condition and the adapter
fails without silently changing the user's selected default connection.

Database migration remains a separate, explicit action:
`-Action DesktopDatabaseRepair`.
