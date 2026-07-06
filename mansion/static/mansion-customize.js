(function () {
  const STORAGE_KEY = "mansion_customize";

  const DEFAULTS = {
    siteName: "The Mansion",
    siteNameLocked: "The mansion is locked.",
    eyebrow: "Headspace directory",
    loginEyebrow: "Private system space",
    intro:
      "A private room system for the mansion headspace. Rooms can be added, edited, locked, unlocked, and imported from PluralKit with dev permissions.",
    loginIntro: "Enter the house password to continue.",
    loginCaption: "The headspace stretches wider than it should.",
    summaryLabel: "Current mansion summary",
    tabsLabel: "Mansion sections",
    colors: {
      gold: "#d4a853",
      goldBright: "#e8c878",
      goldDim: "#9a7338",
      moss: "#6d9470",
      stone: "#7a8a94",
      red: "#b85c5c",
      ember: "#c45a2c",
      ink: "#f4efe6",
      muted: "#c4b8aa",
      dim: "#8a7f74",
    },
  };

  function loadPrefs() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return structuredClone(DEFAULTS);
      const saved = JSON.parse(raw);
      return {
        ...DEFAULTS,
        ...saved,
        colors: { ...DEFAULTS.colors, ...(saved.colors || {}) },
      };
    } catch {
      return structuredClone(DEFAULTS);
    }
  }

  function savePrefs(prefs) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  }

  function hexToRgb(hex) {
    const value = hex.replace("#", "").trim();
    if (value.length === 3) {
      const r = parseInt(value[0] + value[0], 16);
      const g = parseInt(value[1] + value[1], 16);
      const b = parseInt(value[2] + value[2], 16);
      return { r, g, b };
    }
    if (value.length !== 6) return null;
    return {
      r: parseInt(value.slice(0, 2), 16),
      g: parseInt(value.slice(2, 4), 16),
      b: parseInt(value.slice(4, 6), 16),
    };
  }

  function rgba(hex, alpha) {
    const rgb = hexToRgb(hex);
    if (!rgb) return hex;
    return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
  }

  function darken(hex, amount) {
    const rgb = hexToRgb(hex);
    if (!rgb) return hex;
    const mix = (channel) => Math.round(channel * (1 - amount));
    const toHex = (channel) => mix(channel).toString(16).padStart(2, "0");
    return `#${toHex(rgb.r)}${toHex(rgb.g)}${toHex(rgb.b)}`;
  }

  function applyColors(colors) {
    const root = document.documentElement;
    const gold = colors.gold || DEFAULTS.colors.gold;
    const goldBright = colors.goldBright || DEFAULTS.colors.goldBright;
    const moss = colors.moss || DEFAULTS.colors.moss;
    const stone = colors.stone || DEFAULTS.colors.stone;
    const red = colors.red || DEFAULTS.colors.red;
    const ember = colors.ember || DEFAULTS.colors.ember;
    const ink = colors.ink || DEFAULTS.colors.ink;
    const muted = colors.muted || DEFAULTS.colors.muted;
    const dim = colors.dim || DEFAULTS.colors.dim;
    const goldDim = colors.goldDim || darken(gold, 0.28);

    root.style.setProperty("--ink", ink);
    root.style.setProperty("--muted", muted);
    root.style.setProperty("--dim", dim);
    root.style.setProperty("--gold", gold);
    root.style.setProperty("--gold-bright", goldBright);
    root.style.setProperty("--gold-dim", goldDim);
    root.style.setProperty("--ember", ember);
    root.style.setProperty("--moss", moss);
    root.style.setProperty("--stone", stone);
    root.style.setProperty("--red", red);
    root.style.setProperty("--moss-glow", rgba(moss, 0.35));
    root.style.setProperty("--stone-glow", rgba(stone, 0.3));
    root.style.setProperty("--red-glow", rgba(red, 0.32));
    root.style.setProperty("--open-glow", rgba(gold, 0.28));
    root.style.setProperty("--line", rgba(ink, 0.12));
    root.style.setProperty("--line-strong", rgba(ink, 0.22));
    root.style.setProperty("--accent-rgb", `${hexToRgb(gold)?.r || 212}, ${hexToRgb(gold)?.g || 168}, ${hexToRgb(gold)?.b || 83}`);
    root.style.setProperty("--moss-rgb", `${hexToRgb(moss)?.r || 109}, ${hexToRgb(moss)?.g || 148}, ${hexToRgb(moss)?.b || 112}`);
    root.style.setProperty("--stone-rgb", `${hexToRgb(stone)?.r || 122}, ${hexToRgb(stone)?.g || 138}, ${hexToRgb(stone)?.b || 148}`);
    root.style.setProperty("--red-rgb", `${hexToRgb(red)?.r || 184}, ${hexToRgb(red)?.g || 92}, ${hexToRgb(red)?.b || 92}`);
    root.style.setProperty("--ember-rgb", `${hexToRgb(ember)?.r || 196}, ${hexToRgb(ember)?.g || 90}, ${hexToRgb(ember)?.b || 44}`);
  }

  function applyText(prefs) {
    document.querySelectorAll("[data-customize]").forEach((node) => {
      const key = node.dataset.customize;
      const value = prefs[key];
      if (value) node.textContent = value;
    });

    document.querySelectorAll("[data-customize-aria]").forEach((node) => {
      const key = node.dataset.customizeAria;
      const value = prefs[key];
      if (value) node.setAttribute("aria-label", value);
    });

    const title = prefs.siteName || DEFAULTS.siteName;
    document.title = title;
  }

  function applyPrefs(prefs) {
    applyColors(prefs.colors);
    if (document.body) {
      applyText(prefs);
    }
  }

  function readForm(form, basePrefs) {
    const prefs = { ...basePrefs, colors: { ...basePrefs.colors } };
    form.querySelectorAll("[data-customize-field]").forEach((input) => {
      const key = input.dataset.customizeField;
      prefs[key] = input.value.trim() || DEFAULTS[key] || "";
    });
    form.querySelectorAll("[data-customize-color]").forEach((input) => {
      const key = input.dataset.customizeColor;
      prefs.colors[key] = input.value;
    });
    prefs.colors.goldDim = darken(prefs.colors.gold, 0.28);
    return prefs;
  }

  function fillForm(form, prefs) {
    form.querySelectorAll("[data-customize-field]").forEach((input) => {
      const key = input.dataset.customizeField;
      input.value = prefs[key] || DEFAULTS[key] || "";
    });
    form.querySelectorAll("[data-customize-color]").forEach((input) => {
      const key = input.dataset.customizeColor;
      input.value = prefs.colors[key] || DEFAULTS.colors[key];
    });
  }

  function initCustomizeForm() {
    const form = document.getElementById("customize-form");
    if (!form) return;

    let prefs = loadPrefs();
    fillForm(form, prefs);

    function commit() {
      if (document.body.dataset.role && document.body.dataset.role !== "owner") {
        return;
      }
      prefs = readForm(form, prefs);
      savePrefs(prefs);
      applyPrefs(prefs);
    }

    form.addEventListener("input", commit);
    form.addEventListener("change", commit);

    const reset = document.getElementById("customize-reset");
    if (reset) {
      reset.addEventListener("click", () => {
        if (!window.confirm("Reset all customization to the default mansion theme?")) {
          return;
        }
        localStorage.removeItem(STORAGE_KEY);
        prefs = structuredClone(DEFAULTS);
        fillForm(form, prefs);
        applyPrefs(prefs);
      });
    }
  }

  applyPrefs(loadPrefs());

  document.addEventListener("DOMContentLoaded", () => {
    applyText(loadPrefs());
    initCustomizeForm();
  });

  window.MansionCustomize = { loadPrefs, applyPrefs, DEFAULTS };
})();
