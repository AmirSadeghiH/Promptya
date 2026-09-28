/* Promptya theme — dark ⇄ light with persistence and system preference.
   The switch itself is a sliding sun/moon drawn purely in CSS from
   html[data-theme]; this module owns state, persistence, the <meta
   theme-color> tags and the accessible labelling of every copy. */
(function (global) {
  "use strict";

  var THEME_KEY = "promptya-theme";
  var DARK_BG = "#0a0a0f";
  var LIGHT_BG = "#f6f6f9";

  /* Fallbacks so labels are never raw keys before i18n.js boots. */
  var FALLBACK_LABELS = {
    en: { theme_to_light: "Switch to light mode", theme_to_dark: "Switch to dark mode" },
    fa: { theme_to_light: "تغییر به حالت روز", theme_to_dark: "تغییر به حالت شب" },
  };

  function label(key) {
    var i18n = global.PromptyaI18n;
    if (i18n) {
      var value = i18n.t(key);
      if (value && value !== key) return value;
    }
    var lang = document.documentElement.getAttribute("lang") === "fa" ? "fa" : "en";
    return FALLBACK_LABELS[lang][key] || FALLBACK_LABELS.en[key];
  }

  function readStored() {
    try {
      var t = localStorage.getItem(THEME_KEY);
      if (t === "dark" || t === "light") return t;
    } catch (e) {}
    return null;
  }

  function cookieTheme() {
    var m = document.cookie.match(/(?:^|;\s*)promptya-theme=(dark|light)(?:;|$)/);
    return m ? m[1] : null;
  }

  function systemTheme() {
    return global.matchMedia && global.matchMedia("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  }

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
  }

  function updateMeta(theme) {
    // One unscoped tag, so this always wins: the browser-chrome colour tracks
    // the theme the visitor chose, which may be the opposite of their OS.
    var wanted = theme === "light" ? LIGHT_BG : DARK_BG;
    document.querySelectorAll('meta[name="theme-color"]').forEach(function (meta) {
      if (meta.getAttribute("content") !== wanted) meta.setAttribute("content", wanted);
    });
  }

  function syncToggles() {
    var theme = currentTheme();
    var nextKey = theme === "light" ? "theme_to_dark" : "theme_to_light";
    var text = label(nextKey);
    document.querySelectorAll(".js-theme-toggle").forEach(function (btn) {
      // aria-pressed reflects "light mode is on" so state is machine-readable.
      btn.setAttribute("aria-pressed", theme === "light" ? "true" : "false");
      btn.setAttribute("aria-label", text);
      btn.setAttribute("title", text);
    });
  }

  function apply(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    updateMeta(theme);
    syncToggles();
  }

  function setTheme(theme, persist) {
    apply(theme);
    if (persist !== false) {
      try { localStorage.setItem(THEME_KEY, theme); } catch (e) {}
      document.cookie = THEME_KEY + "=" + theme + "; path=/; max-age=31536000; samesite=Lax";
    }
  }

  function toggle() {
    setTheme(currentTheme() === "light" ? "dark" : "light");
  }

  var api = {
    init: function () {
      // An explicit choice (localStorage OR cookie) must always beat the system
      // preference — a cookie-only choice used to be clobbered on load.
      apply(readStored() || cookieTheme() || systemTheme());

      document.querySelectorAll(".js-theme-toggle").forEach(function (btn) {
        btn.addEventListener("click", toggle);
      });

      // Re-label after a language switch so the switch reads in the new locale.
      global.addEventListener("promptya:langchange", syncToggles);

      if (global.matchMedia) {
        var mq = global.matchMedia("(prefers-color-scheme: light)");
        var onChange = function (e) {
          if (!readStored() && !cookieTheme()) apply(e.matches ? "light" : "dark");
        };
        if (mq.addEventListener) mq.addEventListener("change", onChange);
        else if (mq.addListener) mq.addListener(onChange);
      }
    },
    toggle: toggle,
    set: setTheme,
    get: currentTheme,
  };

  global.PromptyaTheme = api;

  document.addEventListener("DOMContentLoaded", api.init);
})(window);
