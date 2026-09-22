return (() => {
  const cfg = __CONFIG__;
  const GLOBAL_KEY = '__VUT_AI_TUTOR_RIGHT_DOCK_V1220__';
  const HOST_ID = 'study-tutor-right-panel';
  const UI_KEY = '__VUT_AI_TUTOR_UI_COORDINATOR_V1220__';
  const OPEN_KEY = '__VUT_AI_TUTOR_PANEL_OPEN_V1265__';
  const LAYOUT_REVISION = 'canvas-layout-r1';
  // One owner for each opening attempt and fallback dock. A stale timeout must
  // never resurrect a dock after a newer request, close, or page teardown.
  try { window[OPEN_KEY]?.dispose?.(); } catch (_) {}
  try { window[UI_KEY]?.dispose?.(); } catch (_) {}
  try { window[GLOBAL_KEY]?.close?.(); } catch (_) {}
  let disposed = false;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const isVisible = (el) => Boolean(el?.isConnected && !el.hidden && el.getClientRects().length &&
    el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0 &&
    getComputedStyle(el).visibility !== 'hidden');
  const canvasUrl = (frame) => {
    try {
      const url = new URL(frame.getAttribute('src') || frame.src, window.location.href);
      const expected = new URL(cfg.embedUrl, window.location.href);
      return url.origin === expected.origin && url.pathname === expected.pathname ? url : null;
    } catch (_) { return null; }
  };
  const matchesCanvas = (frame) => {
    const url = canvasUrl(frame);
    if (!url) return false;
    const sid = new URLSearchParams(url.hash.slice(1)).get('session_id');
    if (sid && cfg.sessionId) return sid === cfg.sessionId;
    if (cfg.messageId && url.searchParams.has('message_id')) return url.searchParams.get('message_id') === cfg.messageId;
    if (cfg.sourceId && url.searchParams.has('source_id')) return url.searchParams.get('source_id') === cfg.sourceId;
    return false;
  };
  const messageRoot = () => cfg.messageId ? document.getElementById(`message-${cfg.messageId}`) : null;

  const nativePanelOpen = () => {
    // Test the specific request, not any old Tutor iframe still mounted in chat.
    for (const frame of document.querySelectorAll('iframe')) {
      if (matchesCanvas(frame) && isVisible(frame)) return true;
    }
    // A title can be present before the native iframe mounts (lazy rendering).
    for (const close of document.querySelectorAll('button[aria-label="Close embed"]')) {
      if (!isVisible(close)) continue;
      const container = close.closest('#controls-container') || close.parentElement?.parentElement?.parentElement;
      if (cfg.title && String(container?.textContent || '').includes(cfg.title)) return true;
    }
    return false;
  };

  const findInlineCitation = () => {
    const roots = [messageRoot(), document].filter(Boolean);
    for (const root of roots) {
      const buttons = Array.from(root.querySelectorAll('button[aria-label]'));
      const exact = buttons.find((button) => {
        if (button.classList.contains('no-toggle')) return false;
        if (!isVisible(button)) return false;
        const label = String(button.getAttribute('aria-label') || '');
        return label.includes(cfg.title);
      });
      if (exact) return exact;
    }
    return null;
  };

  const setChatPrompt = async (text, submit) => {
    const value = typeof text === 'string' ? text : '';
    if (!value.trim()) return false;

    // Do not manipulate the contenteditable composer and never search for a generic
    // submit button. Older Desktop builds may render prompt-suggestion cards as
    // submit buttons; clicking the first global match can replace the intended study
    // prompt with an unrelated Open WebUI example. Forward the request to the native
    // same-origin Chat.svelte message handler instead. It owns MessageInput.setText()
    // and submitPrompt(), so Svelte state and the visible composer remain consistent.
    const eventType = submit ? 'input:prompt:submit' : 'input:prompt';
    const targetOrigin = window.location.origin && window.location.origin !== 'null'
      ? window.location.origin
      : '*';
    window.postMessage({
      type: eventType,
      text: value,
      source: 'vut-ai-tutor',
      requestId: `vut-native-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    }, targetOrigin);
    await sleep(0);
    return true;
  };

  // Stable bridge for actions emitted by both the native Embeds iframe and the
  // compatibility right dock. The request id prevents duplicate submission if a delayed
  // generic Open WebUI postMessage handler also wakes up.
  const ACTION_KEY = '__VUT_AI_TUTOR_ACTION_BRIDGE_V1220__';
  try { window[ACTION_KEY]?.dispose?.(); } catch (_) {}
  const handledActions = new Set();
  const isKnownCanvasWindow = (sourceWindow) => {
    if (!sourceWindow) return false;
    if (window[GLOBAL_KEY]?.frame?.contentWindow === sourceWindow) return true;
    return Array.from(document.querySelectorAll('iframe')).some((frame) => {
      if (frame.contentWindow !== sourceWindow) return false;
      return Boolean(canvasUrl(frame));
    });
  };
  const actionListener = async (event) => {
    const data = event.data || {};
    if (disposed || data.type !== 'study:tutor-action' || data.source !== 'vut-ai-tutor-canvas' || !cfg.actionBridge || data.bridge !== cfg.actionBridge) return;
    if (!isKnownCanvasWindow(event.source)) return;
    const requestId = String(data.requestId || '');
    if (!requestId || handledActions.has(requestId)) return;
    handledActions.add(requestId);
    if (handledActions.size > 200) handledActions.delete(handledActions.values().next().value);
    const ok = await setChatPrompt(String(data.text || ''), data.submit !== false);
    try {
      event.source?.postMessage({ type: 'study:tutor-action:ack', requestId, ok }, '*');
    } catch (_) {}
  };
  window.addEventListener('message', actionListener);
  const actionController = window[ACTION_KEY] = {
    bridge: cfg.actionBridge,
    dispose: () => window.removeEventListener('message', actionListener),
  };

  // Native Embeds owns its layout. Never derive a parent width from a child
  // iframe and then resize that parent: this is a closed feedback loop, including
  // while the panel is being mounted/unmounted by Open WebUI.
  // Only the fixed fallback dock reserves space, once at the outer chat root.
  // Its width is an explicit, viewport-clamped input, not a measured child output.
  const rememberedStyles = new Map();
  const observedResizeTargets = new Set();
  const diagnostics = { revision: LAYOUT_REVISION, mode: 'idle', syncs: 0, styleWrites: 0 };
  let resizeObserver = null;
  let layoutFrame = null;
  let reservedChat = null;
  let originalPaddingRight = 0;
  const rememberStyle = (element, property) => {
    let properties = rememberedStyles.get(element);
    if (!properties) { properties = new Map(); rememberedStyles.set(element, properties); }
    if (!properties.has(property)) properties.set(property, {
      value: element.style.getPropertyValue(property),
      priority: element.style.getPropertyPriority(property), applied: null,
    });
    return properties.get(property);
  };
  const restoreLayouts = () => {
    for (const [element, properties] of rememberedStyles) {
      // Restore only our properties, and only while we still own their values.
      // Never replay a snapshot of the whole style attribute over framework edits.
      for (const [property, prior] of properties) {
        if (element.style.getPropertyValue(property) !== prior.applied ||
            element.style.getPropertyPriority(property) !== 'important') continue;
        if (prior.value) element.style.setProperty(property, prior.value, prior.priority);
        else element.style.removeProperty(property);
        diagnostics.styleWrites++;
      }
    }
    rememberedStyles.clear();
    reservedChat = null;
  };
  const setImportant = (element, property, value) => {
    if (!element) return;
    const prior = rememberStyle(element, property);
    // If the framework has replaced a property we wrote, preserve its new value
    // as the baseline before a new explicit fallback sizing pass.
    if (prior.applied !== null && (element.style.getPropertyValue(property) !== prior.applied ||
        element.style.getPropertyPriority(property) !== 'important')) {
      prior.value = element.style.getPropertyValue(property);
      prior.priority = element.style.getPropertyPriority(property);
    }
    prior.applied = value;
    if (element.style.getPropertyValue(property) === value && element.style.getPropertyPriority(property) === 'important') return;
    element.style.setProperty(property, value, 'important');
    diagnostics.styleWrites++;
  };
  const allCanvasFrames = () => Array.from(document.querySelectorAll('iframe')).filter(frame => canvasUrl(frame) && isVisible(frame));
  const nativeCanvasEntry = () => {
    const frame = allCanvasFrames()[0];
    return frame ? { frame, panel: frame, rect: frame.getBoundingClientRect() } : null;
  };
  const fallbackCanvasEntry = () => {
    const dock = window[GLOBAL_KEY];
    if (!dock?.host || !isVisible(dock.host)) return null;
    return { frame: dock.frame, panel: dock.host, rect: dock.host.getBoundingClientRect(), width: dock.width };
  };
  const findChatRoot = () => {
    // Do not fall back to a generic <main> or resize the composer separately.
    // Unknown host layouts get an overlay rather than a speculative DOM rewrite.
    const direct = document.querySelector('#chat-container,[data-testid="chat-container"],[data-testid="chat-page"]');
    return direct && isVisible(direct) ? direct : null;
  };
  const observeOnly = (targets) => {
    for (const old of observedResizeTargets) if (!targets.includes(old)) {
      resizeObserver?.unobserve(old);
      observedResizeTargets.delete(old);
    }
    for (const target of targets) if (!observedResizeTargets.has(target)) {
      resizeObserver?.observe(target);
      observedResizeTargets.add(target);
    }
  };
  const syncChatLayout = () => {
    layoutFrame = null;
    if (disposed) return;
    diagnostics.syncs++;
    // Late native mounting wins over the compatibility fallback. There must not
    // be two active sizing mechanisms or two visible copies of the same Canvas.
    if (window[GLOBAL_KEY] && nativePanelOpen()) window[GLOBAL_KEY].close();
    const dock = window[GLOBAL_KEY];
    if (!dock?.host?.isConnected || !isVisible(dock.host) || window.innerWidth < 900) {
      observeOnly([]);
      restoreLayouts();
      diagnostics.mode = dock?.host?.isConnected ? 'fallback-overlay' : nativePanelOpen() ? 'native' : 'idle';
      return;
    }
    const chat = findChatRoot();
    if (reservedChat !== chat) restoreLayouts();
    if (!chat) { observeOnly([dock.host]); diagnostics.mode = 'fallback-overlay'; return; }
    if (!reservedChat) {
      reservedChat = chat;
      originalPaddingRight = parseFloat(getComputedStyle(chat).paddingRight) || 0;
    }
    setImportant(chat, 'box-sizing', 'border-box');
    setImportant(chat, 'min-width', '0');
    setImportant(chat, 'transition', 'none');
    setImportant(chat, 'padding-right', `${originalPaddingRight + dock.width}px`);
    // Crucially, do not observe chat, composer, or native iframe sizes.
    observeOnly([dock.host]);
    diagnostics.mode = 'fallback-reserved';
  };
  const scheduleLayout = () => {
    if (disposed || layoutFrame !== null) return;
    layoutFrame = requestAnimationFrame(syncChatLayout);
  };

  const technicalDetailsSelector = [
    'details[type="reasoning"]',
    'details[data-vut-ai-reasoning]',
    'details[type="tool_calls"]',
    'details[data-type="reasoning"]',
  ].join(',');
  const enhanceTechnicalDetails = (root = document) => {
    const candidates = [];
    if (root?.matches?.(technicalDetailsSelector)) candidates.push(root);
    candidates.push(...Array.from(root?.querySelectorAll?.(technicalDetailsSelector) || []));
    for (const details of candidates) {
      if (details.dataset.vutTechnicalEnhanced === 'true') continue;
      details.dataset.vutTechnicalEnhanced = 'true';
      details.dataset.vutTechnicalTrace = 'true';
      details.open = false;
      const summary = details.querySelector(':scope > summary');
      if (summary) {
        const original = String(summary.textContent || '').trim();
        const isTool = String(details.getAttribute('type') || '').includes('tool');
        summary.textContent = isTool ? `Technický průběh nástroje${original ? ` · ${original}` : ''}` : `Technické uvažování modelu${original && !/technick|reason|think/i.test(original) ? ` · ${original}` : ''}`;
        summary.addEventListener('click', () => {
          queueMicrotask(() => { details.dataset.vutUserExpanded = details.open ? 'true' : 'false'; });
        });
      }
    }
  };
  let uiStyle = document.getElementById('vut-ai-tutor-ui-coordinator-style');
  if (!uiStyle) {
    uiStyle = document.createElement('style');
    uiStyle.id = 'vut-ai-tutor-ui-coordinator-style';
    uiStyle.textContent = `
      details[data-vut-technical-trace="true"]{margin:.55rem 0!important;border:1px solid color-mix(in srgb,currentColor 14%,transparent)!important;border-radius:.7rem!important;background:color-mix(in srgb,currentColor 3%,transparent)!important;overflow:hidden!important;opacity:.82!important}
      details[data-vut-technical-trace="true"]>summary{cursor:pointer!important;padding:.5rem .7rem!important;font-size:.78rem!important;font-weight:650!important;color:color-mix(in srgb,currentColor 72%,transparent)!important;list-style:none!important;user-select:none!important}
      details[data-vut-technical-trace="true"]>summary::-webkit-details-marker{display:none!important}
      details[data-vut-technical-trace="true"]>summary:before{content:'▸';display:inline-block;margin-right:.45rem;transition:transform .14s ease}
      details[data-vut-technical-trace="true"][open]>summary:before{transform:rotate(90deg)}
      details[data-vut-technical-trace="true"][open]{opacity:1!important}
      details[data-vut-technical-trace="true"]>:not(summary){padding-left:.75rem!important;padding-right:.75rem!important}
    `;
    document.head.appendChild(uiStyle);
  }
  enhanceTechnicalDetails();

  const sendOutsideClick = (event) => {
    const fallback = fallbackCanvasEntry();
    const native = nativeCanvasEntry();
    const insideRect = (entry) => Boolean(entry && event.clientX >= entry.rect.left && event.clientX <= entry.rect.right && event.clientY >= entry.rect.top && event.clientY <= entry.rect.bottom);
    if (insideRect(fallback) || insideRect(native)) return;
    const frames = new Set(allCanvasFrames().map((frame) => frame.contentWindow).filter(Boolean));
    if (window[GLOBAL_KEY]?.frame?.contentWindow) frames.add(window[GLOBAL_KEY].frame.contentWindow);
    for (const frameWindow of frames) {
      try { frameWindow.postMessage({ type: 'study:outside-click' }, '*'); } catch (_) {}
    }
  };

  resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(scheduleLayout) : null;
  const uiObserver = new MutationObserver((mutations) => {
    if (disposed) return;
    for (const mutation of mutations) for (const node of mutation.addedNodes || []) if (node.nodeType === 1) enhanceTechnicalDetails(node);
    scheduleLayout();
  });
  uiObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style', 'hidden', 'aria-hidden'] });
  document.addEventListener('pointerdown', sendOutsideClick, true);
  window.addEventListener('resize', scheduleLayout);
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    finish();
    if (layoutFrame !== null) cancelAnimationFrame(layoutFrame);
    layoutFrame = null;
    uiObserver.disconnect();
    resizeObserver?.disconnect();
    observedResizeTargets.clear();
    document.removeEventListener('pointerdown', sendOutsideClick, true);
    window.removeEventListener('resize', scheduleLayout);
    window.removeEventListener('pagehide', dispose);
    if (window[GLOBAL_KEY]?.owner === uiController) window[GLOBAL_KEY].close();
    if (window[ACTION_KEY] === actionController) {
      actionController.dispose();
      delete window[ACTION_KEY];
    }
    restoreLayouts();
    if (window[UI_KEY] === uiController) delete window[UI_KEY];
    if (window[OPEN_KEY] === opener) delete window[OPEN_KEY];
  };
  const uiController = window[UI_KEY] = {
    revision: LAYOUT_REVISION,
    sync: scheduleLayout,
    snapshot: () => ({ ...diagnostics, disposed, observedResizeTargets: observedResizeTargets.size,
      ownedElements: rememberedStyles.size, pendingLayout: layoutFrame !== null }),
    dispose,
  };
  window.addEventListener('pagehide', dispose);
  scheduleLayout();


  const openFallbackDock = () => {
    if (disposed || window[UI_KEY] !== uiController || nativePanelOpen() || !cfg.embedUrl || !cfg.token) return false;
    const previous = window[GLOBAL_KEY];
    if (previous?.close) previous.close();
    document.getElementById(HOST_ID)?.remove();

    const host = document.createElement('aside');
    host.id = HOST_ID;
    host.setAttribute('role', 'complementary');
    host.setAttribute('aria-label', 'VUT AI Tutor Canvas');
    host.style.cssText = [
      'position:fixed', 'top:0', 'right:0', 'bottom:0',
      'width:min(48vw,900px)', 'min-width:380px',
      'z-index:2147483000', 'background:#fff',
      'box-shadow:-10px 0 36px rgba(0,0,0,.22)'
    ].join(';');
    const shadow = host.attachShadow({ mode: 'open' });
    shadow.innerHTML = `
      <style>
        :host{all:initial} *{box-sizing:border-box}
        .panel{height:100%;display:flex;flex-direction:column;background:#fff;color:#111827;font-family:Inter,system-ui,sans-serif}
        .head{height:48px;flex:0 0 48px;display:flex;align-items:center;gap:10px;padding:0 10px 0 14px;border-bottom:1px solid #e5e7eb;background:#fff}
        .title{font-size:13px;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1}
        button,a{height:32px;min-width:32px;border:0;border-radius:9px;background:#f3f4f6;color:#111827;display:inline-flex;align-items:center;justify-content:center;text-decoration:none;cursor:pointer;font:600 13px Inter,system-ui,sans-serif;padding:0 10px}
        button:hover,a:hover{background:#e5e7eb}.frame{border:0;width:100%;height:100%;flex:1;min-height:0;background:#fff}
        .resize{position:absolute;left:-5px;top:0;bottom:0;width:10px;cursor:col-resize;z-index:2}
        @media (prefers-color-scheme:dark){.panel,.head{background:#111827;color:#f9fafb}.head{border-color:#374151}button,a{background:#374151;color:#f9fafb}button:hover,a:hover{background:#4b5563}}
        @media (max-width:899px){.resize{display:none}}
      </style>
      <div class="panel">
        <div class="resize" title="Změnit šířku"></div>
        <div class="head"><div class="title"></div><a class="external" target="_blank" rel="noopener noreferrer" aria-label="Otevřít v novém okně">↗</a><button class="close" aria-label="Zavřít VUT AI Tutor Canvas">✕</button></div>
        <iframe class="frame" title="VUT AI Tutor Canvas" sandbox="allow-scripts allow-downloads" referrerpolicy="strict-origin-when-cross-origin"></iframe>
      </div>`;
    shadow.querySelector('.title').textContent = cfg.title;

    const url = new URL(cfg.embedUrl, window.location.href);
    if (cfg.messageId) url.searchParams.set('message_id', cfg.messageId);
    if (cfg.sourceId) url.searchParams.set('source_id', cfg.sourceId);
    const hash = new URLSearchParams(String(url.hash || '').replace(/^#/, ''));
    hash.set('session_id', cfg.sessionId);
    hash.set('view', cfg.view || 'book');
    hash.set('token', cfg.token);
    url.hash = hash.toString();

    const frame = shadow.querySelector('.frame');
    frame.src = url.toString();
    shadow.querySelector('.external').href = url.toString();
    document.body.appendChild(host);

    let preferredWidth = Math.min(900, Math.max(380, Math.round(window.innerWidth * 0.48)));
    let closed = false;
    let moveFrame = null;
    let resizing = false;
    let pointerId = null;
    let pendingX = null;
    let previousCursor = '';
    const resizeHandle = shadow.querySelector('.resize');
    const applyLayout = () => {
      if (closed || disposed) return;
      const viewport = Math.max(0, window.innerWidth || document.documentElement.clientWidth);
      const width = viewport < 900 ? viewport : Math.min(Math.max(380, preferredWidth), Math.min(1000, viewport - 320));
      for (const [property, value] of [['width', `${width}px`], ['min-width', '0px']]) {
        if (host.style.getPropertyValue(property) !== value) host.style.setProperty(property, value);
      }
      if (window[GLOBAL_KEY]?.host === host) window[GLOBAL_KEY].width = width;
      scheduleLayout();
    };
    const flushMove = () => {
      moveFrame = null;
      if (!resizing || closed || !Number.isFinite(pendingX)) return;
      preferredWidth = Math.min(Math.max(380, window.innerWidth - pendingX), Math.min(1000, window.innerWidth - 320));
      pendingX = null;
      applyLayout();
    };
    const onMove = (event) => {
      if (!resizing || event.pointerId !== pointerId) return;
      pendingX = event.clientX;
      if (moveFrame === null) moveFrame = requestAnimationFrame(flushMove);
    };
    const onUp = () => {
      if (!resizing && moveFrame === null && pointerId === null) return;
      if (moveFrame !== null) cancelAnimationFrame(moveFrame);
      moveFrame = null;
      if (!closed) flushMove();
      resizing = false;
      pendingX = null;
      if (pointerId !== null) {
        try { resizeHandle.releasePointerCapture(pointerId); } catch (_) {}
        pointerId = null;
      }
      if (document.body.style.cursor === 'col-resize') document.body.style.cursor = previousCursor;
    };
    resizeHandle.addEventListener('pointerdown', (event) => {
      if (closed || event.button !== 0 || resizing) return;
      resizing = true;
      pointerId = event.pointerId;
      previousCursor = document.body.style.cursor;
      document.body.style.cursor = 'col-resize';
      resizeHandle.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    resizeHandle.addEventListener('lostpointercapture', onUp);
    window.addEventListener('resize', applyLayout);

    const onMessage = (event) => {
      if (closed || disposed || event.source !== frame.contentWindow || !event.data) return;
      const data = event.data;
      if (data.type === 'payload') {
        frame.contentWindow?.postMessage({ type: 'payload', requestId: data.requestId ?? null, payload: cfg.payload }, '*');
      } else if (data.type === 'input:prompt' || data.type === 'input:prompt:submit') {
        void setChatPrompt(String(data.text || ''), data.type === 'input:prompt:submit').then((ok) => {
          frame.contentWindow?.postMessage({ type: 'study:prompt-status', ok: Boolean(ok) }, '*');
        });
      }
    };
    window.addEventListener('message', onMessage);

    const close = () => {
      if (closed) return;
      closed = true;
      onUp();
      window.removeEventListener('message', onMessage);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      resizeHandle.removeEventListener('lostpointercapture', onUp);
      window.removeEventListener('resize', applyLayout);
      if (window[GLOBAL_KEY]?.host === host) delete window[GLOBAL_KEY];
      host.remove();
      scheduleLayout();
    };
    shadow.querySelector('.close').addEventListener('click', close);
    window[GLOBAL_KEY] = { host, frame, close, owner: uiController, width: preferredWidth };
    applyLayout();
    return true;
  };

  let clicked = false;
  let finished = false;
  let timer = null;
  let observer = null;
  const started = Date.now();
  const finish = () => {
    if (finished) return;
    finished = true;
    if (timer !== null) clearInterval(timer);
    timer = null;
    observer?.disconnect();
    if (window[OPEN_KEY] === opener) delete window[OPEN_KEY];
  };
  const opener = window[OPEN_KEY] = { dispose: finish };
  const step = () => {
    if (finished || disposed || window[UI_KEY] !== uiController) { finish(); return; }
    if (nativePanelOpen()) { finish(); scheduleLayout(); return; }
    if (!clicked) {
      const citation = findInlineCitation();
      if (citation) {
        clicked = true;
        citation.click();
        if (nativePanelOpen()) { finish(); scheduleLayout(); return; }
      }
    }
    if (Date.now() - started >= 1200) {
      finish();
      if (!nativePanelOpen()) openFallbackDock();
    }
  };
  observer = new MutationObserver(step);
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-label', 'class', 'style', 'hidden'] });
  timer = setInterval(step, 250); // Bounded opening retry, never a layout poll.
  step();
  return { installed: true, fallbackAfterMs: 1200, citationIndex: cfg.citationIndex, layoutRevision: LAYOUT_REVISION };
})();
