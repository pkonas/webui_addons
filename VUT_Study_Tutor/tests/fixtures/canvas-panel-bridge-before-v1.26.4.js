return (() => {
  const cfg = __CONFIG__;
  const GLOBAL_KEY = '__VUT_AI_TUTOR_RIGHT_DOCK_V1220__';
  const HOST_ID = 'study-tutor-right-panel';
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const isVisible = (el) => Boolean(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  const messageRoot = () => cfg.messageId ? document.getElementById(`message-${cfg.messageId}`) : null;

  const nativePanelOpen = () => {
    const candidates = Array.from(document.querySelectorAll('button[aria-label="Close embed"]'));
    for (const close of candidates) {
      if (!isVisible(close)) continue;
      const container = close.closest('#controls-container') || close.parentElement?.parentElement?.parentElement;
      const title = String(container?.textContent || '');
      const frame = container?.querySelector?.('iframe');
      if (title.includes(cfg.title) || String(frame?.src || '').includes('/study-tutor/canvas')) return true;
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
      const source = String(frame.getAttribute('src') || frame.src || '');
      return source.includes('/study-tutor/canvas');
    });
  };
  const actionListener = async (event) => {
    const data = event.data || {};
    if (data.type !== 'study:tutor-action' || data.source !== 'vut-ai-tutor-canvas' || !cfg.actionBridge || data.bridge !== cfg.actionBridge) return;
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
  window[ACTION_KEY] = {
    bridge: cfg.actionBridge,
    dispose: () => window.removeEventListener('message', actionListener),
  };

  // Coordinate native/fallback Canvas panels with the chat and technical traces.
  const UI_KEY = '__VUT_AI_TUTOR_UI_COORDINATOR_V1220__';
  try { window[UI_KEY]?.dispose?.(); } catch (_) {}
  const rememberedStyles = new Map();
  const observedResizeTargets = new Set();
  let resizeObserver = null;
  let syncTimer = null;

  const rememberStyle = (element) => {
    if (element && !rememberedStyles.has(element)) rememberedStyles.set(element, element.getAttribute('style'));
  };
  const restoreLayouts = () => {
    for (const [element, style] of rememberedStyles) {
      if (!element?.isConnected) continue;
      if (style === null) element.removeAttribute('style');
      else element.setAttribute('style', style);
    }
    rememberedStyles.clear();
  };
  const setImportant = (element, property, value) => {
    if (!element) return;
    rememberStyle(element);
    if (element.style.getPropertyValue(property) === value && element.style.getPropertyPriority(property) === 'important') return;
    element.style.setProperty(property, value, 'important');
  };
  const allCanvasFrames = () => Array.from(document.querySelectorAll('iframe')).filter((frame) => {
    const src = String(frame.getAttribute('src') || frame.src || '');
    return src.includes('/study-tutor/canvas') && isVisible(frame);
  });
  const nativeCanvasEntry = () => {
    for (const frame of allCanvasFrames()) {
      const rect = frame.getBoundingClientRect();
      if (rect.width < 80 || rect.height < 80) continue;
      // The nearest #controls-container can span the whole application in some Desktop
      // builds. The iframe rectangle itself is the reliable reserved workspace.
      return { frame, panel: frame, rect };
    }
    return null;
  };
  const fallbackCanvasEntry = () => {
    const host = window[GLOBAL_KEY]?.host || document.getElementById(HOST_ID);
    if (!host || !isVisible(host)) return null;
    return { frame: window[GLOBAL_KEY]?.frame || null, panel: host, rect: host.getBoundingClientRect() };
  };
  const findChatRoot = () => {
    const direct = document.querySelector('#chat-container,[data-testid="chat-container"],[data-testid="chat-page"]');
    if (direct && isVisible(direct)) return direct;
    const composer = document.querySelector('#message-input-container,[data-testid="message-input-container"],form textarea,form [contenteditable="true"]');
    const main = composer?.closest('main') || composer?.closest('[role="main"]');
    return main && isVisible(main) ? main : null;
  };
  const findComposerRoot = (chat) => {
    const direct = document.querySelector('#message-input-container,[data-testid="message-input-container"]');
    if (direct && isVisible(direct)) return direct;
    const input = document.querySelector('textarea[placeholder],form [contenteditable="true"],form textarea');
    const form = input?.closest('form');
    return form && (!chat || chat.contains(form)) ? form : null;
  };
  const syncChatLayout = () => {
    const entry = fallbackCanvasEntry() || nativeCanvasEntry();
    if (!entry || window.innerWidth < 900) {
      restoreLayouts();
      return;
    }
    const rect = entry.rect;
    const viewport = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
    const onRight = rect.left >= viewport / 2;
    const onLeft = rect.right <= viewport / 2;
    const reserveRight = onRight ? Math.max(0, Math.round(viewport - rect.left)) : 0;
    const reserveLeft = onLeft ? Math.max(0, Math.round(rect.right)) : 0;
    if (!reserveRight && !reserveLeft) {
      restoreLayouts();
      return;
    }
    const available = Math.max(360, viewport - reserveLeft - reserveRight);
    const chat = findChatRoot();
    const composer = findComposerRoot(chat);
    for (const element of [chat, composer].filter(Boolean)) {
      setImportant(element, 'box-sizing', 'border-box');
      setImportant(element, 'width', `${available}px`);
      setImportant(element, 'max-width', `${available}px`);
      setImportant(element, 'margin-left', `${reserveLeft}px`);
      setImportant(element, 'margin-right', `${reserveRight}px`);
      setImportant(element, 'transition', 'width .18s ease,max-width .18s ease,margin .18s ease');
    }
    if (resizeObserver) {
      for (const target of [entry.panel, entry.frame, chat, composer].filter(Boolean)) {
        if (!observedResizeTargets.has(target)) {
          observedResizeTargets.add(target);
          try { resizeObserver.observe(target); } catch (_) {}
        }
      }
    }
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

  resizeObserver = typeof ResizeObserver === 'function' ? new ResizeObserver(() => syncChatLayout()) : null;
  const uiObserver = new MutationObserver((mutations) => {
    for (const mutation of mutations) for (const node of mutation.addedNodes || []) if (node.nodeType === 1) enhanceTechnicalDetails(node);
    syncChatLayout();
  });
  uiObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'open', 'aria-hidden'] });
  document.addEventListener('pointerdown', sendOutsideClick, true);
  window.addEventListener('resize', syncChatLayout);
  syncTimer = setInterval(syncChatLayout, 700);
  window[UI_KEY] = {
    sync: syncChatLayout,
    dispose: () => {
      clearInterval(syncTimer);
      uiObserver.disconnect();
      resizeObserver?.disconnect?.();
      document.removeEventListener('pointerdown', sendOutsideClick, true);
      window.removeEventListener('resize', syncChatLayout);
      restoreLayouts();
    },
  };
  syncChatLayout();


  const openFallbackDock = () => {
    if (!cfg.embedUrl || !cfg.token) return false;
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

    let width = Math.min(900, Math.max(380, Math.round(window.innerWidth * 0.48)));
    const applyLayout = () => {
      if (window.innerWidth < 900) {
        host.style.width = '100vw';
        host.style.minWidth = '0';
      } else {
        host.style.width = `${width}px`;
        host.style.minWidth = '380px';
      }
      window[UI_KEY]?.sync?.();
    };

    let resizing = false;
    const resizeHandle = shadow.querySelector('.resize');
    const onMove = (event) => {
      if (!resizing) return;
      width = Math.min(Math.max(380, window.innerWidth - event.clientX), Math.min(1000, window.innerWidth - 320));
      applyLayout();
    };
    const onUp = () => { resizing = false; document.body.style.cursor = ''; };
    resizeHandle.addEventListener('pointerdown', (event) => {
      resizing = true;
      document.body.style.cursor = 'col-resize';
      resizeHandle.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('resize', applyLayout);

    const onMessage = (event) => {
      if (event.source !== frame.contentWindow || !event.data) return;
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
      window.removeEventListener('message', onMessage);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('resize', applyLayout);
      document.body.style.cursor = '';
      host.remove();
      window[UI_KEY]?.sync?.();
      if (window[GLOBAL_KEY]?.host === host) delete window[GLOBAL_KEY];
    };
    shadow.querySelector('.close').addEventListener('click', close);
    window[GLOBAL_KEY] = { host, frame, close };
    applyLayout();
    return true;
  };

  let clicked = false;
  let finished = false;
  const started = Date.now();
  const finish = () => {
    if (finished) return;
    finished = true;
    clearInterval(timer);
    observer.disconnect();
  };
  const step = () => {
    if (nativePanelOpen()) { finish(); return; }
    if (!clicked) {
      const citation = findInlineCitation();
      if (citation) {
        clicked = true;
        citation.click();
      }
    }
    if (Date.now() - started >= 1200) {
      finish();
      if (!nativePanelOpen()) openFallbackDock();
    }
  };
  const observer = new MutationObserver(step);
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['aria-label', 'class'] });
  const timer = setInterval(step, 250);
  step();
  return { installed: true, fallbackAfterMs: 1200, citationIndex: cfg.citationIndex };
})();