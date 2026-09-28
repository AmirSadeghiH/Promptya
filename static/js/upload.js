/* Promptya — custom media upload component.
   Replaces bare <input type=file> everywhere on the platform:

     <div data-upload='{"kind":"image"}'></div>

   Provides: click-to-pick, drag & drop, keyboard operation, a live preview
   frame (image inline / video+audio through the platform's own player /
   text rendered as content), remove button, and client-side validation that
   mirrors posts/validation.py — extension whitelist, size cap and MIME
   sanity — before anything is attached to the form.

   The hidden <input> keeps its name, so forms submit exactly as before. */
(function (global) {
  "use strict";

  /* ---- Client mirror of posts/validation.py ---------------------------- */
  var RULES = {
    image: {
      extensions: ["jpg", "jpeg", "png", "webp", "gif"],
      mimes: ["image/jpeg", "image/png", "image/webp", "image/gif"],
      maxMB: 10,
    },
    video: {
      extensions: ["mp4", "webm", "mov"],
      mimes: ["video/mp4", "video/webm", "video/quicktime"],
      maxMB: 200,
    },
    audio: {
      extensions: ["mp3", "wav", "ogg", "m4a"],
      mimes: ["audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave", "audio/ogg", "application/ogg", "audio/mp4", "audio/x-m4a", "audio/m4a"],
      maxMB: 30,
    },
  };

  var ICONS = {
    image:
      '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>',
    video:
      '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m22 8-6 4 6 4V8Z"/><rect x="2" y="6" width="14" height="12" rx="2"/></svg>',
    audio:
      '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
    text:
      '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>',
    upload:
      '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5M12 3v12"/></svg>',
    close:
      '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
  };

  function t(key) {
    return global.PromptyaI18n ? global.PromptyaI18n.t(key) : key;
  }

  function ext(name) {
    var dot = name.lastIndexOf(".");
    return dot === -1 ? "" : name.slice(dot + 1).toLowerCase();
  }

  /* First validation pass — cheap client checks so users get instant
     feedback. The server always re-validates the real bytes. */
  function validate(file, kind) {
    var rule = RULES[kind];
    if (!rule) return "unknown_kind";
    var fileExt = ext(file.name);
    if (rule.extensions.indexOf(fileExt) === -1) return "bad_type";
    if (file.size > rule.maxMB * 1024 * 1024) return "too_large";
    if (file.type && rule.mimes.indexOf(file.type.split(";")[0]) === -1) return "bad_type";
    return null;
  }

  /* ------------------------------------------------------------------ UI */
  var objectUrls = [];

  function previewUrl(file) {
    var url = URL.createObjectURL(file);
    objectUrls.push(url);
    return url;
  }

  function buildPreview(kind, file) {
    var url = previewUrl(file);
    if (kind === "image") {
      var img = document.createElement("img");
      img.className = "up-preview-media";
      img.src = url;
      img.alt = file.name;
      return img;
    }
    if (kind === "video") {
      var video = document.createElement("video");
      video.src = url;
      video.setAttribute("data-media-player", "");
      video.preload = "metadata";
      video.playsInline = true;
      return video;
    }
    if (kind === "audio") {
      var audio = document.createElement("audio");
      audio.src = url;
      audio.setAttribute("data-media-player", "");
      audio.setAttribute("data-title", file.name);
      audio.preload = "metadata";
      return audio;
    }
    return null; // text kind handled separately
  }

  function initUpload(container) {
    var config;
    try {
      config = JSON.parse(container.getAttribute("data-upload") || "{}");
    } catch (e) {
      return;
    }
    var kind = config.kind; // image | video | audio
    var input = container.querySelector('input[type="file"]');
    if (!input || !RULES[kind]) return;

    var frame = document.createElement("div");
    frame.className = "upload-zone";
    frame.tabIndex = 0;
    frame.setAttribute("role", "button");
    frame.setAttribute("aria-label", config.label || t("upload_media"));
    frame.innerHTML =
      '<span class="up-icon">' + (ICONS[kind] || ICONS.upload) + "</span>" +
      '<span class="up-hint" data-i18n="upload_drop">' + t("upload_drop") + "</span>" +
      '<span class="up-formats">' + fmtFormats(kind) + "</span>";

    var previewWrap = document.createElement("div");
    previewWrap.className = "upload-preview";
    previewWrap.hidden = true;

    // Preview sits *above* the field; the zone stays visible underneath as a
    // compact "choose another file" control once a file is attached.
    container.insertBefore(previewWrap, input);
    container.insertBefore(frame, input);
    input.hidden = true;

    var errorBox = document.createElement("div");
    errorBox.className = "upload-error form-error";
    errorBox.hidden = true;
    container.appendChild(errorBox);

    function showError(key, detail) {
      errorBox.hidden = false;
      errorBox.textContent = t(key) + (detail ? " " + detail : "");
    }

    function clearError() {
      errorBox.hidden = true;
      errorBox.textContent = "";
    }

    function clearPreview() {
      previewWrap.innerHTML = "";
      previewWrap.hidden = true;
      frame.hidden = false;
      frame.classList.remove("has-file");
    }

    function showPreview(file) {
      previewWrap.innerHTML = "";
      var head = document.createElement("div");
      head.className = "up-preview-head";
      var name = document.createElement("span");
      name.className = "up-preview-name";
      name.textContent = file.name;
      var size = document.createElement("span");
      size.className = "up-preview-size";
      size.textContent = (file.size / (1024 * 1024)).toFixed(1) + " MB";
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "up-remove";
      remove.setAttribute("aria-label", t("remove_file"));
      remove.innerHTML = ICONS.close;
      remove.addEventListener("click", function () {
        input.value = "";
        clearPreview();
        input.dispatchEvent(new Event("change", { bubbles: true }));
      });
      head.appendChild(name);
      head.appendChild(size);
      head.appendChild(remove);
      previewWrap.appendChild(head);

      var media = buildPreview(kind, file);
      if (media) {
        var holder = document.createElement("div");
        holder.className = "up-preview-frame";
        holder.appendChild(media);
        previewWrap.appendChild(holder);
        // Hand the fresh media element to the platform player.
        if (global.PromptyaPlayer) global.PromptyaPlayer.init();
      }
      previewWrap.hidden = false;
      frame.hidden = false;
      frame.classList.add("has-file");
    }

    function accept(file) {
      if (!file) return;
      clearError();
      var problem = validate(file, kind);
      if (problem === "bad_type") {
        showError("upload_bad_type", "· " + fmtFormats(kind));
        input.value = "";
        clearPreview();
        return;
      }
      if (problem === "too_large") {
        showError("upload_too_large", "· " + t("upload_max_" + kind));
        input.value = "";
        clearPreview();
        return;
      }
      showPreview(file);
    }

    frame.addEventListener("click", function () { input.click(); });
    frame.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        input.click();
      }
    });

    ["dragenter", "dragover"].forEach(function (evt) {
      frame.addEventListener(evt, function (e) {
        e.preventDefault();
        frame.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach(function (evt) {
      frame.addEventListener(evt, function (e) {
        e.preventDefault();
        frame.classList.remove("is-dragging");
      });
    });
    frame.addEventListener("drop", function (e) {
      var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) {
        try {
          var dt = new DataTransfer();
          dt.items.add(file);
          input.files = dt.files;
        } catch (err) { /* older browsers: submit still carries the file via input */ }
      }
      accept(file);
    });

    input.addEventListener("change", function () {
      accept(input.files && input.files[0]);
    });

    // Expose for programmatic use (e.g. clearing on post-type switch).
    container.promptyaUpload = { accept: accept, clear: function () { input.value = ""; clearPreview(); clearError(); } };
  }

  function fmtFormats(kind) {
    var rule = RULES[kind];
    if (!rule) return "";
    var map = { jpg: "JPG", jpeg: "JPG", png: "PNG", webp: "WebP", gif: "GIF", mp4: "MP4", webm: "WebM", mov: "MOV", mp3: "MP3", wav: "WAV", ogg: "OGG", m4a: "M4A" };
    var seen = [];
    rule.extensions.forEach(function (e2) {
      var label = map[e2];
      if (label && seen.indexOf(label) === -1) seen.push(label);
    });
    return seen.join(" · ");
  }

  function initAll() {
    document.querySelectorAll("[data-upload]").forEach(initUpload);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }

  global.PromptyaUpload = { init: initAll, validate: validate, RULES: RULES };
})(window);
