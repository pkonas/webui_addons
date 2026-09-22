# Canvas reopen / resize feedback correction — 2.3.4 / 1.26.5

## Evidence and scope

The supplied `server(20260919-151528).log` records a successful Canvas request at 17:10:17.743 with the same message ID as a 10:26:42.883 open. Its HTTP status is 200. The log does not record the client element geometry or ResizeObserver callbacks; it cannot prove the exact on-device event sequence. The current part of `main(7).log` contains no matching renderer-crash stack. Historical GPU/renderer entries must not be misattributed to this incident. No raw user logs, PDF bytes or credentials are distributed in this package.

## Reproduced mechanism in the supplied runtime

`StudyRuntime._canvas_open_panel_code` installed a page-global coordinator. It measured a native iframe, derived `available` from its rectangle, and forced `width`, `max-width`, left/right margins and width transitions on **both** the chat root and the composer. It then observed the native iframe, chat and composer with ResizeObserver. A MutationObserver and an unbounded 700ms interval also ran the same synchronous sizing function. When the selected chat root contains the native side panel, the child rectangle changes as a consequence of the parent's write; crossing the half-viewport heuristic restores old styles, which reverses the change. Closing/remounting can enter this cycle. Observed targets were accumulated across remounts. Separately, opening retry observers/timers had no shared owner, and a late native mount could coexist with an already-open fallback.

The included reduced nested-flex browser fixture executes the original **unmodified bridge template** from runtime 1.26.4. It reproduces oscillating widths and ResizeObserver loop errors. The same fixture with the new bridge stays stable and makes no native layout writes. It is not a recording or full clone of the user's Open WebUI build. `docs/canvas-browser-metrics.json` and the test log report actual measured results.

## Correction

1. Native Open WebUI owns native geometry. Tutor never resizes the native chat/composer or observes their sizes for resizing.
2. Only a fixed fallback reserves space, through padding on one known outer chat root. The reserved width comes from the fallback's explicit clamped state, not an iframe measurement. Unknown structures retain an overlay rather than a guessed ancestor rewrite.
3. One animation-frame scheduler coalesces UI events. There is no permanent layout interval. The 250ms interval is ONLY the bounded initial opening retry and is cancelled on success, supersession or disposal.
4. Opening attempts and the page coordinator are single-owner; superseded attempts cannot resurrect a dock. A matching native panel arriving later closes the fallback. Closing/remounting clears old fallback ResizeObserver targets. Each native reopen continues using native sizing, with no historic pixel widths restored over it.
5. Style restoration is property-level and ownership-aware; it does not overwrite another component's later whole-style edits. Drag callbacks are frame-coalesced and released on close/cancel. Action forwarding and technical trace presentation remain available.

## Deployment / limitations

Update using the complete installer, then **fully reload the Open WebUI parent page**. On Desktop, quit the app including the tray process and restart. Replacing backend Functions alone does not execute new JavaScript in an already loaded main page. No history, database schema, PDFs, DLP settings, GPU sandbox settings, or native Open WebUI binaries are changed.

All earlier platforms and recovery branches remain in the package. The only changed runtime method ASTs are the parent bridge method and `register_routes` (the latter exposes additive health diagnostics). Full preservation is checked against the actual previous ZIP; unchanged function bodies and inner Canvas assets are hashed.

Live Windows/Electron, the exact Svelte build on the user's computer, e-INFRA services and actual Docker/Podman deployments have not been exercised in this environment. Existing installer/API regressions use their original mock backends. Browser tests do not load external content or exercise real PDF rendering; the retained PDF test suite tests the isolated ASGI runtime separately.

## Diagnostics

Health: `/study-tutor/health` → `version: 1.26.5`, `canvas_layout.revision: canvas-layout-r1`, `live_window_verified: false`.

The page-local `window.__VUT_AI_TUTOR_UI_COORDINATOR_V1220__.snapshot()` reports counters, revision, mode and active target counts without tokens, text or file IDs. No telemetry or network endpoint was added. A reopened historical native citation can work without installing a coordinator; an absent snapshot is not by itself a layout failure.

## External technical reference

For the semantics of callbacks and resize-loop errors, consult W3C Resize Observer, sections 3.4.6 and 3.6.1: https://www.w3.org/TR/resize-observer/ . The diagnosis above comes from the supplied code and local reproduction, not from assuming any current upstream Open WebUI source matches the installed application.
