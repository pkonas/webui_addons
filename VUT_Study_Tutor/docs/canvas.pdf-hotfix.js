window.__STUDY_CANVAS_MAIN_LOADED__ = true;
const boot = window.__STUDY_BOOT || { step() {}, fail() {}, finish() {} };
boot.step(10, "Spouštím VUT AI Tutor Canvas…", "Načetl se hlavní modul rozhraní.");

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  token: "",
  bridge: "",
  panelMode: false,
  layout: { reader_ratio: 0.66, dock_tab: "guidance", dock_collapsed: true, mode: "side-drawer-v3", drawer_width: 390, dock_side: "right" },
  layoutSaveTimer: null,
  dockAutoCloseTimer: null,
  dockHoverTimer: null,
  sessionId: "",
  data: null,
  activeBook: null,
  pdfjs: null,
  pdfViewerLib: null,
  pdf: null,
  pdfViewer: null,
  pdfLinkService: null,
  pdfFindController: null,
  pdfEventBus: null,
  pdfLoadingTask: null,
  pageRenderTask: null,
  textLayerTask: null,
  pdfViewerReady: false,
  fitWidthMode: true,
  pageViewport: null,
  pageTextContent: null,
  pageTextItems: [],
  pageTextSpans: [],
  renderGeneration: 0,
  pdfLoadGeneration: 0,
  pdfModuleAttempt: 0,
  pdfBundleKind: null,
  pdfBundleLabel: "",
  pdfImageResourcesPath: "/study-tutor/pdfjs/legacy/web/images/",
  pdfViewerStyleHref: "/study-tutor/pdfjs/web/pdf_viewer.css",
  lastRendererError: null,
  pageLabels: null,
  browserToc: [],
  page: 1,
  scale: 1.0,
  currentSelection: null,
  lastActivityIds: new Set(),
  pollTimer: null,
  fallbackMode: false,
  activeView: "book",
  mapData: null,
  mapParent: "root",
  mapSelected: null,
  mapStatus: null,
  mapMode: "auto",
  tocData: [],
  learningPath: null,
  learningPathTemplates: [],
  toolCapabilities: [],
  toolInventory: [],
  toolCatalogRevision: 0,
  toolCatalogUpdatedAt: 0,
  toolCatalogLastTurnAt: 0,
  toolCatalogSummary: {},
  toolCatalogNote: "",
  toolCatalogFilter: "",
  toolInventoryLimit: 180,
  toolPollBusy: false,
  toolLastPollAt: 0,
  mapRevision: 0,
  mapNodeIds: new Set(),
  mapNodeLookup: new Map(),
  mapHovered: null,
  mapWheelDelta: 0,
  mapWheelDirection: 0,
  mapWheelTimer: null,
  mapWheelBusy: false,
  wheelPageDelta: 0,
  wheelPageTimer: null,
  wheelTransitioning: false,
  actionPending: false,
  actionBridge: "",
  actionRequests: new Map(),
  confirmResolver: null,
  confirmPreviousFocus: null,
};

const el = {
  app: $("#app"), subtitle: $("#subtitle"), documentControls: $("#document-controls"),
  indexStatus: $("#index-status"), addBook: $("#add-book"), onboarding: $("#onboarding"),
  processingStrip: $("#processing-strip"), processingLabel: $("#processing-label"),
  processingDetail: $("#processing-detail"), processingMeter: $("#processing-meter"),
  workspace: $("#workspace"), workspaceResizer: $("#workspace-resizer"), supportDock: $("#support-dock"), dockContent: $("#dock-content"), dockTitle: $("#dock-title"), dockRails: $$(".edge-rail"), dockCollapse: $("#dock-collapse"), dockTabs: $$("[data-dock-tab]"), selectionDockBadge: $("#selection-dock-badge"), selectionModule: $("#selection-module"), dropZone: $("#drop-zone"), fileInput: $("#file-input"),
  dialogFileInput: $("#dialog-file-input"), uploadDialog: $("#upload-dialog"), uploadDialogClose: $("#upload-dialog-close"),
  uploadProgress: $("#upload-progress"), uploadBar: $("#upload-bar"), uploadLabel: $("#upload-label"),
  existingLibrary: $("#existing-library"), onboardingBooks: $("#onboarding-books"), installDemo: $("#install-demo"),
  bookList: $("#book-list"), refreshState: $("#refresh-state"),
  prevPage: $("#prev-page"), nextPage: $("#next-page"), pageInput: $("#page-input"),
  pageTotal: $("#page-total"), zoomOut: $("#zoom-out"), zoomIn: $("#zoom-in"),
  zoomLabel: $("#zoom-label"), fitWidth: $("#fit-width"),
  readerMessage: $("#reader-message"), pageStage: $("#page-stage"),
  rendererError: $("#renderer-error"), rendererErrorText: $("#renderer-error-text"),
  rendererErrorDetail: $("#renderer-error-detail"), rendererRetry: $("#renderer-retry"),
  rendererUseText: $("#renderer-use-text"), viewerContainer: $("#viewer-container"),
  pageRenderHost: $("#page-render-host"), pageShell: $("#page-shell"), pageCanvas: $("#page-canvas"),
  pageTextLayer: $("#page-text-layer"), selectionOverlay: $("#selection-overlay"),
  pageRenderState: $("#page-render-state"), pageRenderLabel: $("#page-render-label"), pdfViewer: $("#page-shell"),
  textFallback: $("#text-fallback"), fallbackContent: $("#fallback-content"),
  selectionPopover: $("#selection-popover"), selectionCard: $("#selection-card"),
  selectionActions: $("#selection-actions"), scopeLabel: $("#scope-label"),
  searchForm: $("#search-form"), searchInput: $("#search-input"), searchResults: $("#search-results"),
  viewBook: $("#view-book"), viewMap: $("#view-map"), viewToc: $("#view-toc"), viewPath: $("#view-path"),
  bookView: $("#book-view"), mapView: $("#map-view"), tocView: $("#toc-view"), pathView: $("#path-view"),
  mapBreadcrumbs: $("#map-breadcrumbs"), mapUp: $("#map-up"), mapDown: $("#map-down"),
  mapLevelLabel: $("#map-level-label"), mapRebuild: $("#map-rebuild"),
  mapDeepAnalyze: $("#map-deep-analyze"), mapModeBadge: $("#map-mode-badge"),
  mapStatusBox: $("#map-status"), mapStatusText: $("#map-status-text"), mapProgressBar: $("#map-progress-bar"),
  mapLayout: $("#map-layout"), mapCanvasWrap: $("#map-canvas-wrap"), conceptMap: $("#concept-map"), mapDetail: $("#map-detail"),
  tocStatus: $("#toc-status"), tocList: $("#toc-list"), tocFilter: $("#toc-filter"),
  pathScrollRegion: $("#path-scroll-region"), pathEmpty: $("#path-empty"), pathContent: $("#path-content"), pathName: $("#path-name"),
  pathDescription: $("#path-description"), pathTags: $("#path-tags"), pathMetaSummary: $("#path-meta-summary"),
  pathGoalSelect: $("#path-goal-select"), pathGoalDetail: $("#path-goal-detail"), pathMetadata: $("#path-metadata"),
  pathPhases: $("#path-phases"), pathPhaseStatus: $("#path-phase-status"), pathSections: $("#path-sections"),
  pathWarnings: $("#path-warnings"), pathFileInput: $("#path-file-input"), pathEmptyFileInput: $("#path-empty-file-input"), pathSwitchFileInput: $("#path-switch-file-input"),
  builtinPathGridEmpty: $("#builtin-path-grid-empty"), builtinPathGridActive: $("#builtin-path-grid-active"), pathRemove: $("#path-remove"),
  progressList: $("#progress-list"), recommendation: $("#recommendation"),
  recommendedAction: $("#recommended-action"), teachPage: $("#teach-page"), quizPage: $("#quiz-page"),
  testPage: $("#test-page"), cardsPage: $("#cards-page"), activityList: $("#activity-list"),
  refreshActivities: $("#refresh-activities"), activityDialog: $("#activity-dialog"), activityDialogClose: $("#activity-dialog-close"),
  activityContent: $("#activity-content"), modelSelect: $("#model-select"), toast: $("#toast"),
  selectionToolPerspectives: $("#selection-tool-perspectives"), selectionToolActions: $("#selection-tool-actions"),
  pageToolPerspectives: $("#page-tool-perspectives"), pageToolActions: $("#page-tool-actions"), toolCatalogStatus: $("#tool-catalog-status"),
  selectionToolActionsPopover: $("#selection-tool-actions-popover"), toolTabActions: $("#tool-tab-actions"),
  toolInventorySummary: $("#tool-inventory-summary"), toolInventoryList: $("#tool-inventory-list"), toolDockBadge: $("#tool-dock-badge"),
  toolCatalogNote: $("#tool-catalog-note"), refreshToolCatalog: $("#refresh-tool-catalog"),
  toolInventoryFilter: $("#tool-inventory-filter"), toolInventoryMore: $("#tool-inventory-more"),
  confirmDialog: $("#confirm-dialog"), confirmDialogTitle: $("#confirm-dialog-title"),
  confirmDialogMessage: $("#confirm-dialog-message"), confirmDialogDetail: $("#confirm-dialog-detail"),
  confirmDialogIcon: $("#confirm-dialog-icon"), confirmDialogCancel: $("#confirm-dialog-cancel"),
  confirmDialogAccept: $("#confirm-dialog-accept"), confirmDialogClose: $("#confirm-dialog-close"),
};

function uniqueBooks(items) {
  const result = [];
  const seen = new Set();
  for (const book of items || []) {
    if (book?.canonical_file_id) continue;
    const key = String(book?.file_sha256 || book?.file_id || "");
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(book);
  }
  return result;
}

function dockSideForTab(tab) {
  return ["library", "search", "progress"].includes(String(tab || "")) ? "left" : "right";
}

function dockTitleForTab(tab) {
  return ({ guidance: "Výuka", tools: "Ověřené pohledy", library: "Moje knihy", search: "Hledat v knize", progress: "Studijní pokrok", activities: "Aktivity a model" })[tab] || "Studijní nástroje";
}

function normalizeLayout(raw = {}) {
  const allowed = new Set(["guidance", "tools", "library", "search", "progress", "activities"]);
  const tab = allowed.has(String(raw.dock_tab || "")) ? String(raw.dock_tab) : "guidance";
  const dynamicMode = String(raw.mode || "");
  const migrated = dynamicMode === "side-drawer-v3";
  const width = Math.max(280, Math.min(720, Number(raw.drawer_width ?? 390)));
  return {
    reader_ratio: Math.max(0.38, Math.min(0.82, Number(raw.reader_ratio ?? 0.66))),
    dock_tab: tab,
    dock_collapsed: migrated ? Boolean(raw.dock_collapsed) : true,
    dock_side: ["left", "right"].includes(String(raw.dock_side || "")) ? String(raw.dock_side) : dockSideForTab(tab),
    drawer_width: width,
    mode: "side-drawer-v3",
  };
}

function cancelDockAutoClose() {
  clearTimeout(state.dockAutoCloseTimer);
  state.dockAutoCloseTimer = null;
}

function scheduleDockAutoClose(delay = 650) {
  cancelDockAutoClose();
  state.dockAutoCloseTimer = setTimeout(() => {
    if (el.supportDock?.matches(":hover") || el.supportDock?.matches(":focus-within")) return;
    if (el.dockRails?.some(rail => rail.matches(":hover"))) return;
    applyLayout({ dock_collapsed: true }, true);
  }, delay);
}

function applyDockTab(tab, persist = true, openPanel = true) {
  const side = dockSideForTab(tab);
  const next = normalizeLayout({ ...state.layout, dock_tab: tab, dock_side: side, dock_collapsed: openPanel ? false : state.layout.dock_collapsed });
  state.layout = next;
  if (el.supportDock) el.supportDock.dataset.side = side;
  if (el.dockTitle) el.dockTitle.textContent = dockTitleForTab(tab);
  el.dockTabs.forEach(button => {
    const active = button.dataset.dockTab === next.dock_tab && !next.dock_collapsed;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
    button.setAttribute("aria-expanded", active ? "true" : "false");
  });
  $$('[data-dock-group]').forEach(section => section.classList.toggle("dock-visible", section.dataset.dockGroup === next.dock_tab));
  if (el.dockContent) el.dockContent.dataset.activeTab = next.dock_tab;
  if (next.dock_tab === "tools" && openPanel && Date.now() - state.toolLastPollAt > 1200) {
    refreshToolCatalog(false).catch(() => {});
  }
  if (persist) queueLayoutSave();
}

function applyLayout(raw = {}, persist = false) {
  state.layout = normalizeLayout({ ...state.layout, ...raw });
  el.workspace?.style.setProperty("--drawer-width", `${Math.round(state.layout.drawer_width)}px`);
  el.workspace?.classList.toggle("dock-collapsed", state.layout.dock_collapsed);
  if (el.supportDock) el.supportDock.dataset.side = state.layout.dock_side || dockSideForTab(state.layout.dock_tab);
  if (el.dockCollapse) {
    el.dockCollapse.textContent = "×";
    el.dockCollapse.setAttribute("aria-expanded", state.layout.dock_collapsed ? "false" : "true");
  }
  applyDockTab(state.layout.dock_tab, false, false);
  if (!state.layout.dock_collapsed) cancelDockAutoClose();
  if (persist) queueLayoutSave();
}

function queueLayoutSave() {
  clearTimeout(state.layoutSaveTimer);
  state.layoutSaveTimer = setTimeout(() => {
    api("/study-tutor/api/settings/layout", { method: "POST", body: JSON.stringify(state.layout) }).catch(() => {});
  }, 350);
}

function bindWorkspaceLayout() {
  el.dockTabs.forEach(button => {
    const open = () => {
      clearTimeout(state.dockHoverTimer);
      const tab = button.dataset.dockTab;
      applyLayout({ dock_tab: tab, dock_side: button.dataset.dockSide || dockSideForTab(tab), dock_collapsed: false }, true);
    };
    button.addEventListener("click", () => {
      const tab = button.dataset.dockTab;
      const closeCurrent = !state.layout.dock_collapsed && state.layout.dock_tab === tab;
      if (closeCurrent) applyLayout({ dock_collapsed: true }, true);
      else open();
    });
    button.addEventListener("pointerenter", () => {
      clearTimeout(state.dockHoverTimer);
      state.dockHoverTimer = setTimeout(open, 170);
      cancelDockAutoClose();
    });
    button.addEventListener("pointerleave", () => { clearTimeout(state.dockHoverTimer); scheduleDockAutoClose(760); });
  });
  el.dockRails?.forEach(rail => {
    rail.addEventListener("pointerenter", cancelDockAutoClose);
    rail.addEventListener("pointerleave", () => scheduleDockAutoClose(760));
  });
  el.supportDock?.addEventListener("pointerenter", cancelDockAutoClose);
  el.supportDock?.addEventListener("pointerleave", () => scheduleDockAutoClose(620));
  el.dockCollapse?.addEventListener("click", () => applyLayout({ dock_collapsed: true }, true));
  document.addEventListener("keydown", event => { if (event.key === "Escape" && !state.layout.dock_collapsed) applyLayout({ dock_collapsed: true }, true); });

  const resizer = el.workspaceResizer;
  if (!resizer || !el.supportDock) return;
  let dragging = false;
  const update = clientX => {
    if (!dragging || state.layout.dock_collapsed) return;
    const viewportWidth = Math.max(320, el.workspace?.getBoundingClientRect().width || window.innerWidth);
    const width = state.layout.dock_side === "left" ? clientX : viewportWidth - clientX;
    applyLayout({ drawer_width: Math.max(280, Math.min(Math.min(720, viewportWidth - 58), width)) }, false);
  };
  resizer.addEventListener("pointerdown", event => {
    if (state.layout.dock_collapsed) return;
    dragging = true;
    cancelDockAutoClose();
    resizer.classList.add("dragging");
    resizer.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  });
  resizer.addEventListener("pointermove", event => update(event.clientX));
  const finish = event => {
    if (!dragging) return;
    update(event.clientX);
    dragging = false;
    resizer.classList.remove("dragging");
    queueLayoutSave();
  };
  resizer.addEventListener("pointerup", finish);
  resizer.addEventListener("pointercancel", finish);
  resizer.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key) || state.layout.dock_collapsed) return;
    event.preventDefault();
    const physicalDelta = event.key === "ArrowRight" ? 24 : -24;
    const delta = state.layout.dock_side === "left" ? physicalDelta : -physicalDelta;
    applyLayout({ drawer_width: state.layout.drawer_width + delta }, true);
  });
}

function withLayoutRerender() {
  // The side drawer overlays the reader instead of resizing it, so PDF re-rendering is not needed.
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function foldText(value) {
  return String(value ?? "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("cs");
}

async function verifyRuntimeRoute() {
  boot.step(16, "Ověřuji lokální službu VUT AI Tutor…", "Kontroluji, že Canvas neobsluhuje kořenová SPA stránka Open WebUI.");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const url = new URL("/study-tutor/health", location.href);
    url.searchParams.set("t", String(Date.now()));
    const response = await fetch(url, { cache: "no-store", signal: controller.signal });
    const contentType = response.headers.get("content-type") || "";
    if (!response.ok) throw new Error(`Kontrola pluginu vrátila HTTP ${response.status}.`);
    if (!contentType.includes("application/json")) {
      throw new Error("Místo služby VUT AI Tutor byla načtena hlavní stránka Open WebUI. Routy pluginu jsou ve špatném pořadí.");
    }
    const payload = await response.json();
    if (payload?.marker !== "study-tutor-canvas" || payload?.ok !== true) {
      throw new Error("Lokální endpoint VUT AI Tutor nevrátil očekávanou odpověď.");
    }
    boot.step(23, "Lokální služba je dostupná", `VUT AI Tutor ${payload.version || ""}; připravuji bezpečnou relaci.`);
    return payload;
  } catch (error) {
    if (error?.name === "AbortError") throw new Error("Lokální endpoint VUT AI Tutor neodpověděl do 8 sekund.");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function showToast(message, duration = 3600) {
  el.toast.textContent = message;
  el.toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { el.toast.hidden = true; }, duration);
}

function reportHeight() {
  if (state.panelMode) return;
  const height = Math.max(860, document.documentElement.scrollHeight);
  parent.postMessage({ type: "iframe:height", height }, "*");
}

function safeStoreGet(key) {
  try { return sessionStorage.getItem(key) || ""; } catch (_) { return ""; }
}
function safeStoreSet(key, value) {
  try { sessionStorage.setItem(key, value); } catch (_) { /* opaque sandbox */ }
}

function decodeToken(token) {
  try {
    const part = token.split(".")[0].replaceAll("-", "+").replaceAll("_", "/");
    const padded = part + "=".repeat((4 - part.length % 4) % 4);
    return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(padded), c => c.charCodeAt(0))));
  } catch (_) { return {}; }
}

async function initializeToken() {
  boot.step(27, "Ověřuji studijní relaci…", "Canvas si bezpečně vyžádá relaci z pravého panelu Open WebUI.");
  const hash = new URLSearchParams(location.hash.replace(/^#/, ""));
  const panelQuery = new URLSearchParams(location.search);
  state.panelMode = panelQuery.get("panel") === "1" || panelQuery.has("source_id") || panelQuery.has("message_id");
  state.bridge = hash.get("bridge") || "";
  state.actionBridge = hash.get("action_bridge") || "";
  state.sessionId = hash.get("session_id") || "";
  const initialView = hash.get("view") || "book";
  state.activeView = ["book", "map", "toc", "path"].includes(initialView) ? initialView : "book";

  const incoming = hash.get("token") || "";
  const tokenKey = () => `studyTutorToken:${state.sessionId || "default"}`;
  const isUsable = (token) => {
    if (!token) return false;
    const payload = decodeToken(token);
    return !payload.exp || Number(payload.exp) > Math.floor(Date.now() / 1000) + 30;
  };

  if (incoming && isUsable(incoming)) {
    state.token = incoming;
    safeStoreSet(tokenKey(), incoming);
    hash.delete("token");
    history.replaceState(null, "", `${location.pathname}${location.search}#${hash.toString()}`);
  } else {
    const cached = safeStoreGet(tokenKey());
    if (isUsable(cached)) state.token = cached;
  }
  if (!state.sessionId && state.token) state.sessionId = decodeToken(state.token).sid || "";
  if (state.token) return;

  const payloadRequestId = `study-tutor-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  state.token = await new Promise((resolve) => {
    let settled = false;
    let timer = null;
    const finish = (token = "") => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      window.removeEventListener("message", listener);
      resolve(token);
    };
    const applyPanelPayload = (payload) => {
      if (payload && typeof payload === "object") state.panelMode = true;
      const config = payload?.source?.study_tutor
        || payload?.study_tutor
        || payload?.source?.source?.study_tutor
        || payload?.data?.source?.study_tutor
        || null;
      if (!config || typeof config !== "object") return "";
      if (typeof config.session_id === "string" && config.session_id) state.sessionId = config.session_id;
      if (typeof config.action_bridge === "string" && config.action_bridge) state.actionBridge = config.action_bridge;
      if (["book", "map", "toc", "path"].includes(config.initial_view)) state.activeView = config.initial_view;
      return typeof config.token === "string" ? config.token : "";
    };
    const listener = (event) => {
      if (event.source !== parent || !event.data) return;
      if (event.data.type === "payload" && event.data.requestId === payloadRequestId) {
        const token = applyPanelPayload(event.data.payload);
        if (isUsable(token)) finish(token);
        return;
      }
      if (event.data.type === "study:token" && event.data.bridge === state.bridge) {
        const token = typeof event.data.token === "string" ? event.data.token : "";
        if (isUsable(token)) finish(token);
      }
    };
    window.addEventListener("message", listener);
    // Native Open WebUI right-side Embeds panel.
    parent.postMessage({ type: "payload", requestId: payloadRequestId }, "*");
    // Backward compatibility with VUT AI Tutor <= 1.3 inline wrapper.
    parent.postMessage({ type: "study:token:request", bridge: state.bridge }, "*");
    timer = setTimeout(() => finish(""), 8000);
  });
  if (state.token) {
    safeStoreSet(tokenKey(), state.token);
    boot.step(38, "Studijní relace je ověřena", "Načítám knihovnu, stav indexace a pedagogická nastavení.");
  }
}

function apiUrl(path, query = {}) {
  const url = new URL(path, location.href);
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  return url.toString();
}


function settleCanvasConfirmation(accepted) {
  const resolver = state.confirmResolver;
  if (!resolver) return;
  state.confirmResolver = null;
  const previousFocus = state.confirmPreviousFocus;
  state.confirmPreviousFocus = null;
  if (el.confirmDialog) {
    try {
      if (el.confirmDialog.open && typeof el.confirmDialog.close === "function") el.confirmDialog.close(accepted ? "accepted" : "cancelled");
      else el.confirmDialog.removeAttribute("open");
    } catch (_) {
      el.confirmDialog.removeAttribute("open");
    }
    el.confirmDialog.removeAttribute("data-fallback-open");
  }
  resolver(Boolean(accepted));
  if (previousFocus && typeof previousFocus.focus === "function") {
    requestAnimationFrame(() => { try { previousFocus.focus({ preventScroll: true }); } catch (_) { previousFocus.focus(); } });
  }
}


function closeCanvasDialog(dialog, reason = "outside") {
  if (!dialog) return;
  if (dialog === el.confirmDialog) {
    if (state.confirmResolver) settleCanvasConfirmation(false);
    return;
  }
  try {
    if (dialog.open && typeof dialog.close === "function") dialog.close(reason);
    else dialog.removeAttribute("open");
  } catch (_) {
    dialog.removeAttribute("open");
  }
  dialog.removeAttribute("data-fallback-open");
}

function dismissDynamicWindows({ keep = null, reason = "outside" } = {}) {
  if (keep !== "dock" && !state.layout.dock_collapsed) applyLayout({ dock_collapsed: true }, true);
  if (keep !== "selection" && el.selectionPopover && !el.selectionPopover.hidden) el.selectionPopover.hidden = true;
  if (keep !== "confirm" && (el.confirmDialog?.open || el.confirmDialog?.hasAttribute("data-fallback-open"))) closeCanvasDialog(el.confirmDialog, reason);
  if (keep !== "activity" && (el.activityDialog?.open || el.activityDialog?.hasAttribute("data-fallback-open"))) closeCanvasDialog(el.activityDialog, reason);
  if (keep !== "upload" && (el.uploadDialog?.open || el.uploadDialog?.hasAttribute("data-fallback-open"))) closeCanvasDialog(el.uploadDialog, reason);
}

function bindOutsideDynamicDismissal() {
  const dynamicContainers = () => [el.supportDock, el.selectionPopover, el.confirmDialog, el.activityDialog, el.uploadDialog, ...(el.dockRails || [])].filter(Boolean);
  document.addEventListener("pointerdown", event => {
    const path = typeof event.composedPath === "function" ? event.composedPath() : [];
    const inside = node => Boolean(node && (path.includes(node) || node.contains?.(event.target)));

    // A click on a dialog backdrop is represented by the dialog element itself.
    if ((el.confirmDialog?.open || el.confirmDialog?.hasAttribute("data-fallback-open")) && event.target === el.confirmDialog) {
      settleCanvasConfirmation(false);
      return;
    }
    if ((el.activityDialog?.open || el.activityDialog?.hasAttribute("data-fallback-open")) && event.target === el.activityDialog) {
      closeCanvasDialog(el.activityDialog, "outside");
      return;
    }
    if ((el.uploadDialog?.open || el.uploadDialog?.hasAttribute("data-fallback-open")) && event.target === el.uploadDialog) {
      closeCanvasDialog(el.uploadDialog, "outside");
      return;
    }

    const containers = dynamicContainers();
    if (containers.some(inside)) return;
    dismissDynamicWindows({ reason: "outside" });
  }, true);
}

function requestCanvasConfirmation({
  title = "Potvrdit akci",
  message = "Opravdu chcete pokračovat?",
  detail = "",
  acceptLabel = "Pokračovat",
  cancelLabel = "Zrušit",
  icon = "⚙",
} = {}) {
  if (!el.confirmDialog || !el.confirmDialogAccept || !el.confirmDialogCancel) {
    showToast("Potvrzovací dialog se nepodařilo otevřít. Akce nebyla spuštěna.", 6500);
    return Promise.resolve(false);
  }
  if (state.confirmResolver) settleCanvasConfirmation(false);
  el.confirmDialogTitle.textContent = String(title || "Potvrdit akci");
  el.confirmDialogMessage.textContent = String(message || "Opravdu chcete pokračovat?");
  el.confirmDialogIcon.textContent = String(icon || "⚙");
  el.confirmDialogAccept.textContent = String(acceptLabel || "Pokračovat");
  el.confirmDialogCancel.textContent = String(cancelLabel || "Zrušit");
  const detailText = String(detail || "").trim();
  el.confirmDialogDetail.hidden = !detailText;
  el.confirmDialogDetail.textContent = detailText;
  state.confirmPreviousFocus = document.activeElement;
  return new Promise((resolve) => {
    state.confirmResolver = resolve;
    try {
      if (typeof el.confirmDialog.showModal === "function") el.confirmDialog.showModal();
      else {
        el.confirmDialog.setAttribute("open", "");
        el.confirmDialog.setAttribute("data-fallback-open", "true");
      }
    } catch (_) {
      el.confirmDialog.setAttribute("open", "");
      el.confirmDialog.setAttribute("data-fallback-open", "true");
    }
    requestAnimationFrame(() => el.confirmDialogAccept?.focus());
  });
}

async function api(path, options = {}, query = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(apiUrl(path, query), { ...options, headers });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
    throw new Error(detail);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

function waitForActionAck(requestId, timeoutMs = 6500) {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      state.actionRequests.delete(requestId);
      resolve(false);
    }, timeoutMs);
    state.actionRequests.set(requestId, (ok) => {
      clearTimeout(timer);
      state.actionRequests.delete(requestId);
      resolve(Boolean(ok));
    });
  });
}

async function sendPrompt(text, submit = true) {
  const requestId = `vut-action-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  if (state.actionBridge) {
    const ack = waitForActionAck(requestId);
    parent.postMessage({
      type: "study:tutor-action",
      bridge: state.actionBridge,
      requestId,
      text,
      submit,
      source: "vut-ai-tutor-canvas",
    }, "*");
    if (await ack) {
      showToast(submit
        ? "Požadavek byl odeslán tutorovi; Canvas zůstává na aktuální knize."
        : "Požadavek byl vložen do chatu.", 4500);
      return true;
    }
  }
  // Compatibility path for older Open WebUI builds. The marker still binds the
  // request to one exact session, book and selection on the backend.
  parent.postMessage({ type: submit ? "input:prompt:submit" : "input:prompt", text }, "*");
  showToast(submit
    ? "Požadavek byl předán přes kompatibilní chatový most. Výběr zůstává uložený."
    : "Požadavek byl vložen do chatu.", 5000);
  return false;
}

const VUT_LATEX_SYMBOLS = Object.freeze({
  "α":"\\alpha", "β":"\\beta", "γ":"\\gamma", "δ":"\\delta", "ε":"\\varepsilon",
  "ζ":"\\zeta", "η":"\\eta", "θ":"\\theta", "ι":"\\iota", "κ":"\\kappa", "λ":"\\lambda",
  "μ":"\\mu", "ν":"\\nu", "ξ":"\\xi", "π":"\\pi", "ρ":"\\rho", "σ":"\\sigma",
  "τ":"\\tau", "υ":"\\upsilon", "φ":"\\varphi", "χ":"\\chi", "ψ":"\\psi", "ω":"\\omega",
  "Γ":"\\Gamma", "Δ":"\\Delta", "Θ":"\\Theta", "Λ":"\\Lambda", "Ξ":"\\Xi", "Π":"\\Pi",
  "Σ":"\\Sigma", "Φ":"\\Phi", "Ψ":"\\Psi", "Ω":"\\Omega",
  "∞":"\\infty", "∂":"\\partial", "∇":"\\nabla", "∑":"\\sum", "∏":"\\prod",
  "∫":"\\int", "∬":"\\iint", "∭":"\\iiint", "√":"\\sqrt{}", "∈":"\\in", "∉":"\\notin",
  "⊂":"\\subset", "⊆":"\\subseteq", "⊃":"\\supset", "⊇":"\\supseteq", "∪":"\\cup", "∩":"\\cap",
  "≤":"\\le", "≥":"\\ge", "≠":"\\ne", "≈":"\\approx", "≃":"\\simeq", "≅":"\\cong",
  "→":"\\to", "↦":"\\mapsto", "⇒":"\\Rightarrow", "⇔":"\\Leftrightarrow", "←":"\\leftarrow",
  "±":"\\pm", "∓":"\\mp", "×":"\\times", "÷":"\\div", "·":"\\cdot", "∘":"\\circ",
  "⊗":"\\otimes", "⊕":"\\oplus", "⊥":"\\perp", "∥":"\\parallel", "∝":"\\propto",
  "∀":"\\forall", "∃":"\\exists", "¬":"\\neg", "∧":"\\land", "∨":"\\lor", "∅":"\\varnothing",
  "ℝ":"\\mathbb{R}", "ℂ":"\\mathbb{C}", "ℤ":"\\mathbb{Z}", "ℕ":"\\mathbb{N}", "ℚ":"\\mathbb{Q}",
  "−":"-", "–":"-", "—":"-", "⋯":"\\cdots", "…":"\\ldots"
});
const VUT_SUPERSCRIPTS = Object.freeze({"⁰":"0","¹":"1","²":"2","³":"3","⁴":"4","⁵":"5","⁶":"6","⁷":"7","⁸":"8","⁹":"9","⁺":"+","⁻":"-","⁼":"=","⁽":"(","⁾":")","ⁿ":"n","ⁱ":"i"});
const VUT_SUBSCRIPTS = Object.freeze({"₀":"0","₁":"1","₂":"2","₃":"3","₄":"4","₅":"5","₆":"6","₇":"7","₈":"8","₉":"9","₊":"+","₋":"-","₌":"=","₍":"(","₎":")","ₐ":"a","ₑ":"e","ₕ":"h","ᵢ":"i","ⱼ":"j","ₖ":"k","ₗ":"l","ₘ":"m","ₙ":"n","ₒ":"o","ₚ":"p","ᵣ":"r","ₛ":"s","ₜ":"t","ₓ":"x"});

function normalizeSelectedText(value) {
  return String(value || "")
    .replace(/\r\n?/g, "\n")
    .replace(/[ \t\f\v]+/g, " ")
    .replace(/ *\n */g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function normalizeSpatialText(value) {
  return String(value || "")
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map(line => line.replace(/\t/g, "    ").replace(/[ \f\v]+$/g, "").slice(0, 260))
    .join("\n")
    .replace(/\n{4,}/g, "\n\n\n")
    .trim();
}

function rectanglesIntersect(first, second) {
  return first.left < second.right && first.right > second.left && first.top < second.bottom && first.bottom > second.top;
}

function annotateTextLayerSpans(container, textContent) {
  const items = (textContent?.items || []).filter(item => item && typeof item.str === "string" && item.str.length);
  const spans = Array.from(container.querySelectorAll("span")).filter(span => String(span.textContent || "").length);
  state.pageTextContent = textContent || null;
  state.pageTextItems = items;
  state.pageTextSpans = spans;
  let spanCursor = 0;
  for (let itemIndex = 0; itemIndex < items.length && spanCursor < spans.length; itemIndex += 1) {
    const item = items[itemIndex];
    let span = spans[spanCursor++];
    // Marked-content wrappers can add empty/decorative spans. Search a few nodes ahead
    // for the closest textual match without making selection dependent on exact equality.
    if (span && normalizeSelectedText(span.textContent) !== normalizeSelectedText(item.str)) {
      for (let lookAhead = spanCursor; lookAhead < Math.min(spans.length, spanCursor + 5); lookAhead += 1) {
        if (normalizeSelectedText(spans[lookAhead].textContent) === normalizeSelectedText(item.str)) {
          span = spans[lookAhead];
          spanCursor = lookAhead + 1;
          break;
        }
      }
    }
    if (span) span.dataset.vutTextIndex = String(itemIndex);
  }
}

function textOffsetWithin(span, node, offset) {
  if (!span || !node || !span.contains(node)) return null;
  const walker = document.createTreeWalker(span, NodeFilter.SHOW_TEXT);
  let total = 0;
  for (let current = walker.nextNode(); current; current = walker.nextNode()) {
    if (current === node) return total + Math.max(0, Math.min(Number(offset || 0), current.nodeValue?.length || 0));
    total += current.nodeValue?.length || 0;
  }
  return null;
}

function selectedTextWithinSpan(span, range) {
  const raw = String(span?.textContent || "");
  if (!raw || !range) return "";
  let start = 0;
  let end = raw.length;
  const startOffset = textOffsetWithin(span, range.startContainer, range.startOffset);
  const endOffset = textOffsetWithin(span, range.endContainer, range.endOffset);
  if (startOffset !== null) start = startOffset;
  if (endOffset !== null) end = endOffset;
  if (startOffset !== null && endOffset !== null && end < start) [start, end] = [end, start];
  return raw.slice(Math.max(0, start), Math.max(start, end));
}

function rectangleOverlapRatio(first, second) {
  const left = Math.max(first.left, second.left);
  const top = Math.max(first.top, second.top);
  const right = Math.min(first.right, second.right);
  const bottom = Math.min(first.bottom, second.bottom);
  const area = Math.max(0, right - left) * Math.max(0, bottom - top);
  const base = Math.max(1, Math.min(first.width * first.height, second.width * second.height));
  return area / base;
}

function selectedGlyphRuns(range, pageElement) {
  if (!range || !pageElement) return [];
  const pageRect = pageElement.getBoundingClientRect();
  if (!pageRect.width || !pageRect.height) return [];
  const selectionRects = Array.from(range.getClientRects()).filter(rect => rect.width > 0.5 && rect.height > 0.5);
  const spans = Array.from(pageElement.querySelectorAll(".textLayer span, #page-text-layer span"));
  const runs = [];
  for (const span of spans) {
    const fullText = String(span.textContent || "");
    if (!fullText.trim()) continue;
    const rect = span.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue;
    const boundarySpan = span.contains(range.startContainer) || span.contains(range.endContainer);
    const geometricMatch = selectionRects.some(selected => rectangleOverlapRatio(rect, selected) >= 0.08 || rectanglesIntersect(rect, selected));
    // DOM order in PDF text layers is not guaranteed to follow visual reading order. Requiring
    // a geometric overlap prevents a cross-column selection from silently swallowing unrelated
    // paragraphs that merely happen to sit between the range endpoints in the DOM.
    if (!boundarySpan && !geometricMatch) continue;
    let raw = selectedTextWithinSpan(span, range);
    if (!raw && geometricMatch) raw = fullText;
    if (!raw.trim()) continue;
    const itemIndex = Number(span.dataset.vutTextIndex || -1);
    const item = itemIndex >= 0 ? state.pageTextItems[itemIndex] : null;
    const style = getComputedStyle(span);
    runs.push({
      text: raw,
      x: Math.max(0, Math.min(1, (rect.left - pageRect.left) / pageRect.width)),
      y: Math.max(0, Math.min(1, (rect.top - pageRect.top) / pageRect.height)),
      width: Math.max(0.0001, Math.min(1, rect.width / pageRect.width)),
      height: Math.max(0.0001, Math.min(1, rect.height / pageRect.height)),
      font_size: Math.max(1, Number.parseFloat(style.fontSize || "0") || rect.height),
      font_name: String(item?.fontName || style.fontFamily || ""),
      direction: String(item?.dir || span.dir || "ltr"),
      item_index: itemIndex,
    });
  }
  return runs.sort((a, b) => (a.y + a.height / 2) - (b.y + b.height / 2) || a.x - b.x).slice(0, 1600);
}

function clusterGlyphLines(runs) {
  const lines = [];
  for (const run of runs || []) {
    const center = run.y + run.height / 2;
    let best = null;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (const line of lines) {
      const distance = Math.abs(center - line.center);
      const tolerance = Math.max(0.004, Math.min(0.03, Math.max(run.height, line.height) * 0.62));
      if (distance <= tolerance && distance < bestDistance) { best = line; bestDistance = distance; }
    }
    if (!best) {
      best = { runs: [], center, height: run.height };
      lines.push(best);
    }
    best.runs.push(run);
    const count = best.runs.length;
    best.center = ((best.center * (count - 1)) + center) / count;
    best.height = Math.max(best.height, run.height);
  }
  for (const line of lines) line.runs.sort((a, b) => a.x - b.x);
  lines.sort((a, b) => a.center - b.center);
  return lines;
}

function spatialTranscript(runs, fallbackText = "") {
  if (!runs?.length) return normalizeSelectedText(fallbackText);
  const lines = clusterGlyphLines(runs);
  const minX = Math.min(...runs.map(run => run.x));
  const maxX = Math.max(...runs.map(run => run.x + run.width));
  const spanWidth = Math.max(0.01, maxX - minX);
  const columns = 84;
  const rendered = [];
  for (const line of lines.slice(0, 80)) {
    let row = "";
    let cursor = 0;
    for (const run of line.runs) {
      const column = Math.max(0, Math.min(columns, Math.round(((run.x - minX) / spanWidth) * columns)));
      if (column > cursor) row += " ".repeat(Math.min(24, column - cursor));
      row += run.text;
      cursor = column + Math.max(1, run.text.length);
    }
    const clean = row.replace(/[ \t]+$/g, "");
    if (clean.trim()) rendered.push(clean);
  }
  return normalizeSpatialText(rendered.join("\n")) || normalizeSelectedText(fallbackText);
}

function latexFromUnicode(value) {
  let out = "";
  let superscript = "";
  let subscript = "";
  const flushScripts = () => {
    if (superscript) { out += `^{${superscript}}`; superscript = ""; }
    if (subscript) { out += `_{${subscript}}`; subscript = ""; }
  };
  for (const char of String(value || "")) {
    if (Object.prototype.hasOwnProperty.call(VUT_SUPERSCRIPTS, char)) {
      superscript += VUT_SUPERSCRIPTS[char];
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(VUT_SUBSCRIPTS, char)) {
      subscript += VUT_SUBSCRIPTS[char];
      continue;
    }
    flushScripts();
    if (Object.prototype.hasOwnProperty.call(VUT_LATEX_SYMBOLS, char)) {
      out += ` ${VUT_LATEX_SYMBOLS[char]} `;
      continue;
    }
    if (char === "\\") out += "\\backslash ";
    else if (char === "%") out += "\\%";
    else if (char === "#") out += "\\#";
    else if (char === "&") out += "\\&";
    else if (char === "_") out += "\\_";
    else if (char === "{") out += "\\{";
    else if (char === "}") out += "\\}";
    else out += char;
  }
  flushScripts();
  return out
    .replace(/\b(sin|cos|tan|cot|sinh|cosh|tanh|log|ln|exp|lim|max|min|sup|inf|det|ker|rank|dim)\b/g, "\\\\$1")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function mathSignal(value, runs = []) {
  const text = String(value || "");
  const symbols = (text.match(/[=+\-−×÷∫∑∏√∞≤≥≠≈∈∂∇^_{}()[\]|α-ωΑ-Ω0-9]/g) || []).length;
  const letters = (text.match(/[A-Za-zÀ-ž]/g) || []).length;
  const geometry = runs.some(run => run.height < Math.max(...runs.map(item => item.height), 0) * 0.72);
  return symbols / Math.max(1, symbols + letters) + (geometry ? 0.12 : 0);
}

function normalizedMathSource(value) {
  return String(value || "")
    .normalize("NFKC")
    .replace(/[−–—]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

function commonCalculusLatex(value) {
  const source = normalizedMathSource(value);
  if (!source) return { text: "", confidence: 0, ruleHits: 0 };
  const formulas = [];
  const add = (pattern, latex) => {
    if (pattern.test(source) && !formulas.includes(latex)) formulas.push(latex);
  };
  add(/ρ\s*∂\s*(?:2|²)?\s*u\s*∂\s*t\s*(?:2|²)?[\s\S]{0,80}∂\s*∂\s*x[\s\S]{0,80}=\s*f/i,
    "\\rho\\frac{\\partial^2 u}{\\partial t^2}-\\frac{\\partial}{\\partial x}\\left(E\\frac{\\partial u}{\\partial x}\\right)=f");
  add(/u\s*\(\s*0\s*,\s*t\s*\)\s*=\s*0/i, "u(0,t)=0");
  add(/E\s*∂\s*u\s*∂\s*x\s*\(\s*l\s*,\s*t\s*\)\s*=\s*\^?\s*τ\s*\(\s*t\s*\)/i,
    "E\\frac{\\partial u}{\\partial x}(l,t)=\\widehat{\\tau}(t)");
  add(/u\s*\(\s*x\s*,\s*t\s*0\s*\)\s*=\s*U\s*0\s*\(\s*x\s*\)/i, "u(x,t_0)=U_0(x)");
  add(/∂\s*u\s*∂\s*t\s*\(\s*x\s*,\s*t\s*0\s*\)\s*=\s*U\s*1\s*\(\s*x\s*\)/i,
    "\\frac{\\partial u}{\\partial t}(x,t_0)=U_1(x)");
  add(/∂\s*ε\s*∂\s*t[\s\S]{0,50}=\s*τ[\s\S]{0,30}η/i,
    "\\frac{\\partial \\varepsilon}{\\partial t}(x,t)=\\frac{\\tau(x,t)}{\\eta(x)}");
  add(/ε\s*=\s*d\s*u\s*d\s*x\s*=\s*ε\s*T\s*\+\s*ε\s*P/i,
    "\\varepsilon=\\frac{du}{dx}=\\varepsilon_T+\\varepsilon_P");
  if (!formulas.length) return { text: "", confidence: 0, ruleHits: 0 };
  const text = formulas.length === 1
    ? formulas[0]
    : `\\begin{aligned}\n${formulas.map(item => `${item}\\\\`).join("\n")}\n\\end{aligned}`;
  return { text, confidence: Math.min(0.96, 0.68 + formulas.length * 0.055), ruleHits: formulas.length };
}

function bestEffortLatex(runs, fallbackText = "") {
  const spatial = spatialTranscript(runs, fallbackText);
  const source = normalizedMathSource(`${fallbackText}\n${spatial}`);
  const common = commonCalculusLatex(source);
  const lines = spatial.split("\n").map(line => line.trim()).filter(Boolean);
  const mathLines = lines.filter(line => mathSignal(line, runs) >= 0.19 || /[=∫∑∏√≤≥≠→⇒∂]/.test(line));
  if (!mathLines.length) return { text: "", confidence: 0, source: "none" };
  const converted = mathLines.slice(0, 28).map(line => latexFromUnicode(line)).filter(Boolean);
  const generic = converted.length === 1
    ? converted[0].slice(0, 16000)
    : converted.length ? `\\begin{aligned}\n${converted.join(" \\\\\n")}\n\\end{aligned}`.slice(0, 16000) : "";
  // Multi-line fraction layouts are precisely where a glyph-only conversion is least reliable.
  // Use the rule-repaired representation only when it actually recognized structure; otherwise
  // keep a low-confidence transcript for hidden model context but do not advertise it to users.
  if (common.ruleHits >= 1) {
    // The rule engine already emits syntactically valid LaTeX. Sending it through the
    // Unicode escaper would turn command backslashes into literal \backslash tokens.
    return { text: common.text.slice(0, 16000), confidence: common.confidence, source: "common-calculus-rules" };
  }
  const fractionLike = /∂|∫|∑|√/.test(source) && lines.length >= 2;
  return {
    text: generic,
    confidence: generic ? (fractionLike ? 0.38 : 0.62) : 0,
    source: generic ? "unicode-geometry" : "none",
  };
}

function selectionSurroundingContext(runs, radius = 12) {
  const indices = (runs || [])
    .map(run => Number(run.item_index))
    .filter(index => Number.isInteger(index) && index >= 0)
    .sort((a, b) => a - b);
  if (!indices.length || !state.pageTextItems?.length) return { before: "", after: "" };
  const first = indices[0];
  const last = indices[indices.length - 1];
  const joinItems = items => normalizeSelectedText(items.map(item => String(item?.str || "")).join(" "));
  return {
    before: joinItems(state.pageTextItems.slice(Math.max(0, first - radius), first)).slice(-3500),
    after: joinItems(state.pageTextItems.slice(last + 1, Math.min(state.pageTextItems.length, last + 1 + radius))).slice(0, 3500),
  };
}

function captureSelectionCrop(rectangles) {
  const source = el.pageCanvas;
  if (!source || !source.width || !source.height || !rectangles?.length) return "";
  const left = Math.max(0, Math.min(...rectangles.map(rect => rect.x)) - 0.018);
  const top = Math.max(0, Math.min(...rectangles.map(rect => rect.y)) - 0.018);
  const right = Math.min(1, Math.max(...rectangles.map(rect => rect.x + rect.width)) + 0.018);
  const bottom = Math.min(1, Math.max(...rectangles.map(rect => rect.y + rect.height)) + 0.018);
  const sx = Math.floor(left * source.width);
  const sy = Math.floor(top * source.height);
  const sw = Math.max(2, Math.ceil((right - left) * source.width));
  const sh = Math.max(2, Math.ceil((bottom - top) * source.height));
  const scale = Math.min(1, 1600 / sw, 1200 / sh);
  const target = document.createElement("canvas");
  target.width = Math.max(2, Math.round(sw * scale));
  target.height = Math.max(2, Math.round(sh * scale));
  const context = target.getContext("2d", { alpha: false });
  if (!context) return "";
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, target.width, target.height);
  context.drawImage(source, sx, sy, sw, sh, 0, 0, target.width, target.height);
  let data = "";
  try { data = target.toDataURL("image/webp", 0.9); } catch (_) { /* fallback below */ }
  if (!data.startsWith("data:image/webp")) {
    try { data = target.toDataURL("image/png"); } catch (_) { return ""; }
  }
  return data.length <= 2_900_000 ? data : "";
}

function markdownQuote(value, maxChars = 18000) {
  const clean = normalizeSelectedText(value).slice(0, maxChars);
  return clean.split("\n").map(line => `> ${line || " "}`).join("\n");
}

function actionPrompt(type, selection) {
  const labels = {
    explain: "Vysvětli následující označenou pasáž podrobně, objasni každý symbol a netriviální krok a nakonec jednou krátkou otázkou ověř, zda jí rozumím.",
    simplify: "Vysvětli následující označenou pasáž nejprve intuitivně a potom přesně matematicky.",
    derive: "Odvoď výsledek v následující označené pasáži krok za krokem a zdůvodni každý netriviální přechod.",
    example: "Vytvoř k následující označené pasáži jeden plně řešený a jeden samostatný příklad.",
  };
  const page = Number(selection?.page_index ?? (state.page - 1)) + 1;
  const title = String(state.activeBook?.title || "Studijní kniha");
  const parts = [
    labels[type] || "Pracuj s následující označenou pasáží.",
    `**Zdroj:** ${title}, fyzická PDF strana ${page}`,
    "### Označená pasáž",
    markdownQuote(selection?.selected_text || "", 20000),
  ];
  const latex = normalizeSelectedText(selection?.latex_text || "");
  const latexConfidence = Number(selection?.latex_confidence || 0);
  if (latex && latexConfidence >= 0.72) {
    parts.push(
      `### Rekonstrukce matematického zápisu (automatická, jistota ${Math.round(latexConfidence * 100)} %)` ,
      `\`\`\`latex\n${latex.slice(0, 12000)}\n\`\`\``
    );
  } else if (selection?.has_visual_crop) {
    parts.push("Automatický matematický přepis má nízkou jistotu. Vycházej z přímého textu a pokud je modelu dostupný originální výřez PDF, použij jej ke kontrole symbolů a struktury vzorce.");
  }
  parts.push(
    "Pracuj pouze s významem označené pasáže. Nevymýšlej jednotky ani fyzikální předpoklady, které nejsou ve zdroji; pracovní předpoklad vždy výslovně označ. Ve výsledku zobraz každý vzorec jen jednou v čistém LaTeXu."
  );
  return parts.filter(Boolean).join("\n\n");
}

async function queueSelectionAction(prompt, action, selection) {
  const response = await api("/study-tutor/api/selection-actions", {
    method: "POST",
    body: JSON.stringify({
      prompt,
      action: String(action || "explain"),
      selection_id: String(selection?.id || ""),
      file_id: String(selection?.file_id || state.activeBook?.file_id || ""),
      session_id: String(selection?.session_id || state.sessionId || ""),
      page: Number(selection?.page_index || 0) + 1,
    }),
  });
  if (!response?.ok) throw new Error("Výběr se nepodařilo bezpečně navázat na chat.");
  return response;
}

function toolActionPrompt(item, selection = null, scenario = null) {
  const capabilityInstructions = {
    plot: "Vytvoř názorný kvantitativní graf. Pokud chybí data, nejprve je bezpečně získej nebo si vyžádej jejich původ; renderer nikdy nepoužívej jako zdroj dat.",
    symbolic: "Symbolicky ověř nebo odvoď klíčový výraz, uveď předpoklady a zkontroluj ekvivalenci rozhodujících kroků.",
    numerical: "Proveď malý reprodukovatelný numerický experiment, zkontroluj stabilitu a jasně odděl údaje knihy od ilustračních voleb.",
    simulation: "Připrav simulační model až po potvrzení geometrie, materiálu, jednotek, okrajových podmínek, zatížení, sítě a požadovaných výsledků. Pokud něco chybí, nejprve se zeptej a solver nespouštěj.",
    field_visualization: "Vytvoř vizualizaci skutečného pole, sítě nebo kontur a vysvětli extrémy, gradienty a vazbu na rovnici či numerickou chybu.",
    diagram: "Vytvoř schéma objektů, předpokladů, kroků a důsledků tak, aby student dokázal rekonstruovat logiku tématu.",
    model3d: "Vytvoř geometrický 3D pohled s rozměry a jasně popiš, co je zdrojový údaj a co pracovní ilustrace.",
    code: "Vytvoř a spusť krátký kontrolovatelný výpočet; ověř vstupy, výstupy a případnou chybu oprav nejvýše jednou.",
    research: "Doplň ověřitelný odborný kontext, cituj zdroje a důsledně jej odděl od obsahu knihy.",
    generic: "Použij přesnou zvolenou funkci k uvedenému studijnímu cíli a výstup porovnej s knihou.",
  };
  const base = selection
    ? actionPrompt("explain", selection)
    : `Pracuj s tématem na fyzické PDF straně ${state.page} knihy **${state.activeBook?.title || "Studijní kniha"}**.`;
  const exactTool = String(item?.installed_name || item?.display_name || item?.tool_id || "Open WebUI");
  const exactFunction = String(item?.workflow_kind ? `${ansysWorkflowLabel(ansysProductFromItem(item))[0]} workflow` : (item?.function_name || ""));
  const provider = String(item?.provider || "generic");
  const strictSimulation = String(item?.capability || "") === "simulation"
    ? "Tato volba je závazná: použij provider ANSYS/solver uvedený níže. SciViz, lokální graf ani jiný renderer nesmí solver nahradit; vizualizaci lze použít až jako postprocessing potvrzeného solverového výsledku."
    : "Použij přesně zvolenou funkci; jiný provider ji nesmí tiše nahradit.";
  const scenarioBlock = scenario ? [
    "### Studijní scénář",
    `**Cíl pro studenta:** ${scenario.goal}`,
    `**Konkrétní úloha:** ${scenario.instruction}`,
    `**Očekávaný výstup:** ${scenario.output}`,
    `**Jak výstup použít při studiu:** ${scenario.studyUse}`,
  ].join("\n\n") : "";
  return [
    base,
    scenarioBlock,
    `### Závazně zvolený nástroj`,
    `**Nástroj:** ${exactTool}\n\n**Provider:** ${provider}\n\n**Přesná operace:** \`${exactFunction}\``,
    strictSimulation,
    `### Pravidla provedení`,
    capabilityInstructions[item?.capability] || capabilityInstructions.generic,
    "Nástroj spustí VUT AI Tutor přímo; nevypisuj žádný interní tool-call protokol ani JSON volání. Za úspěch považuj pouze skutečně dokončený a doručený výstup. Potom stručně vysvětli, co výstup ukazuje, jaké má předpoklady a jak pomáhá pochopit zdrojovou látku.",
  ].filter(Boolean).join("\n\n");
}

function toolActionReference(actionId, sessionId = "") {
  const action = encodeURIComponent(String(actionId || ""));
  const session = encodeURIComponent(String(sessionId || ""));
  return `<!-- VUT_AI_TUTOR_TOOL_ACTION_REF action_id=${action} session_id=${session} -->`;
}

function toolActionPayload(item, selection = null, prompt = "") {
  return {
    prompt,
    function_name: String(item?.function_name || ""),
    tool_id: String(item?.tool_id || ""),
    capability: String(item?.capability || ""),
    provider: String(item?.provider || ""),
    installed_name: String(item?.installed_name || item?.display_name || ""),
    workflow_kind: String(item?.workflow_kind || ""),
    ansys_product: String(item?.ansys_product || ""),
    preferred_function: String(item?.preferred_function || ""),
    origin_key: String(item?.origin_key || ""),
    origin_url: String(item?.origin_url || ""),
    origin_aliases: Array.isArray(item?.origin_aliases) ? item.origin_aliases.slice(0, 32) : [],
    candidate_operations: Array.isArray(item?.candidate_operations) ? item.candidate_operations.slice(0, 64) : [],
    candidate_functions: Array.isArray(item?.candidate_functions) ? item.candidate_functions.slice(0, 64) : [],
    strict_exact: true,
    selection_id: String(selection?.id || ""),
    file_id: String(selection?.file_id || state.activeBook?.file_id || ""),
    session_id: String(selection?.session_id || state.sessionId || ""),
    page: Number(selection?.page_index ?? (state.page - 1)) + 1,
  };
}

function ansysProductFromItem(item) {
  const blob = foldText([item?.ansys_product, item?.installed_name, item?.display_name, item?.tool_id, item?.function_name, item?.description, item?.origin_url, ...(item?.origin_aliases || []), ...(item?.candidate_operations || [])].filter(Boolean).join(" "));
  if (blob.includes("fluent")) return "fluent";
  if (blob.includes("mechanical")) return "mechanical";
  if (blob.includes("mapdl") || /\bapdl\b/.test(blob)) return "mapdl";
  if (blob.includes("aedt") || blob.includes("electronics desktop") || blob.includes("pyaedt")) return "aedt";
  if (blob.includes("cfx")) return "cfx";
  if (blob.includes("lumerical")) return "lumerical";
  return "ansys";
}

function ansysWorkflowLabel(product) {
  const labels = {
    fluent: ["ANSYS Fluent", "Spustit ANSYS Fluent analýzu"],
    mechanical: ["ANSYS Mechanical", "Spustit ANSYS Mechanical analýzu"],
    mapdl: ["ANSYS MAPDL", "Spustit ANSYS MAPDL analýzu"],
    aedt: ["ANSYS Electronics Desktop", "Spustit ANSYS AEDT analýzu"],
    cfx: ["ANSYS CFX", "Spustit ANSYS CFX analýzu"],
    lumerical: ["ANSYS Lumerical", "Spustit ANSYS Lumerical analýzu"],
    ansys: ["ANSYS", "Spustit ANSYS analýzu"],
  };
  return labels[product] || labels.ansys;
}

function ansysProductFitScore(product, text = "") {
  const value = foldText(text);
  let score = product === "mechanical" ? 8 : product === "mapdl" ? 7 : 0;
  const noFlow = /proudeni nehraje roli|bez proudeni|zadne proudeni|ne cfd|solid heat|pevne teleso|tepelna vodivost|kondukce/.test(value);
  const structural = /tyc|prut|nosnik|konstrukc|pruznost|elast|mechanik|napeti|deform|posun|trakce|dirichlet|neumann|vlnov|kmit|modal|mkp|konecnych prvku|finite element|solid/.test(value);
  const solidHeat = /vedeni tepla|heat conduction|thermal conduction|teplotni pole|termopruz|thermal stress|stacionarni teplo|nestacionarni teplo/.test(value);
  const cfd = /proudeni|fluid|tekutin|cfd|navier stokes|turbulen|inlet|outlet|prutok|konvekce|aerodynam/.test(value) && !noFlow;
  if (structural) { if (product === "mechanical") score += 52; else if (product === "mapdl") score += 45; else if (["fluent","cfx"].includes(product)) score -= 58; }
  if (solidHeat || noFlow) { if (product === "mechanical") score += 58; else if (product === "mapdl") score += 50; else if (["fluent","cfx"].includes(product)) score -= 85; }
  if (cfd) { if (product === "fluent") score += 62; else if (product === "cfx") score += 52; else if (["mechanical","mapdl"].includes(product)) score -= 38; }
  if (/elektromagnet|rf|mikrovln|antena|aedt/.test(value)) score += product === "aedt" ? 70 : -25;
  if (/foton|optik|laser|waveguide|lumerical/.test(value)) score += product === "lumerical" ? 70 : -25;
  return score;
}

function ensureAnsysWorkflowItems(capabilities = [], inventory = []) {
  const source = [...(capabilities || [])];
  const existing = new Set(source.filter(item => String(item?.workflow_kind || "").startsWith("ansys-")).map(item => ansysProductFromItem(item)));
  const bestRaw = new Map();
  for (const raw of inventory || []) {
    if (!raw?.invocable || String(raw?.provider || "") !== "ansys") continue;
    const product = ansysProductFromItem(raw);
    const score = Number(raw?.confidence || 0) * 10 + Number(raw?.classification_score || 0) + (raw?.active_in_chat ? 3 : 0);
    const previous = bestRaw.get(product);
    if (!previous || score > previous.score) bestRaw.set(product, { raw, score });
  }
  for (const [product, entry] of bestRaw) {
    if (existing.has(product)) continue;
    const raw = entry.raw;
    const [productName, actionLabel] = ansysWorkflowLabel(product);
    source.push({
      registry_key: `vut:ansys-${product}-analysis:${raw.tool_id || ""}`,
      function_name: `__vut_ansys_${product}_analysis_workflow__`,
      declared_name: `__vut_ansys_${product}_analysis_workflow__`,
      tool_id: String(raw.tool_id || ""),
      installed_name: `${productName} · řízený analytický workflow`,
      display_name: `${productName} analysis workflow`,
      provider: "ansys",
      ansys_product: product,
      capability: "simulation",
      action_label: actionLabel,
      action_icon: "◫",
      action_description: `Řízený ${productName} workflow s povinnými vstupy a bez přímého run_code.`,
      confidence: 0.995,
      classification_score: 30,
      rank_score: 38,
      verified: true,
      active: true,
      active_in_chat: Boolean(raw.active_in_chat),
      invocable: true,
      workflow_kind: `ansys-${product}-analysis`,
      preferred_function: String(raw.function_name || raw.declared_name || ""),
      preferred_operation: String(raw.preferred_operation || raw.canonical_operation || ""),
      origin_key: String(raw.origin_key || ""),
      origin_url: String(raw.origin_url || ""),
      origin_aliases: Array.isArray(raw.origin_aliases) ? raw.origin_aliases.slice(0, 32) : [],
      candidate_operations: Array.isArray(raw.candidate_operations) ? raw.candidate_operations.slice(0, 64) : [String(raw.canonical_operation || "")].filter(Boolean),
      candidate_functions: Array.isArray(raw.candidate_functions) ? raw.candidate_functions.slice(0, 64) : [String(raw.function_name || raw.declared_name || "")].filter(Boolean),
      description: `Tool Kernel shromáždí vstupy a použije pouze ${productName}; SciViz ani obecný code runner jej nenahradí.`,
    });
  }
  return source;
}

function studyScenarioCatalogItems() {
  const workflows = ensureAnsysWorkflowItems(state.toolCapabilities, state.toolInventory);
  const ansysWorkflowProducts = new Set(workflows.filter(item => String(item?.workflow_kind || "").startsWith("ansys-")).map(item => ansysProductFromItem(item)));
  const raw = (state.toolInventory || []).filter(item => !(String(item?.provider || "") === "ansys" && item?.invocable && ansysWorkflowProducts.has(ansysProductFromItem(item))));
  const merged = [...workflows, ...raw];
  const seen = new Set();
  return merged.filter(item => {
    const key = String(item?.workflow_kind || `${item?.tool_id || ""}::${item?.function_name || item?.declared_name || ""}`);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function verifiedPrimaryTools(items, text = "", limit = 7) {
  const byRole = new Map();
  const learning = learningAffordanceProfile(null, text);
  for (const item of items || []) {
    if (!item || item.active === false || item.verified !== true || Number(item.confidence || 0) < 0.72) continue;
    const learningFit = toolLearningFit(item, learning);
    if (learningFit.blocked) continue;
    const specialistBonus = item.provider && !["generic", "office"].includes(String(item.provider)) ? 3.4 : 0;
    const workflowBonus = item.workflow_kind ? 8 : 0;
    const score = toolRelevanceScore(item, text, learning)
      + Number(item.confidence || 0) * 4
      + Number(item.rank_score || 0) * 0.12
      + specialistBonus + workflowBonus
      + (item.auto_discovered ? 0 : 0.8);
    const provider = String(item.provider || "generic");
    const key = item.workflow_kind
      ? String(item.workflow_kind)
      : (provider === "ansys" ? `simulation:ansys:${ansysProductFromItem(item)}` : `${item.capability || "generic"}:${provider}`);
    const previous = byRole.get(key);
    if (!previous || score > previous.score) byRole.set(key, { item, score });
  }
  return [...byRole.values()]
    .sort((a, b) => b.score - a.score || String(a.item.action_label || "").localeCompare(String(b.item.action_label || ""), "cs"))
    .slice(0, limit)
    .map(entry => entry.item);
}

function studySourceText(selection = null) {
  if (selection) {
    return [selection.selected_text, selection.linear_text, selection.latex_text, selection.context_before, selection.context_after, state.activeBook?.title]
      .filter(Boolean).join(" ");
  }
  const pageText = (state.pageTextItems || []).slice(0, 800).map(item => String(item?.str || "")).join(" ");
  return `${state.activeBook?.title || ""} ${pageText}`;
}

function learningAffordanceProfile(selection = null, extraText = "") {
  const raw = `${studySourceText(selection)} ${extraText || ""}`;
  const value = foldText(raw);
  const hit = pattern => pattern.test(value) ? 1 : 0;
  const count = pattern => (value.match(pattern) || []).length;
  const mathSymbols = Math.min(1, ((raw.match(/[=+−×÷∫∑∏√∞≤≥≠≈∈∂∇]|\\(?:frac|sum|int|partial|begin)/g) || []).length) / 8);
  const equation = Math.max(mathSymbols, hit(/\b(rovnic[a-z0-9]*|equation|formula|vzorec|derivac[a-z0-9]*|integral|matice|vektor|pde|ode)\b/));
  const proof = Math.max(hit(/\b(veta|lemma|dukaz[a-z0-9]*|tvrzeni|theorem|proof|corollary|implik[a-z0-9]*|nutn.*podmink|postacuj[a-z0-9]*)\b/), equation * hit(/\b(plati|dokaz[a-z0-9]*|odtud|tedy|proto|therefore|hence)\b/) * .65);
  const textileCore = hit(/\b(plet[a-z0-9]*|hackov[a-z0-9]*|prize|jehlic[a-z0-9]*|nahod[a-z0-9]*|uplet[a-z0-9]*|obrace|hladce|rubov[a-z0-9]*|licov[a-z0-9]*|stitch|knit|purl|crochet|yarn)\b/);
  const stitchToken = hit(/\b(oko|oka|ok)\b/) * Math.max(textileCore, hit(/\b(rada|rad[a-z0-9]*|row|rapport|zebrov[a-z0-9]*|vzor|pattern)\b/));
  const woolContext = hit(/\bvlna\b/) * Math.max(textileCore, stitchToken);
  const craft = Math.max(textileCore, stitchToken, woolContext);
  const procedure = Math.max(Math.min(1, count(/\b(krok|step|postup|nejprve|potom|nasledne|opakuj[a-z0-9]*|repeat|row|rada|nahod[a-z0-9]*|uplet[a-z0-9]*|plet[a-z0-9]*|obrace|hladce|sew|stitch|mix|install|press|turn)\b/g) / 5), Math.min(1, ((raw.match(/^\s*(?:\d+[.)]|[-*])\s+/gm) || []).length) / 5));
  const genericPattern = hit(/\b(vzor|pattern|schema|chart|mrizk[a-z0-9]*|grid|rapport|opakujici.*jednotk|period[a-z0-9]*)\b/);
  const patternStructure = Math.max(genericPattern, craft * .85, procedure * hit(/\b(opak[a-z0-9]*|repeat|rada|row|sloupec|column)\b/) * .70);
  const relational = Math.max(Math.min(1, count(/\b(zavis[a-z0-9]*|souvis[a-z0-9]*|vztah[a-z0-9]*|pricin[a-z0-9]*|dusled[a-z0-9]*|protoze|sklada.*se|obsahuj[a-z0-9]*|patri|vede k|zmen[a-z0-9]*|urychl[a-z0-9]*|vyvol[a-z0-9]*|zpusob[a-z0-9]*|if|then|because|depends|consists)\b/g) / 4), proof);
  const taxonomy = Math.max(hit(/\b(typy|druhy|kategorie|klasifik[a-z0-9]*|taxonomy|rozdeleni|hierarch[a-z0-9]*|podtyp|skupina)\b/), relational * hit(/\b(pojem|definic[a-z0-9]*|category|class)\b/) * .55);
  const spatial = Math.max(Math.min(1, count(/\b(geometri[a-z0-9]*|tvar|rozmer[a-z0-9]*|vlevo|vpravo|nahore|dole|vrstva|plocha|objem|prostor|uzel|hrana|sit|mesh|pattern|vzor|diagram|mapa|orientac[a-z0-9]*)\b/g) / 4), patternStructure);
  const temporal = Math.max(Math.min(1, count(/\b(cas|casov[a-z0-9]*|time|evoluc[a-z0-9]*|dynam[a-z0-9]*|tranzient[a-z0-9]*|transient|sekvence|iterac[a-z0-9]*|cyklus|period[a-z0-9]*|rychlost|zrychleni)\b/g) / 4), procedure * .65);
  const quantities = (raw.match(/(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?(?:\s*(?:%|mm|cm|m|km|g|kg|s|min|h|K|Pa|N|V|A|Hz|W|ml|l))?/g) || []).length;
  const numericDensity = Math.min(1, quantities / 7);
  const quantitative = Math.max(equation, numericDensity, hit(/\b(hodnot[a-z0-9]*|parametr[a-z0-9]*|mereni|vypocet|pocet|velikost|delka|sirka|hustota|tabulka|data|ratio|gauge)\b/));
  const data = Math.max(hit(/\b(csv|json|dataset|tabulka|series|rada hodnot|mereni|experiment.*data)\b/), Math.min(1, ((raw.match(/^\s*\|.*\|\s*$/gm) || []).length) / 4));
  const algorithmLanguage = hit(/\b(algorit[a-z0-9]*|pseudokod|program|kod|code|while|for loop|rekur[a-z0-9]*|numerick.*metod|iteracni metoda)\b/);
  const algorithmic = Math.max(algorithmLanguage, procedure * hit(/\b(pokud|jestlize|if|dokud|while|pro kazd|for each|opakuj dokud)\b/) * .55);
  const comparison = hit(/\b(porovn[a-z0-9]*|rozdil[a-z0-9]*|oproti|versus|vs|variant[a-z0-9]*|alternativ[a-z0-9]*|stejn[a-z0-9]*|odlis[a-z0-9]*)\b/);
  const explicitVisual = hit(/\b(obrazek|ilustrac[a-z0-9]*|nakresli|diagram|schema|vizualiz[a-z0-9]*|graf|chart|mapa)\b/);
  const explicitChart = hit(/\b(graf|chart|heatmap|kontur[a-z0-9]*|vykresli[a-z0-9]*|plot)\b/);
  const explicitComputation = hit(/\b(spocit[a-z0-9]*|vypocit[a-z0-9]*|dopoct[a-z0-9]*|numerick.*experiment|vyres.*rovnic|compute|calculate|solve numerically)\b/);
  const explicitSimulation = hit(/\b(simulac[a-z0-9]*|solver|fea|fem|cfd|ansys|comsol|openfoam|modeluj[a-z0-9]*|analyz.*modelem)\b/);
  const mechanics = hit(/\b(hmotnost|hustota|sila|zatizeni|napeti|deform[a-z0-9]*|posun[a-z0-9]*|rychlost|zrychleni|pruznost|viskoz[a-z0-9]*|trakce|young|rho|mechanik[a-z0-9]*)\b/);
  const thermal = hit(/\b(teplota|teplo|tepel[a-z0-9]*|vodivost|kondukce|konvekce|heat|thermal)\b/);
  const fluid = hit(/\b(proudeni|tekutin[a-z0-9]*|tlak|prutok|turbulen[a-z0-9]*|fluid|cfd|navier|inlet|outlet)\b/);
  const electromagnetics = hit(/\b(elektrick[a-z0-9]*|magnetick[a-z0-9]*|napeti elektr|proud elektr|rf|antena|electromagnetic)\b/);
  const optics = hit(/\b(optick[a-z0-9]*|foton[a-z0-9]*|laser|waveguide|lumerical)\b/);
  const physicalEntity = Math.max(mechanics, thermal, fluid, electromagnetics, optics);
  const governingModel = Math.max(equation * physicalEntity, hit(/\b(zakon zachovani|rovnovaha|konstitutiv[a-z0-9]*|pohybov.*rovnic|vedeni tepla|navier|maxwell|wave equation|vlnov.*rovnic|finite element model|mkp)\b/));
  const conditionEquations = Math.min(1, ((raw.match(/(?:u|T|p|v|\w+)\s*\([^)]*(?:0|l|L|t_?0)[^)]*\)\s*=/g) || []).length) / 2);
  const modelConstraints = Math.max(hit(/\b(okrajov.*podmink|pocatecn.*podmink|boundary condition|materialov.*vlastnost|zatizeni|load|mesh|sit[a-z0-9]*|geometri[a-z0-9]*|domena|domain|source term|zdrojov.*clen|ulozeni)\b/), conditionEquations);
  let physicalModel = Math.min(1, .32 * physicalEntity + .38 * governingModel + .30 * modelConstraints);
  let solverReadiness = Math.min(1, physicalEntity * (.45 * governingModel + .35 * modelConstraints + .20 * explicitSimulation));
  if (craft >= .55 && !explicitSimulation) { solverReadiness *= .08; physicalModel *= .35; }
  const quantitativeRelation = Math.max(equation, data, comparison * quantitative, hit(/\b(zavislost|funkce parametru|rychlost zmeny|trend|regrese|interpolac[a-z0-9]*|aproximac[a-z0-9]*|citlivost)\b/));
  let computationalReadiness = Math.max(data, equation * .95, algorithmLanguage, explicitComputation, comparison * quantitative * .80);
  if (proof >= .70 && data < .25 && algorithmLanguage < .25 && !explicitComputation) computationalReadiness *= .35;
  if (craft >= .55 && !explicitComputation) computationalReadiness *= .18;
  let chartReadiness = Math.max(data, explicitChart, comparison * quantitativeRelation, temporal * quantitativeRelation, quantities >= 3 ? quantitativeRelation * .70 : 0);
  if (patternStructure >= .55 && data < .25 && equation < .25 && !explicitChart) chartReadiness *= .20;
  const patternChartReadiness = patternStructure;
  const geometryObject = hit(/\b(3d|trojrozmern[a-z0-9]*|objemov[a-z0-9]*|teleso|soucast|dil|konstrukce|cad|model geometrie|prurez|plocha|solid)\b/);
  const geometryReadiness = Math.max(solverReadiness * spatial, spatial * geometryObject);
  const visual = Math.max(explicitVisual, spatial, patternStructure, procedure * .80);
  const engineering = Math.max(solverReadiness, hit(/\b(inzenyr[a-z0-9]*|mechanik[a-z0-9]*|termik[a-z0-9]*|elektromagnet[a-z0-9]*|fotonik[a-z0-9]*|cfd|mkp|finite element)\b/));
  const mathematics = Math.max(equation, proof, hit(/\b(matemat[a-z0-9]*|algebra|analyz[a-z0-9]*|topolog[a-z0-9]*|pravdepodob[a-z0-9]*|statistik[a-z0-9]*)\b/));
  const domainHint = craft >= .60 ? "craft-or-textile-procedure" : engineering >= .55 ? "engineering-physical-model" : mathematics >= .55 ? "mathematical-formal" : procedure >= .55 ? "procedural" : Math.max(relational, taxonomy) >= .50 ? "conceptual-relational" : "general-text";
  const capabilityScores = {
    diagram: Math.max(relational, taxonomy, procedure * .90, patternStructure * .95),
    image: Math.max(visual, spatial * .90, procedure * .85),
    plot: chartReadiness,
    numerical: computationalReadiness,
    symbolic: Math.max(equation, proof),
    simulation: solverReadiness,
    field_visualization: Math.min(1, Math.max(data * spatial, solverReadiness * spatial, solverReadiness * temporal)),
    model3d: geometryReadiness,
    code: Math.max(algorithmic, computationalReadiness * .80),
    research: .35,
  };
  return { domainHint, equation, proof, procedure, patternStructure, relational, taxonomy, spatial, temporal, quantitative, data, algorithmic, comparison, visual, craft, physicalModel, solverReadiness, computationalReadiness, chartReadiness, patternChartReadiness, geometryReadiness, explicitComputation: Boolean(explicitComputation), explicitSimulation: Boolean(explicitSimulation), capabilityScores };
}

function toolLearningFit(item, profile) {
  const capability = String(item?.capability || "generic");
  const provider = String(item?.provider || "generic").toLowerCase();
  let fit = Number(profile?.capabilityScores?.[capability] ?? (capability === "generic" ? .28 : 0));
  let blocked = false;
  if (provider === "ansys") {
    const readiness = Number(profile?.solverReadiness || 0);
    if (readiness < .52) { blocked = true; fit *= .06; } else fit = Math.max(fit, readiness);
  } else if (provider === "matlab") {
    const readiness = Number(profile?.computationalReadiness || 0);
    if (readiness < .34) { blocked = true; fit *= .12; } else fit = Math.max(fit, readiness * .95);
  } else if (provider === "sciviz") {
    const schema = foldText(JSON.stringify({ parameters: item?.parameters || {}, description: item?.description || "", function: item?.function_name || item?.declared_name || "" }));
    const patternCapable = /\b(heatmap|matrix|grid|plotly|specification|z data|cell|tile)\b/.test(schema);
    let readiness = Number(profile?.chartReadiness || 0);
    if (patternCapable) readiness = Math.max(readiness, Number(profile?.patternChartReadiness || 0) * .88);
    if (readiness < .30) { blocked = true; fit *= .12; } else fit = Math.max(fit, readiness);
  } else if (provider === "paraview") {
    const fieldFit = Math.max(Number(profile?.data || 0) * Number(profile?.spatial || 0), Number(profile?.solverReadiness || 0) * .85);
    if (fieldFit < .38) blocked = true;
    fit = Math.max(fit, fieldFit);
  }
  if (capability === "model3d" && Number(profile?.geometryReadiness || 0) < .42) { blocked = true; fit *= .15; }
  return { fit: Math.max(0, Math.min(1, fit)), blocked };
}

function scenarioApplicable(item, scenario, profile) {
  const { fit, blocked } = toolLearningFit(item, profile);
  if (blocked) return false;
  const capability = String(item?.capability || "generic");
  const thresholds = { simulation: .58, field_visualization: .42, model3d: .48, symbolic: .36, numerical: .34, plot: .30, code: .34, diagram: .20, image: .20, research: .20, generic: .24 };
  if (fit < Number(thresholds[capability] ?? .24)) return false;
  const id = String(scenario?.id || "");
  if (["mesh-study", "boundary-comparison", "solver-model"].includes(id) && Number(profile?.solverReadiness || 0) < .52) return false;
  if (["verify-derivation", "boundary-case"].includes(id) && Math.max(Number(profile?.equation || 0), Number(profile?.proof || 0)) < .42) return false;
  if (["key-dependence", "compare-methods"].includes(id) && Number(profile?.chartReadiness || 0) < .32) return false;
  if (["sensitivity", "reproduce-example"].includes(id) && Number(profile?.computationalReadiness || 0) < .34) return false;
  if (id === "pattern-grid" && Number(profile?.patternChartReadiness || 0) < .50) return false;
  if (id === "geometry-model" && Number(profile?.geometryReadiness || 0) < .45) return false;
  return true;
}

function toolRelevanceScore(item, text = "", profile = null) {
  const learning = profile || learningAffordanceProfile(null, text);
  const { fit, blocked } = toolLearningFit(item, learning);
  if (blocked) return -100;
  let score = fit * 30;
  const capability = String(item?.capability || "");
  if (capability === "diagram" && Math.max(learning.relational, learning.procedure, learning.patternStructure) >= .5) score += 5;
  if (capability === "image" && Math.max(learning.procedure, learning.patternStructure, learning.spatial) >= .55) score += 5;
  if (capability === "simulation" && learning.solverReadiness >= .65) score += 6;
  if (String(item?.provider || "").toLowerCase() === "ansys") score += ansysProductFitScore(ansysProductFromItem(item), `${text} ${state.activeBook?.title || ""}`);
  return score;
}

function canonicalToolGroupKey(item) {
  const provider = foldText(item?.installed_name || item?.provider || item?.display_name || item?.tool_id || "tool");
  return provider.replace(/\b(server|openapi|mcp|workspace|tool)\b/g, " ").replace(/\s+/g, " ").trim() || String(item?.tool_id || item?.function_name || "tool");
}

function toolStudyTarget(selection = null) {
  if (selection) return `označenou pasáž na PDF straně ${Number(selection.page_index || 0) + 1}`;
  return `téma na PDF straně ${state.page}`;
}

function studyScenarioTemplates(item, selection = null, profile = null) {
  const capability = String(item?.capability || "generic");
  const target = toolStudyTarget(selection);
  const blob = foldText([item?.installed_name, item?.display_name, item?.provider, item?.function_name, item?.description].filter(Boolean).join(" "));
  const exact = String(item?.workflow_kind ? `${ansysWorkflowLabel(ansysProductFromItem(item))[0]} workflow` : (item?.function_name || "funkce"));
  const common = { item, icon: item?.action_icon || "⚙" };
  const scenario = (id, label, goal, instruction, output, studyUse, bonus = 0) => ({ ...common, id, label, goal, instruction, output, studyUse, bonus });

  if (/powerpoint|pptx|presentation|slides/.test(blob)) return [
    scenario("study-presentation", "Připravit prezentaci tématu k opakování", "Uspořádat látku do krátké posloupnosti, kterou lze znovu aktivně vybavit.", `Z ${target} vytvoř nejvýše šest snímků: problém, klíčové pojmy, jeden vzorec, řešený krok, častou chybu a závěrečnou otázku. Použij přesnou funkci ${exact}.`, "PPTX nebo prezentace s odkazy na fyzické strany knihy.", "Student nejprve odpoví na otázku na každém snímku a teprve potom odkryje vysvětlení.", 1),
  ];
  if (/word|docx|document|report/.test(blob)) return [
    scenario("study-sheet", "Vytvořit jednostránkový studijní list", "Získat přehledný, ale zdrojově věrný podklad pro další procvičování.", `Zpracuj ${target} do jedné až dvou stran: definice, předpoklady, rozhodovací signály, mini-příklad, typická chyba a tři otázky k vybavení. Použij ${exact}.`, "DOCX/PDF studijní list s fyzickými odkazy do knihy.", "List slouží jako opora pro aktivní vybavení, nikoli jako náhrada čtení.", 1),
  ];
  if (/excel|xlsx|spreadsheet|worksheet/.test(blob)) return [
    scenario("study-table", "Sestavit tabulku parametrů, kroků a kontrol", "Porovnat varianty metody nebo sledovat numerické výsledky bez ztráty významu veličin.", `Převeď relevantní veličiny z ${target} do tabulky se sloupci význam, zdroj/strana, jednotka nebo normalizace, výpočetní krok a kontrola. Použij ${exact}.`, "XLSX/tabulka připravená pro doplnění vlastních výpočtů.", "Student doplní alespoň jeden řádek a vysvětlí, proč zvolená kontrola odhalí chybu.", 1),
  ];

  const templates = {
    plot: [
      ...(Number(profile?.patternChartReadiness || 0) >= .5 && /\b(heatmap|matrix|grid|plotly|specification|z data|cell|tile)\b/.test(foldText(JSON.stringify({ parameters: item?.parameters || {}, description: item?.description || "", function: item?.function_name || "" }))) ? [scenario("pattern-grid", "Vykreslit mřížku nebo chart opakujícího se vzoru", "Převést přesnou opakovací strukturu na čitelnou mřížku bez předstírání numerického grafu.", `Z ${target} vytvoř pomocí ${exact} mřížku/heatmapu vzoru. Osy musí znamenat pořadí nebo polohu kroků/ok, nikoli fyzikální veličiny; přidej legendu a vyznač jednu periodu.`, "Interaktivní mřížka nebo heatmapa s legendou a označenou opakovací jednotkou.", "Student určí jednu periodu a podle ní doplní následující řadu nebo část.", 8)] : []),
      scenario("key-dependence", "Vykreslit klíčovou závislost z knihy", "Vidět, jak se mění hlavní veličina a které parametry její průběh ovládají.", `Urči z ${target} vhodné osy a data. Pokud data nejsou v knize, nejprve nabídni jejich dopočet, ověřený zdroj nebo výslovně normalizovanou ilustraci; teprve potom použij ${exact}.`, "Graf s popsanými osami, původem dat, předpoklady a kontrolou mezních/okrajových podmínek.", "Student před interpretací odhadne tvar, monotonicitu, extrémy nebo asymptotické chování.", 4),
      scenario("compare-methods", "Porovnat dvě metody nebo sady parametrů", "Rozpoznat, kdy se postupy liší a co zůstává invariantní.", `Z ${target} vyber dvě smysluplné varianty (např. síť, časový krok, metoda, parametr) a vykresli je stejnými osami pomocí ${exact}.`, "Srovnávací graf a dvě věty o rozdílu, shodě a omezení srovnání.", "Student nejprve uvede očekávaný rozdíl a potom jej porovná s výsledkem.", 2),
    ],
    symbolic: [
      scenario("verify-derivation", "Ověřit odvození krok za krokem", "Rozlišit algebraicky platný krok od kroku vyžadujícího další předpoklad.", `Rekonstruuj rozhodující výraz z ${target}, symbolicky ověř jednotlivé transformace funkcí ${exact} a u každé uveď podmínky platnosti.`, "Čisté odvození, seznam předpokladů a případný protipříklad k neplatnému kroku.", "Student před spuštěním označí krok, kterému nejméně důvěřuje, a po výpočtu jej vysvětlí vlastními slovy.", 4),
      scenario("boundary-case", "Prozkoumat mezní a speciální případ", "Pochopit význam obecného vztahu zjednodušením jednoho parametru nebo podmínky.", `Vyber jeden mezní případ z ${target}, symbolicky jej odvoď pomocí ${exact} a porovnej s obecným tvarem.`, "Zjednodušený vztah a vysvětlení, co se ztratilo nebo zachovalo.", "Student určí, zda speciální případ potvrzuje intuici, nebo odhaluje omezení metody.", 2),
    ],
    numerical: [
      scenario("reproduce-example", "Reprodukovat numerický příklad z knihy", "Ověřit, že student rozumí vstupům, algoritmu a kontrolám, nikoli jen výslednému číslu.", `Z ${target} sestav malý reprodukovatelný experiment pro ${exact}. Jasně odděl převzaté údaje od ilustrativních, ověř stabilitu/konvergenci a vrať strojově čitelná data i výsledek.`, "Numerický výsledek, kontrolní metriky, případně graf a stručná interpretace.", "Student před během odhadne řád výsledku a po běhu vysvětlí nejcitlivější parametr.", 4),
      scenario("sensitivity", "Provést studii citlivosti", "Zjistit, které parametry modelu nebo metody skutečně ovlivňují závěr.", `Zvol jeden až dva parametry relevantní pro ${target}, změň je v bezpečném rozsahu pomocí ${exact} a porovnej výstupy se stejnou kontrolou.`, "Tabulka nebo graf citlivosti s popisem normalizace a omezení.", "Student označí parametr s největším vlivem a zdůvodní jej z rovnice nebo algoritmu.", 2),
    ],
    simulation: [
      scenario("solver-model", /ansys/.test(blob) ? `Sestavit a ověřit ${ansysWorkflowLabel(ansysProductFromItem(item))[0]} model` : "Sestavit a ověřit simulační model", "Převést matematické zadání knihy do úplného, auditovatelného solverového modelu.", `Nejprve z ${target} sestav formulář: typ analýzy, geometrie a rozměry, materiál a jednotky, okrajové podmínky, zatížení, síť/čas a požadované výsledky. Chybějící údaje si vyžádej. Teprve po potvrzení použij ${exact}; žádný renderer nesmí solver nahradit.`, "Potvrzený model, solverový receipt, výsledky nebo přesná chyba konkrétní operace.", "Student propojí každý solverový vstup s rovnicí, podmínkou nebo předpokladem v knize.", 7),
      scenario("boundary-comparison", "Porovnat vliv okrajových podmínek", "Vidět, jak změna fyzikálního omezení mění řešení a zda je model dobře položený.", `Po potvrzení kompletního modelu vytvoř dvě varianty lišící se jedinou okrajovou podmínkou z ${target}, spusť je přes ${exact} a porovnej stejné výsledkové veličiny.`, "Dva solverové běhy se společným měřítkem, kontrolou rovnováhy a vysvětlením rozdílu.", "Student předem předpoví směr změny a následně jej zdůvodní z modelu.", 4),
      scenario("mesh-study", "Provést síťovou nebo časovou konvergenční studii", "Oddělit fyzikální závěr od chyby diskretizace.", `Po potvrzení modelu spusť nejméně tři úrovně sítě nebo časového kroku přes ${exact}, sleduj jednu relevantní veličinu a náklad výpočtu.`, "Konvergenční tabulka/graf, zvolená tolerance a doporučená úroveň diskretizace.", "Student rozhodne, zda další zjemnění ještě mění pedagogicky podstatný závěr.", 3),
    ],
    field_visualization: [
      scenario("field-gradients", "Prozkoumat pole, gradienty a extrémy", "Spojit lokální obraz řešení s členy rovnice, tokem nebo odhadem chyby.", `Načti skutečná data související s ${target}, pomocí ${exact} vytvoř kontury/pole a označ maxima, minima, gradienty a případné nespojitosti.`, "Interaktivní pole nebo kontury s legendou, jednotkami a původem dat.", "Student vysvětlí, proč se extrém nachází právě v dané oblasti a jak souvisí s okrajovými podmínkami.", 5),
      scenario("time-slices", "Porovnat časové řezy nebo varianty sítě", "Rozpoznat vývoj pole a vliv numerické reprezentace.", `Pomocí ${exact} zobraz několik synchronizovaných řezů relevantních pro ${target}; použij stejné měřítko a popiš rozdíly.`, "Sada porovnatelných řezů/animace a stručný závěr.", "Student určí invariant a změnu mezi řezy bez nahlížení do popisku.", 2),
    ],
    diagram: [
      ...(Number(profile?.procedure || 0) >= .5 ? [scenario("procedure-flow", "Převést postup do krokového schématu", "Uvidět pořadí kroků, opakování, rozhodovací místa a kontrolní body.", `Z ${target} vytvoř pomocí ${exact} krokový diagram. Zachovej terminologii zdroje, označ opakující se části a nevynechávej podmínky úspěšného provedení.`, "Krokové schéma s odkazy na zdroj a kontrolními body.", "Student podle schématu vlastními slovy obnoví postup a označí místo, kde je nejpravděpodobnější chyba.", 6)] : []),
      ...(Number(profile?.patternStructure || 0) >= .5 ? [scenario("pattern-chart", "Převést vzor nebo strukturu do přehledného schématu", "Rozpoznat opakující se jednotku, orientaci a vazby mezi částmi.", `Z ${target} vytvoř pomocí ${exact} schéma nebo mřížku vzoru. Vysvětli legendu a odděl zdrojové instrukce od grafické konvence.`, "Schéma vzoru/struktury s legendou a opakovací jednotkou.", "Student ukáže jednu periodu vzoru a vysvětlí, jak pokračuje další část.", 7)] : []),
      scenario("concept-relations", "Nakreslit vztah pojmů a předpokladů", "Zviditelnit logickou strukturu tématu místo pouhého seznamu definic.", `Z ${target} vytvoř pomocí ${exact} diagram podle povahy zdroje: pojmy a vztahy, kroky postupu nebo části objektu.`, "Čitelný diagram s odkazy na fyzickou stranu knihy.", "Student diagram zakryje a pokusí se jej rekonstruovat vlastními slovy.", 4),
      scenario("method-tree", "Vytvořit rozhodovací strom volby postupu", "Naučit se rozpoznat signály, podle nichž se vybírá vhodný další krok.", `Z ${target} vytvoř pomocí ${exact} rozhodovací strom s otázkami ano/ne, podmínkami a hraničními případy.`, "Rozhodovací strom a příklad pro každou hlavní větev.", "Student projde stromem na nové situaci a zdůvodní každé rozhodnutí.", 3),
    ],
    model3d: [
      scenario("geometry-model", "Převést geometrii knihy do 3D modelu", "Pochopit rozměry, vazby a zjednodušení geometrického modelu.", `Z ${target} vytěž potvrzené rozměry a vazby, chybějící údaje si vyžádej a pomocí ${exact} vytvoř jednoduchý parametrický model.`, "3D model/řez s rozměry a seznamem převzatých versus ilustračních parametrů.", "Student ukáže, které geometrické zjednodušení ovlivňuje platnost matematického modelu.", 4),
    ],
    code: [
      scenario("algorithm-demo", "Spustit krokovou demonstraci algoritmu", "Vidět stav algoritmu po jednotlivých rozhodujících krocích a ověřit invarianty.", `Z ${target} vytvoř krátký reprodukovatelný program pro ${exact}, vypiš mezikroky a automatické kontroly; nepoužívej neověřené externí vstupy.`, "Spustitelný kód, výsledky kontrol a stručná vazba na pseudokód nebo rovnici knihy.", "Student před každým krokem odhadne změnu stavu a po běhu vysvětlí případnou odchylku.", 3),
    ],
    image: [
      ...(Number(profile?.procedure || 0) >= .5 ? [scenario("visual-steps", "Vytvořit názornou sekvenci kroků", "Převést slovní postup na viditelné mezistavy bez změny jeho významu.", `Vytvoř pomocí ${exact} didaktickou sekvenci k ${target}. Každý panel musí odpovídat jednomu kroku zdroje; nejasné detaily označ místo jejich domýšlení.`, "Kroková ilustrace s popisky a vazbou na původní pořadí.", "Student zakryje popisky a popíše, co se mezi dvěma sousedními kroky změnilo.", 7)] : []),
      ...(Number(profile?.patternStructure || 0) >= .5 ? [scenario("visual-pattern", "Znázornit opakující se vzor a jeho jednotku", "Uvidět orientaci, periodu a vazby, které jsou ve slovním popisu obtížně patrné.", `Vytvoř pomocí ${exact} přesnou didaktickou ilustraci vzoru z ${target}; přidej legendu a vyznač jednu opakovací jednotku.`, "Ilustrace vzoru s legendou a označenou periodou.", "Student ukáže, kde vzor začíná znovu, a vysvětlí pravidlo pokračování.", 8)] : []),
      scenario("visual-intuition", "Vytvořit názornou ilustraci tématu", "Převést abstraktní nebo slovní obsah na názornou, ale nepředstíranou reprezentaci.", `Vytvoř pomocí ${exact} didaktický obrázek k ${target} podle skutečné povahy zdroje. Může jít o objekt, postup, vzor, vztah nebo prostorové uspořádání; nepřeváděj automaticky téma na fyzikální model.`, "Obrázek se stručnou legendou a seznamem toho, co je pouze ilustrace.", "Student pojmenuje hlavní části nebo kroky a jednu věc, kterou obrázek nezobrazuje.", 3),
    ],
    research: [
      scenario("external-explanation", "Najít alternativní odborné vysvětlení", "Porovnat formulaci knihy s důvěryhodným externím zdrojem bez smíchání jejich tvrzení.", `Pomocí ${exact} najdi primární nebo univerzitní zdroj k ${target}, shrň pouze relevantní část a odděl ji od textu knihy.`, "Citovaný externí kontext, shody/rozdíly a doporučení, co z něj použít ke studiu.", "Student vysvětlí stejný pojem jednou terminologií knihy a jednou terminologií externího zdroje.", 2),
    ],
    generic: [
      scenario("guided-tool", `Prozkoumat téma pomocí ${item?.installed_name || item?.display_name || exact}`, "Využít konkrétní funkci k hlubšímu porozumění aktivní pasáži, nikoli pouze ji technicky zapnout.", `Použij přesnou funkci ${exact} na ${target}. Nejprve z jejího schématu určete, jaký pedagogicky smysluplný vstup a výstup podporuje; chybějící údaje si vyžádej.`, "Skutečný výstup funkce, popis jeho omezení a vazba na zdrojovou stránku.", "Student porovná výstup s knihou a označí jeden nový poznatek a jednu otevřenou otázku.", 1),
    ],
  };
  return templates[capability] || templates.generic;
}

function buildStudyScenarios(items, selection = null, { maxPerTool = 2, limit = 80, compact = false } = {}) {
  const groups = new Map();
  const profile = learningAffordanceProfile(selection);
  const contextText = studySourceText(selection);
  for (const raw of items || []) {
    const item = raw?.verified === true && raw?.active !== false ? raw : genericInventoryActionItem(raw);
    if (!item || raw?.active === false || raw?.invocable === false) continue;
    if (toolLearningFit(item, profile).blocked) continue;
    const key = canonicalToolGroupKey(item);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  const scenarios = [];
  for (const [groupKey, groupItems] of groups) {
    const ordered = [...groupItems].sort((a, b) => {
      const aScore = toolRelevanceScore(a, contextText, profile) + Number(a.confidence || 0) * 4 + (a.recommended ? 2 : 0);
      const bScore = toolRelevanceScore(b, contextText, profile) + Number(b.confidence || 0) * 4 + (b.recommended ? 2 : 0);
      return bScore - aScore;
    });
    const groupScenarios = [];
    const seen = new Set();
    for (const item of ordered) {
      for (const candidate of studyScenarioTemplates(item, selection, profile)) {
        if (!scenarioApplicable(item, candidate, profile)) continue;
        const dedupe = `${candidate.id}:${item.capability || "generic"}`;
        if (seen.has(dedupe)) continue;
        seen.add(dedupe);
        const learningFit = toolLearningFit(item, profile).fit;
        const score = toolRelevanceScore(item, contextText, profile) + learningFit * 12 + Number(item.confidence || 0) * 5 + Number(candidate.bonus || 0) + (item.active_in_chat ? 1.5 : 0);
        groupScenarios.push({ ...candidate, groupKey, score, learningFit, learningProfile: profile });
      }
    }
    groupScenarios.sort((a, b) => b.score - a.score || a.label.localeCompare(b.label, "cs"));
    scenarios.push(...groupScenarios.slice(0, compact ? 1 : Math.max(1, maxPerTool)));
  }
  scenarios.sort((a, b) => b.score - a.score || String(a.item?.installed_name || "").localeCompare(String(b.item?.installed_name || ""), "cs"));
  if (!scenarios.length) return [];

  const bestScore = Number(scenarios[0]?.score || 0);
  for (const candidate of scenarios) candidate.recommendedForContext = candidate.score >= bestScore - 1.5;
  if (!compact) return scenarios.slice(0, limit);

  // Compact menus preserve complementary representations, but never reserve a slot for a
  // provider merely because it is installed.  This is why a knitting passage can offer a
  // stitch diagram and step illustration while hiding ANSYS; an elastodynamics passage can
  // still offer Mechanical, MATLAB, and SciViz when each provides a distinct learning value.
  const selected = [];
  const keys = new Set();
  const providers = new Set();
  const capabilities = new Set();
  const keyOf = candidate => `${candidate?.item?.workflow_kind || candidate?.item?.tool_id || ""}::${candidate?.item?.function_name || ""}::${candidate?.id || ""}`;
  const push = candidate => {
    if (!candidate || selected.length >= limit) return false;
    const key = keyOf(candidate);
    if (keys.has(key)) return false;
    keys.add(key);
    selected.push(candidate);
    providers.add(String(candidate?.item?.provider || "generic").toLowerCase());
    capabilities.add(String(candidate?.item?.capability || "generic"));
    return true;
  };

  // First pass: best semantically valid scenario from each provider, ordered by learning value.
  for (const candidate of scenarios) {
    const provider = String(candidate?.item?.provider || "generic").toLowerCase();
    if (!providers.has(provider)) push(candidate);
    if (selected.length >= Math.min(limit, 3)) break;
  }
  // Second pass: add a new representation family when available.
  for (const candidate of scenarios) {
    const capability = String(candidate?.item?.capability || "generic");
    if (!capabilities.has(capability)) push(candidate);
  }
  // Final pass: fill remaining places by contextual score.
  for (const candidate of scenarios) push(candidate);
  return selected.slice(0, limit);
}

function renderStudyScenarioButtons(container, items, selection = null, options = {}) {
  if (!container) return;
  container.replaceChildren();
  const scenarios = buildStudyScenarios(items, selection, options);
  if (!scenarios.length) {
    container.innerHTML = '<div class="empty-state">Pro tuto pasáž nevznikl žádný pedagogicky oprávněný scénář z aktuálně dostupných nástrojů. Technický inventář zůstává dostupný níže; samotná instalace nástroje však není důvod jej použít.</div>';
    return;
  }
  for (const scenario of scenarios) {
    const item = scenario.item;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "study-scenario-card";
    button.title = `Studijní scénář pro přesnou funkci ${item.function_name}\nNástroj: ${item.installed_name || item.tool_id || "Open WebUI"}`;
    const recommendation = scenario.recommendedForContext ? '<span class="study-scenario-recommended">Doporučeno pro tuto pasáž</span>' : '';
    button.innerHTML = `<span class="study-scenario-provider"><span class="tool-icon" aria-hidden="true">${escapeHtml(scenario.icon || "⚙")}</span><span>${escapeHtml(item.installed_name || item.display_name || item.tool_id || "Open WebUI")}</span></span>${recommendation}<strong>${escapeHtml(scenario.label)}</strong><p>${escapeHtml(scenario.goal)}</p><span class="study-scenario-output"><b>Výstup:</b> ${escapeHtml(scenario.output)}</span>`;
    button.addEventListener("click", event => { event.preventDefault(); event.stopPropagation(); void invokeVerifiedTool(item, selection, scenario); });
    container.appendChild(button);
  }
}

async function invokeVerifiedTool(item, selection = null, scenario = null) {
  if (!item) return;
  if (state.actionPending) return showToast("Předchozí požadavek se již zpracovává.");
  const capability = String(item.capability || "");
  if (["simulation", "field_visualization", "model3d"].includes(capability)) {
    const provider = String(item.installed_name || item.tool_id || "Open WebUI");
    const ok = await requestCanvasConfirmation({
      title: scenario?.label || item.action_label || (capability === "simulation" ? "Spustit inženýrskou analýzu?" : "Spustit nástroj?"),
      message: capability === "simulation"
        ? "VUT AI Tutor připraví přesnou úlohu pro zvolený solver. Pokud chybí geometrie, materiál, zatížení, síť nebo okrajové podmínky, nejprve si je vyžádá v chatu; analýzu nebude předstírat ani spouštět s neoznačenými domněnkami."
        : "VUT AI Tutor použije přesnou funkci a výsledek označí jako ilustrativní, dokud nebudou potvrzeny všechny vstupy a podmínky.",
      detail: `Nástroj: ${provider}
Funkce: ${item.function_name}
Schopnost: ${capability || "generic"}`,
      acceptLabel: capability === "simulation" ? "Pokračovat k analýze" : "Spustit nástroj",
      icon: item.action_icon || "⚙",
    });
    if (!ok) {
      showToast("Spuštění nástroje bylo zrušeno.", 2500);
      return;
    }
  }
  setSelectionActionPending(true, `Zařazuji ${item.function_name} do chatu…`);
  try {
    const prompt = toolActionPrompt(item, selection, scenario);
    const queued = await api("/study-tutor/api/tool-actions", {
      method: "POST",
      body: JSON.stringify(toolActionPayload(item, selection, prompt)),
    });
    if (!queued || queued.ok !== true || !queued.action_id) {
      throw new Error("Backend nepotvrdil vytvoření jednorázové akce nástroje.");
    }
    showToast(`${item.action_label || item.function_name}: požadavek byl bezpečně zařazen do chatu.`, 3200);
    const boundPrompt = `${prompt}\n\n${toolActionReference(queued.action_id, selection?.session_id || state.sessionId || "")}`;
    await sendPrompt(boundPrompt);
    setSelectionActionPending(false, selection
      ? `PDF strana ${Number(selection.page_index || 0) + 1} · výběr zůstává uložený`
      : "Požadavek byl odeslán");
  } catch (error) {
    setSelectionActionPending(false, selection
      ? `PDF strana ${Number(selection.page_index || 0) + 1} · výběr zůstává uložený`
      : "");
    showToast(`Nástroj se nepodařilo vyvolat: ${error.message}`, 7000);
  }
}

function renderToolButtons(container, items, selection = null, limit = 7) {
  renderStudyScenarioButtons(container, items, selection, { maxPerTool: 1, limit, compact: true });
}

function toolSourceLabel(value = "") {
  const key = String(value || "");
  const labels = {
    turn: "Aktivní v tomto tahu",
    metadata: "Aktivní runtime nástroje",
    "body-metadata": "Aktivní nástroje zprávy",
    "request-metadata": "Aktivní nástroje požadavku",
    "selected-tool": "Zapnuté Workspace Tools",
    "workspace-tool": "Workspace Tools",
    "openapi-server": "OpenAPI servery",
    "mcp-server": "MCP servery",
    terminal: "Terminal servery",
    builtin: "Vestavěné nástroje Open WebUI",
    skill: "Skills (kontext)",
    "function-action": "Message Actions",
    "function-filter": "Filters",
    "function-pipe": "Pipe modely",
    "function-event": "Event Functions",
  };
  if (labels[key]) return labels[key];
  if (key.startsWith("direct-")) return "Přímo připojené nástroje chatu";
  if (key.endsWith("-server")) return `${key.replace(/-server$/, "").toUpperCase()} servery`;
  if (key.startsWith("function-")) return `Functions · ${key.slice(9)}`;
  return key || "Ostatní funkcionality";
}

function toolAvailabilityLabel(item) {
  if (item?.active_in_chat) return "zapnuto v chatu";
  if (item?.availability === "awaiting-next-turn") return "čeká na další zprávu";
  if (!item?.invocable) return "kontextová funkce";
  if (item?.availability === "workspace") return "dostupné ve Workspace";
  if (item?.availability === "direct") return "přímé připojení";
  return "dostupné";
}

function genericInventoryActionItem(item) {
  if (!item?.invocable) return null;
  return {
    ...item,
    function_name: item.function_name || item.declared_name,
    display_name: item.display_name || item.declared_name || item.function_name,
    capability: item.capability || "generic",
    action_label: item.action_label || `Použít ${item.display_name || item.function_name || "funkci"}`,
    action_icon: item.action_icon || "⚙",
    action_description: item.description || "Použije přesnou funkci podle jejího JSON schématu.",
    verified: true,
    active: true,
    confidence: Number(item.confidence || 0.72),
  };
}

function renderToolInventory(items) {
  const source = Array.isArray(items) ? items : [];
  const query = foldText(state.toolCatalogFilter || "");
  const filtered = source.filter(item => {
    if (!query) return true;
    return foldText([
      item.installed_name, item.display_name, item.function_name, item.declared_name,
      item.tool_id, item.source_kind, item.kind, item.description, item.capability,
    ].filter(Boolean).join(" ")).includes(query);
  });
  const visible = filtered.slice(0, state.toolInventoryLimit);
  const summary = state.toolCatalogSummary || {};
  const total = Number(summary.total ?? source.length);
  const invocable = Number(summary.invocable ?? source.filter(item => item?.invocable).length);
  const active = Number(summary.active_in_chat ?? source.filter(item => item?.active_in_chat).length);
  const recommended = Number(summary.recommended ?? source.filter(item => item?.recommended).length);
  if (el.toolInventorySummary) {
    el.toolInventorySummary.className = `status-pill ${total ? "ready" : ""}`;
    el.toolInventorySummary.textContent = `${total} funkcí · ${invocable} volatelných · ${active} zapnutých`;
  }
  if (el.toolDockBadge) {
    el.toolDockBadge.hidden = total === 0;
    el.toolDockBadge.textContent = String(active || recommended || total);
  }
  if (el.toolCatalogNote) {
    const revision = Number(state.toolCatalogRevision || 0);
    const late = source.filter(item => item?.availability === "awaiting-next-turn").length;
    const note = state.toolCatalogNote || (late
      ? `${late} klientských funkcí čeká na nejbližší zprávu po jejich zapnutí.`
      : "Katalog se automaticky obnovuje během konverzace. Z každého skutečně volatelného nástroje vzniká alespoň jeden konkrétní scénář pro aktivní knihu; technický inventář níže slouží pouze k diagnostice.");
    el.toolCatalogNote.textContent = `${note} Revize ${revision}.`;
  }
  if (!el.toolInventoryList) return;
  if (!source.length) {
    el.toolInventoryList.innerHTML = '<div class="empty-state">VUT AI Tutor zatím neobdržel žádný runtime nástroj a nenašel žádnou přístupnou serverovou funkcionalitu. Po zapnutí nástroje odešlete jednu běžnou zprávu nebo použijte „Prohledat Workspace“.</div>';
    if (el.toolInventoryMore) el.toolInventoryMore.hidden = true;
    return;
  }
  if (!filtered.length) {
    el.toolInventoryList.innerHTML = '<div class="empty-state">Žádná funkce neodpovídá filtru.</div>';
    if (el.toolInventoryMore) el.toolInventoryMore.hidden = true;
    return;
  }
  el.toolInventoryList.replaceChildren();
  const groups = new Map();
  for (const item of visible) {
    const sourceKind = String(item?.source_kind || "other");
    if (!groups.has(sourceKind)) groups.set(sourceKind, []);
    groups.get(sourceKind).push(item);
  }
  for (const [sourceKind, groupItems] of groups) {
    const section = document.createElement("section");
    section.className = "tool-inventory-group";
    const heading = document.createElement("h4");
    const groupInvocable = groupItems.filter(item => item?.invocable).length;
    heading.textContent = `${toolSourceLabel(sourceKind)} · ${groupItems.length}${groupInvocable ? ` / ${groupInvocable} volatelných` : ""}`;
    section.appendChild(heading);
    for (const item of groupItems) {
      const row = document.createElement("div");
      row.className = `tool-inventory-item ${item?.active_in_chat ? "active" : "inactive"}`;
      row.title = item.description || "";
      const badges = [toolAvailabilityLabel(item)];
      if (item.recommended) badges.push(`${item.capability || "akce"} · ${Math.round(Number(item.confidence || 0) * 100)} %`);
      if (item.kind && item.kind !== item.source_kind) badges.push(String(item.kind));
      row.innerHTML = `<span class="tool-inventory-icon" aria-hidden="true">${escapeHtml(item.action_icon || (item.invocable ? "⚙" : "◇"))}</span>
        <span class="tool-inventory-copy"><strong>${escapeHtml(item.installed_name || item.tool_id || "Open WebUI")}</strong><small>${escapeHtml(item.display_name || item.declared_name || item.function_name || "funkce")} · ${escapeHtml(item.function_name || item.kind || "")}</small><span class="tool-verification">${escapeHtml(badges.join(" · "))}</span></span>`;
      const stateTag = document.createElement("span");
      stateTag.className = "tool-inventory-diagnostic";
      stateTag.textContent = item?.invocable ? "scénář výše" : "kontext";
      stateTag.title = item?.invocable
        ? "Tato funkce se spouští prostřednictvím konkrétního studijního scénáře nad inventářem."
        : "Položka poskytuje kontext nebo UI/lifecycle chování a nevolá se jako běžný Tool.";
      row.appendChild(stateTag);
      section.appendChild(row);
    }
    el.toolInventoryList.appendChild(section);
  }
  if (el.toolInventoryMore) {
    el.toolInventoryMore.hidden = visible.length >= filtered.length;
    el.toolInventoryMore.textContent = `Zobrazit další (${filtered.length - visible.length})`;
  }
}

function renderToolActions() {
  const items = ensureAnsysWorkflowItems(
    Array.isArray(state.toolCapabilities) ? state.toolCapabilities : [],
    Array.isArray(state.toolInventory) ? state.toolInventory : [],
  );
  const active = items.filter(item => item?.active !== false && item?.verified === true && Number(item?.confidence || 0) >= 0.72);
  const primary = verifiedPrimaryTools(active, state.currentSelection?.selected_text || "", 20);
  const hasActive = primary.length > 0;
  if (el.selectionToolPerspectives) el.selectionToolPerspectives.hidden = !hasActive || !state.currentSelection;
  if (el.pageToolPerspectives) el.pageToolPerspectives.hidden = !hasActive || !state.activeBook;
  if (el.toolCatalogStatus) {
    const total = Number(state.toolCatalogSummary?.total ?? state.toolInventory.length);
    const activeCount = Number(state.toolCatalogSummary?.active_in_chat ?? state.toolInventory.filter(item => item?.active_in_chat).length);
    el.toolCatalogStatus.textContent = hasActive
      ? `${primary.length} doporučených akcí · ${activeCount} právě zapnutých · ${total} evidovaných funkcionalit`
      : `${activeCount} právě zapnutých · ${total} evidovaných funkcionalit; rychlá akce nebyla jednoznačně odvozena`;
  }
  renderToolButtons(el.selectionToolActions, active, state.currentSelection, 7);
  renderToolButtons(el.selectionToolActionsPopover, active, state.currentSelection, 3);
  renderToolButtons(el.pageToolActions, active, null, 7);
  renderStudyScenarioButtons(el.toolTabActions, studyScenarioCatalogItems(), state.currentSelection || null, { maxPerTool: 2, limit: 96, compact: false });
  renderToolInventory(state.toolInventory);
}

function applyToolCatalogPayload(payload, { announce = false } = {}) {
  if (!payload || payload.changed === false) return false;
  state.toolCapabilities = Array.isArray(payload.tool_capabilities) ? payload.tool_capabilities : [];
  state.toolInventory = Array.isArray(payload.tool_inventory) ? payload.tool_inventory : [];
  state.toolCatalogRevision = Number(payload.revision || state.toolCatalogRevision || 0);
  state.toolCatalogUpdatedAt = Number(payload.updated_at || 0);
  state.toolCatalogLastTurnAt = Number(payload.last_turn_at || 0);
  state.toolCatalogSummary = payload.source_summary && typeof payload.source_summary === "object" ? payload.source_summary : {};
  state.toolCatalogNote = String(payload.note || "");
  renderToolActions();
  if (announce) showToast(`Katalog nástrojů byl obnoven: ${state.toolInventory.length} funkcionalit.`);
  return true;
}

async function refreshToolCatalog(force = false) {
  if (state.toolPollBusy || !state.token) return false;
  state.toolPollBusy = true;
  if (el.refreshToolCatalog) el.refreshToolCatalog.disabled = true;
  try {
    const payload = force
      ? await api("/study-tutor/api/tools/refresh", { method: "POST", body: "{}" })
      : await api(`/study-tutor/api/tools?since_revision=${encodeURIComponent(state.toolCatalogRevision || 0)}`);
    return applyToolCatalogPayload(payload, { announce: force });
  } catch (error) {
    if (force) showToast(`Průzkum nástrojů se nepodařil: ${error.message}`, 7000);
    return false;
  } finally {
    state.toolPollBusy = false;
    state.toolLastPollAt = Date.now();
    if (el.refreshToolCatalog) el.refreshToolCatalog.disabled = false;
  }
}

function activityPrompt(kind, scope = {}) {
  const title = kind === "quiz" ? "Vytvoř krátký kvíz" : kind === "test" ? "Vytvoř strukturovaný test" : "Vytvoř studijní kartičky";
  const completeScope = {
    ...scope,
    file_id: scope.file_id || state.activeBook?.file_id || "",
    session_id: scope.session_id || state.sessionId || "",
  };
  const attrs = [`kind=${kind}`];
  for (const [key, value] of Object.entries(completeScope)) if (value !== undefined && value !== "") attrs.push(`${key}=${encodeURIComponent(String(value))}`);
  return `${title} z uvedeného rozsahu a zobraz jej v Canvasu.\n\n[[STUDY_ACTIVITY ${attrs.join(" ")}]]`;
}

function currentScope() {
  return { scope: "page", page: state.page, file_id: state.activeBook?.file_id || "", session_id: state.sessionId || "" };
}

async function loadState({ reopenBook = false } = {}) {
  const previousFileId = state.activeBook?.file_id || "";
  if (!window.__STUDY_CANVAS_READY__) boot.step(43, "Načítám stav knihy…", "Zjišťuji stav Knowledge indexu, učební cesty a mapy pojmů.");
  state.data = await api("/study-tutor/api/state");
  state.data.books = uniqueBooks(state.data.books || []);
  applyLayout(state.data.settings?.layout || state.layout, false);
  if (!window.__STUDY_CANVAS_READY__) boot.step(56, "Stav knihy byl načten", "Připravuji čtečku originálního PDF.");
  state.activeBook = state.data.active_book || null;
  state.learningPath = state.data.learning_path || state.activeBook?.learning_path || null;
  state.learningPathTemplates = state.data.learning_path_templates || [];
  state.toolCapabilities = Array.isArray(state.data.tool_capabilities) ? state.data.tool_capabilities : [];
  state.toolInventory = Array.isArray(state.data.tool_inventory) ? state.data.tool_inventory : [];
  state.toolCatalogRevision = Number(state.data.tool_catalog?.revision || state.data.tool_catalog_revision || 0);
  state.toolCatalogUpdatedAt = Number(state.data.tool_catalog?.updated_at || 0);
  state.toolCatalogLastTurnAt = Number(state.data.tool_catalog?.last_turn_at || 0);
  state.toolCatalogSummary = state.data.tool_catalog?.source_summary || state.data.tool_source_summary || {};
  state.toolCatalogNote = String(state.data.tool_catalog?.note || "");
  renderModels();
  renderBooks();
  renderProgress();
  renderLearningPath();
  renderToolActions();
  renderRecommendation();

  const hasBooks = (state.data.books || []).length > 0;
  const hasActive = Boolean(state.activeBook);
  el.onboarding.hidden = hasActive;
  el.workspace.hidden = !hasActive;
  el.documentControls.hidden = !hasActive;
  el.existingLibrary.hidden = !hasBooks || hasActive;
  if (!hasActive) {
    if (!window.__STUDY_CANVAS_READY__) boot.step(92, "Studijní prostředí je připraveno", "Přidejte PDF knihu nebo otevřete některou z dříve nahraných knih.");
    renderOnboardingBooks();
    el.subtitle.textContent = "Přidejte první knihu a začněte studovat";
    setIndexStatus("Připraven", "ready");
  } else {
    el.subtitle.textContent = state.activeBook.title;
    updateBookStatus();
    updateAnalysisBadge();
    if (!window.__STUDY_CANVAS_READY__) boot.step(62, "Otevírám knihu…", state.activeBook.title || "Načítám originální PDF.");
    if (reopenBook || previousFileId !== state.activeBook.file_id || !state.pdf) await openActiveBook();
  }
  await refreshActivities(false);
  setView(state.activeView);
  el.app.setAttribute("aria-busy", "false");
  reportHeight();
}

function setIndexStatus(text, kind = "") {
  el.indexStatus.textContent = text;
  el.indexStatus.className = `status-pill ${kind}`.trim();
}


function updateBookStatus() {
  const status = state.activeBook?.status || "processing";
  const textStatus = state.activeBook?.text_status || status;
  const semantic = state.activeBook?.semantic_index_reused ? "completed" : (state.activeBook?.semantic_index_status || status);
  const analysis = state.activeBook?.analysis || {};
  if (status === "failed" || textStatus === "failed") setIndexStatus("Zpracování textu selhalo", "failed");
  else if (analysis.status === "completed" && analysis.deep_status === "processing") setIndexStatus("Kniha a rychlá mapa připraveny · zpřesňuji mapu", "processing");
  else if (analysis.status === "completed" && semantic === "completed") setIndexStatus(`${analysis.cached ? "Načteno z cache · " : ""}Kniha, mapa i hledání připraveny`, "ready");
  else if (analysis.status === "completed" && semantic === "failed") setIndexStatus("Kniha a mapa připraveny · hledání omezené", "warning");
  else if (analysis.status === "failed") setIndexStatus("PDF připraveno · mapa vyžaduje opravu", "warning");
  else if (textStatus === "completed") setIndexStatus("PDF připraveno · analyzuji pojmy…", "processing");
  else setIndexStatus("Získávám text knihy…", "processing");
  updateProcessingProgress();
}

function updateProcessingProgress() {
  const strip = el.processingStrip;
  const meter = el.processingMeter;
  if (!strip || !meter || !state.activeBook) { if (strip) strip.hidden = true; return; }
  const fileStatus = state.activeBook.status || "processing";
  const textStatus = state.activeBook.text_status || fileStatus;
  const semantic = state.activeBook.semantic_index_reused ? "completed" : (state.activeBook.semantic_index_status || fileStatus);
  const analysis = state.activeBook.analysis || {};
  strip.className = "processing-strip";

  if (fileStatus === "failed" || textStatus === "failed") {
    strip.hidden = false;
    strip.classList.add("failed");
    meter.value = 100;
    el.processingLabel.textContent = "Text knihy se nepodařilo zpracovat";
    el.processingDetail.textContent = state.activeBook.error || "Originální PDF je stále možné otevřít; mapa a hledání potřebují textovou vrstvu.";
    return;
  }
  if (textStatus !== "completed") {
    strip.hidden = false;
    meter.removeAttribute("value");
    el.processingLabel.textContent = "Získávám textovou vrstvu knihy";
    el.processingDetail.textContent = "Originální PDF se vykresluje nezávisle; obsah a mapa se zpřístupní po extrakci textu.";
    return;
  }
  if (analysis.status === "failed") {
    strip.hidden = false;
    strip.classList.add("warning");
    meter.value = 100;
    el.processingLabel.textContent = "PDF je připraveno, ale analýza pojmů selhala";
    el.processingDetail.textContent = analysis.error || "Zkuste na kartě Mapa pojmů použít Přegenerovat.";
    return;
  }
  if (analysis.status !== "completed") {
    strip.hidden = false;
    const progress = Math.max(0, Math.min(1, Number(analysis.progress || 0)));
    meter.value = 15 + progress * 75;
    const partial = Boolean(analysis.partial_ready || analysis.fast_ready || analysis.ready);
    const eta = formatDuration(analysis.eta_seconds);
    el.processingLabel.textContent = partial
      ? `Částečná mapa je dostupná · ${Math.round(progress * 100)} %`
      : `Vytvářím rychlou lokální mapu · ${Math.round(progress * 100)} %`;
    el.processingDetail.textContent = `${analysis.stage || "Knihu lze mezitím číst a označovat."}${partial ? " Mapa zatím není kompletní." : ""}${eta ? ` Odhad zbývajícího času: ${eta}.` : ""}`;
    return;
  }
  if (analysis.deep_status === "processing") {
    strip.hidden = false;
    const progress = Math.max(0, Math.min(1, Number(analysis.deep_progress || 0)));
    meter.value = progress * 100;
    el.processingLabel.textContent = "Zpřesňuji mapu pomocí LLM";
    el.processingDetail.textContent = analysis.deep_stage || "Rychlá mapa i PDF zůstávají během analýzy použitelné.";
    return;
  }
  if (semantic === "failed") {
    strip.hidden = false;
    strip.classList.add("warning");
    meter.value = 100;
    el.processingLabel.textContent = "Kniha, obsah a mapa jsou připraveny";
    el.processingDetail.textContent = `Sémantický Knowledge index se nepodařil: ${state.activeBook.semantic_index_error || "embedding služba není dostupná"}. Lokální vyhledávání a výuka zůstávají funkční.`;
    return;
  }
  if (semantic !== "completed") {
    strip.hidden = false;
    meter.removeAttribute("value");
    el.processingLabel.textContent = "Dokončuji sémantické vyhledávání";
    el.processingDetail.textContent = "PDF, obsah i mapa pojmů jsou již použitelné.";
    return;
  }
  strip.hidden = true;
  meter.value = 100;
}


function humanBytes(value) {
  const bytes = Math.max(0, Number(value || 0));
  if (!bytes) return "0 B";
  const units = ["B", "KiB", "MiB", "GiB"];
  const power = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / (1024 ** power)).toFixed(power ? 1 : 0)} ${units[power]}`;
}

function formatDuration(seconds) {
  const value = Math.max(0, Math.round(Number(seconds || 0)));
  if (!value) return "";
  if (value < 60) return `asi ${value} s`;
  const minutes = Math.ceil(value / 60);
  if (minutes < 60) return `asi ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `asi ${hours} h ${rest} min` : `asi ${hours} h`;
}

function showPdfLoadProgress(loaded = 0, total = 0) {
  if (!window.__STUDY_CANVAS_READY__ || !el.processingStrip || !el.processingMeter) return;
  el.processingStrip.hidden = false;
  el.processingStrip.className = "processing-strip";
  el.processingLabel.textContent = "Načítám originální PDF";
  if (Number(total) > 0) {
    const percent = Math.max(0, Math.min(100, Number(loaded || 0) / Number(total) * 100));
    el.processingMeter.value = percent;
    el.processingDetail.textContent = `${Math.round(percent)} % · ${humanBytes(loaded)} z ${humanBytes(total)}`;
  } else {
    el.processingMeter.removeAttribute("value");
    el.processingDetail.textContent = loaded ? `Načteno ${humanBytes(loaded)}` : "Připravuji PDF čtečku a zabezpečené spojení se souborem.";
  }
}

function updateAnalysisBadge() {
  const analysis = state.activeBook?.analysis || {};
  state.mapStatus = analysis;
  if (!el.mapStatusText) return;
  updateMapStatus({ ready: Boolean(analysis.ready || analysis.fast_ready), analysis, mode: analysis.active_mode || "fast" });
}

function renderBooks() {
  const books = uniqueBooks(state.data?.books || []);
  if (!books.length) {
    el.bookList.innerHTML = '<div class="empty-state">Zatím nemáte žádnou knihu.</div>';
    return;
  }
  el.bookList.innerHTML = books.map(book => `
    <div class="book-item ${book.file_id === state.activeBook?.file_id ? "active" : ""}">
      <div><strong>${escapeHtml(book.title)}</strong><small>${escapeHtml(statusLabel(book))}</small>${book.learning_path ? `<span class="path-chip">🧭 ${escapeHtml(book.learning_path.name || "Učební cesta")}</span>` : ""}</div>
      <button type="button" data-book-id="${escapeHtml(book.file_id)}">Otevřít</button>
    </div>`).join("");
  el.bookList.querySelectorAll("button[data-book-id]").forEach(button => {
    button.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      switchBook(button.dataset.bookId).catch(error => showToast(error.message, 7000));
    });
  });
}

function renderOnboardingBooks() {
  const books = uniqueBooks(state.data?.books || []);
  el.existingLibrary.hidden = !books.length;
  el.onboardingBooks.innerHTML = books.map(book => `
    <button type="button" class="book-item" data-book-id="${escapeHtml(book.file_id)}">
      <span><strong>${escapeHtml(book.title)}</strong><small>${escapeHtml(statusLabel(book))}</small>${book.learning_path ? `<span class="path-chip">🧭 ${escapeHtml(book.learning_path.name || "Učební cesta")}</span>` : ""}</span>
      <span>Otevřít →</span>
    </button>`).join("");
  el.onboardingBooks.querySelectorAll("[data-book-id]").forEach(button => {
    button.addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      switchBook(button.dataset.bookId).catch(error => showToast(error.message, 7000));
    });
  });
}

function statusLabel(book) {
  const status = book?.status || "processing";
  if (status === "failed" || book?.text_status === "failed") return "Chyba textové vrstvy";
  if (book?.analysis?.status === "completed" && book?.semantic_index_status === "failed") return "Připravená · hledání omezené";
  if (book?.analysis?.status === "completed") return "Připravená";
  if (book?.text_status === "completed") return "Analyzuje se";
  return "Zpracovává se";
}

async function switchBook(fileId) {
  const targetFileId = String(fileId || "").trim();
  if (!targetFileId) return;
  if (targetFileId === String(state.activeBook?.file_id || "")) {
    showToast("Tato kniha je již otevřená.", 2500);
    return;
  }
  // Choosing a book is local Canvas navigation. It must never communicate with
  // or mutate the Open WebUI composer.
  await api("/study-tutor/api/active-book", { method: "POST", body: JSON.stringify({ file_id: targetFileId }) });
  clearReader();
  await loadState({ reopenBook: true });
  showToast(`Otevřena kniha „${state.activeBook?.title || "Studijní kniha"}“.`, 3000);
}

function clearSelectionHighlights() {
  if (el.selectionOverlay) el.selectionOverlay.replaceChildren();
}

async function closePdfDocument() {
  const loadingTask = state.pdfLoadingTask;
  state.pdfLoadingTask = null;
  state.renderGeneration += 1;
  try { state.pageRenderTask?.cancel?.(); } catch (_) {}
  state.pageRenderTask = null;
  try { state.textLayerTask?.cancel?.(); } catch (_) {}
  state.textLayerTask = null;
  if (loadingTask?.destroy) {
    try { await loadingTask.destroy(); } catch (_) {}
  }
  try { await state.pdf?.destroy?.(); } catch (_) {}
  state.pdf = null;
  state.pageViewport = null;
  state.pageLabels = null;
  state.browserToc = [];
  if (el.pageCanvas) {
    const context = el.pageCanvas.getContext("2d");
    context?.clearRect(0, 0, el.pageCanvas.width, el.pageCanvas.height);
    el.pageCanvas.width = 1;
    el.pageCanvas.height = 1;
  }
  el.pageTextLayer?.replaceChildren();
  clearSelectionHighlights();
}

function clearReader() {
  state.pdfLoadGeneration += 1;
  closePdfDocument().catch(() => {});
  state.currentSelection = null;
  state.mapData = null;
  state.mapParent = "root";
  state.mapSelected = null;
  state.tocData = [];
  state.lastRendererError = null;
  if (el.rendererError) el.rendererError.hidden = true;
  clearSelectionHighlights();
  el.selectionPopover.hidden = true;
  el.selectionActions.hidden = true;
  if (el.selectionDockBadge) el.selectionDockBadge.hidden = true;
  if (el.selectionModule) el.selectionModule.open = false;
  el.selectionCard.className = "selection-card empty-state";
  el.selectionCard.textContent = "Označte text nebo vzorec v knize. Potom vyberte způsob vysvětlení.";
}


function renderModels() {
  const models = state.data?.models || [];
  const settings = state.data?.settings || {};
  const selected = settings.base_model_user_selected ? (settings.base_model_id || "") : "";
  const preferred = settings.default_base_model_id || "glm-5.2";
  const resolved = settings.resolved_base_model_id || preferred;
  const options = [`<option value="">Výchozí: ${escapeHtml(preferred)}${resolved && resolved !== preferred ? ` → ${escapeHtml(resolved)}` : ""}</option>`].concat(
    models.map(model => `<option value="${escapeHtml(model.id)}">${escapeHtml(model.name || model.id)}</option>`)
  );
  el.modelSelect.innerHTML = options.join("");
  el.modelSelect.value = models.some(m => m.id === selected) ? selected : "";
}

async function saveModel() {
  await api("/study-tutor/api/settings/model", { method: "POST", body: JSON.stringify({ model_id: el.modelSelect.value }) });
  if (state.data?.settings) {
    state.data.settings.base_model_id = el.modelSelect.value;
    state.data.settings.base_model_user_selected = Boolean(el.modelSelect.value);
  }
  showToast(el.modelSelect.value ? "Zvolený základní model byl uložen." : "Použije se výchozí model glm-5.2.");
}

function renderProgress() {
  const progress = state.data?.progress || [];
  if (!progress.length) {
    el.progressList.className = "progress-list empty-state";
    el.progressList.textContent = "Pokrok vznikne po prvním kvízu nebo testu.";
    return;
  }
  el.progressList.className = "progress-list";
  el.progressList.innerHTML = progress.slice(0, 12).map(item => `
    <div class="progress-item"><strong>${escapeHtml(item.topic_name || "Studované téma")}</strong>
      <small>${Math.round(Number(item.mastery || 0) * 100)} % · ${Number(item.evidence_count || 0)} důkazů</small>
      <div class="progress-meter"><span style="width:${Math.max(0, Math.min(100, Number(item.mastery || 0) * 100))}%"></span></div>
    </div>`).join("");
}

function renderRecommendation() {
  const progress = state.data?.progress || [];
  delete el.recommendedAction.dataset.kind;
  delete el.recommendedAction.dataset.topic;
  let title = "Začněte orientací";
  let text = "Nechte tutora shrnout aktuální stranu a ověřit nezbytné předpoklady.";
  let button = "Vést výukou";
  if (progress.length) {
    const weakest = [...progress].sort((a, b) => Number(a.mastery) - Number(b.mastery))[0];
    if (weakest && Number(weakest.mastery) < 0.65) {
      title = `Procvičit: ${weakest.topic_name}`;
      text = "Nejslabší evidované téma je vhodné krátce vybavit z paměti a ověřit na novém příkladu.";
      button = "Spustit cílený kvíz";
      el.recommendedAction.dataset.kind = "weak-topic";
      el.recommendedAction.dataset.topic = weakest.topic_name || "";
    }
  }
  if (!progress.length && state.learningPath?.current_phase) {
    title = state.learningPath.current_phase.name || "Pokračovat v učební cestě";
    const goal = state.learningPath.current_goal?.name || "zvolený pedagogický cíl";
    text = `Aktuální fáze šablony směřuje k cíli „${goal}“. Tutor přizpůsobí tempo, diagnostiku i způsob zpětné vazby.`;
    button = "Pokračovat podle cesty";
  }
  if (!el.recommendedAction.dataset.kind) el.recommendedAction.dataset.kind = "teach";
  el.recommendation.querySelector("strong").textContent = title;
  el.recommendation.querySelector("p").textContent = text;
  el.recommendedAction.textContent = button;
}

async function installDemoBook() {
  if (!el.installDemo || el.installDemo.disabled) return;
  const accepted = await requestCanvasConfirmation({
    title: "Přidat ukázkovou knihu?",
    message: "VUT AI Tutor stáhne z oficiální stránky autora otevřenou knihu An Infinitely Large Napkin (CC BY-SA 4.0), uloží ji lokálně a zaindexuje.",
    acceptLabel: "Stáhnout knihu",
    icon: "📚",
  });
  if (!accepted) return;
  const original = el.installDemo.textContent;
  el.installDemo.disabled = true;
  el.installDemo.textContent = "Stahuji rozsáhlé PDF…";
  el.uploadProgress.hidden = false;
  el.uploadBar.style.width = "35%";
  el.uploadLabel.textContent = "Stahuji ukázkovou knihu z oficiálního zdroje…";
  try {
    const payload = await api("/study-tutor/api/demo/install", { method: "POST" });
    el.uploadBar.style.width = "100%";
    el.uploadLabel.textContent = payload.reused
      ? "Ukázková kniha už byla v knihovně. Otevírám ji…"
      : "Kniha je uložena. Na pozadí začíná indexování…";
    showToast(payload.reused ? "Ukázková kniha byla otevřena." : "Ukázková kniha byla přidána do knihovny.");
    clearReader();
    await loadState({ reopenBook: true });
  } catch (error) {
    el.uploadLabel.textContent = error.message;
    showToast(error.message, 6500);
  } finally {
    el.installDemo.disabled = false;
    el.installDemo.textContent = original;
    setTimeout(() => { el.uploadProgress.hidden = true; }, 2200);
  }
}

function isPdfFile(file) {
  return Boolean(file) && (file.name.toLowerCase().endsWith(".pdf") || file.type === "application/pdf");
}

function isMarkdownFile(file) {
  if (!file) return false;
  const name = file.name.toLowerCase();
  return name.endsWith(".md") || name.endsWith(".markdown") || file.type === "text/markdown";
}

async function xhrUpload(path, form, onProgress = null) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.setRequestHeader("Authorization", `Bearer ${state.token}`);
    xhr.upload.onprogress = event => {
      if (onProgress && event.lengthComputable) onProgress(event.loaded / event.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try { resolve(JSON.parse(xhr.responseText)); } catch (_) { reject(new Error("Neplatná odpověď serveru.")); }
      } else {
        try { reject(new Error(JSON.parse(xhr.responseText).detail || `Nahrání selhalo (${xhr.status}).`)); }
        catch (_) { reject(new Error(`Nahrání selhalo (${xhr.status}).`)); }
      }
    };
    xhr.onerror = () => reject(new Error("Síťová chyba při nahrávání."));
    xhr.send(form);
  });
}

async function uploadPdf(file, progressBase = 0, progressSpan = 1) {
  const form = new FormData();
  form.append("file", file, file.name);
  return xhrUpload("/study-tutor/api/upload", form, ratio => {
    el.uploadBar.style.width = `${Math.round((progressBase + ratio * progressSpan) * 100)}%`;
  });
}

async function uploadLearningPath(file, bookFileId, progressBase = 0, progressSpan = 1) {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("book_file_id", bookFileId || "");
  return xhrUpload("/study-tutor/api/learning-path/upload", form, ratio => {
    el.uploadBar.style.width = `${Math.round((progressBase + ratio * progressSpan) * 100)}%`;
  });
}

async function uploadFiles(fileList) {
  const files = Array.from(fileList || []).filter(Boolean);
  if (!files.length) return;
  const pdfs = files.filter(isPdfFile);
  const markdowns = files.filter(isMarkdownFile);
  const unsupported = files.filter(file => !isPdfFile(file) && !isMarkdownFile(file));
  if (unsupported.length) {
    showToast(`Nepodporovaný soubor: ${unsupported[0].name}. Použijte PDF a Markdown.`);
    return;
  }
  if (pdfs.length > 1 || markdowns.length > 1) {
    showToast("V jednom kroku vyberte nejvýše jednu knihu PDF a jednu Markdown učební cestu.");
    return;
  }
  if (!pdfs.length && !markdowns.length) return;

  el.uploadProgress.hidden = false;
  el.uploadBar.style.width = "0%";
  const labels = [];
  if (pdfs[0]) labels.push(pdfs[0].name);
  if (markdowns[0]) labels.push(markdowns[0].name);
  el.uploadLabel.textContent = `Nahrávám ${labels.join(" + ")}…`;

  try {
    let bookFileId = state.activeBook?.file_id || "";
    let bookResult = null;
    let pathResult = null;
    if (pdfs[0]) {
      const span = markdowns[0] ? .72 : 1;
      bookResult = await uploadPdf(pdfs[0], 0, span);
      bookFileId = bookResult.file_id;
      el.uploadLabel.textContent = markdowns[0]
        ? "PDF je uloženo. Přiřazuji pedagogickou šablonu…"
        : "PDF je uloženo. Začíná indexování…";
    }
    if (markdowns[0]) {
      if (!bookFileId) throw new Error("Nejprve přidejte PDF knihu, ke které se má učební cesta přiřadit.");
      const base = pdfs[0] ? .72 : 0;
      const span = pdfs[0] ? .28 : 1;
      pathResult = await uploadLearningPath(markdowns[0], bookFileId, base, span);
      state.activeView = "path";
      el.uploadLabel.textContent = "Učební cesta byla přiřazena ke knize.";
    }
    el.uploadBar.style.width = "100%";
    if (el.uploadDialog.open) el.uploadDialog.close();
    clearReader();
    await loadState({ reopenBook: Boolean(pdfs[0]) });
    if (pathResult) showToast(`Učební cesta „${pathResult.learning_path?.name || markdowns[0].name}“ je aktivní.`);
    else if (bookResult) showToast(`Kniha „${bookResult.title || pdfs[0].name}“ byla přidána.`);
  } catch (error) {
    el.uploadLabel.textContent = error.message;
    showToast(error.message, 6500);
  } finally {
    setTimeout(() => { el.uploadProgress.hidden = true; }, 1800);
    el.fileInput.value = "";
    el.dialogFileInput.value = "";
    if (el.pathFileInput) el.pathFileInput.value = "";
    if (el.pathEmptyFileInput) el.pathEmptyFileInput.value = "";
  }
}

async function ensurePdfViewerStylesheet(href) {
  const targetHref = new URL(href, location.href).href;
  let link = document.getElementById("pdfjs-viewer-style");
  if (link && link.href === targetHref && link.sheet) return;
  const replacement = document.createElement("link");
  replacement.id = "pdfjs-viewer-style";
  replacement.rel = "stylesheet";
  replacement.crossOrigin = "anonymous";
  replacement.href = href;
  const loaded = new Promise((resolve, reject) => {
    replacement.addEventListener("load", resolve, { once: true });
    replacement.addEventListener("error", () => reject(new Error(`Nepodařilo se načíst styly PDF.js z ${href}.`)), { once: true });
  });
  link?.remove();
  document.head.appendChild(replacement);
  await loaded;
}

function defineCompatibilityMethod(prototype, name, implementation) {
  if (!prototype || typeof prototype[name] === "function") return;
  Object.defineProperty(prototype, name, {
    configurable: true,
    enumerable: false,
    writable: true,
    value: implementation,
  });
}

function installPdfCompatibilityShims() {
  if (typeof Promise.withResolvers !== "function") {
    Promise.withResolvers = function withResolvers() {
      let resolve, reject;
      const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
      return { promise, resolve, reject };
    };
  }
  if (typeof URL.parse !== "function") {
    URL.parse = function parseUrl(value, base) {
      try { return new URL(value, base); } catch (_error) { return null; }
    };
  }
  if (typeof Array.prototype.toSorted !== "function") {
    defineCompatibilityMethod(Array.prototype, "toSorted", function toSorted(compareFn) {
      return Array.from(this).sort(compareFn);
    });
  }
  defineCompatibilityMethod(Map.prototype, "getOrInsert", function getOrInsert(key, value) {
    if (!this.has(key)) this.set(key, value);
    return this.get(key);
  });
  defineCompatibilityMethod(Map.prototype, "getOrInsertComputed", function getOrInsertComputed(key, callbackFn) {
    if (!this.has(key)) this.set(key, callbackFn(key));
    return this.get(key);
  });
  if (typeof WeakMap !== "undefined") {
    defineCompatibilityMethod(WeakMap.prototype, "getOrInsert", function getOrInsert(key, value) {
      if (!this.has(key)) this.set(key, value);
      return this.get(key);
    });
    defineCompatibilityMethod(WeakMap.prototype, "getOrInsertComputed", function getOrInsertComputed(key, callbackFn) {
      if (!this.has(key)) this.set(key, callbackFn(key));
      return this.get(key);
    });
  }
  if (typeof Math.sumPrecise !== "function") {
    Math.sumPrecise = function sumPrecise(numbers) {
      let total = 0;
      for (const value of numbers) total += Number(value);
      return total;
    };
  }
}

function supportsModernPdfJsRuntime() {
  return typeof Promise.withResolvers === "function"
    && typeof URL.parse === "function"
    && typeof Array.prototype.toSorted === "function"
    && typeof Map.prototype.getOrInsert === "function"
    && typeof Map.prototype.getOrInsertComputed === "function";
}

function pdfRuntimeFeatureSummary() {
  return [
    `Map.getOrInsert=${typeof Map.prototype.getOrInsert === "function"}`,
    `Map.getOrInsertComputed=${typeof Map.prototype.getOrInsertComputed === "function"}`,
    `Promise.withResolvers=${typeof Promise.withResolvers === "function"}`,
    `URL.parse=${typeof URL.parse === "function"}`,
  ].join(", ");
}


async function diagnosePdfTransport(fileId, token) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  let reader = null;
  try {
    const response = await fetch(`/study-tutor/api/pdf/${encodeURIComponent(fileId)}`, {
      headers: { Authorization: `Bearer ${token}`, Range: "bytes=0-1023" },
      credentials: "omit", cache: "no-store", signal: controller.signal,
    });
    const status = response.status;
    if (response.ok) {
      await response.body?.cancel();
      return { status, text: `Kontrolní načtení PDF nyní vrací HTTP ${status}; původní chyba mohla nastat později nebo být dočasná.` };
    }
    let text = "";
    const contentType = response.headers.get("Content-Type") || "";
    if (contentType.includes("application/json") && response.body) {
      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let received = 0;
      while (received < 16384) {
        const { done, value } = await reader.read();
        if (done) break;
        const part = value.subarray(0, 16384 - received);
        text += decoder.decode(part, { stream: true });
        received += part.length;
      }
      text += decoder.decode();
      try {
        const data = JSON.parse(text);
        const detail = data.detail;
        text = typeof detail === "string" ? detail : (detail?.message || "Server odmítl načtení PDF.");
        const code = detail?.code || data.code;
        const errorId = detail?.error_id || data.error_id;
        const errorType = detail?.error_type || data.error_type;
        if (code) text += `\nKód: ${code}`;
        if (typeof detail?.recovery === "string") text += `\nObnova zdroje: ${detail.recovery.slice(0, 120)}`;
        if (typeof detail?.hint === "string") text += `\nPostup: ${detail.hint.slice(0, 1000)}`;
        if (errorId) text += `\nID chyby pro serverový log: ${errorId}`;
        if (errorType) text += `\nTyp výjimky: ${errorType}`;
      } catch (_) { text = "Server nevrátil platnou JSON diagnostiku."; }
    } else {
      await response.body?.cancel();
      text = "Server nevrátil PDF ani JSON diagnostiku. Podrobnosti jsou v logu Open WebUI.";
    }
    return { status, text: `PDF endpoint: HTTP ${status}\n${text}` };
  } catch (error) {
    return { status: 0, text: `Kontrolní načtení PDF selhalo: ${error?.name === "AbortError" ? "časový limit" : (error?.message || String(error))}` };
  } finally {
    if (reader) { try { await reader.cancel(); } catch (_) {} }
    clearTimeout(timer);
  }
}

function showRendererError(error) {
  state.lastRendererError = error instanceof Error ? error : new Error(String(error || "Neznámá chyba PDF rendereru."));
  state.fallbackMode = false;
  el.readerMessage.hidden = true;
  el.pageStage.hidden = true;
  el.textFallback.hidden = true;
  if (el.rendererError) {
    el.rendererError.hidden = false;
    const transport = state.lastRendererError.pdfTransportDiagnostic;
    const httpStatus = Number(state.lastRendererError.status || transport?.status || 0);
    el.rendererErrorText.textContent = httpStatus >= 400
      ? "Server neposkytl PDF. Jde o chybu načtení souboru, ne o prokázanou chybu PDF.js rendereru. Podrobnosti jsou uvedeny níže."
      : "PDF se nepodařilo načíst nebo vykreslit. Textový režim je dostupný jako diagnostický fallback.";
    el.rendererErrorDetail.textContent = [
      state.lastRendererError.message || String(state.lastRendererError),
      state.lastRendererError.stack || "",
      state.lastRendererError.pdfTransportDiagnostic?.text || "",
      "PDF delivery hotfix: 1.26.4 / pdf-delivery-r2",
      `PDF.js asset version: ${state.pdfjs?.version || "6.2.108"}`,
      `PDF.js bundle: ${state.pdfBundleLabel || state.pdfBundleKind || "nezjištěno"}`,
      `Runtime: ${pdfRuntimeFeatureSummary()}`,
      `Browser: ${navigator.userAgent || "nezjištěno"}`,
      `Book: ${state.activeBook?.title || ""}`,
    ].filter(Boolean).join("\n\n");
  }
  setIndexStatus("PDF nelze načíst nebo vykreslit", "warning");
}

async function loadPdfJs({ forceLegacy = false } = {}) {
  if (state.pdfjs) return state.pdfjs;
  if (!window.__STUDY_CANVAS_READY__) {
    boot.step(67, "Načítám PDF.js renderer…", "Používám přímé vykreslení stránky na canvas bez závislosti na generickém vieweru.");
  }
  const nativeModernRuntime = supportsModernPdfJsRuntime();
  installPdfCompatibilityShims();
  ++state.pdfModuleAttempt;

  const legacyCandidate = {
    core: "/study-tutor/pdfjs/legacy/build/pdf.mjs",
    worker: "/study-tutor/pdfjs/legacy/build/pdf.worker.min.mjs",
    resources: "/study-tutor/pdfjs/legacy/",
    kind: "legacy",
    label: "kompatibilní PDF.js core pro starší Chromium",
  };
  const modernCandidate = {
    core: "/study-tutor/pdfjs/build/pdf.mjs",
    worker: "/study-tutor/pdfjs/build/pdf.worker.min.mjs",
    resources: "/study-tutor/pdfjs/",
    kind: "modern",
    label: "moderní PDF.js core",
  };
  const candidates = [legacyCandidate];
  if (!forceLegacy && nativeModernRuntime) candidates.push(modernCandidate);

  let lastError = null;
  for (const candidate of candidates) {
    try {
      const pdfjs = await import(candidate.core);
      if (typeof pdfjs.getDocument !== "function") throw new Error("PDF.js modul neposkytuje getDocument().");
      pdfjs.GlobalWorkerOptions.workerSrc = candidate.worker;
      state.pdfjs = pdfjs;
      state.pdfViewerLib = null;
      state.pdfBundleKind = candidate.kind;
      state.pdfBundleLabel = candidate.label;
      state.pdfViewerReady = true;
      state.pdfViewer = el.pageShell;
      globalThis.pdfjsLib = pdfjs;
      if (!window.__STUDY_CANVAS_READY__) {
        boot.step(76, "PDF renderer je připraven", `Používám ${candidate.label}, PDF.js ${pdfjs.version || ""}.`);
      }
      return pdfjs;
    } catch (error) {
      console.warn(`PDF.js ${candidate.label} bundle failed`, error);
      lastError = error;
      state.pdfjs = null;
      state.pdfViewer = null;
      state.pdfBundleKind = null;
      state.pdfBundleLabel = "";
      globalThis.pdfjsLib = undefined;
    }
  }
  const modernNote = nativeModernRuntime
    ? ""
    : " Moderní bundle nebyl spuštěn, protože zabudované Chromium nepodporuje všechna požadovaná API.";
  throw new Error(`PDF.js renderer se nepodařilo načíst. ${lastError?.message || ""}${modernNote}`.trim());
}

function setPageRenderBusy(busy, label = "Vykresluji stranu…") {
  if (!el.pageRenderState) return;
  el.pageRenderState.hidden = !busy;
  if (el.pageRenderLabel) el.pageRenderLabel.textContent = label;
}

function pageScaleForViewport(page) {
  const base = page.getViewport({ scale: 1 });
  if (state.fitWidthMode) {
    const available = Math.max(260, (el.viewerContainer?.clientWidth || 800) - 38);
    state.scale = Math.max(0.2, Math.min(4.0, available / Math.max(1, base.width)));
  }
  return Math.max(0.2, Math.min(4.0, Number(state.scale || 1)));
}

function manualTextTransform(pdfjs, viewport, item) {
  const util = pdfjs?.Util;
  const transform = typeof util?.transform === "function"
    ? util.transform(viewport.transform, item.transform)
    : item.transform;
  const angle = Math.atan2(transform[1] || 0, transform[0] || 1);
  const fontHeight = Math.max(1, Math.hypot(transform[2] || 0, transform[3] || 0));
  return { transform, angle, fontHeight };
}

async function renderManualTextLayer(page, viewport, container, generation, providedContent = null) {
  const content = providedContent || await page.getTextContent({ includeMarkedContent: true });
  if (generation !== state.renderGeneration) return;
  const fragment = document.createDocumentFragment();
  let itemIndex = 0;
  for (const item of content.items || []) {
    if (!item || typeof item.str !== "string" || !item.str) continue;
    const span = document.createElement("span");
    span.textContent = item.str;
    span.dir = item.dir || "ltr";
    span.dataset.vutTextIndex = String(itemIndex++);
    const { transform, angle, fontHeight } = manualTextTransform(state.pdfjs, viewport, item);
    span.style.left = `${transform[4] || 0}px`;
    span.style.top = `${(transform[5] || 0) - fontHeight}px`;
    span.style.fontSize = `${fontHeight}px`;
    span.style.fontFamily = "sans-serif";
    if (angle) span.style.transform = `rotate(${angle}rad)`;
    fragment.appendChild(span);
  }
  container.replaceChildren(fragment);
  annotateTextLayerSpans(container, content);
  // Align horizontal metrics after nodes are attached. This is only a selection layer;
  // the visible mathematical typography always comes from the rendered canvas below it.
  const spans = Array.from(container.querySelectorAll("span"));
  let index = 0;
  for (const item of content.items || []) {
    if (!item || typeof item.str !== "string" || !item.str) continue;
    const span = spans[index++];
    const measured = span?.getBoundingClientRect().width || 0;
    const expected = Math.abs(Number(item.width || 0) * viewport.scale);
    if (span && measured > 0 && expected > 0) {
      const current = span.style.transform || "";
      span.style.transform = `${current} scaleX(${Math.max(.1, Math.min(10, expected / measured))})`.trim();
    }
  }
}

async function renderTextSelectionLayer(page, viewport, generation) {
  const container = el.pageTextLayer;
  if (!container) return;
  container.replaceChildren();
  container.style.width = `${viewport.width}px`;
  container.style.height = `${viewport.height}px`;
  // PDF.js TextLayer reads these variables from the container in recent releases.
  // Setting both keeps the layer aligned across modern and legacy bundles.
  container.style.setProperty("--scale-factor", String(viewport.scale));
  container.style.setProperty("--total-scale-factor", String(viewport.scale));
  const textContent = await page.getTextContent({ includeMarkedContent: true });
  if (generation !== state.renderGeneration) return;
  state.pageTextContent = textContent;
  state.pageTextItems = (textContent.items || []).filter(item => item && typeof item.str === "string" && item.str.length);

  // PDF.js 4+ exports TextLayer from the display module. It positions transparent
  // glyph spans over the exact visual canvas, preserving native selection/copy.
  if (typeof state.pdfjs?.TextLayer === "function") {
    try {
      const task = new state.pdfjs.TextLayer({
        textContentSource: textContent,
        container,
        viewport,
      });
      state.textLayerTask = task;
      await task.render();
      if (generation !== state.renderGeneration) return;
      annotateTextLayerSpans(container, textContent);
      return;
    } catch (error) {
      console.info("PDF.js TextLayer fallback", error);
      container.replaceChildren();
    }
  }
  if (typeof state.pdfjs?.renderTextLayer === "function") {
    try {
      const task = state.pdfjs.renderTextLayer({
        textContentSource: textContent,
        container,
        viewport,
        textDivs: [],
      });
      state.textLayerTask = task;
      await (task?.promise || task);
      if (generation !== state.renderGeneration) return;
      annotateTextLayerSpans(container, textContent);
      return;
    } catch (error) {
      console.info("PDF.js renderTextLayer fallback", error);
      container.replaceChildren();
    }
  }
  await renderManualTextLayer(page, viewport, container, generation, textContent);
}

async function renderCurrentPage({ resetScroll = false, scrollTo = "top" } = {}) {
  if (!state.pdf || !el.pageCanvas || !el.pageShell) return;
  const generation = ++state.renderGeneration;
  try { state.pageRenderTask?.cancel?.(); } catch (_) {}
  state.pageRenderTask = null;
  try { state.textLayerTask?.cancel?.(); } catch (_) {}
  state.textLayerTask = null;
  state.pageTextContent = null;
  state.pageTextItems = [];
  state.pageTextSpans = [];
  clearSelectionHighlights();
  setPageRenderBusy(true, `Vykresluji PDF stranu ${state.page}…`);

  const page = await state.pdf.getPage(state.page);
  if (generation !== state.renderGeneration) return;
  const scale = pageScaleForViewport(page);
  const viewport = page.getViewport({ scale });
  state.pageViewport = viewport;
  state.scale = scale;
  el.pageShell.dataset.pageNumber = String(state.page);
  el.pageShell.style.width = `${Math.ceil(viewport.width)}px`;
  el.pageShell.style.height = `${Math.ceil(viewport.height)}px`;

  const canvas = el.pageCanvas;
  const context = canvas.getContext("2d", { alpha: false, willReadFrequently: false });
  if (!context) throw new Error("Prohlížeč neposkytuje 2D canvas kontext.");
  let outputScale = Math.max(1, Math.min(2.5, Number(window.devicePixelRatio || 1)));
  const maxPixels = 48 * 1024 * 1024;
  const desiredPixels = viewport.width * viewport.height * outputScale * outputScale;
  if (desiredPixels > maxPixels) outputScale *= Math.sqrt(maxPixels / desiredPixels);
  canvas.width = Math.max(1, Math.floor(viewport.width * outputScale));
  canvas.height = Math.max(1, Math.floor(viewport.height * outputScale));
  canvas.style.width = `${viewport.width}px`;
  canvas.style.height = `${viewport.height}px`;
  context.save();
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.restore();

  const renderTask = page.render({
    canvasContext: context,
    viewport,
    transform: outputScale === 1 ? null : [outputScale, 0, 0, outputScale, 0, 0],
    intent: "display",
    annotationMode: state.pdfjs?.AnnotationMode?.ENABLE_FORMS ?? 2,
    background: "rgb(255,255,255)",
  });
  state.pageRenderTask = renderTask;
  await renderTask.promise;
  if (generation !== state.renderGeneration) return;
  await renderTextSelectionLayer(page, viewport, generation);
  if (generation !== state.renderGeneration) return;

  setPageRenderBusy(false);
  el.readerMessage.hidden = true;
  el.pageStage.hidden = false;
  if (resetScroll && el.viewerContainer) {
    el.viewerContainer.scrollTop = scrollTo === "bottom"
      ? Math.max(0, el.viewerContainer.scrollHeight - el.viewerContainer.clientHeight)
      : 0;
    el.viewerContainer.scrollLeft = Math.max(0, (el.pageRenderHost.scrollWidth - el.viewerContainer.clientWidth) / 2);
  }
  updatePdfControls(state.page);
  if (!window.__STUDY_CANVAS_READY__) {
    boot.step(97, "První strana je vykreslena", "Originální sazba je na canvasu a průhledná textová vrstva umožňuje výběr pasáží.");
  }
}

function pageLabel(pageNumber) {
  const label = Array.isArray(state.pageLabels) ? state.pageLabels[pageNumber - 1] : null;
  return label && String(label) !== String(pageNumber) ? String(label) : "";
}

function updatePdfControls(pageNumber = state.page) {
  const total = Number(state.pdf?.numPages || 0);
  const page = Math.max(1, Math.min(total || 1, Number(pageNumber || 1)));
  state.page = page;
  el.pageInput.value = String(page);
  el.pageInput.max = String(total || 1);
  el.pageTotal.textContent = total ? `/ ${total}${pageLabel(page) ? ` · tisk ${pageLabel(page)}` : ""}` : "/ …";
  el.prevPage.disabled = page <= 1;
  el.nextPage.disabled = !total || page >= total;
  const scale = Number(state.scale || 1);
  state.scale = scale;
  el.zoomLabel.textContent = state.fitWidthMode ? "Na šířku" : `${Math.round(scale * 100)} %`;
  el.scopeLabel.textContent = `Rozsah: PDF strana ${page}${pageLabel(page) ? ` (tištěná ${pageLabel(page)})` : ""}`;
}

async function openActiveBook() {
  if (!state.activeBook) return;
  const generation = ++state.pdfLoadGeneration;
  const loadingFileId = state.activeBook.file_id;
  const loadingToken = state.token;
  await closePdfDocument();
  state.page = Math.max(1, Number(state.data.session?.current_page || 1));
  state.fitWidthMode = true;
  state.scale = 1;
  el.pageInput.value = String(state.page);
  el.scopeLabel.textContent = `Rozsah: PDF strana ${state.page}`;
  el.readerMessage.hidden = false;
  el.readerMessage.textContent = "Načítám originální PDF…";
  if (el.rendererError) el.rendererError.hidden = true;
  el.pageStage.hidden = true;
  el.textFallback.hidden = true;
  state.fallbackMode = false;
  try {
    const pdfjs = await loadPdfJs();
    if (generation !== state.pdfLoadGeneration) return;
    showPdfLoadProgress(0, 0);
    const loadingTask = pdfjs.getDocument({
      url: `/study-tutor/api/pdf/${encodeURIComponent(loadingFileId)}`,
      httpHeaders: { Authorization: `Bearer ${loadingToken}` },
      withCredentials: false,
      cMapUrl: "/study-tutor/pdfjs/cmaps/",
      cMapPacked: true,
      standardFontDataUrl: "/study-tutor/pdfjs/standard_fonts/",
      wasmUrl: "/study-tutor/pdfjs/wasm/",
      iccUrl: "/study-tutor/pdfjs/iccs/",
      enableXfa: true,
      disableAutoFetch: false,
      disableStream: false,
      rangeChunkSize: 131072,
      stopAtErrors: false,
      isEvalSupported: true,
    });
    state.pdfLoadingTask = loadingTask;
    loadingTask.onProgress = ({ loaded = 0, total = 0 } = {}) => showPdfLoadProgress(loaded, total);
    state.pdf = await loadingTask.promise;
    if (generation !== state.pdfLoadGeneration) return;
    if (!window.__STUDY_CANVAS_READY__) {
      boot.step(86, "PDF bylo otevřeno", `Dokument má ${state.pdf.numPages} stran; vykresluji aktuální stránku.`);
    }
    state.page = Math.min(state.page, state.pdf.numPages);
    state.pageLabels = await state.pdf.getPageLabels().catch(() => null);
    updatePdfControls(state.page);
    el.pageStage.hidden = false;
    await renderCurrentPage({ resetScroll: true });
    if (generation !== state.pdfLoadGeneration) return;
    if (el.rendererError) el.rendererError.hidden = true;
    extractBrowserToc().catch(error => console.info("Native PDF outline unavailable", error));
    if (window.__STUDY_CANVAS_READY__) updateBookStatus();
  } catch (error) {
    if (error?.name === "RenderingCancelledException" || generation !== state.pdfLoadGeneration) return;
    const diagnostic = await diagnosePdfTransport(loadingFileId, loadingToken);
    if (generation !== state.pdfLoadGeneration) return;
    if (!(error instanceof Error)) error = new Error(String(error));
    error.pdfTransportDiagnostic = diagnostic;
    console.error("PDF loading/rendering failed", error);
    setPageRenderBusy(false);
    showRendererError(error);
    if (window.__STUDY_CANVAS_READY__) updateProcessingProgress();
    if (!window.__STUDY_CANVAS_READY__) {
      boot.step(94, "PDF nelze načíst nebo vykreslit", "Podrobnost a bezpečný textový fallback jsou dostupné v čtečce.");
    }
  }
}

async function openTextFallback(cause) {
  state.fallbackMode = true;
  if (el.rendererError) el.rendererError.hidden = true;
  el.readerMessage.hidden = true;
  el.pageStage.hidden = true;
  el.textFallback.hidden = false;
  el.pageTotal.textContent = "/ text";
  try {
    const payload = await api(`/study-tutor/api/text/${encodeURIComponent(state.activeBook.file_id)}`);
    const prefix = `Plný PDF renderer se nepodařilo spustit: ${cause?.message || "neznámá chyba"}\n\n`;
    el.fallbackContent.textContent = prefix + (payload.content || "Text knihy zatím není dostupný. Stiskněte Obnovit po dokončení extrakce.");
    if (!payload.content) setIndexStatus("Čekám na extrakci textu", "processing");
  } catch (error) {
    el.fallbackContent.textContent = `Knihu se nepodařilo zobrazit. ${cause?.message || ""}\n${error.message}`;
  }
  reportHeight();
}

async function renderPage() {
  return renderCurrentPage();
}

async function goToPage(page, { scrollTo = "top" } = {}) {
  if (state.fallbackMode || !state.pdf) return;
  const target = Math.max(1, Math.min(state.pdf.numPages, Number(page) || 1));
  state.page = target;
  updatePdfControls(target);
  await renderCurrentPage({ resetScroll: true, scrollTo });
  api("/study-tutor/api/page", { method: "POST", body: JSON.stringify({ page: target }) }).catch(() => {});
}

function resetWheelPageIntent() {
  state.wheelPageDelta = 0;
  clearTimeout(state.wheelPageTimer);
  state.wheelPageTimer = null;
}

function handleReaderWheel(event) {
  if (!state.pdf || state.fallbackMode || state.activeView !== "book" || state.wheelTransitioning) return;
  if (event.ctrlKey || event.metaKey || event.shiftKey || Math.abs(event.deltaY) < Math.abs(event.deltaX)) return;
  const container = el.viewerContainer;
  if (!container) return;
  const multiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? Math.max(1, container.clientHeight) : 1;
  const delta = Number(event.deltaY || 0) * multiplier;
  const atTop = container.scrollTop <= 3;
  const atBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 3;
  const canNext = state.page < Number(state.pdf.numPages || 0);
  const canPrevious = state.page > 1;
  const boundaryDirection = (delta > 0 && atBottom && canNext) ? 1 : (delta < 0 && atTop && canPrevious) ? -1 : 0;
  if (!boundaryDirection) {
    resetWheelPageIntent();
    return;
  }
  event.preventDefault();
  state.wheelPageDelta += Math.abs(delta);
  clearTimeout(state.wheelPageTimer);
  state.wheelPageTimer = setTimeout(resetWheelPageIntent, 450);
  if (state.wheelPageDelta < 90) return;
  resetWheelPageIntent();
  state.wheelTransitioning = true;
  const target = state.page + boundaryDirection;
  const scrollTo = boundaryDirection > 0 ? "top" : "bottom";
  goToPage(target, { scrollTo })
    .catch(error => showRendererError(error))
    .finally(() => setTimeout(() => { state.wheelTransitioning = false; }, 180));
}

async function fitWidth() {
  if (!state.pdf) return;
  state.fitWidthMode = true;
  await renderCurrentPage();
  updatePdfControls();
}

async function changeZoom(factor) {
  if (!state.pdf) return;
  state.fitWidthMode = false;
  state.scale = Math.max(.2, Math.min(4, Number(state.scale || 1) * factor));
  await renderCurrentPage();
  updatePdfControls();
}

function normalizedRectangles(range, pageElement) {
  const pageRect = pageElement.getBoundingClientRect();
  if (!pageRect.width || !pageRect.height) return [];
  return Array.from(range.getClientRects()).map(rect => {
    const left = Math.max(rect.left, pageRect.left);
    const top = Math.max(rect.top, pageRect.top);
    const right = Math.min(rect.right, pageRect.right);
    const bottom = Math.min(rect.bottom, pageRect.bottom);
    if (right - left <= 1 || bottom - top <= 1) return null;
    return {
      x: Math.max(0, Math.min(1, (left - pageRect.left) / pageRect.width)),
      y: Math.max(0, Math.min(1, (top - pageRect.top) / pageRect.height)),
      width: Math.max(.0001, Math.min(1, (right - left) / pageRect.width)),
      height: Math.max(.0001, Math.min(1, (bottom - top) / pageRect.height)),
    };
  }).filter(Boolean).slice(0, 120);
}

function elementFromNode(node) {
  if (!node) return null;
  return node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
}

async function captureSelection(event) {
  const browserSelection = window.getSelection();
  const rawText = normalizeSelectedText(browserSelection?.toString());
  if (!browserSelection || !rawText || rawText.length < 2 || browserSelection.rangeCount === 0 || !state.activeBook) return;
  const range = browserSelection.getRangeAt(0);
  let pageNumber = state.page;
  let rectangles = [];
  let pageElement = null;
  let glyphs = [];
  let selectedText = rawText;
  let linearText = rawText;
  let latexText = "";
  let latexConfidence = 0;
  let latexSource = "none";
  let contextBefore = "";
  let contextAfter = "";
  let imageDataUrl = "";
  let transcriptionQuality = "plain-text";
  if (state.fallbackMode) {
    if (!el.fallbackContent.contains(range.commonAncestorContainer)) return;
  } else {
    const startElement = elementFromNode(range.startContainer);
    pageElement = startElement?.closest?.(".pdf-page-shell[data-page-number]");
    if (!pageElement || !el.pdfViewer.contains(pageElement)) return;
    const endElement = elementFromNode(range.endContainer);
    if (endElement?.closest?.(".pdf-page-shell[data-page-number]") !== pageElement) {
      showToast("Výběr musí ležet na jedné PDF stránce.", 5500);
      return;
    }
    pageNumber = Number(pageElement.dataset.pageNumber || state.page);
    rectangles = normalizedRectangles(range, pageElement);
    glyphs = selectedGlyphRuns(range, pageElement);
    linearText = spatialTranscript(glyphs, rawText);
    // The geometry-filtered transcript is more reliable than DOM selection order in multi-column PDFs.
    const geometryText = normalizeSelectedText(clusterGlyphLines(glyphs)
      .map(line => line.runs.map(run => run.text).join(" "))
      .join("\n"));
    if (geometryText && geometryText.length >= Math.min(2, rawText.length)) selectedText = geometryText;
    const latex = bestEffortLatex(glyphs, selectedText);
    latexText = latex.text || "";
    latexConfidence = Number(latex.confidence || 0);
    latexSource = String(latex.source || "none");
    const surrounding = selectionSurroundingContext(glyphs);
    contextBefore = surrounding.before;
    contextAfter = surrounding.after;
    imageDataUrl = captureSelectionCrop(rectangles);
    transcriptionQuality = `${latexSource}+pdf-geometry${imageDataUrl ? "+visual-crop" : ""}`;
  }
  try {
    const payload = await api("/study-tutor/api/selections", {
      method: "POST",
      body: JSON.stringify({
        page_index: Math.max(0, pageNumber - 1),
        text: selectedText.slice(0, 40000),
        linear_text: linearText.slice(0, 40000),
        latex_text: latexText.slice(0, 20000),
        latex_confidence: Math.max(0, Math.min(1, latexConfidence)),
        mathml_text: "",
        context_before: contextBefore.slice(0, 4000),
        context_after: contextAfter.slice(0, 4000),
        transcription_quality: transcriptionQuality,
        glyphs: glyphs.slice(0, 1600),
        image_data_url: imageDataUrl,
        rectangles,
      }),
    });
    state.currentSelection = {
      ...payload,
      file_id: payload.file_id || state.activeBook?.file_id || "",
      session_id: payload.session_id || state.sessionId || "",
    };
    renderSelection();
    if (pageElement) drawSelection(rectangles, pageElement);
    const rangeRect = range.getBoundingClientRect();
    const x = event?.clientX || rangeRect.left;
    const y = event?.clientY || rangeRect.top;
    el.selectionPopover.hidden = false;
    el.selectionPopover.style.left = `${Math.max(8, Math.min(window.innerWidth - 410, x - 120))}px`;
    el.selectionPopover.style.top = `${Math.max(80, y - 54)}px`;
    browserSelection.removeAllRanges();
    showToast(latexConfidence >= 0.72
      ? "Výběr je uložen včetně matematického přepisu s vyšší jistotou."
      : "Výběr je uložen. Složitý zápis bude ověřen z originálního výřezu PDF.", 4600);
  } catch (error) { showToast(error.message); }
}

function drawSelection(rectangles, pageElement) {
  clearSelectionHighlights();
  if (!pageElement || !el.selectionOverlay) return;
  for (const rect of rectangles || []) {
    const marker = document.createElement("div");
    marker.className = "selection-highlight";
    marker.style.left = `${rect.x * 100}%`;
    marker.style.top = `${rect.y * 100}%`;
    marker.style.width = `${rect.width * 100}%`;
    marker.style.height = `${rect.height * 100}%`;
    el.selectionOverlay.appendChild(marker);
  }
}

async function extractBrowserToc() {
  if (!state.pdf) return;
  const outline = await state.pdf.getOutline();
  if (!outline?.length) return;
  const labels = state.pageLabels || await state.pdf.getPageLabels().catch(() => null);
  const flat = [];
  let sequence = 0;
  const resolvePage = async dest => {
    try {
      let value = dest;
      if (typeof value === "string") value = await state.pdf.getDestination(value);
      if (!Array.isArray(value) || value.length < 1) return 0;
      const ref = value[0];
      const index = Number.isInteger(ref) ? ref : await state.pdf.getPageIndex(ref);
      return Number(index) + 1;
    } catch (_) { return 0; }
  };
  const walk = async (items, level = 0, parentId = null) => {
    for (const item of items || []) {
      if (flat.length >= 3000) return;
      const id = `pdf-outline-${++sequence}`;
      const page = await resolvePage(item.dest);
      flat.push({
        id, parent_id: parentId, level,
        title: String(item.title || "Bez názvu").trim(),
        page,
        page_label: page && labels?.[page - 1] ? String(labels[page - 1]) : String(page || ""),
        source: "pdf-outline",
      });
      if (item.items?.length) await walk(item.items, level + 1, id);
    }
  };
  await walk(outline);
  if (!flat.length) return;
  state.browserToc = flat;
  if (!state.tocData.length) state.tocData = flat;
  if (state.activeView === "toc") renderToc();
  api("/study-tutor/api/toc/import", {
    method: "POST",
    body: JSON.stringify({ items: flat, total_pages: state.pdf.numPages }),
  }).catch(() => {});
}

function setSelectionActionPending(pending, label = "") {
  state.actionPending = Boolean(pending);
  el.selectionActions?.querySelectorAll("button").forEach(button => { button.disabled = Boolean(pending); });
  if (el.selectionCard) {
    el.selectionCard.classList.toggle("pending", Boolean(pending));
    el.selectionCard.setAttribute("aria-busy", pending ? "true" : "false");
    const meta = el.selectionCard.querySelector(".selection-meta");
    if (meta && label) meta.textContent = label;
  }
}

function renderSelection() {
  const selection = state.currentSelection;
  if (selection) applyDockTab("guidance", true, true);
  if (!selection) return;
  if (el.selectionDockBadge) el.selectionDockBadge.hidden = false;
  if (el.selectionModule) el.selectionModule.open = true;
  el.selectionCard.className = "selection-card";
  const confidence = Math.round(Number(selection.latex_confidence || 0) * 100);
  const mathBadge = selection.latex_text && confidence >= 72 ? ` · matematický přepis ${confidence} %` : selection.has_visual_crop ? " · vizuální kontrola zápisu" : "";
  el.selectionCard.innerHTML = `<blockquote>${escapeHtml(selection.selected_text)}</blockquote><div class="selection-meta">PDF strana ${selection.page_index + 1}${mathBadge}</div>`;
  el.selectionActions.hidden = false;
  renderToolActions();
}

async function searchBook(event) {
  applyDockTab("search");
  event?.preventDefault();
  const query = el.searchInput.value.trim();
  if (!query || !state.activeBook) return;
  el.searchResults.className = "search-results empty-state";
  el.searchResults.textContent = "Hledám pojmy a pasáže…";
  try {
    const payload = await api("/study-tutor/api/search", {}, { q: query, limit: 10 });
    const concepts = payload.concepts || [];
    const items = payload.results || [];
    if (!concepts.length && !items.length) {
      el.searchResults.textContent = "Nic nebylo nalezeno. Analýza pojmů nebo Knowledge indexování možná ještě probíhá.";
      return;
    }
    el.searchResults.className = "search-results";
    const conceptHtml = concepts.map(item => `
      <div class="search-result search-concept-result" data-concept-result="${escapeHtml(item.id)}">
        <strong>${escapeHtml(item.name)}</strong>
        <span>${escapeHtml(item.description || "Klíčový pojem v učebnici")}</span>
        <small>${(item.pages || []).length ? `Výskyty: PDF str. ${(item.pages || []).slice(0, 5).join(", ")}` : "Pojem z mapy znalostí"}</small>
        <div class="search-result-actions">
          ${(item.pages || []).slice(0, 3).map(page => `<button type="button" data-open-page="${Number(page)}">Str. ${Number(page)}</button>`).join("")}
          <button type="button" data-open-concept="${escapeHtml(item.id)}">Ukázat v mapě</button>
        </div>
      </div>`).join("");
    const passageHtml = items.map(item => `
      <div class="search-result" data-page="${Number(item.page || 0)}">
        <span>${escapeHtml(item.snippet || "")}</span>
        <small>${item.page ? `PDF strana ${Number(item.page)}` : "Relevantní pasáž"}</small>
      </div>`).join("");
    el.searchResults.innerHTML =
      (concepts.length ? `<div class="search-group-label">Pojmy</div>${conceptHtml}` : "") +
      (items.length ? `<div class="search-group-label">Pasáže</div>${passageHtml}` : "");
    el.searchResults.querySelectorAll("[data-page]").forEach(item => item.addEventListener("click", () => {
      const page = Number(item.dataset.page || 0);
      if (page > 0) openPageFromKnowledge(page);
    }));
    el.searchResults.querySelectorAll("[data-open-page]").forEach(button => button.addEventListener("click", event => {
      event.stopPropagation();
      openPageFromKnowledge(Number(button.dataset.openPage));
    }));
    el.searchResults.querySelectorAll("[data-open-concept]").forEach(button => button.addEventListener("click", event => {
      event.stopPropagation();
      revealConcept(button.dataset.openConcept);
    }));
  } catch (error) {
    el.searchResults.textContent = error.message;
  }
}


const PATH_SECTION_ORDER = [
  "identity", "learner_profile", "goals", "goal_modes", "route", "session_design",
  "didactics", "diagnostics", "misconceptions", "knowledge_gaps", "feedback",
  "assessment", "motivation", "wellbeing", "cognitive_load", "metacognition",
  "accessibility", "communication", "ethics_safety", "decision_rules", "completion", "teacher_notes",
];

function plainMarkdown(value) {
  return escapeHtml(value || "").replaceAll("\n", "<br>");
}

function renderBuiltinLearningPaths() {
  const templates = state.learningPathTemplates || [];
  const currentBuiltin = state.learningPath?.builtin_id || "";
  const render = container => {
    if (!container) return;
    if (!templates.length) {
      container.innerHTML = '<div class="empty-state">Integrované plány se nepodařilo načíst. Vlastní Markdown lze nadále nahrát.</div>';
      return;
    }
    container.innerHTML = templates.map(item => {
      const active = currentBuiltin === item.id;
      const facts = [
        `${Number(item.session_length_minutes || 35)} min`,
        `mastery ${Math.round(Number(item.mastery_threshold || .8) * 100)} %`,
        `max. ${Number(item.max_new_concepts || 3)} nové pojmy`,
      ];
      return `<article class="builtin-path-card ${active ? "active" : ""} ${item.recommended ? "recommended" : ""}">
        <h3>${escapeHtml(item.name || item.id)}</h3>
        <p>${escapeHtml(item.description || "Integrovaná pedagogická cesta VUT AI Tutoru.")}</p>
        <div class="path-audience">${escapeHtml(item.target_audience || "Vysokoškolské studium matematiky")}</div>
        <div class="builtin-path-facts">${facts.map(value => `<span>${escapeHtml(value)}</span>`).join("")}</div>
        <button class="${active ? "secondary-button" : "primary-button"}" data-apply-builtin-path="${escapeHtml(item.id)}" ${active ? "disabled" : ""} type="button">${active ? "Aktivní plán" : "Použít tento plán"}</button>
      </article>`;
    }).join("");
    container.querySelectorAll("[data-apply-builtin-path]").forEach(button => button.addEventListener("click", () => applyBuiltinLearningPath(button.dataset.applyBuiltinPath)));
  };
  render(el.builtinPathGridEmpty);
  render(el.builtinPathGridActive);
}

async function applyBuiltinLearningPath(templateId) {
  if (!state.activeBook || !templateId) return;
  const previous = state.learningPath;
  const replacingCustom = previous && previous.source_type === "custom";
  if (replacingCustom && !(await requestCanvasConfirmation({
    title: "Nahradit vlastní učební cestu?",
    message: "Aktivní vlastní Markdown bude nahrazen integrovaným plánem. Kniha a studijní pokrok zůstanou zachovány.",
    acceptLabel: "Nahradit plán",
    icon: "🧭",
  }))) return;
  try {
    const payload = await api("/study-tutor/api/learning-path/apply", {
      method: "POST",
      body: JSON.stringify({ template_id: templateId, book_file_id: state.activeBook.file_id }),
    });
    state.learningPath = payload.learning_path || null;
    if (state.data) state.data.learning_path = state.learningPath;
    renderLearningPath();
    renderRecommendation();
    showToast(`Učební plán „${state.learningPath?.name || templateId}“ je aktivní.`);
  } catch (error) { showToast(error.message, 6500); }
}

function renderLearningPath() {
  const path = state.learningPath;
  renderBuiltinLearningPaths();
  if (!el.pathEmpty || !el.pathContent) return;
  el.pathEmpty.hidden = Boolean(path);
  el.pathContent.hidden = !path;
  el.pathRemove.hidden = !path;
  if (!path) return;

  el.pathName.textContent = path.name || "Učební cesta";
  el.pathDescription.textContent = path.description || path.target_audience || "Pedagogická specifikace pro strukturovanou výuku nad touto knihou.";
  el.pathTags.innerHTML = (path.tags || []).map(tag => `<span>${escapeHtml(tag)}</span>`).join("");
  el.pathMetaSummary.innerHTML = [
    `Verze ${escapeHtml(path.version || "1.0")}`,
    `${Number(path.session_length_minutes || 35)} min / setkání`,
    `Mastery ${Math.round(Number(path.mastery_threshold || .8) * 100)} %`,
    `Horní limit ${Number(path.hard_stop_minutes || Math.max(60, Number(path.session_length_minutes || 35) + 20))} min`,
    path.strictness === "strict" ? "Přísná cesta" : path.strictness === "flexible" ? "Flexibilní cesta" : "Vyvážená cesta",
  ].map(item => `<span>${item}</span>`).join("");

  const goals = path.goals || [];
  el.pathGoalSelect.innerHTML = goals.map(goal => `<option value="${escapeHtml(goal.id)}">${escapeHtml(goal.name || goal.id)}</option>`).join("");
  el.pathGoalSelect.value = path.current_goal_id || path.default_goal_id || goals[0]?.id || "";
  const selectedGoal = goals.find(goal => goal.id === el.pathGoalSelect.value) || path.current_goal || goals[0];
  el.pathGoalDetail.innerHTML = plainMarkdown(selectedGoal?.description || "Tutor přizpůsobí výuku tomuto cíli.");

  const audience = path.target_audience || "Nespecifikováno";
  const source = path.source_type === "builtin" ? `Integrovaný plán VUT AI Tutor · ${path.source_name || path.builtin_id || ""}` : (path.source_name || "Vlastní Markdown šablona");
  el.pathMetadata.innerHTML = `
    <dt>Cílová skupina</dt><dd>${escapeHtml(audience)}</dd>
    <dt>Zdroj</dt><dd>${escapeHtml(source)}</dd>
    <dt>Fází</dt><dd>${Number(path.phase_count || (path.phases || []).length)}</dd>
    <dt>Režim</dt><dd>${escapeHtml(path.strictness || "balanced")}</dd>
    <dt>Nové pojmy</dt><dd>max. ${Number(path.max_new_concepts || 3)} / blok</dd>
    <dt>Check-in</dt><dd>${escapeHtml(path.check_in_frequency || "podle potřeby")}</dd>
    <dt>Pohoda</dt><dd>${escapeHtml(path.wellbeing_mode || "výchozí prevence")}</dd>
    <dt>Návraty</dt><dd>${(path.review_schedule_days || []).length ? escapeHtml((path.review_schedule_days || []).join(", ") + " dní") : "podle výkonu"}</dd>
    <dt>Volba uživatele</dt><dd>${path.allow_user_override === false ? "šablona preferuje konzistenci" : "má přednost"}</dd>`;

  const phases = path.phases || [];
  el.pathPhases.innerHTML = phases.map(phase => `
    <li class="path-phase ${phase.id === path.current_phase_id ? "active" : ""}" data-phase-id="${escapeHtml(phase.id)}">
      <div><strong>${escapeHtml(phase.name || phase.id)}</strong><p>${plainMarkdown(phase.description || "")}</p></div>
      <button type="button" data-select-phase="${escapeHtml(phase.id)}">${phase.id === path.current_phase_id ? "Aktivní" : "Nastavit"}</button>
    </li>`).join("");
  const currentPhase = phases.find(phase => phase.id === path.current_phase_id) || path.current_phase || phases[0];
  el.pathPhaseStatus.textContent = currentPhase ? `Aktuálně: ${currentPhase.name}` : "";
  el.pathPhases.querySelectorAll("[data-select-phase]").forEach(button => {
    button.disabled = button.dataset.selectPhase === path.current_phase_id;
    button.addEventListener("click", () => saveLearningPathState({ phase_id: button.dataset.selectPhase }));
  });

  const sections = path.sections || {};
  el.pathSections.innerHTML = PATH_SECTION_ORDER.filter(key => sections[key]).map(key => {
    const section = sections[key];
    const body = [section.content || ""].concat((section.subsections || []).map(sub => `### ${sub.title || ""}\n${sub.content || ""}`)).filter(Boolean).join("\n\n");
    return `<details class="path-section"><summary>${escapeHtml(section.title || key)}</summary><div class="path-section-content">${plainMarkdown(body)}</div></details>`;
  }).join("") || '<div class="empty-state">Šablona neobsahuje rozpoznané sekce.</div>';

  const warnings = path.warnings || [];
  el.pathWarnings.hidden = !warnings.length;
  el.pathWarnings.innerHTML = warnings.length
    ? `<strong>Doporučení pro úplnější šablonu</strong><br>${warnings.map(item => `• ${escapeHtml(item)}`).join("<br>")}`
    : "";
  reportHeight();
}

async function saveLearningPathState(patch) {
  try {
    const payload = await api("/study-tutor/api/learning-path/state", { method: "POST", body: JSON.stringify(patch) });
    state.learningPath = payload.learning_path || null;
    if (state.data) state.data.learning_path = state.learningPath;
    renderLearningPath();
    renderRecommendation();
    showToast("Učební cesta byla aktualizována.");
  } catch (error) { showToast(error.message, 6000); }
}

async function removeLearningPath() {
  if (!state.learningPath) return;
  if (!(await requestCanvasConfirmation({
    title: "Odpojit učební cestu?",
    message: "Pedagogická šablona bude od této knihy odpojena. Kniha a studijní pokrok zůstanou zachovány.",
    acceptLabel: "Odpojit šablonu",
    icon: "🧭",
  }))) return;
  try {
    await api("/study-tutor/api/learning-path", { method: "DELETE" });
    state.learningPath = null;
    await loadState({ reopenBook: false });
    showToast("Kniha nyní používá výchozí pedagogiku.");
  } catch (error) { showToast(error.message, 6000); }
}


function setView(view) {
  state.activeView = ["book", "map", "toc", "path"].includes(view) ? view : "book";
  el.bookView.hidden = state.activeView !== "book";
  el.mapView.hidden = state.activeView !== "map";
  el.tocView.hidden = state.activeView !== "toc";
  el.pathView.hidden = state.activeView !== "path";
  [el.viewBook, el.viewMap, el.viewToc, el.viewPath].forEach(button => {
    button.classList.toggle("active", button.dataset.view === state.activeView);
  });
  el.documentControls.hidden = !state.activeBook || state.activeView !== "book";
  if (state.activeView === "map") loadConceptMap(state.mapParent || "root").catch(error => showToast(error.message));
  if (state.activeView === "toc") loadToc().catch(error => showToast(error.message));
  if (state.activeView === "path") { renderLearningPath(); requestAnimationFrame(() => { if (el.pathScrollRegion) el.pathScrollRegion.scrollTop = Math.max(0, el.pathScrollRegion.scrollTop); }); }
  reportHeight();
}

async function openPageFromKnowledge(page) {
  if (!Number.isFinite(Number(page)) || Number(page) < 1) return;
  setView("book");
  await goToPage(Number(page));
}

function mapLevelName(parent) {
  if (!parent || parent.kind === "root") return "Velké shluky";
  if (parent.kind === "domain") return "Tematické podshluky";
  if (parent.kind === "cluster") return "Jednotlivé pojmy";
  return "Detail pojmu";
}

async function loadConceptMap(parentId = "root", selectId = "", { preserveDetail = false } = {}) {
  if (!state.activeBook) return;
  const previousSelectedId = preserveDetail ? state.mapSelected?.id : "";
  state.mapParent = parentId || "root";
  const payload = await api("/study-tutor/api/map", {}, { parent_id: state.mapParent, mode: "auto" });
  state.mapStatus = payload.analysis || {};
  state.mapMode = payload.mode || state.mapStatus.active_mode || "fast";
  updateMapStatus(payload);
  if (!payload.ready) {
    state.mapData = null;
    el.mapLayout.hidden = true;
    return;
  }
  state.mapData = payload;
  el.mapLayout.hidden = false;
  renderBreadcrumbs(payload.breadcrumbs || []);
  el.mapLevelLabel.textContent = mapLevelName(payload.parent);
  el.mapUp.disabled = (payload.parent?.kind || "root") === "root";
  el.mapDown.disabled = !(payload.nodes || []).some(node => node.kind !== "concept");
  renderConceptMap(payload);
  const requestedId = selectId || previousSelectedId;
  if (requestedId) {
    const node = (payload.nodes || []).find(item => item.id === requestedId);
    if (node) selectMapNode(node, false);
    else if (!preserveDetail) { state.mapSelected = null; renderMapDetail(payload.parent, true); }
  } else {
    state.mapSelected = null;
    renderMapDetail(payload.parent, true);
  }
  state.mapRevision = Number(payload.analysis?.graph_revision || state.mapRevision || 0);
  reportHeight();
}

function updateMapStatus(payload) {
  const analysis = payload.analysis || state.mapStatus || {};
  state.mapStatus = analysis;
  const fastReady = Boolean(payload.ready || analysis.fast_ready || analysis.ready);
  const deepStatus = analysis.deep_status || "not_requested";
  const showingDeep = (payload.mode || analysis.active_mode || state.mapMode) === "deep";
  state.mapMode = showingDeep ? "deep" : "fast";
  if (el.mapModeBadge) {
    el.mapModeBadge.textContent = showingDeep ? "Hlubší LLM mapa" : "Rychlá lokální mapa";
  }
  if (el.mapDeepAnalyze) {
    el.mapDeepAnalyze.disabled = !Boolean(analysis.complete) || deepStatus === "processing";
    if (deepStatus === "processing") {
      el.mapDeepAnalyze.textContent = `Hlubší analýza ${Math.round(Number(analysis.deep_progress || 0) * 100)} %`;
    } else if (deepStatus === "completed") {
      el.mapDeepAnalyze.textContent = "Hlubší mapa připravena";
      el.mapDeepAnalyze.title = "Kliknutím lze po potvrzení hlubší mapu přegenerovat.";
    } else {
      el.mapDeepAnalyze.textContent = "Hlubší analýza LLM";
      el.mapDeepAnalyze.title = analysis.complete
        ? "Volitelně zpřesní názvy, popisy a vztahy několika paralelními LLM dávkami."
        : "Hlubší analýzu lze spustit po dokončení rychlé mapy; částečná mapa je mezitím použitelná.";
    }
  }

  let percent = Math.round(Number(analysis.progress || 0) * 100);
  const eta = formatDuration(analysis.eta_seconds);
  const partialReady = Boolean(analysis.partial_ready || (fastReady && !analysis.complete));
  let label = analysis.error || analysis.stage || "Vytvářím rychlou lokální mapu…";
  let heading = analysis.status === "failed" ? "Rychlou mapu se nepodařilo vytvořit" : `Rychlá mapa se připravuje… ${percent} %`;
  let showStatus = !fastReady;
  if (partialReady && analysis.status !== "failed") {
    heading = `Částečná mapa je dostupná · ${percent} %`;
    const visibleCount = Number(analysis.visible_concept_count || analysis.concept_count || 0);
    label = `${analysis.stage || "Pokračuji v analýze celé knihy."} Mapa zatím není kompletní${visibleCount ? `; aktuálně je dostupných ${visibleCount} pojmů a další průběžně přibývají` : ""}.${eta ? ` Odhad zbývajícího času: ${eta}.` : ""}`;
    showStatus = true;
  } else if (!fastReady && eta) {
    label = `${label} Odhad zbývajícího času: ${eta}.`;
  }
  el.mapStatusBox.classList.remove("deep-processing");

  if (fastReady && deepStatus === "processing") {
    percent = Math.round(Number(analysis.deep_progress || 0) * 100);
    label = analysis.deep_stage || "Zpřesňuji pojmy pomocí LLM…";
    heading = `Hlubší analýza probíhá… ${percent} %`;
    showStatus = true;
    el.mapStatusBox.classList.add("deep-processing");
  } else if (fastReady && deepStatus === "failed") {
    percent = 100;
    label = analysis.deep_error || analysis.deep_stage || "Hlubší analýza selhala; rychlá mapa zůstává dostupná.";
    heading = "Hlubší analýzu se nepodařilo dokončit";
    showStatus = true;
  }
  el.mapProgressBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  el.mapStatusText.textContent = label;
  el.mapStatusBox.hidden = !showStatus;
  const strong = el.mapStatusBox.querySelector("strong");
  if (strong) strong.textContent = heading;
}


function renderBreadcrumbs(items) {
  el.mapBreadcrumbs.replaceChildren();
  items.forEach((item, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.name || "Kniha";
    button.dataset.parentId = item.id || "root";
    button.disabled = index === items.length - 1;
    button.addEventListener("click", () => loadConceptMap(button.dataset.parentId));
    el.mapBreadcrumbs.appendChild(button);
  });
}

function hashNumber(value) {
  let h = 2166136261;
  for (const ch of String(value || "")) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function mapLayout(nodes, edges) {
  const width = 1000, height = 680, cx = width / 2, cy = height / 2;
  const count = Math.max(1, nodes.length);
  const positions = new Map();
  const weightedDegree = new Map(nodes.map(node => [node.id, 0]));
  for (const edge of edges || []) {
    const similarity = Math.max(0.01, Math.min(1, Number(edge.similarity ?? 0.15)));
    weightedDegree.set(edge.source, (weightedDegree.get(edge.source) || 0) + similarity);
    weightedDegree.set(edge.target, (weightedDegree.get(edge.target) || 0) + similarity);
  }
  const ordered = [...nodes].sort((a, b) => (weightedDegree.get(b.id) || 0) - (weightedDegree.get(a.id) || 0));
  ordered.forEach((node, index) => {
    const seed = hashNumber(node.id);
    const angle = (index / count) * Math.PI * 2 + ((seed % 997) / 997) * 0.42;
    const centrality = Math.min(1, (weightedDegree.get(node.id) || 0) / 4);
    const ring = 110 + (1 - centrality) * 250 + (index % 3) * 24;
    positions.set(node.id, { x: cx + Math.cos(angle) * ring, y: cy + Math.sin(angle) * ring, vx: 0, vy: 0 });
  });
  const nodeById = new Map(nodes.map(node => [node.id, node]));
  const limitedEdges = (edges || []).slice(0, 650);
  const iterations = nodes.length > 100 ? 95 : 145;
  for (let iter = 0; iter < iterations; iter++) {
    for (let i = 0; i < nodes.length; i++) {
      const first = positions.get(nodes[i].id);
      first.vx += (cx - first.x) * 0.00065;
      first.vy += (cy - first.y) * 0.00065;
      for (let j = i + 1; j < nodes.length; j++) {
        const second = positions.get(nodes[j].id);
        let dx = first.x - second.x, dy = first.y - second.y;
        const dist2 = Math.max(160, dx * dx + dy * dy);
        const repulsion = (nodes.length > 70 ? 2900 : 3900) / dist2;
        first.vx += dx * repulsion; first.vy += dy * repulsion;
        second.vx -= dx * repulsion; second.vy -= dy * repulsion;
      }
    }
    for (const edge of limitedEdges) {
      if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) continue;
      const first = positions.get(edge.source), second = positions.get(edge.target);
      const dx = second.x - first.x, dy = second.y - first.y;
      const dist = Math.max(1, Math.hypot(dx, dy));
      const similarity = Math.max(0.01, Math.min(1, Number(edge.similarity ?? 0.15)));
      const desired = Math.max(58, Math.min(350, Number(edge.distance || (62 + (1 - similarity) * 278))));
      const strength = 0.0007 + similarity * 0.0016;
      const pull = (dist - desired) * strength;
      first.vx += dx * pull; first.vy += dy * pull;
      second.vx -= dx * pull; second.vy -= dy * pull;
    }
    for (const node of nodes) {
      const point = positions.get(node.id);
      point.vx *= 0.72; point.vy *= 0.72;
      point.x = Math.max(62, Math.min(width - 62, point.x + point.vx));
      point.y = Math.max(62, Math.min(height - 62, point.y + point.vy));
    }
  }
  return positions;
}

function nodeRadius(node) {
  if (node.kind === "domain") return Math.min(72, 34 + Math.sqrt(Number(node.concept_count || 1)) * 3.2);
  if (node.kind === "cluster") return Math.min(58, 28 + Math.sqrt(Number(node.concept_count || 1)) * 2.4);
  return 12 + Math.min(15, Number(node.importance || 0) * 15);
}

function wrapMapLabel(name, maxChars = 19, maxLines = 3) {
  const words = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return ["Pojem"];
  const lines = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= maxChars || !current) current = candidate;
    else { lines.push(current); current = word; }
    if (lines.length >= maxLines - 1) break;
  }
  if (current && lines.length < maxLines) lines.push(current);
  const consumed = lines.join(" ").length;
  if (consumed < String(name || "").trim().length && lines.length) {
    lines[lines.length - 1] = lines[lines.length - 1].replace(/[.…]*$/, "") + "…";
  }
  return lines.slice(0, maxLines);
}

function appendMapLabel(group, node, radius, ns) {
  const isConcept = node.kind === "concept";
  const lines = wrapMapLabel(node.name, isConcept ? 18 : 20, isConcept ? 2 : 3);
  const text = document.createElementNS(ns, "text");
  text.setAttribute("class", "node-label");
  const lineHeight = isConcept ? 13 : 15;
  const baseY = isConcept ? radius + 15 : -((lines.length - 1) * lineHeight) / 2;
  lines.forEach((line, index) => {
    const tspan = document.createElementNS(ns, "tspan");
    tspan.setAttribute("x", "0");
    tspan.setAttribute("y", String(baseY + index * lineHeight));
    tspan.textContent = line;
    text.appendChild(tspan);
  });
  group.appendChild(text);
  const title = document.createElementNS(ns, "title");
  title.textContent = String(node.name || "Pojem");
  group.appendChild(title);
}

function edgeComponentSummary(edge) {
  const labels = {
    cooccurrence: "společný výskyt",
    page_proximity: "blízkost v knize",
    shared_vocabulary: "sdílená terminologie",
    topic_profile: "podobnost tematického profilu",
    cross_relations: "vazby mezi pojmy",
    relation_density: "hustota vazeb",
    explicit_llm_relation: "explicitní vztah z hlubší analýzy",
  };
  return Object.entries(edge?.components || {})
    .filter(([, value]) => Number.isFinite(Number(value)))
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 4)
    .map(([key, value]) => `${labels[key] || key}: ${Math.round(Number(value) * 100)} %`)
    .join(" · ");
}

function renderConceptMap(payload) {
  const svg = el.conceptMap;
  svg.replaceChildren();
  const nodes = (payload.nodes || []).slice(0, 150);
  const previousIds = state.mapNodeIds || new Set();
  const currentIds = new Set(nodes.map(node => node.id));
  const allowed = new Set(nodes.map(n => n.id));
  const edges = (payload.edges || []).filter(e => allowed.has(e.source) && allowed.has(e.target)).slice(0, 500);
  const pos = mapLayout(nodes, edges);
  const ns = "http://www.w3.org/2000/svg";

  for (const edge of edges) {
    const a = pos.get(edge.source), b = pos.get(edge.target);
    if (!a || !b) continue;
    const line = document.createElementNS(ns, "line");
    line.setAttribute("x1", a.x); line.setAttribute("y1", a.y);
    line.setAttribute("x2", b.x); line.setAttribute("y2", b.y);
    line.setAttribute("class", "edge");
    const similarity = Math.max(0.01, Math.min(1, Number(edge.similarity ?? 0.15)));
    line.setAttribute("stroke-width", String(Math.max(1, Math.min(7, 1 + similarity * 5 + Math.log1p(Number(edge.weight || 1)) * 0.45))));
    line.setAttribute("stroke-opacity", String(0.18 + similarity * 0.68));
    const title = document.createElementNS(ns, "title");
    const componentSummary = edgeComponentSummary(edge);
    title.textContent = `${edge.type || "souvislost"} · významová příbuznost ${Math.round(similarity * 100)} % · cílová vzdálenost ${Math.round(Number(edge.distance || 0))}${componentSummary ? ` · ${componentSummary}` : ""}`;
    line.appendChild(title);
    svg.appendChild(line);
  }

  for (const node of nodes) {
    const p = pos.get(node.id);
    const group = document.createElementNS(ns, "g");
    group.setAttribute("class", `node ${node.kind || ""}${previousIds.size && !previousIds.has(node.id) ? " map-node-new" : ""}`);
    group.dataset.nodeId = node.id;
    group.setAttribute("transform", `translate(${p.x} ${p.y})`);
    group.setAttribute("role", "button");
    group.setAttribute("aria-label", node.name || "Pojem");
    const circle = document.createElementNS(ns, "circle");
    const radius = nodeRadius(node);
    circle.setAttribute("r", String(radius));
    group.appendChild(circle);
    appendMapLabel(group, node, radius, ns);
    group.addEventListener("pointerenter", () => { state.mapHovered = node; });
    group.addEventListener("pointerleave", () => { if (state.mapHovered?.id === node.id) state.mapHovered = null; });
    group.addEventListener("click", event => { event.stopPropagation(); selectMapNode(node, true); });
    group.addEventListener("dblclick", event => { event.preventDefault(); event.stopPropagation(); semanticMapZoom(1, node); });
    svg.appendChild(group);
  }
  state.mapNodeIds = currentIds;
  state.mapNodeLookup = new Map(nodes.map(node => [node.id, node]));
  state.mapHovered = null;
  if ((payload.nodes || []).length > nodes.length) {
    showToast(`Shluk obsahuje ${(payload.nodes || []).length} pojmů; mapa zobrazuje 150 nejvýznamnějších. Další najdete vyhledáváním.`);
  }
}

async function selectMapNode(node, updateSvg = true) {
  state.mapSelected = node;
  if (updateSvg) {
    el.conceptMap.querySelectorAll(".node").forEach(g => g.classList.toggle("selected", g.dataset.nodeId === node.id));
  }
  if (node.kind === "concept") {
    try {
      const detail = await api(`/study-tutor/api/concepts/${encodeURIComponent(node.id)}`);
      renderMapDetail(detail.concept, false, detail.neighbors || []);
    } catch (_) { renderMapDetail(node, false); }
  } else {
    renderMapDetail(node, false);
  }
}

function renderMapDetail(node, isParent = false, neighbors = []) {
  if (!node) {
    el.mapDetail.innerHTML = '<div class="empty-state">Vyberte shluk nebo pojem.</div>';
    return;
  }
  const isConcept = node.kind === "concept";
  const pages = (node.pages || []).slice(0, 18);
  el.mapDetail.innerHTML = `
    <h3>${escapeHtml(node.name || "Kniha")}</h3>
    <span class="analysis-chip">${isConcept ? "Pojem" : node.kind === "domain" ? "Velký shluk" : node.kind === "cluster" ? "Tematický shluk" : "Mapa knihy"}${node.concept_count ? ` · ${Number(node.concept_count)} pojmů` : ""}</span>
    <p>${escapeHtml(node.description || (isConcept ? "Pojem identifikovaný v učebnici." : "Kliknutím nebo přiblížením zobrazíte detailnější úroveň."))}</p>
    ${(node.keywords || []).length ? `<strong>Klíčové pojmy vymezující téma</strong><div class="map-keywords">${(node.keywords || []).slice(0, 10).map(value => `<span>${escapeHtml(value)}</span>`).join("")}</div>` : ""}
    ${(node.related_topics || []).length ? `<strong>Významově nejbližší témata</strong><div class="related-topic-list">${(node.related_topics || []).slice(0, 6).map(value => `<button type="button" data-related-topic="${escapeHtml(value.id)}">${escapeHtml(value.name)} · ${Math.round(Number(value.similarity || 0) * 100)} %</button>`).join("")}</div>` : ""}
    ${pages.length ? `<strong>Odkazy do knihy</strong><div class="page-links">${pages.map(page => `<button type="button" class="page-link" data-map-page="${Number(page)}">PDF str. ${Number(page)}</button>`).join("")}</div>` : ""}
    ${!isConcept && node.kind !== "root" ? '<button id="map-detail-drill" class="primary-button" type="button">Přiblížit a rozbalit</button>' : ""}
    ${neighbors.length ? `<div class="neighbor-list"><strong>Související pojmy</strong>${neighbors.slice(0, 12).map(n => `<button type="button" data-neighbor="${escapeHtml(n.id)}">${escapeHtml(n.name)} <small>— ${escapeHtml(n.relation || "souvisí s")}</small></button>`).join("")}</div>` : ""}
  `;
  el.mapDetail.querySelectorAll("[data-map-page]").forEach(button => button.addEventListener("click", () => openPageFromKnowledge(Number(button.dataset.mapPage))));
  const drill = $("#map-detail-drill");
  if (drill) drill.addEventListener("click", () => drillMapNode(node));
  el.mapDetail.querySelectorAll("[data-neighbor]").forEach(button => button.addEventListener("click", () => revealConcept(button.dataset.neighbor)));
  el.mapDetail.querySelectorAll("[data-related-topic]").forEach(button => button.addEventListener("click", () => loadConceptMap(button.dataset.relatedTopic).catch(error => showToast(error.message))));
}

function mapNodeFromEventTarget(target) {
  const group = target?.closest?.(".node");
  return group ? state.mapNodeLookup.get(group.dataset.nodeId) || null : null;
}

function defaultZoomTarget() {
  if (state.mapHovered && state.mapHovered.kind !== "concept") return state.mapHovered;
  if (state.mapSelected && state.mapSelected.kind !== "concept") return state.mapSelected;
  return [...(state.mapData?.nodes || [])]
    .filter(node => node.kind !== "concept")
    .sort((a, b) => Number(b.concept_count || 0) - Number(a.concept_count || 0))[0] || null;
}

async function semanticMapZoom(direction, explicitNode = null) {
  if (state.mapWheelBusy) return;
  state.mapWheelBusy = true;
  try {
    if (direction > 0) {
      const target = explicitNode || defaultZoomTarget();
      if (!target || target.kind === "concept") {
        showToast("Na této úrovni jsou už jednotlivé pojmy. Kolečkem dolů se vrátíte výš.", 2600);
        return;
      }
      selectMapNode(target, true);
      el.conceptMap.classList.remove("semantic-zoom-out");
      el.conceptMap.classList.add("semantic-zoom-in");
      await loadConceptMap(target.id);
    } else {
      if ((state.mapData?.parent?.kind || "root") === "root") {
        showToast("Jste na nejvyšší úrovni mapy.", 1800);
        return;
      }
      el.conceptMap.classList.remove("semantic-zoom-in");
      el.conceptMap.classList.add("semantic-zoom-out");
      await mapUpOneLevel();
    }
  } finally {
    setTimeout(() => {
      state.mapWheelBusy = false;
      el.conceptMap.classList.remove("semantic-zoom-in", "semantic-zoom-out");
    }, 170);
  }
}

function handleMapWheel(event) {
  if (state.activeView !== "map" || !state.mapData) return;
  event.preventDefault();
  event.stopPropagation();
  const delta = Number(event.deltaY || 0);
  if (!delta) return;
  const direction = delta < 0 ? 1 : -1;
  if (state.mapWheelDirection && state.mapWheelDirection !== direction) state.mapWheelDelta = 0;
  state.mapWheelDirection = direction;
  state.mapWheelDelta += Math.min(120, Math.abs(delta));
  clearTimeout(state.mapWheelTimer);
  state.mapWheelTimer = setTimeout(() => { state.mapWheelDelta = 0; state.mapWheelDirection = 0; }, 420);
  if (state.mapWheelDelta < 58 || state.mapWheelBusy) return;
  state.mapWheelDelta = 0;
  const target = direction > 0 ? (mapNodeFromEventTarget(event.target) || state.mapHovered || state.mapSelected) : null;
  semanticMapZoom(direction, target).catch(error => showToast(error.message));
}

function drillMapNode(node) {
  if (!node || node.kind === "concept") return;
  loadConceptMap(node.id).catch(error => showToast(error.message));
}

async function mapUpOneLevel() {
  const crumbs = state.mapData?.breadcrumbs || [];
  if (crumbs.length <= 1) return;
  const parent = crumbs[Math.max(0, crumbs.length - 2)];
  await loadConceptMap(parent?.id || "root");
}

async function revealConcept(conceptId) {
  const detail = await api(`/study-tutor/api/concepts/${encodeURIComponent(conceptId)}`);
  const concept = detail.concept;
  setView("map");
  await loadConceptMap(concept.parent_id || "root", concept.id);
}

async function rebuildMap() {
  const accepted = await requestCanvasConfirmation({
    title: "Znovu vytvořit rychlou mapu?",
    message: "Rychlá lokální mapa a obsah se přepočítají bez volání LLM. Studijní pokrok i uložená hlubší mapa zůstanou zachovány.",
    acceptLabel: "Spustit přepočet",
    icon: "🗺",
  });
  if (!accepted) return;
  await api("/study-tutor/api/analysis/rebuild", { method: "POST" });
  state.mapParent = "root";
  el.mapStatusBox.hidden = false;
  showToast("Rychlá lokální analýza byla spuštěna znovu.");
  await refreshAnalysis();
}

async function startDeepAnalysis() {
  if (!state.activeBook) return;
  const alreadyReady = state.mapStatus?.deep_status === "completed";
  if (alreadyReady && !(await requestCanvasConfirmation({
    title: "Přegenerovat hlubší mapu?",
    message: "Hlubší LLM mapa už je uložená. Nová analýza nahradí její současnou verzi; rychlá lokální mapa zůstane dostupná.",
    acceptLabel: "Spustit hlubší analýzu",
    icon: "🧠",
  }))) return;
  const query = alreadyReady ? "?force=true" : "";
  await api(`/study-tutor/api/analysis/deep${query}`, { method: "POST" });
  showToast("Hlubší analýza běží na omezené sadě pojmů. Rychlou mapu můžete dál používat.", 6000);
  await refreshAnalysis();
}


async function refreshAnalysis() {
  if (!state.activeBook) return;
  try {
    const status = await api("/study-tutor/api/analysis/status");
    state.mapStatus = status;
    state.activeBook.analysis = status;
    updateAnalysisBadge();
    updateBookStatus();
    if (state.activeView === "map") {
      if (status.ready) {
        const revision = Number(status.graph_revision || 0);
        if (!state.mapData || revision !== Number(state.mapRevision || 0)) {
          await loadConceptMap(state.mapParent || "root", "", { preserveDetail: true });
          if (status.partial_ready) showToast(`Průběžná mapa se rozšířila na ${Number(status.visible_concept_count || status.concept_count || 0)} pojmů.`, 2600);
        } else {
          updateMapStatus({ ready: true, analysis: status, mode: state.mapMode });
        }
      } else updateMapStatus({ ready: false, analysis: status });
    }
    if (state.activeView === "toc" && status.ready && !state.tocData.length) await loadToc();
  } catch (_) { /* transient */ }
}

async function loadToc() {
  if (!state.activeBook) return;
  const payload = await api("/study-tutor/api/toc");
  const serverItems = payload.items || [];
  if (serverItems.length) state.tocData = serverItems;
  else if (!state.tocData.length && state.browserToc.length) state.tocData = state.browserToc;
  if (!payload.ready && !state.tocData.length) {
    el.tocStatus.hidden = false;
    el.tocStatus.textContent = payload.analysis?.stage || "Obsah se připravuje…";
    el.tocList.replaceChildren();
    return;
  }
  el.tocStatus.hidden = true;
  renderToc();
}

function renderToc() {
  const query = foldText((el.tocFilter.value || "").trim());
  const items = (state.tocData || []).filter(item => !query || foldText(item.title || "").includes(query));
  if (!items.length) {
    el.tocList.innerHTML = '<div class="empty-state">Obsah neobsahuje odpovídající položku.</div>';
    return;
  }
  el.tocList.innerHTML = items.slice(0, 2500).map(item => {
    const level = Math.max(0, Math.min(8, Number(item.level || 0)));
    return `<div class="toc-item" style="padding-left:${8 + level * 18}px">
      <button type="button" data-toc-page="${Number(item.page || 0)}">${escapeHtml(item.title)}</button>
      <button type="button" class="toc-page" data-toc-page="${Number(item.page || 0)}">${item.page ? `PDF ${Number(item.page)}${item.page_label && String(item.page_label) !== String(item.page) ? ` · ${escapeHtml(item.page_label)}` : ""}` : "—"}</button>
    </div>`;
  }).join("");
  el.tocList.querySelectorAll("[data-toc-page]").forEach(button => button.addEventListener("click", () => {
    const page = Number(button.dataset.tocPage || 0);
    if (page > 0) openPageFromKnowledge(page);
  }));
  reportHeight();
}

async function refreshActivities(announce = true) {
  if (!state.token) return;
  try {
    const payload = await api("/study-tutor/api/activities");
    const activities = payload.activities || [];
    const newItems = activities.filter(item => !state.lastActivityIds.has(item.id));
    state.lastActivityIds = new Set(activities.map(item => item.id));
    renderActivities(activities);
    if (announce && newItems.length) showToast(`Nová aktivita „${newItems[0].title}“ je připravena.`);
  } catch (error) {
    if (announce) showToast(error.message);
  }
}

function renderActivities(activities) {
  if (!activities.length) {
    el.activityList.className = "activity-list empty-state";
    el.activityList.textContent = "Zatím nebyla vytvořena žádná aktivita.";
    return;
  }
  el.activityList.className = "activity-list";
  el.activityList.innerHTML = activities.map(activity => `
    <div class="activity-item"><div><strong>${escapeHtml(activity.title)}</strong><small>${escapeHtml(activity.type_label || activity.activity_type)} · ${activity.item_count} položek</small></div>
      <button type="button" data-activity-id="${escapeHtml(activity.id)}">Otevřít</button></div>`).join("");
  el.activityList.querySelectorAll("[data-activity-id]").forEach(button => button.addEventListener("click", () => openActivity(button.dataset.activityId)));
}

async function openActivity(id) {
  const activity = await api(`/study-tutor/api/activities/${encodeURIComponent(id)}`);
  renderActivity(activity);
  if (!el.activityDialog.open) el.activityDialog.showModal();
}

function renderActivity(activity) {
  const isCards = activity.activity_type === "flashcards";
  el.activityContent.innerHTML = `
    <header class="activity-header"><h2>${escapeHtml(activity.title)}</h2><p>${escapeHtml(activity.instructions || "")}</p></header>
    <form id="activity-form" data-activity-id="${escapeHtml(activity.id)}">
      <div>${activity.items.map((item, index) => isCards ? renderFlashcard(item, index) : renderQuestion(item, index)).join("")}</div>
      <div class="activity-footer"><span id="activity-score"></span><button class="primary-button" type="submit">${isCards ? "Uložit sebehodnocení" : "Vyhodnotit"}</button></div>
    </form>`;
  const form = $("#activity-form");
  form.addEventListener("submit", submitActivity);
  el.activityContent.querySelectorAll(".flashcard").forEach(card => card.addEventListener("click", () => {
    const back = card.querySelector(".flashcard-back");
    back.hidden = !back.hidden;
  }));
}

function renderQuestion(item, index) {
  const name = `q_${item.id}`;
  let control = "";
  if (item.kind === "single_choice" || item.kind === "true_false") {
    const choices = item.kind === "true_false" ? [{ id: "true", text: "Pravda" }, { id: "false", text: "Nepravda" }] : item.choices || [];
    control = `<div class="choice-list">${choices.map(choice => `<label><input type="radio" name="${escapeHtml(name)}" value="${escapeHtml(choice.id)}"><span>${escapeHtml(choice.text)}</span></label>`).join("")}</div>`;
  } else if (item.kind === "multiple_choice") {
    control = `<div class="choice-list">${(item.choices || []).map(choice => `<label><input type="checkbox" name="${escapeHtml(name)}" value="${escapeHtml(choice.id)}"><span>${escapeHtml(choice.text)}</span></label>`).join("")}</div>`;
  } else if (item.kind === "numeric") {
    control = `<input type="number" step="any" name="${escapeHtml(name)}" placeholder="Číselná odpověď">`;
  } else if (item.kind === "free_response") {
    control = `<textarea name="${escapeHtml(name)}" placeholder="Napište postup nebo důkaz…"></textarea>`;
  } else {
    control = `<input type="text" name="${escapeHtml(name)}" placeholder="Vaše odpověď">`;
  }
  return `<section class="activity-question" data-item-id="${escapeHtml(item.id)}"><h3>${index + 1}. ${escapeHtml(item.prompt)}</h3>${control}<div class="item-feedback" hidden></div></section>`;
}

function renderFlashcard(item, index) {
  return `<section class="activity-question" data-item-id="${escapeHtml(item.id)}">
    <div class="flashcard"><div><small>Kartička ${index + 1}</small><h3>${escapeHtml(item.prompt)}</h3><p>Kliknutím zobrazíte odpověď.</p></div><div class="flashcard-back" hidden>${escapeHtml(item.back || "")}</div></div>
    <div class="choice-list"><label><input type="radio" name="q_${escapeHtml(item.id)}" value="known">Znám</label><label><input type="radio" name="q_${escapeHtml(item.id)}" value="unknown">Potřebuji zopakovat</label></div>
  </section>`;
}

async function submitActivity(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const answers = {};
  form.querySelectorAll(".activity-question").forEach(section => {
    const id = section.dataset.itemId;
    const checked = Array.from(section.querySelectorAll("input:checked")).map(input => input.value);
    const field = section.querySelector("textarea, input[type=text], input[type=number]");
    answers[id] = checked.length > 1 ? checked : checked.length === 1 ? checked[0] : field ? field.value : null;
  });
  try {
    const payload = await api(`/study-tutor/api/activities/${encodeURIComponent(form.dataset.activityId)}/submit`, {
      method: "POST", body: JSON.stringify({ answers }),
    });
    $("#activity-score").textContent = `Výsledek: ${Math.round(payload.percentage)} %`;
    for (const result of payload.items || []) {
      const section = form.querySelector(`[data-item-id="${CSS.escape(result.id)}"]`);
      if (!section) continue;
      const feedback = section.querySelector(".item-feedback");
      if (!feedback) continue;
      feedback.hidden = false;
      feedback.className = `item-feedback ${result.correct === true ? "correct" : result.correct === false ? "incorrect" : ""}`;
      feedback.textContent = result.feedback || (result.correct ? "Správně." : "Zkontrolujte řešení.");
    }
    if (!form.querySelector("[data-review-result]")) {
      const review = document.createElement("button");
      review.type = "button";
      review.dataset.reviewResult = "true";
      review.textContent = "Rozebrat výsledek s tutorem";
      review.addEventListener("click", () => sendPrompt(`Rozebereš můj výsledek aktivity a navrhneš jeden další krok?\n\n[[STUDY_RESULT activity_id=${form.dataset.activityId} file_id=${state.activeBook?.file_id || ""} session_id=${state.sessionId || ""}]]`));
      form.querySelector(".activity-footer").prepend(review);
    }
    await loadState();
  } catch (error) { showToast(error.message); }
}

function bindDropZone(zone, input) {
  ["dragenter", "dragover"].forEach(name => zone.addEventListener(name, event => { event.preventDefault(); zone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach(name => zone.addEventListener(name, event => { event.preventDefault(); zone.classList.remove("dragover"); }));
  zone.addEventListener("drop", event => uploadFiles(event.dataTransfer?.files));
  input.addEventListener("change", () => uploadFiles(input.files));
}

function bindEvents() {
  bindOutsideDynamicDismissal();
  bindWorkspaceLayout();
  bindDropZone(el.dropZone, el.fileInput);
  const dialogZone = el.uploadDialog.querySelector(".drop-zone");
  bindDropZone(dialogZone, el.dialogFileInput);
  el.addBook.addEventListener("click", () => el.uploadDialog.showModal());
  el.activityDialogClose?.addEventListener("click", () => closeCanvasDialog(el.activityDialog, "close-button"));
  el.uploadDialogClose?.addEventListener("click", () => closeCanvasDialog(el.uploadDialog, "close-button"));
  el.activityDialog?.addEventListener("cancel", event => { event.preventDefault(); closeCanvasDialog(el.activityDialog, "escape"); });
  el.uploadDialog?.addEventListener("cancel", event => { event.preventDefault(); closeCanvasDialog(el.uploadDialog, "escape"); });
  el.confirmDialogCancel?.addEventListener("click", () => settleCanvasConfirmation(false));
  el.confirmDialogClose?.addEventListener("click", () => settleCanvasConfirmation(false));
  el.confirmDialogAccept?.addEventListener("click", () => settleCanvasConfirmation(true));
  el.confirmDialog?.addEventListener("cancel", event => { event.preventDefault(); settleCanvasConfirmation(false); });
  el.confirmDialog?.addEventListener("close", () => { if (state.confirmResolver) settleCanvasConfirmation(false); });
  if (el.installDemo) el.installDemo.addEventListener("click", installDemoBook);
  el.refreshState.addEventListener("click", () => loadState({ reopenBook: false }).catch(error => showToast(error.message)));
  if (el.refreshToolCatalog) el.refreshToolCatalog.addEventListener("click", () => refreshToolCatalog(true));
  if (el.toolInventoryFilter) el.toolInventoryFilter.addEventListener("input", () => {
    state.toolCatalogFilter = el.toolInventoryFilter.value || "";
    state.toolInventoryLimit = 180;
    renderToolInventory(state.toolInventory);
  });
  if (el.toolInventoryMore) el.toolInventoryMore.addEventListener("click", () => {
    state.toolInventoryLimit += 180;
    renderToolInventory(state.toolInventory);
  });
  el.modelSelect.addEventListener("change", saveModel);
  el.prevPage.addEventListener("click", () => goToPage(state.page - 1));
  el.nextPage.addEventListener("click", () => goToPage(state.page + 1));
  el.pageInput.addEventListener("change", () => goToPage(el.pageInput.value));
  el.zoomOut.addEventListener("click", () => changeZoom(1 / 1.15).catch(error => showRendererError(error)));
  el.zoomIn.addEventListener("click", () => changeZoom(1.15).catch(error => showRendererError(error)));
  el.fitWidth.addEventListener("click", fitWidth);
  el.rendererRetry?.addEventListener("click", () => openActiveBook().catch(error => showRendererError(error)));
  el.rendererUseText?.addEventListener("click", () => openTextFallback(state.lastRendererError));
  el.viewerContainer.addEventListener("mouseup", captureSelection);
  el.viewerContainer.addEventListener("wheel", handleReaderWheel, { passive: false });
  el.fallbackContent.addEventListener("mouseup", captureSelection);
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    if (!state.pdf || !state.fitWidthMode || state.activeView !== "book") return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => renderCurrentPage().catch(error => showRendererError(error)), 180);
  });
  el.searchForm.addEventListener("submit", searchBook);
  [el.viewBook, el.viewMap, el.viewToc, el.viewPath].forEach(button => button.addEventListener("click", () => setView(button.dataset.view)));
  [el.pathFileInput, el.pathEmptyFileInput, el.pathSwitchFileInput].forEach(input => input?.addEventListener("change", () => uploadFiles(input.files)));
  el.pathGoalSelect.addEventListener("change", () => saveLearningPathState({ goal_id: el.pathGoalSelect.value }));
  el.pathRemove.addEventListener("click", removeLearningPath);
  el.mapUp.addEventListener("click", () => semanticMapZoom(-1).catch(error => showToast(error.message)));
  el.mapDown.addEventListener("click", () => semanticMapZoom(1).catch(error => showToast(error.message)));
  el.mapDeepAnalyze?.addEventListener("click", () => startDeepAnalysis().catch(error => showToast(error.message, 7000)));
  el.mapRebuild.addEventListener("click", () => rebuildMap().catch(error => showToast(error.message)));
  (el.mapCanvasWrap || el.conceptMap).addEventListener("wheel", handleMapWheel, { passive: false, capture: true });
  el.conceptMap.addEventListener("click", () => {
    state.mapSelected = null;
    el.conceptMap.querySelectorAll(".node").forEach(g => g.classList.remove("selected"));
    renderMapDetail(state.mapData?.parent, true);
  });
  el.tocFilter.addEventListener("input", renderToc);
  if (el.pathScrollRegion) {
    el.pathScrollRegion.addEventListener("wheel", event => {
      if (el.pathView.hidden) return;
      const maximum = Math.max(0, el.pathScrollRegion.scrollHeight - el.pathScrollRegion.clientHeight);
      if (maximum <= 0) return;
      event.preventDefault();
      event.stopPropagation();
      el.pathScrollRegion.scrollTop = Math.max(0, Math.min(maximum, el.pathScrollRegion.scrollTop + event.deltaY));
    }, { passive: false });
    el.pathScrollRegion.addEventListener("keydown", event => {
      if (el.pathView.hidden) return;
      const maximum = Math.max(0, el.pathScrollRegion.scrollHeight - el.pathScrollRegion.clientHeight);
      const step = Math.max(120, Math.round(el.pathScrollRegion.clientHeight * 0.82));
      let target = null;
      if (event.key === "PageDown" || event.key === " ") target = el.pathScrollRegion.scrollTop + step;
      if (event.key === "PageUp" || (event.key === " " && event.shiftKey)) target = el.pathScrollRegion.scrollTop - step;
      if (event.key === "Home") target = 0;
      if (event.key === "End") target = maximum;
      if (target !== null) { event.preventDefault(); event.stopPropagation(); el.pathScrollRegion.scrollTop = Math.max(0, Math.min(maximum, target)); }
    });
  }
  el.refreshActivities.addEventListener("click", () => refreshActivities(true));

  $$('[data-selection-action]').forEach(button => button.addEventListener("click", async () => {
    const type = button.dataset.selectionAction;
    const selection = state.currentSelection;
    if (!selection) return showToast("Nejprve označte pasáž v knize.");
    if (state.actionPending) return showToast("Předchozí požadavek už se předává tutorovi.");
    const expectedFileId = selection.file_id || state.activeBook?.file_id || "";
    const expectedSessionId = selection.session_id || state.sessionId || "";
    if (!expectedFileId || !expectedSessionId) return showToast("Výběr není bezpečně svázán s knihou. Obnovte Canvas a označte pasáž znovu.", 7000);
    const scope = {
      scope: "selection",
      selection_id: selection.id,
      file_id: expectedFileId,
      session_id: expectedSessionId,
      page: Number(selection.page_index || 0) + 1,
    };
    const prompt = type === "quiz" || type === "flashcards"
      ? `${actionPrompt(type === "quiz" ? "explain" : "simplify", selection)}\n\n${activityPrompt(type, scope)}`
      : actionPrompt(type, selection);
    setSelectionActionPending(true, `PDF strana ${Number(selection.page_index || 0) + 1} · předávám přesný výběr tutorovi…`);
    try {
      if (type !== "quiz" && type !== "flashcards") await queueSelectionAction(prompt, type, selection);
      await sendPrompt(prompt);
      el.selectionPopover.hidden = true;
      setSelectionActionPending(false, `PDF strana ${Number(selection.page_index || 0) + 1} · výběr byl předán a zůstává uložený`);
    } catch (error) {
      setSelectionActionPending(false, `PDF strana ${Number(selection.page_index || 0) + 1} · výběr je stále uložený`);
      showToast(`Požadavek se nepodařilo předat: ${error.message}`, 7000);
    }
  }));

  el.teachPage.addEventListener("click", () => sendPrompt(`Veď mě aktivní výukou nad aktuální stranou. Začni orientací a jednou diagnostickou otázkou.\n\n[[STUDY_TEACH page=${state.page} file_id=${state.activeBook?.file_id || ""} session_id=${state.sessionId || ""}]]`));
  el.quizPage.addEventListener("click", () => sendPrompt(activityPrompt("quiz", currentScope())));
  el.testPage.addEventListener("click", () => sendPrompt(activityPrompt("test", currentScope())));
  el.cardsPage.addEventListener("click", () => sendPrompt(activityPrompt("flashcards", currentScope())));
  el.recommendedAction.addEventListener("click", () => {
    if (el.recommendedAction.dataset.kind === "weak-topic") {
      sendPrompt(activityPrompt("quiz", { scope: "topic", topic: el.recommendedAction.dataset.topic, file_id: state.activeBook?.file_id || "", session_id: state.sessionId || "" }));
    } else {
      el.teachPage.click();
    }
  });

  window.addEventListener("message", event => {
    if (event.source !== parent) return;
    if (event.data?.type === "study:navigate" && Number(event.data.page) > 0) goToPage(Number(event.data.page));
    if (event.data?.type === "study:refresh") loadState().catch(() => {});
    if (event.data?.type === "study:outside-click") { dismissDynamicWindows({ reason: "parent-outside" }); return; }
    if (event.data?.type === "study:tutor-action:ack") {
      const requestId = String(event.data.requestId || "");
      const resolver = state.actionRequests.get(requestId);
      if (resolver) resolver(Boolean(event.data.ok));
      return;
    }
    if (event.data?.type === "study:prompt-status") {
      if (event.data.ok) {
        showToast("Výběr byl odeslán do chatu; Canvas zůstává na stejné knize.", 4500);
      } else {
        setSelectionActionPending(false, `PDF strana ${Number(state.currentSelection?.page_index || 0) + 1} · výběr je stále uložený`);
        showToast("Chat zatím nemohl požadavek odeslat. Výběr zůstal uložený; zkuste akci znovu.", 7000);
      }
    }
  });
  window.addEventListener("resize", reportHeight);
  if (typeof ResizeObserver === "function") new ResizeObserver(reportHeight).observe(document.body);
}

async function start() {
  await verifyRuntimeRoute();
  bindEvents();
  await initializeToken();
  if (!state.token) {
    throw new Error("Canvas neobdržel bezpečný token relace. Zavřete pravý panel a znovu otevřete zdroj VUT AI Tutor Canvas.");
  }
  await loadState({ reopenBook: true });
  window.__STUDY_CANVAS_READY__ = true;
  boot.step(100, "VUT AI Tutor Canvas je připraven", "");
  boot.finish();
  state.pollTimer = setInterval(async () => {
    try {
      await refreshActivities(true);
      if (Date.now() - state.toolLastPollAt >= 2800) await refreshToolCatalog(false);
      if (
        state.activeBook?.status !== "completed" ||
        state.activeBook?.text_status === "processing" ||
        state.activeBook?.semantic_index_status === "processing"
      ) await loadState();
      else if (
        state.activeBook?.analysis?.status !== "completed" ||
        state.activeBook?.analysis?.deep_status === "processing"
      ) await refreshAnalysis();
    } catch (_) { /* transient */ }
  }, 1800);
}

start().catch(error => {
  window.__STUDY_CANVAS_READY__ = false;
  el.app.setAttribute("aria-busy", "false");
  console.error(error);
  boot.fail(error, "Po aktualizaci Function ji vypněte/zapněte a obnovte celé okno Open WebUI Desktop.");
  reportHeight();
});


;(() => {
  "use strict";
  if (window.__VUT_MODEL_TOP_1241__) return;
  window.__VUT_MODEL_TOP_1241__ = true;

  function mountModelPicker() {
    const select = document.getElementById("model-select");
    if (!select || document.getElementById("vut-model-picker-top")) return;
    const host = document.createElement("label");
    host.id = "vut-model-picker-top";
    host.setAttribute("aria-label", "Základní jazykový model VUT AI Tutoru");
    const caption = document.createElement("span");
    caption.textContent = "LLM";
    host.append(caption, select);
    document.body.appendChild(host);
  }

  const start = () => {
    mountModelPicker();
    const observer = new MutationObserver(mountModelPicker);
    observer.observe(document.documentElement, { childList: true, subtree: true });
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();
