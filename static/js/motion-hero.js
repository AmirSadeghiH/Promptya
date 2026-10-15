/* Promptya — home hero behaviour.
   Extracted from the inline <script> that used to live inside
   templates/web/motion-graphic.html (along with a full <html>/<head>/<body>).

   The Persian strings that script used to substitute are gone with it: every
   label in the hero now carries data-i18n and is rendered server-side from
   web/i18n_strings.py, then re-applied by i18n.js. A second, private copy of the
   translations was how "mh_caption" ended up untranslated while "mh_pause"
   appeared on screen as its own key name. */
(function () {
  "use strict";

  /* Pause / resume, reduced motion, and stop-when-offscreen. */
  document.querySelectorAll("[data-motion-hero]").forEach(function (hero) {
    var toggle = hero.querySelector("[data-mh-toggle]");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var paused = hero.classList.toggle("is-paused");
        toggle.setAttribute("aria-pressed", String(paused));
      });
    }

    /* prefers-reduced-motion: freeze on the first frame rather than hide, so the
       panel still reads as a finished composition. CSS does the actual work. */
    var mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    var applyStill = function () {
      hero.classList.toggle("is-still", mq.matches);
    };
    applyStill();
    if (mq.addEventListener) mq.addEventListener("change", applyStill);
    else if (mq.addListener) mq.addListener(applyStill);

    /* Scrolled out of view: park the animation so it stops costing CPU. A
       24-keyframe loop is cheap to composite but not free on a phone. */
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        hero.classList.toggle("is-offscreen", !entries[0].isIntersecting);
      }).observe(hero);
    }
  });
})();
