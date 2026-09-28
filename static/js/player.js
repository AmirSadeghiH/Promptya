/* Promptya media player — the platform's own video & audio player.
   The browser's native chrome is never shown: every control, the scrubber,
   the buffered range, the volume, the speed menu and fullscreen are ours.

   Declarative:
     <video src="…" data-media-player>            → video player
     <audio src="…" data-media-player data-title="…"> → audio player card

   Features: RTL-aware seek and progress, flicker-free scrubbing while
   playing, intrinsic aspect ratio (portrait video is not force-letterboxed),
   one-at-a-time playback, buffered range, loading/error states, idle control
   auto-hide, keyboard shortcuts, persisted volume, and Picture-in-Picture. */
(function (global) {
  "use strict";

  var FALLBACK = {
    en: {
      player_play: "Play",
      player_pause: "Pause",
      player_seek: "Seek",
      player_mute: "Mute",
      player_unmute: "Unmute",
      player_volume: "Volume",
      player_fullscreen: "Fullscreen",
      player_pip: "Picture in picture",
      player_speed: "Playback speed",
      player_normal: "Normal",
      player_error: "This media could not be loaded.",
    },
    fa: {
      player_play: "پخش",
      player_pause: "توقف",
      player_seek: "جابه‌جایی",
      player_mute: "بی‌صدا",
      player_unmute: "با صدا",
      player_volume: "صدا",
      player_fullscreen: "تمام‌صفحه",
      player_pip: "تصویر در تصویر",
      player_speed: "سرعت پخش",
      player_normal: "معمولی",
      player_error: "بارگیری این رسانه ممکن نشد.",
    },
  };

  function t(key) {
    var i18n = global.PromptyaI18n;
    if (i18n) {
      var value = i18n.t(key);
      if (value && value !== key) return value;
    }
    var lang = document.documentElement.getAttribute("lang") === "fa" ? "fa" : "en";
    return FALLBACK[lang][key] || FALLBACK.en[key];
  }

  function fmtTime(seconds) {
    if (!isFinite(seconds) || seconds < 0) seconds = 0;
    seconds = Math.floor(seconds);
    var h = Math.floor(seconds / 3600);
    var m = Math.floor((seconds % 3600) / 60);
    var s = seconds % 60;
    if (h) return h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
    return m + ":" + String(s).padStart(2, "0");
  }

  var ICON = {
    play: '<path d="M8 5.5v13l11-6.5z"/>',
    pause: '<path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/>',
    replay: '<path d="M12 5V1L7 6l5 5V7a5 5 0 1 1-5 5H5a7 7 0 1 0 7-7z"/>',
    volume:
      '<path d="M3 10v4h4l5 4V6L7 10H3z"/><path d="M16 8.5a5 5 0 0 1 0 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    muted:
      '<path d="M3 10v4h4l5 4V6L7 10H3z"/><path d="m16 9 5 6M21 9l-5 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
    fullscreen:
      '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    exitscreen:
      '<path d="M9 4v5H4M15 4v5h5M15 20v-5h5M9 20v-5H4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    pip: '<path d="M3 5h18v14H3z" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 12h7v6h-7z" fill="currentColor"/>',
  };

  function icon(path, filled) {
    return (
      '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false" fill="' +
      (filled ? "currentColor" : "none") +
      '" stroke="none">' +
      path +
      "</svg>"
    );
  }

  function el(tag, className, html) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (html != null) node.innerHTML = html;
    return node;
  }

  /* ---------------------------------------------------------------- volume */
  var VOL_KEY = "promptya-volume";

  function readVolume() {
    try {
      var v = parseFloat(localStorage.getItem(VOL_KEY));
      if (isFinite(v) && v >= 0 && v <= 1) return v;
    } catch (e) {}
    return 1;
  }

  function writeVolume(v) {
    try { localStorage.setItem(VOL_KEY, String(v)); } catch (e) {}
  }

  /* ---------------------------------------------------------------- controls */
  function buildControls(media, kind) {
    var root = el("div", "pl-controls" + (kind === "audio" ? " pl-audio-controls" : ""));

    root.innerHTML =
      '<button class="pl-btn pl-play" type="button" aria-label="' + t("player_play") + '">' +
        icon(ICON.play, true) +
      "</button>" +
      '<span class="pl-time pl-current" aria-hidden="true">0:00</span>' +
      '<div class="pl-progress" role="slider" tabindex="0" aria-label="' + t("player_seek") + '"' +
        ' aria-valuemin="0" aria-valuemax="0" aria-valuenow="0" aria-valuetext="0:00">' +
        '<div class="pl-track"><div class="pl-buffer"></div><div class="pl-fill"></div></div>' +
        '<div class="pl-knob"></div>' +
      "</div>" +
      '<span class="pl-time pl-duration" aria-hidden="true">0:00</span>' +
      (kind === "video"
        ? '<button class="pl-btn pl-speed" type="button" aria-label="' + t("player_speed") +
            '" title="' + t("player_speed") + '">1×</button>'
        : "") +
      (kind === "video" && global.document.pictureInPictureEnabled
        ? '<button class="pl-btn pl-pip" type="button" aria-label="' + t("player_pip") + '" title="' +
            t("player_pip") + '">' + icon(ICON.pip, true) + "</button>"
        : "") +
      '<button class="pl-btn pl-mute" type="button" aria-label="' + t("player_mute") + '">' +
        icon(ICON.volume, true) +
      "</button>" +
      '<input class="pl-volume" type="range" min="0" max="1" step="0.05" value="' + readVolume() +
        '" aria-label="' + t("player_volume") + '">' +
      (kind === "video"
        ? '<button class="pl-btn pl-fs" type="button" aria-label="' + t("player_fullscreen") +
            '" title="' + t("player_fullscreen") + '">' + icon(ICON.fullscreen, true) + "</button>"
        : "");

    var playBtn = root.querySelector(".pl-play");
    var currentEl = root.querySelector(".pl-current");
    var durationEl = root.querySelector(".pl-duration");
    var progress = root.querySelector(".pl-progress");
    var fill = root.querySelector(".pl-fill");
    var buffer = root.querySelector(".pl-buffer");
    var muteBtn = root.querySelector(".pl-mute");
    var volume = root.querySelector(".pl-volume");
    var fsBtn = root.querySelector(".pl-fs");
    var pipBtn = root.querySelector(".pl-pip");
    var speedBtn = root.querySelector(".pl-speed");

    var scrubbing = false;
    var scrubRaf = null;
    var pendingX = null;

    /* ---------- progress ---------- */
    function duration() {
      return isFinite(media.duration) && media.duration > 0 ? media.duration : 0;
    }

    function paint(ratio) {
      ratio = Math.min(Math.max(ratio, 0), 1);
      fill.style.width = (ratio * 100).toFixed(3) + "%";
      knob.style.insetInlineStart = (ratio * 100).toFixed(3) + "%";
    }
    var knob = root.querySelector(".pl-knob");

    function paintBuffer() {
      if (!duration()) return;
      try {
        var end = media.buffered.end(media.buffered.length - 1);
        buffer.style.width = Math.min((end / duration()) * 100, 100).toFixed(2) + "%";
      } catch (e) {}
    }

    function syncAria(ratio) {
      var d = duration();
      progress.setAttribute("aria-valuemax", Math.round(d));
      progress.setAttribute("aria-valuenow", Math.round(media.currentTime || 0));
      progress.setAttribute(
        "aria-valuetext",
        fmtTime(media.currentTime) + " / " + fmtTime(d)
      );
    }

    /* ---------- play / pause ---------- */
    function togglePlay() {
      if (media.paused) {
        var p = media.play();
        if (p && p.catch) p.catch(function () {});
      } else {
        media.pause();
      }
    }

    function markPlaying(playing) {
      if (playing) {
        playBtn.innerHTML = icon(ICON.pause, true);
        playBtn.setAttribute("aria-label", t("player_pause"));
      } else {
        playBtn.innerHTML = icon(ICON.play, true);
        playBtn.setAttribute("aria-label", t("player_play"));
      }
      root.classList.toggle("is-playing", playing);
    }

    media.addEventListener("play", function () {
      markPlaying(true);
      // Social-network behaviour: starting one clip stops everything else.
      document.querySelectorAll("audio, video").forEach(function (other) {
        if (other !== media && !other.paused) other.pause();
      });
    });
    media.addEventListener("pause", function () { markPlaying(false); });
    media.addEventListener("ended", function () {
      playBtn.innerHTML = icon(ICON.replay, true);
      playBtn.setAttribute("aria-label", t("player_play"));
      root.classList.remove("is-playing");
      paint(1);
      currentEl.textContent = fmtTime(duration());
      syncAria(1);
    });

    media.addEventListener("timeupdate", function () {
      if (scrubbing) return;
      var d = duration();
      var ratio = d ? media.currentTime / d : 0;
      paint(ratio);
      currentEl.textContent = fmtTime(media.currentTime);
      syncAria(ratio);
      paintBuffer();
    });
    media.addEventListener("progress", paintBuffer);
    media.addEventListener("durationchange", function () {
      durationEl.textContent = fmtTime(duration());
      syncAria(duration() ? media.currentTime / duration() : 0);
    });
    media.addEventListener("loadedmetadata", function () {
      durationEl.textContent = fmtTime(duration());
      // Adopt the clip's own shape — portrait and square video must not be
      // force-fitted into a 16:9 box.
      if (kind === "video") {
        var w = media.videoWidth;
        var h = media.videoHeight;
        var wrapper = media.closest(".pl-wrapper");
        if (wrapper && w && h) {
          var ratio = Math.min(Math.max(w / h, 0.42), 2.6);
          wrapper.style.setProperty("--pl-ratio", ratio.toFixed(4));
          wrapper.classList.toggle("is-portrait", ratio < 1);
        }
      }
      paint(0);
      syncAria(0);
    });

    playBtn.addEventListener("click", togglePlay);

    /* ---------- scrubbing ----------
       We never pause while dragging: pausing on pointerdown made the clip
       visibly stutter and could drop playback on iOS. */
    function flushSeek() {
      scrubRaf = null;
      if (pendingX == null || !duration()) return;
      var rect = progress.getBoundingClientRect();
      var ratio = (pendingX - rect.left) / rect.width;
      if (document.documentElement.dir === "rtl") ratio = 1 - ratio;
      ratio = Math.min(Math.max(ratio, 0), 1);
      pendingX = null;
      media.currentTime = ratio * duration();
      paint(ratio);
      currentEl.textContent = fmtTime(media.currentTime);
      syncAria(ratio);
    }

    function queueSeek(clientX) {
      pendingX = clientX;
      if (scrubRaf == null) scrubRaf = requestAnimationFrame(flushSeek);
    }

    progress.addEventListener("pointerdown", function (e) {
      scrubbing = true;
      progress.setPointerCapture(e.pointerId);
      progress.classList.add("is-scrubbing");
      queueSeek(e.clientX);
      e.preventDefault();
    });
    progress.addEventListener("pointermove", function (e) {
      if (scrubbing) queueSeek(e.clientX);
    });
    function endScrub() {
      if (!scrubbing) return;
      scrubbing = false;
      progress.classList.remove("is-scrubbing");
      flushSeek();
    }
    progress.addEventListener("pointerup", endScrub);
    progress.addEventListener("pointercancel", endScrub);

    /* ---------- keyboard ---------- */
    progress.addEventListener("keydown", function (e) {
      var d = duration();
      if (!d) return;
      var rtl = document.documentElement.dir === "rtl";
      var step = e.shiftKey ? 30 : 5;
      var delta = 0;
      switch (e.key) {
        case "ArrowRight": delta = rtl ? -step : step; break;
        case "ArrowLeft": delta = rtl ? step : -step; break;
        case "ArrowUp": delta = step; break;
        case "ArrowDown": delta = -step; break;
        case "PageUp": delta = 30; break;
        case "PageDown": delta = -30; break;
        case "Home": delta = -media.currentTime; break;
        case "End": delta = d - media.currentTime; break;
        case " ":
        case "Enter":
          e.preventDefault();
          togglePlay();
          return;
        default:
          return;
      }
      e.preventDefault();
      media.currentTime = Math.min(Math.max(media.currentTime + delta, 0), d);
      paint(media.currentTime / d);
      currentEl.textContent = fmtTime(media.currentTime);
      syncAria(media.currentTime / d);
    });

    /* ---------- volume ---------- */
    function syncMuteUI() {
      var silent = media.muted || media.volume === 0;
      muteBtn.innerHTML = icon(silent ? ICON.muted : ICON.volume, true);
      muteBtn.setAttribute("aria-label", t(silent ? "player_unmute" : "player_mute"));
      volume.value = silent ? 0 : media.volume;
    }
    muteBtn.addEventListener("click", function () {
      media.muted = !media.muted;
      if (!media.muted && media.volume === 0) media.volume = readVolume() || 1;
      syncMuteUI();
    });
    volume.addEventListener("input", function () {
      var v = Number(volume.value);
      media.volume = v;
      media.muted = v === 0;
      writeVolume(v);
      syncMuteUI();
    });
    media.addEventListener("volumechange", syncMuteUI);

    /* ---------- playback speed ---------- */
    /* Cycles on click: a popover would be clipped by the media frame's own
       overflow, and this stays usable with one thumb on a phone. */
    if (speedBtn) {
      var SPEEDS = [1, 1.25, 1.5, 2, 0.5];
      speedBtn.addEventListener("click", function () {
        var index = SPEEDS.indexOf(media.playbackRate);
        var rate = SPEEDS[(index + 1) % SPEEDS.length];
        media.playbackRate = rate;
        speedBtn.textContent = rate + "×";
      });
    }

    /* ---------- picture in picture ---------- */
    if (pipBtn) {
      pipBtn.addEventListener("click", function () {
        try {
          if (document.pictureInPictureElement) document.exitPictureInPicture();
          else if (media.requestPictureInPicture) media.requestPictureInPicture();
        } catch (e) {}
      });
    }

    /* ---------- fullscreen ---------- */
    function fullscreenTarget() {
      return media.closest(".pl-wrapper") || media;
    }
    function syncFsIcon() {
      if (!fsBtn) return;
      var active =
        document.fullscreenElement === fullscreenTarget() || media.webkitDisplayingFullscreen;
      fsBtn.innerHTML = icon(active ? ICON.exitscreen : ICON.fullscreen, true);
      fsBtn.setAttribute("aria-label", t("player_fullscreen"));
    }
    if (fsBtn) {
      fsBtn.addEventListener("click", function () {
        var target = fullscreenTarget();
        if (document.fullscreenElement) {
          (document.exitFullscreen || document.webkitExitFullscreen || function () {}).call(document);
        } else if (target.requestFullscreen) {
          target.requestFullscreen().catch(function () {});
        } else if (target.webkitRequestFullscreen) {
          target.webkitRequestFullscreen();
        } else if (media.webkitEnterFullscreen) {
          media.webkitEnterFullscreen(); // iOS Safari fallback
        }
      });
      document.addEventListener("fullscreenchange", syncFsIcon);
      media.addEventListener("webkitbeginfullscreen", syncFsIcon);
      media.addEventListener("webkitendfullscreen", syncFsIcon);
    }

    /* ---------- language switch ---------- */
    function refreshLabels() {
      playBtn.setAttribute("aria-label", t(media.paused ? "player_play" : "player_pause"));
      progress.setAttribute("aria-label", t("player_seek"));
      muteBtn.setAttribute("aria-label", t(media.muted || media.volume === 0 ? "player_unmute" : "player_mute"));
      volume.setAttribute("aria-label", t("player_volume"));
      if (speedBtn) {
        speedBtn.setAttribute("aria-label", t("player_speed"));
        speedBtn.setAttribute("title", t("player_speed"));
      }
      if (fsBtn) fsBtn.setAttribute("title", t("player_fullscreen"));
      if (pipBtn) pipBtn.setAttribute("aria-label", t("player_pip"));
    }
    global.addEventListener("promptya:langchange", refreshLabels);

    /* ---------- initial state ---------- */
    markPlaying(!media.paused);
    media.volume = readVolume();
    syncMuteUI();
    durationEl.textContent = fmtTime(duration());
    paint(0);
    syncAria(0);
    syncFsIcon();

    return root;
  }

  /* ------------------------------------------------------------- wrappers */
  function addStateOverlays(media, wrapper) {
    var spinner = el("div", "pl-spinner");
    spinner.hidden = true;
    spinner.setAttribute("aria-hidden", "true");
    wrapper.appendChild(spinner);

    var errorBox = el("div", "pl-error", t("player_error"));
    errorBox.hidden = true;
    errorBox.setAttribute("role", "alert");
    wrapper.appendChild(errorBox);

    media.addEventListener("waiting", function () { spinner.hidden = false; });
    media.addEventListener("seeking", function () { spinner.hidden = false; });
    ["playing", "canplay", "canplaythrough", "seeked"].forEach(function (evt) {
      media.addEventListener(evt, function () { spinner.hidden = true; });
    });
    media.addEventListener("error", function () {
      spinner.hidden = true;
      if (media.error) errorBox.hidden = false;
    });
    media.addEventListener("loadstart", function () { errorBox.hidden = true; });
    media.addEventListener("emptied", function () { errorBox.hidden = true; });
  }

  function upgrade(media, kind) {
    if (media.dataset.playerReady === "1") return;
    media.dataset.playerReady = "1";
    media.removeAttribute("controls"); // native chrome must never appear
    media.classList.add("pl-media");

    if (kind === "video") {
      media.setAttribute("playsinline", "");
      media.setAttribute("controlslist", "nodownload noplaybackrate noremoteplayback");
      media.setAttribute("disablepictureinpicture", ""); // we draw our own PiP
      var wrapper = el("div", "pl-wrapper pl-video");
      media.parentNode.insertBefore(wrapper, media);
      wrapper.appendChild(media);

      // Big centre play affordance — decorative; the wrapper handles the click
      // so a paused clip can be resumed from anywhere on the surface.
      var overlay = el("div", "pl-overlay", icon(ICON.play, true));
      overlay.setAttribute("aria-hidden", "true");
      wrapper.appendChild(overlay);
      wrapper.appendChild(buildControls(media, "video"));
      addStateOverlays(media, wrapper);

      function setOverlay() {
        overlay.classList.toggle("is-hidden", !media.paused);
      }
      media.addEventListener("play", setOverlay);
      media.addEventListener("pause", setOverlay);
      media.addEventListener("ended", setOverlay);
      setOverlay();

      wrapper.addEventListener("click", function (e) {
        if (e.target.closest(".pl-controls")) return;
        if (media.paused) {
          var p = media.play();
          if (p && p.catch) p.catch(function () {});
        } else {
          media.pause();
        }
      });
      wrapper.addEventListener("dblclick", function (e) {
        if (e.target.closest(".pl-controls")) return;
        var fs = wrapper.querySelector(".pl-fs");
        if (fs) fs.click();
      });

      // Auto-hide the controls (and cursor) while the clip plays.
      var hideTimer = null;
      function poke() {
        wrapper.classList.remove("pl-idle");
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () {
          if (!media.paused) wrapper.classList.add("pl-idle");
        }, 2600);
      }
      ["pointermove", "pointerdown", "focusin"].forEach(function (evt) {
        wrapper.addEventListener(evt, poke, { passive: true });
      });
      wrapper.addEventListener("pointerleave", function () {
        if (!media.paused) wrapper.classList.add("pl-idle");
      });
      media.addEventListener("play", poke);
      media.addEventListener("pause", function () {
        clearTimeout(hideTimer);
        wrapper.classList.remove("pl-idle");
      });
    } else {
      var card = el("div", "pl-wrapper pl-audio");
      var title = media.dataset.title || "";
      var subtitle = media.dataset.subtitle || "";
      var head = el(
        "div",
        "pl-audio-head",
        '<span class="pl-audio-meta">' +
          (title ? '<span class="pl-audio-title"></span>' : "") +
          (subtitle ? '<span class="pl-audio-sub"></span>' : "") +
          "</span>" +
          '<span class="pl-eq" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span>'
      );
      // Set text via textContent so a post title can never inject markup.
      var titleEl = head.querySelector(".pl-audio-title");
      if (titleEl) titleEl.textContent = title;
      var subEl = head.querySelector(".pl-audio-sub");
      if (subEl) subEl.textContent = subtitle;
      card.appendChild(head);
      media.parentNode.insertBefore(card, media);
      card.appendChild(media);
      card.appendChild(buildControls(media, "audio"));
      addStateOverlays(media, card);
    }
  }

  function init() {
    document.querySelectorAll("audio[data-media-player]").forEach(function (node) {
      upgrade(node, "audio");
    });
    document
      .querySelectorAll("video[data-media-player], video[controls]")
      .forEach(function (node) {
        upgrade(node, "video");
      });
  }

  /* Deferred scripts execute before DOMContentLoaded, so binding there lets
     i18n.js initialise first and guarantees correct labels on first paint. */
  if (document.readyState === "loading" || document.readyState === "interactive") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  global.PromptyaPlayer = { init: init };
})(window);
