(() => {
  "use strict";

  if (window.top !== window || window.__raiseAiWearInstalled) return;
  window.__raiseAiWearInstalled = true;

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
    const testIds = kind === "mic"
      ? ["composer-speech-button", "speech-button"]
      : ["send-button", "composer-submit-button", "stop-button"];
    for (const testId of testIds) {
      const exact = composer.querySelector(`button[data-testid="${testId}"]`);
      if (exact) return exact;
    }
    const words = kind === "mic"
      ? ["dictate", "dictation", "dicteer", "dicteren", "microphone", "microfoon", "speech input", "spraak invoer"]
      : ["send", "verstuur", "verzenden", "submit", "stop generating", "stoppen"];
    return Array.from(composer.querySelectorAll("button")).find((button) => {
      const label = labelOf(button);
      if (kind === "mic" && (label.includes("voice mode") || label.includes("spraakmodus"))) {
        return false;
      }
      return words.some((word) => label.includes(word));
    }) || null;
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
        if (sibling !== kept && sibling.id !== "raiseai-wear-topbar") {
          const tag = sibling.tagName?.toLowerCase();
          if (tag === "aside" || tag === "nav" || sibling.getAttribute("data-testid")?.includes("sidebar")) {
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
    bar.textContent = "RaiseGPT";
    document.body.appendChild(bar);
  }

  function adapt() {
    const prompt = findPrompt();
    if (!prompt) return;
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
  }

  let scheduled = false;
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
    attributes: true,
    attributeFilter: ["aria-label", "data-testid", "disabled"]
  });
  scheduleAdapt();
  setInterval(adapt, 1_500);
})();
