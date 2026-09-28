/* Promptya — create page: dynamic media fields per post type.
   The upload zone is swapped when the type changes; the prompt textarea
   doubles as the text "preview" (required for prompt posts, optional
   elsewhere). Client-side presence checks mirror the server's rules. */
(function () {
  "use strict";

  var form = document.getElementById("create-form");
  if (!form) return;

  var typeSelect = document.getElementById("id_post_type");
  var mediaFields = document.getElementById("media-upload-fields");
  var imageField = document.getElementById("image-field");
  var videoField = document.getElementById("video-field");
  var audioField = document.getElementById("audio-field");
  var promptField = document.getElementById("prompt-field");
  var promptTextarea = promptField ? promptField.querySelector("textarea") : null;
  var promptPreviewField = document.getElementById("prompt-preview-field");
  var promptPreviewText = document.getElementById("prompt-preview-text");
  var errorBox = document.getElementById("create-error");

  function zone(field) {
    return field && field.promptyaUpload ? field.promptyaUpload : null;
  }

  function t(key) {
    return window.PromptyaI18n ? window.PromptyaI18n.t(key) : key;
  }

  function showError(messages) {
    if (!errorBox) return;
    errorBox.hidden = false;
    errorBox.textContent = Array.isArray(messages) ? messages.join(" ") : String(messages);
  }

  function updateFields() {
    var type = typeSelect ? typeSelect.value : "prompt";
    var isPrompt = type === "prompt";

    mediaFields.hidden = isPrompt;
    imageField.hidden = type !== "image";
    videoField.hidden = type !== "video";
    audioField.hidden = type !== "audio";

    // Clear any file from the now-hidden zones so a stale video can't ride
    // along under an image post.
    [imageField, videoField, audioField].forEach(function (field) {
      if (field.hidden) {
        var z = zone(field);
        if (z) z.clear();
      }
    });

    // Prompt is the content of a text post; elsewhere it stays optional.
    if (promptTextarea) promptTextarea.required = isPrompt;
    updateTextPreview();
  }

  /* The prompt doubles as the content of a text post, so mirror it into the
     preview frame exactly as the media zones do for files. */
  function updateTextPreview() {
    if (!promptPreviewField || !promptPreviewText || !promptTextarea) return;
    var value = (promptTextarea.value || "").trim();
    promptPreviewField.hidden = !value;
    promptPreviewText.textContent = value;
  }

  if (promptTextarea) promptTextarea.addEventListener("input", updateTextPreview);

  if (typeSelect) {
    typeSelect.addEventListener("change", updateFields);
    updateFields();
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (errorBox) errorBox.hidden = true;

    var type = typeSelect ? typeSelect.value : "prompt";
    var promptText = (form.querySelector('[name="prompt"]').value || "").trim();

    if (type === "prompt" && !promptText) {
      showError([t("prompt_required")]);
      return;
    }

    var fieldByType = { image: imageField, video: videoField, audio: audioField };
    var activeField = fieldByType[type];
    if (activeField) {
      var input = activeField.querySelector('input[type="file"]');
      if (!input || !input.files || !input.files.length) {
        showError([t("media_required_" + type)]);
        return;
      }
      // Re-run client validation on submit (file may have been replaced).
      var problem = window.PromptyaUpload.validate(input.files[0], type);
      if (problem === "bad_type") {
        showError([t("upload_bad_type")]);
        return;
      }
      if (problem === "too_large") {
        showError([t("upload_too_large"), t("upload_max_" + type)]);
        return;
      }
    }

    var fd = new FormData(form);
    // Only submit the field matching the type — no cross-field leftovers.
    ["image", "video", "audio"].forEach(function (name) {
      if (name !== type) fd.delete(name);
    });
    fd.set("category_id", parseInt(fd.get("category_id"), 10) || 0);

    var button = form.querySelector('button[type="submit"]');
    if (button) button.disabled = true;

    fetch("/api/posts/create/", {
      method: "POST",
      headers: { "X-CSRFToken": getCookie("csrftoken") },
      credentials: "same-origin",
      body: fd,
    })
      .then(function (r) {
        return r.ok ? r.json() : r.json().then(function (data) { return Promise.reject({ status: r.status, data: data }); });
      })
      .then(function (data) {
        toast(t("published_toast"));
        setTimeout(function () { window.location.href = "/post/" + data.post.id + "/"; }, 700);
      })
      .catch(function (err) {
        if (button) button.disabled = false;
        var errors = err && err.data && err.data.errors;
        showError(errors ? Object.values(errors) : t("publish_error"));
      });
  });

  function getCookie(name) {
    var row = document.cookie.split("; ").find(function (r) { return r.startsWith(name + "="); });
    return row ? row.split("=")[1] : "";
  }

  function toast(message) {
    var toastEl = document.getElementById("toast");
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add("show");
    setTimeout(function () { return toastEl.classList.remove("show"); }, 2200);
  }
})();
