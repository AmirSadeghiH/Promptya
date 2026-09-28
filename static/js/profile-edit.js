/* Promptya — profile edit page logic */
(function () {
  "use strict";

  const CSRF = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1];

  const toastEl = document.getElementById("toast");
  let toastTimer = null;
  function toast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2600);
  }

  function t(key) {
    return window.PromptyaI18n ? window.PromptyaI18n.t(key) : key;
  }

  const form = document.getElementById("profile-edit-form");
  if (!form) return;

  /* ---------------- Avatar ---------------- */
  const avatarInput = document.getElementById("avatar-input");
  const avatarImg = document.getElementById("avatar-img");
  const avatarFallback = document.getElementById("avatar-fallback");
  const avatarError = document.getElementById("avatar-error");
  const removeBtn = document.getElementById("avatar-remove");

  function showAvatarError(msg) {
    if (!avatarError) return;
    avatarError.hidden = !msg;
    avatarError.textContent = msg || "";
  }

  function openPicker() {
    const zone = document.getElementById("avatar-upload");
    const frame = zone && zone.querySelector(".upload-zone");
    if (frame) frame.click();
    else if (avatarInput) avatarInput.click();
  }

  ["avatar-btn", "avatar-pick"].forEach((id) => {
    const btn = document.getElementById(id);
    if (btn) btn.addEventListener("click", openPicker);
  });

  if (avatarInput) {
    avatarInput.addEventListener("change", () => {
      const file = avatarInput.files && avatarInput.files[0];
      showAvatarError("");
      if (!file) return;
      // Client-side mirror of the server's image rules (posts/validation.py):
      // extension whitelist, size cap, MIME sanity.
      const problem =
        window.PromptyaUpload && window.PromptyaUpload.validate
          ? window.PromptyaUpload.validate(file, "image")
          : null;
      if (problem === "bad_type") {
        showAvatarError(t("invalid_image_type"));
        avatarInput.value = "";
        return;
      }
      if (problem === "too_large") {
        showAvatarError(t("image_too_large"));
        avatarInput.value = "";
        return;
      }
      const url = URL.createObjectURL(file);
      if (avatarImg) {
        avatarImg.src = url;
      } else if (avatarFallback) {
        const img = document.createElement("img");
        img.id = "avatar-img";
        img.src = url;
        img.alt = "";
        avatarFallback.replaceWith(img);
      }
      // Persist the avatar immediately so the preview matches the site.
      saveProfile(new FormData(form));
    });
  }
  if (removeBtn) {
    removeBtn.addEventListener("click", () => {
      const fd = new FormData(form);
      fd.set("remove_picture", "1");
      if (avatarImg) avatarImg.remove();
      if (avatarInput) avatarInput.value = "";
      const zone = document.getElementById("avatar-upload");
      if (zone && zone.promptyaUpload) zone.promptyaUpload.clear();
      if (!document.getElementById("avatar-img")) {
        const wrap = document.getElementById("avatar-preview");
        if (wrap) {
          const span = document.createElement("span");
          span.id = "avatar-fallback";
          const name = document.getElementById("id_display_name");
          span.textContent = ((name && name.value) || window.PROMPTYA_PROFILE_USERNAME || "?")
            .charAt(0)
            .toUpperCase();
          wrap.appendChild(span);
        }
      }
      saveProfile(fd);
    });
  }

  /* ---------------- Bio counter ---------------- */
  const bioField = document.getElementById("id_biography");
  const bioCount = document.getElementById("bio-count");
  if (bioField && bioCount) {
    bioField.addEventListener("input", () => {
      bioCount.textContent = String(bioField.value.length);
    });
  }

  /* ---------------- Password strength ---------------- */
  const newPassword = document.getElementById("id_new_password");
  const bars = document.querySelectorAll("#pw-strength .pw-bar");
  const pwLabel = document.getElementById("pw-label");
  const LABEL_KEYS = ["pw_weak", "pw_fair", "pw_good", "pw_strong"];

  function scorePassword(value) {
    if (!value) return -1;
    let score = 0;
    if (value.length >= 8) score++;
    if (value.length >= 12) score++;
    if (/[a-z]/.test(value) && /[A-Z]/.test(value)) score++;
    if (/\d/.test(value) && /[^A-Za-z0-9]/.test(value)) score++;
    return Math.min(score, 4);
  }

  if (newPassword) {
    newPassword.addEventListener("input", () => {
      const score = scorePassword(newPassword.value);
      bars.forEach((bar, index) => {
        bar.classList.toggle("on", score >= 0 && index < Math.max(score, 0));
        bar.dataset.level = String(Math.max(score, 0));
      });
      if (pwLabel) {
        pwLabel.textContent = score < 0 ? "" : t(LABEL_KEYS[Math.max(score - 1, 0)]);
      }
    });
  }

  /* ---------------- Save profile ---------------- */
  const profileError = document.getElementById("profile-error");
  const saveState = document.getElementById("save-state");
  const saveButton = document.getElementById("profile-save");

  function showError(box, messages) {
    if (!box) return;
    box.hidden = false;
    box.textContent = Array.isArray(messages) ? messages.join(" ") : String(messages);
  }

  function saveProfile(formData) {
    if (saveButton) saveButton.disabled = true;
    if (saveState) saveState.textContent = t("saving");
    return fetch("/api/me/profile/", {
      method: "POST",
      headers: { "X-CSRFToken": CSRF },
      credentials: "same-origin",
      body: formData,
    })
      .then((r) =>
        r.ok ? r.json() : r.json().then((data) => Promise.reject({ status: r.status, data }))
      )
      .then((data) => {
        if (saveState) saveState.textContent = t("saved_check");
        toast(t("profile_saved"));
        const username = data.user && data.user.username;
        if (
          username &&
          username !== window.PROMPTYA_PROFILE_USERNAME &&
          !formData.get("profile_picture") &&
          formData.get("remove_picture") !== "1"
        ) {
          // Username changed — reflect it in the URL without losing state.
          window.history.replaceState(null, "", `/settings/profile/`);
          window.PROMPTYA_PROFILE_USERNAME = username;
        }
        return data;
      })
      .catch((err) => {
        if (saveState) saveState.textContent = "";
        const errors = (err && err.data && err.data.errors) || null;
        if (errors) {
          if (errors.profile_picture && avatarError) showAvatarError(errors.profile_picture);
          showError(profileError, Object.values(errors));
        } else {
          showError(profileError, t("something_wrong"));
        }
        throw err;
      })
      .finally(() => {
        if (saveButton) saveButton.disabled = false;
        setTimeout(() => {
          if (saveState) saveState.textContent = "";
        }, 2500);
      });
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    profileError.hidden = true;
    saveProfile(new FormData(form));
  });

  /* ---------------- Change password ---------------- */
  const passwordSave = document.getElementById("password-save");
  const passwordError = document.getElementById("password-error");

  if (passwordSave) {
    passwordSave.addEventListener("click", () => {
      passwordError.hidden = true;
      const current = document.getElementById("id_current_password").value;
      const next = document.getElementById("id_new_password").value;
      const confirm = document.getElementById("id_confirm_password").value;

      if (!current || !next) {
        showError(passwordError, t("fill_password_fields"));
        return;
      }
      if (next !== confirm) {
        showError(passwordError, t("passwords_mismatch"));
        return;
      }

      fetch("/api/me/password/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": CSRF,
        },
        credentials: "same-origin",
        body: JSON.stringify({ current_password: current, new_password: next }),
      })
        .then((r) =>
          r.ok ? r.json() : r.json().then((data) => Promise.reject({ status: r.status, data }))
        )
        .then(() => {
          toast(t("password_changed"));
          ["id_current_password", "id_new_password", "id_confirm_password"].forEach((id) => {
            const input = document.getElementById(id);
            if (input) input.value = "";
          });
          if (pwLabel) pwLabel.textContent = "";
          bars.forEach((bar) => bar.classList.remove("on"));
        })
        .catch((err) => {
          const errors = (err && err.data && err.data.errors) || null;
          showError(passwordError, errors ? Object.values(errors) : t("something_wrong"));
        });
    });
  }
})();
