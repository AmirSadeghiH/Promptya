/* Promptya — responsive navigation drawer.
   Makes the hamburger functional on tablet/mobile: animated off-canvas panel,
   scroll lock, focus trap, Escape-to-close, scrim click, and RTL-aware motion.
   Degrades to nothing on desktop, where the sidebar is always visible. */
(function () {
  "use strict";

  var BREAKPOINT = 1024; // matches the sidebar's CSS breakpoint
  var FOCUSABLE =
    'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

  var btn = document.getElementById("menu-btn");
  var closeBtn = document.getElementById("menu-close");
  var drawer = document.getElementById("nav-drawer");
  var scrim = document.getElementById("nav-scrim");
  if (!btn || !drawer || !scrim) return;

  var isOpen = false;
  var lastFocused = null;

  function focusable() {
    return Array.prototype.filter.call(drawer.querySelectorAll(FOCUSABLE), function (el) {
      return el.offsetParent !== null || el === document.activeElement;
    });
  }

  function lockScroll(lock) {
    document.body.classList.toggle("nav-open", lock);
  }

  function open() {
    if (isOpen) return;
    isOpen = true;
    lastFocused = document.activeElement;
    drawer.classList.add("is-open");
    drawer.setAttribute("aria-hidden", "false");
    btn.setAttribute("aria-expanded", "true");
    scrim.hidden = false;
    // Next frame so the transition runs from the off-canvas position.
    requestAnimationFrame(function () {
      scrim.classList.add("is-visible");
    });
    lockScroll(true);
    // `visibility` flips to visible the moment the class lands, so we can try
    // immediately — but frames and timers are both throttled in background or
    // non-compositing pages, so do not depend on any single one of them. Each
    // attempt yields to focus that is already inside the panel.
    focusFirst();
    requestAnimationFrame(focusFirst);
    setTimeout(focusFirst, 0);
  }

  function focusFirst() {
    if (!isOpen) return;
    if (drawer.contains(document.activeElement)) return;
    var first = closeBtn || focusable()[0];
    if (first) first.focus();
  }

  function close(returnFocus) {
    if (!isOpen) return;
    isOpen = false;
    drawer.classList.remove("is-open");
    drawer.setAttribute("aria-hidden", "true");
    btn.setAttribute("aria-expanded", "false");
    scrim.classList.remove("is-visible");
    lockScroll(false);
    window.setTimeout(function () {
      if (!isOpen) scrim.hidden = true;
    }, 260);
    if (returnFocus !== false) {
      var back = lastFocused && document.contains(lastFocused) ? lastFocused : btn;
      back.focus();
    }
  }

  btn.addEventListener("click", function () {
    isOpen ? close() : open();
  });
  if (closeBtn) closeBtn.addEventListener("click", function () { close(); });
  scrim.addEventListener("click", function () { close(); });

  // Tapping a link inside the drawer should close it before navigating.
  drawer.addEventListener("click", function (e) {
    if (e.target.closest("a[href]")) close(false);
  });

  document.addEventListener("keydown", function (e) {
    if (!isOpen) return;
    if (e.key === "Escape") {
      e.preventDefault();
      close();
      return;
    }
    if (e.key !== "Tab") return;
    // Focus trap: keep Tab inside the open drawer.
    var items = focusable();
    if (!items.length) return;
    var first = items[0];
    var last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  });

  // Leaving the small-screen range must never strand the page with a locked body.
  function onResize() {
    if (window.innerWidth > BREAKPOINT && isOpen) close(false);
  }
  window.addEventListener("resize", onResize);
  var mq = window.matchMedia("(min-width: " + (BREAKPOINT + 1) + "px)");
  if (mq.addEventListener) mq.addEventListener("change", onResize);
  else if (mq.addListener) mq.addListener(onResize);

  window.PromptyaNav = { open: open, close: close, isOpen: function () { return isOpen; } };
})();
