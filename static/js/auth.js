/* Promptya standalone auth pages: password reveal, strength meter, and a
   double-submit guard. Progressive enhancement only: every form works without it. */
(function () {
  "use strict";

  function t(key) {
    return window.PromptyaI18n ? window.PromptyaI18n.t(key) : key;
  }

  function setupReveal() {
    document.querySelectorAll(".field-toggle").forEach(function (btn) {
      var input = btn.parentElement.querySelector(".field-input");
      if (!input) return;
      btn.setAttribute("aria-label", t("show_password"));
      btn.addEventListener("click", function () {
        var reveal = input.type === "password";
        input.type = reveal ? "text" : "password";
        btn.setAttribute("aria-pressed", reveal ? "true" : "false");
        btn.setAttribute("aria-label", t(reveal ? "hide_password" : "show_password"));
      });
    });
  }

  function setupStrength() {
    var input = document.getElementById("signup-password");
    var meter = document.querySelector(".password-strength");
    if (!input || !meter) return;
    var bars = meter.querySelectorAll(".strength-bars span");
    var label = meter.querySelector(".strength-label");
    var names = ["", "pw_weak", "pw_fair", "pw_good", "pw_strong"];

    input.addEventListener("input", function () {
      var v = input.value;
      var score = 0;
      if (v.length >= 8) score++;
      if (v.length >= 12) score++;
      if (/[a-z]/.test(v) && /[A-Z]/.test(v)) score++;
      if (/[0-9]/.test(v)) score++;
      if (/[^A-Za-z0-9]/.test(v)) score++;
      var level = v ? Math.min(4, Math.max(1, Math.ceil((score * 4) / 5))) : 0;
      meter.setAttribute("data-level", String(level));
      bars.forEach(function (bar, i) {
        bar.classList.toggle("is-on", i < level);
      });
      label.textContent = level ? t(names[level]) : "";
    });
  }

  function setupSubmitGuard() {
    document.querySelectorAll(".auth-form").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (form.getAttribute("data-busy") === "1") {
          event.preventDefault();
          return;
        }
        form.setAttribute("data-busy", "1");
        var btn = form.querySelector(".auth-submit");
        if (btn) {
          btn.classList.add("is-loading");
          btn.disabled = true;
        }
      });
    });
    // Back/forward cache can restore a page whose button is still disabled.
    window.addEventListener("pageshow", function (event) {
      if (!event.persisted) return;
      document.querySelectorAll(".auth-form").forEach(function (form) {
        form.removeAttribute("data-busy");
        var btn = form.querySelector(".auth-submit");
        if (btn) {
          btn.classList.remove("is-loading");
          btn.disabled = false;
        }
      });
    });
  }

  function setupVerifyCode() {
    var input = document.getElementById("verify-code");
    if (!input) return;
    var form = input.closest(".auth-form");
    if (!form) return;

    // Keep the field to 6 digits and submit automatically once a complete
    // code is present — this also covers the browser's one-time-code
    // autofill. The shared double-submit guard still applies (requestSubmit
    // fires the normal submit handler).
    input.addEventListener("input", function () {
      var cleaned = input.value.replace(/[^0-9]/g, "").slice(0, 6);
      if (cleaned !== input.value) input.value = cleaned;
      if (cleaned.length === 6 && form.getAttribute("data-busy") !== "1") {
        form.requestSubmit();
      }
    });

    // Resend cooldown, anchored to the server-rendered expiry. Absent
    // attribute = always enabled (fallback mode, or the server already
    // allows a resend). The server re-checks everything, so this is
    // cosmetic.
    var resend = document.getElementById("verify-resend");
    if (!resend || !resend.hasAttribute("data-resend-at")) return;
    var resendAt = parseInt(resend.getAttribute("data-resend-at"), 10) * 1000;
    var label = resend.querySelector(".auth-submit-label");

    function tick() {
      var remaining = Math.ceil((resendAt - Date.now()) / 1000);
      if (remaining > 0) {
        resend.disabled = true;
        if (label) label.textContent = t("verify_resend_cooldown").replace("{n}", String(remaining));
      } else {
        resend.disabled = false;
        if (label) label.textContent = t("verify_resend_btn");
      }
    }
    tick();
    setInterval(function () {
      tick();
      if (!resend.disabled) clearInterval(tick);
    }, 1000);
  }

  // Runs after i18n.js has initialised the language on DOMContentLoaded.
  document.addEventListener("DOMContentLoaded", function () {
    setupReveal();
    setupStrength();
    setupSubmitGuard();
    setupVerifyCode();
  });
})();
