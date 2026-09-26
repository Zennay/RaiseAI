(() => {
  "use strict";

  if (window.top !== window || window.__raiseAiWearInstalled) return;
  window.__raiseAiWearInstalled = true;

  const NATIVE_APP = "raiseai";
  const SILENCE_MS = 4000;
  const START_RETRY_MS = 450;
  const START_RETRY_LIMIT = 18;

  let state = "loading";
  let port = null;
  let silenceTimer = null;
  let startRetryTimer = null;
  let startRetryCount = 0;
  let lastPromptText = "";
  let listeningStartedWithText = "";
  let scheduled = false;

  const clean = (value) => (value || "").toString().trim().toLowerCase();
  const visible = (element) => element && !element.disabled &&
    element.getClientRects().length > 0;

  function labelOf(element) {
    return clean([
      element?.getAttribute?.("aria-label"),
      element?.getAttribute?.("title"),
      element?.getAttribute?.("data-testid"),
      element?.textContent
    ].filter(Boolean).join(" "));
  }

  function promptText(prompt) {
    if (!prompt) return "";
    return (prompt.value ?? prompt.textContent ?? "").toString().trim();
  }

  function findPrompt() {
    return document.querySelector(
      "#prompt-textarea, textarea[placeholder], [contenteditable='true'][data-virtualkeyboard]"
    );
  }

  function findComposer(prompt) {
    if (!prompt) return null;
    const form = prompt.closest("form");
    if (form) return form;
    let node = prompt.parentElement;
    while (node && node !== document.body) {
      if (node.querySelectorAll("button").length >= 1) return node;
      node = node.parentElement;
    }
    return prompt.parentElement;
  }

  function findButton(composer, kind) {
    if (!composer) return null;
    const buttons = Array.from(composer.querySelectorAll("button"));

    if (kind === "mic") {
      const exactIds = ["composer-speech-button", "speech-button"];
      for (const testId of exactIds) {
        const exact = composer.querySelector(`button[data-testid="${testId}"]`);
        if (exact) return exact;
      }

      const words = [
        "dictate", "dictation", "dicteer", "dicteren", "microphone", "microfoon",
        "speech input", "spraak invoer", "stop dictation", "stop recording",
        "stop dicteren", "stop opname"
      ];
      return buttons.find((button) => {
        const label = labelOf(button);
        if (label.includes("voice mode") || label.includes("spraakmodus")) return false;
        return words.some((word) => label.includes(word));
      }) || null;
    }

    const exactIds = ["send-button", "composer-submit-button"];
    for (const testId of exactIds) {
      const exact = composer.querySelector(`button[data-testid="${testId}"]`);
      if (exact && visible(exact)) return exact;
    }

    const words = ["send", "verstuur", "verzenden", "submit"];
    return buttons.find((button) => {
      const label = labelOf(button);
      if (label.includes("stop generating") || label.includes("stoppen")) return false;
      return visible(button) && words.some((word) => label.includes(word));
    }) || null;
  }

  function isMicActive(mic) {
    if (!mic) return false;
    const label = labelOf(mic);
    const pressed = mic.getAttribute("aria-pressed");
    const dataState = clean(mic.getAttribute("data-state"));
    return pressed === "true" || dataState === "active" || dataState === "on" ||
      label.includes("stop dictation") || label.includes("stop recording") ||
      label.includes("stop dicteren") || label.includes("stop opname");
  }

  function emitState(next, detail = {}) {
    state = next;
    document.documentElement.dataset.raiseaiState = next;
    updateVoiceShell(detail);
    try {
      port?.postMessage({ type: "state", state: next, ...detail });
    } catch (_) {
      port = null;
    }
  }

  function clearSilenceTimer() {
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = null;
  }

  function armSilenceTimer() {
    clearSilenceTimer();
    const prompt = findPrompt();
    const text = promptText(prompt);
    if (state !== "listening" || !text || text === listeningStartedWithText) return;

    silenceTimer = setTimeout(() => {
      finalizeAndSend("silence");
    }, SILENCE_MS);
  }

  function trackPromptChange() {
    if (state !== "listening") return;
    const prompt = findPrompt();
    const text = promptText(prompt);
    if (text === lastPromptText) return;

    lastPromptText = text;
    updateVoiceShell({ transcript: text });
    if (text && text !== listeningStartedWithText) armSilenceTimer();
  }

  function markMain(prompt) {
    const main = prompt?.closest("main") || document.querySelector("main");
    if (!main) return;
    main.classList.add("raiseai-main", "raiseai-keep");

    let kept = main;
    let parent = main.parentElement;
    while (parent && parent !== document.body) {
      parent.classList.add("raiseai-keep");
      for (const sibling of parent.children) {
        if (sibling !== kept && sibling.id !== "raiseai-wear-topbar" &&
            sibling.id !== "raiseai-voice-shell") {
          const tag = sibling.tagName?.toLowerCase();
          if (tag === "aside" || tag === "nav" ||
              sibling.getAttribute("data-testid")?.includes("sidebar")) {
            sibling.classList.add("raiseai-hidden");
          }
        }
      }
      kept = parent;
      parent = parent.parentElement;
    }
  }

  function ensureTopbar() {
    if (document.getElementById("raiseai-wear-topbar")) return;
    const bar = document.createElement("div");
    bar.id = "raiseai-wear-topbar";
    bar.className = "raiseai-keep";
    bar.textContent = "Raise AI";
    document.body.appendChild(bar);
  }

  function ensureVoiceShell() {
    if (document.getElementById("raiseai-voice-shell")) return;

    const shell = document.createElement("div");
    shell.id = "raiseai-voice-shell";
    shell.className = "raiseai-keep";
    shell.innerHTML = `
      <div id="raiseai-voice-status">Even laden…</div>
      <div id="raiseai-transcript"></div>
      <button id="raiseai-voice-orb" type="button" aria-label="Praat met ChatGPT">
        <span class="raiseai-orb-ring"></span>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm-1-9a1 1 0 0 1 2 0v6a1 1 0 1 1-2 0V5Zm7 6a6 6 0 0 1-5 5.91V19h3v2H8v-2h3v-2.09A6 6 0 0 1 6 11h2a4 4 0 0 0 8 0h2Z"/>
        </svg>
      </button>
    `;
    document.body.appendChild(shell);

    shell.querySelector("#raiseai-voice-orb")?.addEventListener("click", () => {
      if (state === "listening") finalizeAndSend("tap");
      else startDictation("tap");
    });
  }

  function updateVoiceShell(detail = {}) {
    ensureVoiceShell();
    const status = document.getElementById("raiseai-voice-status");
    const transcript = document.getElementById("raiseai-transcript");
    if (!status || !transcript) return;

    const labels = {
      loading: "ChatGPT laden…",
      ready: "Praat met ChatGPT",
      starting: "Microfoon starten…",
      listening: "Luisteren…",
      finalizing: "Even wachten…",
      sending: "Versturen…",
      disconnected: "Verbinding herstellen…"
    };
    status.textContent = labels[state] || "Praat met ChatGPT";

    if (Object.prototype.hasOwnProperty.call(detail, "transcript")) {
      transcript.textContent = detail.transcript || "";
    } else if (state === "ready" && !promptText(findPrompt())) {
      transcript.textContent = "";
    }
  }

  function adapt() {
    ensureVoiceShell();
    const prompt = findPrompt();
    if (!prompt) {
      if (state !== "listening" && state !== "starting" && state !== "sending") {
        emitState("loading");
      }
      return;
    }

    const composer = findComposer(prompt);
    if (!composer) return;

    document.body.classList.add("raiseai-wear-ready");
    prompt.classList.add("raiseai-prompt");
    composer.classList.add("raiseai-composer");
    markMain(prompt);
    ensureTopbar();

    const mic = findButton(composer, "mic");
    const send = findButton(composer, "send");
    if (mic) mic.classList.add("raiseai-action", "raiseai-mic");
    if (send) send.classList.add("raiseai-action", "raiseai-send");

    document.querySelectorAll(
      "[data-testid='sidebar-button'], [data-testid='model-switcher-dropdown-button'], " +
      "button[aria-label*='sidebar' i], button[aria-label*='share' i], button[aria-label*='delen' i]"
    ).forEach((element) => element.classList.add("raiseai-hidden"));

    trackPromptChange();

    if ((state === "loading" || state === "disconnected") && mic) {
      emitState("ready");
    }

    if (state === "sending" && !promptText(prompt)) {
      emitState("ready");
    }
  }

  function retryStart(source) {
    if (startRetryTimer) clearTimeout(startRetryTimer);
    if (startRetryCount >= START_RETRY_LIMIT) {
      startRetryCount = 0;
      emitState("ready", { error: "microphone_unavailable" });
      return;
    }
    startRetryCount += 1;
    startRetryTimer = setTimeout(() => startDictation(source), START_RETRY_MS);
  }

  function startDictation(source = "unknown") {
    if (state === "listening" || state === "starting" ||
        state === "finalizing" || state === "sending") {
      return false;
    }

    const prompt = findPrompt();
    const composer = findComposer(prompt);
    const mic = findButton(composer, "mic");

    if (!prompt || !composer || !mic || !visible(mic)) {
      emitState("loading", { source });
      retryStart(source);
      return false;
    }

    if (startRetryTimer) clearTimeout(startRetryTimer);
    startRetryTimer = null;
    startRetryCount = 0;
    listeningStartedWithText = promptText(prompt);
    lastPromptText = listeningStartedWithText;
    clearSilenceTimer();

    emitState("starting", { source });
    try {
      mic.click();
      setTimeout(() => {
        if (state === "starting") {
          emitState("listening", {
            source,
            transcript: promptText(findPrompt())
          });
        }
      }, 180);
      return true;
    } catch (_) {
      emitState("ready", { error: "microphone_click_failed" });
      return false;
    }
  }

  function clickSendWhenReady(reason, attempt = 0) {
    const prompt = findPrompt();
    const composer = findComposer(prompt);
    const send = findButton(composer, "send");
    const text = promptText(prompt);

    if (!text || text === listeningStartedWithText) {
      emitState("ready", { reason, error: "empty_transcript" });
      return;
    }

    if (send && visible(send) && !send.disabled) {
      emitState("sending", { reason, transcript: text });
      send.click();
      setTimeout(adapt, 250);
      setTimeout(() => {
        if (state === "sending") emitState("ready");
      }, 2200);
      return;
    }

    if (attempt < 8) {
      setTimeout(() => clickSendWhenReady(reason, attempt + 1), 180);
    } else {
      emitState("ready", { reason, error: "send_unavailable", transcript: text });
    }
  }

  function finalizeAndSend(reason = "unknown") {
    if (state !== "listening" && state !== "starting") return;
    clearSilenceTimer();
    emitState("finalizing", { reason, transcript: promptText(findPrompt()) });

    const prompt = findPrompt();
    const composer = findComposer(prompt);
    const mic = findButton(composer, "mic");

    if (mic && isMicActive(mic)) {
      try { mic.click(); } catch (_) {}
    }

    setTimeout(() => clickSendWhenReady(reason), 320);
  }

  function connectNativeBridge() {
    try {
      port = browser.runtime.connectNative(NATIVE_APP);
      port.onMessage.addListener((message) => {
        if (!message || typeof message !== "object") return;
        if (message.type === "startDictation") {
          startDictation(message.reason || "native");
        } else if (message.type === "cancelDictation") {
          clearSilenceTimer();
          if (state === "listening" || state === "starting") {
            const prompt = findPrompt();
            const mic = findButton(findComposer(prompt), "mic");
            if (mic && isMicActive(mic)) {
              try { mic.click(); } catch (_) {}
            }
          }
          emitState("ready");
        }
      });
      port.onDisconnect.addListener(() => {
        port = null;
        if (state !== "listening" && state !== "sending") emitState("disconnected");
        setTimeout(connectNativeBridge, 1000);
      });
      emitState(state, { bridge: "connected" });
    } catch (_) {
      port = null;
      setTimeout(connectNativeBridge, 1200);
    }
  }

  const scheduleAdapt = () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      adapt();
    });
  };

  new MutationObserver(scheduleAdapt).observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["aria-label", "aria-pressed", "data-testid", "data-state", "disabled"]
  });

  document.addEventListener("input", () => {
    trackPromptChange();
    scheduleAdapt();
  }, true);

  connectNativeBridge();
  scheduleAdapt();
  setInterval(adapt, 1200);
})();