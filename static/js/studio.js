/* Promptly — AI studio.
   Renders four things from one source of truth: the credit wallet, the result
   canvas, the shelf of the user's own generations, and the reward challenges.
   The server seeds all of them as JSON, so nothing here duplicates a number. */
(function () {
  "use strict";

  var config = window.PROMPTLY_STUDIO;
  if (!config) return;

  var state = readSeed();

  var form = document.getElementById("studio-form");
  var promptEl = document.getElementById("studio-prompt");
  var countEl = document.getElementById("studio-count");
  var submitBtn = document.getElementById("studio-submit");
  var errorEl = document.getElementById("studio-error");
  var canvas = document.getElementById("studio-canvas");
  var grid = document.getElementById("studio-generations");
  var refBox = document.getElementById("studio-ref");
  var refMedia = document.getElementById("studio-ref-media");
  var refText = document.getElementById("studio-ref-text");
  var refClear = document.getElementById("studio-ref-clear");
  var balanceEl = document.getElementById("studio-balance");
  var costEl = document.getElementById("studio-cost-value");
  var submitCostEl = document.getElementById("studio-submit-cost");
  var shortfallEl = document.getElementById("studio-shortfall");
  var walletNoteEl = document.getElementById("studio-wallet-note");
  var sourceInput = document.querySelector(".studio-source input[type='file']");

  var activeSource = null;
  var busy = false;

  function readSeed() {
    var node = document.getElementById(config.dataId);
    if (!node) return { credits: null, generations: [], challenges: [] };
    try {
      var parsed = JSON.parse(node.textContent);
      return {
        credits: parsed.credits || null,
        generations: parsed.generations || [],
        challenges: parsed.challenges || [],
      };
    } catch (e) {
      return { credits: null, generations: [], challenges: [] };
    }
  }

  function t(key, params) {
    return window.PromptlyI18n ? window.PromptlyI18n.t(key, params) : key;
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function toast(message) {
    var box = document.getElementById("toast");
    if (!box) return;
    box.textContent = message;
    box.classList.add("show");
    setTimeout(function () { box.classList.remove("show"); }, 2200);
  }

  function getCookie(name) {
    var row = document.cookie.split("; ").find(function (part) {
      return part.indexOf(name + "=") === 0;
    });
    return row ? row.split("=")[1] : "";
  }

  /* ---------------- Credit wallet ---------------- */

  function renderCredits(credits) {
    if (!credits) return;
    state.credits = credits;

    if (balanceEl) balanceEl.textContent = credits.balance;
    if (costEl) costEl.textContent = credits.cost;
    if (submitCostEl) {
      submitCostEl.innerHTML = credits.cost + " " + t("studio_credits_unit");
    }

    if (shortfallEl) {
      if (credits.can_afford) {
        shortfallEl.hidden = true;
        shortfallEl.textContent = "";
      } else {
        shortfallEl.hidden = false;
        shortfallEl.textContent = t("studio_insufficient", { n: credits.shortfall });
      }
    }

    if (submitBtn) {
      submitBtn.disabled = busy || !config.canGenerate || !credits.can_afford;
    }
  }

  function noteRemaining(credits) {
    if (!walletNoteEl || !credits) return;
    walletNoteEl.hidden = false;
    walletNoteEl.textContent = t("studio_balance_after", { n: credits.balance });
  }

  /* ---------------- Canvas ---------------- */

  function latentPlate(promptText) {
    var wrap = el("div", "studio-latent");
    var plate = el("div", "studio-latent-plate");
    plate.appendChild(el("span", "studio-latent-sweep"));
    if (promptText) plate.appendChild(el("p", "studio-latent-prompt", promptText));
    wrap.appendChild(plate);

    var foot = el("div", "studio-latent-foot");
    if (promptText) {
      foot.appendChild(el("span", "studio-latent-status", t("studio_generating")));
      foot.appendChild(el("span", "studio-latent-elapsed", t("studio_elapsed", { n: 0 })));
    } else {
      foot.appendChild(el("span", "studio-latent-hint", t("studio_canvas_empty")));
    }
    wrap.appendChild(foot);
    return wrap;
  }

  function resultCard(generation, hero) {
    var card = el("article", "generation-card" + (hero ? " generation-card-hero" : ""));
    card.dataset.id = generation.id;

    var frame = el("div", "generation-frame");
    var img = el("img");
    img.src = generation.image;
    img.alt = generation.prompt;
    img.loading = "lazy";
    img.decoding = "async";
    frame.appendChild(img);
    frame.appendChild(el("span", "generation-status is-ready", t("studio_ready")));
    card.appendChild(frame);

    var body = el("div", "generation-body");
    var prompt = el("p", "generation-prompt", generation.prompt);
    prompt.dir = "auto";
    body.appendChild(prompt);

    var foot = el("div", "generation-foot");
    foot.appendChild(el("time", "generation-time", generation.label || ""));

    var actions = el("div", "generation-actions");
    var download = el("a", "btn btn-ghost btn-sm");
    download.href = generation.image;
    download.setAttribute("download", "");
    download.textContent = t("studio_download");
    actions.appendChild(download);

    var reuse = el("button", "btn btn-outline btn-sm");
    reuse.type = "button";
    reuse.textContent = t("studio_use_again");
    reuse.addEventListener("click", function () { applyPrompt(generation.prompt, null); });
    actions.appendChild(reuse);

    // A remix keeps its provenance: link back to the prompt it came from.
    if (generation.source_post_id) {
      var origin = el("a", "btn btn-ghost btn-sm generation-source");
      origin.href = "/post/" + generation.source_post_id + "/";
      origin.textContent = t("studio_reference");
      actions.appendChild(origin);
    }

    foot.appendChild(actions);
    body.appendChild(foot);
    card.appendChild(body);
    return card;
  }

  function failedCard(generation) {
    var card = el("article", "generation-card is-failed");
    card.dataset.id = generation.id;

    var frame = el("div", "generation-frame generation-frame-error");
    frame.appendChild(el("span", "generation-status is-failed", t("studio_failed")));
    card.appendChild(frame);

    var body = el("div", "generation-body");
    var prompt = el("p", "generation-prompt", generation.prompt);
    prompt.dir = "auto";
    body.appendChild(prompt);
    if (generation.error) body.appendChild(el("p", "generation-error", generation.error));
    card.appendChild(body);
    return card;
  }

  function renderCanvas(generation) {
    if (!canvas) return;
    canvas.textContent = "";
    if (generation && generation.status === "ready" && generation.image) {
      canvas.appendChild(resultCard(generation, true));
    } else if (generation && generation.status === "failed") {
      canvas.appendChild(failedCard(generation));
    } else {
      canvas.appendChild(latentPlate(null));
    }
  }

  /* ---------------- My generations shelf ---------------- */

  function generationNode(generation) {
    return generation.status === "ready" && generation.image
      ? resultCard(generation, false)
      : failedCard(generation);
  }

  function renderGenerations(list) {
    if (!grid) return;
    grid.textContent = "";
    if (!list || !list.length) {
      grid.appendChild(el("p", "muted studio-empty", t("studio_no_generations")));
      return;
    }
    list.forEach(function (generation) {
      grid.appendChild(generationNode(generation));
    });
  }

  function prependGeneration(generation) {
    if (!grid) return;
    var empty = grid.querySelector(".studio-empty");
    if (empty) empty.remove();
    grid.insertBefore(generationNode(generation), grid.firstChild);
  }

  /* ---------------- Prompt input ---------------- */

  function updateCount() {
    if (!countEl || !promptEl) return;
    var length = promptEl.value.trim().length;
    countEl.textContent = length;
    // The cap is enforced on submit; show the overflow before it is refused.
    countEl.parentNode.classList.toggle("is-over", length > config.maxLength);
  }

  function clearReference() {
    activeSource = null;
    if (refBox) refBox.hidden = true;
    if (refMedia) {
      refMedia.textContent = "";
      refMedia.classList.remove("is-text");
    }
    if (refText) refText.textContent = "";
  }

  function showReference(source) {
    if (!refBox) return;
    refMedia.textContent = "";
    if (source && source.image) {
      refMedia.classList.remove("is-text");
      var thumb = el("img");
      thumb.src = source.image;
      thumb.alt = "";
      refMedia.appendChild(thumb);
    } else {
      refMedia.classList.add("is-text");
      refMedia.textContent = "¶";
    }
    if (refText) refText.textContent = source && source.text ? source.text : "";
    refBox.hidden = false;
  }

  function applyPrompt(text, source) {
    if (!promptEl) return;
    promptEl.value = text || "";
    updateCount();
    activeSource = source && source.post_id ? parseInt(source.post_id, 10) || null : null;
    if (source) {
      showReference({ image: source.image, text: text });
    } else {
      clearReference();
    }
    if (form) {
      form.scrollIntoView({ block: "center", behavior: "smooth" });
      promptEl.focus();
    }
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve) {
      var area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
      resolve();
    });
  }

  /* ---------------- Errors ---------------- */

  function clearError() {
    if (!errorEl) return;
    errorEl.hidden = true;
    errorEl.textContent = "";
  }

  function showError(message, detail, actionLabel, actionHref) {
    if (!errorEl) return;
    errorEl.hidden = false;
    errorEl.textContent = message;
    if (detail) errorEl.appendChild(el("span", "studio-error-detail", detail));
    if (actionLabel && actionHref) {
      var link = el("a", "studio-error-action", actionLabel);
      link.href = actionHref;
      errorEl.appendChild(link);
    }
  }

  function setBusy(next) {
    busy = next;
    if (!submitBtn) return;
    submitBtn.disabled = next || !config.canGenerate || (state.credits && !state.credits.can_afford);
    submitBtn.classList.toggle("is-loading", next);
    if (canvas) canvas.setAttribute("aria-busy", next ? "true" : "false");
  }

  /* ---------------- Request ---------------- */

  function request(prompt) {
    var file = sourceInput && sourceInput.files && sourceInput.files[0];
    var init = {
      method: "POST",
      headers: { "X-CSRFToken": getCookie("csrftoken") },
      credentials: "same-origin",
    };

    if (file) {
      // A reference image makes this a multipart (image-to-image) request.
      var body = new FormData();
      body.append("prompt", prompt);
      if (activeSource) body.append("source_post_id", activeSource);
      body.append("source_image", file);
      init.body = body;
    } else {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify({ prompt: prompt, source_post_id: activeSource });
    }

    return fetch(config.endpoint, init).then(function (response) {
      return response
        .json()
        .catch(function () { return {}; })
        .then(function (body) { return { status: response.status, body: body }; });
    });
  }

  function handleResult(status, body) {
    if (body && body.credits) renderCredits(body.credits);

    if (status === 201 && body.generation) {
      renderCanvas(body.generation);
      prependGeneration(body.generation);
      state.generations.unshift(body.generation);
      clearReference();
      noteRemaining(body.credits);
      toast(t("studio_done_toast"));
      return;
    }

    var code = body && body.error_code;

    if (status === 401) {
      renderCanvas(null);
      showError(t("studio_login_required"));
      setTimeout(function () { window.location.href = config.loginUrl; }, 900);
      return;
    }
    if (code === "insufficient_credits") {
      renderCanvas(null);
      showError(
        t("studio_insufficient", { n: body.shortfall || 0 }),
        null,
        t("studio_insufficient_cta"),
        "#studio-earn"
      );
      return;
    }
    if (code === "invalid_prompt") {
      renderCanvas(null);
      showError(t("studio_prompt_required"));
      return;
    }
    if (code === "invalid_image") {
      renderCanvas(null);
      showError(t("upload_bad_type"), body.error);
      return;
    }

    renderCanvas(null);
    showError(t("studio_provider_error"), body && body.error);
  }

  if (form && promptEl) {
    promptEl.addEventListener("input", updateCount);

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (busy) return;

      if (!config.canGenerate) {
        showError(t("studio_login_required"));
        return;
      }

      var prompt = promptEl.value.trim();
      if (!prompt) {
        showError(t("studio_prompt_required"));
        promptEl.focus();
        return;
      }
      if (prompt.length > config.maxLength) {
        showError(t("studio_max_length", { n: config.maxLength }));
        return;
      }

      clearError();
      setBusy(true);
      if (walletNoteEl) walletNoteEl.hidden = true;
      if (canvas) {
        canvas.textContent = "";
        canvas.appendChild(latentPlate(prompt));
      }

      var elapsed = 0;
      var timer = setInterval(function () {
        elapsed += 1;
        if (!canvas) return;
        var node = canvas.querySelector(".studio-latent-elapsed");
        if (node) node.textContent = t("studio_elapsed", { n: elapsed });
      }, 1000);

      request(prompt)
        .then(function (result) { handleResult(result.status, result.body); })
        .catch(function () {
          renderCanvas(null);
          showError(t("studio_provider_error"));
        })
        .then(function () {
          clearInterval(timer);
          setBusy(false);
        });
    });
  }

  if (refClear) {
    refClear.addEventListener("click", function () {
      clearReference();
      if (promptEl) promptEl.focus();
    });
  }

  /* ---------------- Library: copy or send into the composer ---------------- */

  document.addEventListener("click", function (event) {
    var copyBtn = event.target.closest("[data-studio-copy]");
    if (copyBtn) {
      var copyCard = copyBtn.closest("[data-prompt]");
      if (copyCard) {
        copyText(copyCard.dataset.prompt || "").then(function () { toast(t("copy_toast")); });
      }
      return;
    }

    var useBtn = event.target.closest("[data-studio-use]");
    if (useBtn) {
      var card = useBtn.closest("[data-prompt]");
      if (!card) return;
      var image = card.querySelector(".prompt-card-media img");
      applyPrompt(card.dataset.prompt || "", {
        image: image ? image.src : null,
        text: card.dataset.prompt || "",
        post_id: card.dataset.postId,
      });
    }
  });

  /* ---------------- Reward challenges ---------------- */

  function markChallengeComplete(slug) {
    var card = document.querySelector('[data-challenge="' + slug + '"]');
    if (!card) return;
    var foot = card.querySelector(".challenge-foot");
    var button = foot && foot.querySelector("[data-challenge-claim]");
    if (button) button.replaceWith(el("span", "challenge-done", t("studio_challenge_done")));
  }

  function claimChallenge(slug, evidence) {
    var url = config.challengeEndpoint.replace("__slug__", slug);
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      credentials: "same-origin",
      body: JSON.stringify({ evidence: evidence }),
    }).then(function (response) {
      return response
        .json()
        .catch(function () { return {}; })
        .then(function (body) { return { status: response.status, body: body }; });
    });
  }

  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-challenge-claim]");
    if (!btn) return;

    var slug = btn.dataset.challengeClaim;
    var card = btn.closest("[data-challenge]");
    var needsEvidence = card && card.dataset.needsEvidence === "1";
    var evidence = "";

    if (needsEvidence) {
      evidence = window.prompt(t("studio_challenge_evidence_prompt"), "");
      if (!evidence) return;
    }

    btn.disabled = true;
    claimChallenge(slug, evidence)
      .then(function (result) {
        if (result.body && result.body.credits) renderCredits(result.body.credits);
        if (result.status === 201) {
          markChallengeComplete(slug);
          if (walletNoteEl) walletNoteEl.hidden = true;
          toast(t("studio_challenge_done_toast", { n: result.body.reward || 0 }));
        } else {
          showError(t("studio_challenge_error"), result.body && result.body.error);
          btn.disabled = false;
        }
      })
      .catch(function () {
        showError(t("studio_challenge_error"));
        btn.disabled = false;
      });
  });

  var referralCopy = document.getElementById("referral-copy");
  var referralInput = document.getElementById("referral-url");
  if (referralCopy && referralInput) {
    referralCopy.addEventListener("click", function () {
      copyText(referralInput.value).then(function () { toast(t("studio_referral_copied")); });
    });
  }

  /* i18n.js asks pages to re-apply their own strings after a language switch. */
  window.promptlyApplyPageI18n = function () {
    renderCredits(state.credits);
    renderGenerations(state.generations);
    renderCanvas(state.generations[0] || null);
    if (submitBtn) {
      var label = submitBtn.querySelector("span[data-i18n]");
      if (label) label.textContent = t("studio_generate");
    }
  };

  /* ---------------- Boot ---------------- */

  renderCredits(state.credits);
  renderGenerations(state.generations);
  renderCanvas(state.generations[0] || null);
  updateCount();

  // A post's "Use prompt" action lands here with the prompt already filled in
  // and the source post remembered, so the result links back to it.
  if (config.prefill && config.prefill.sourcePostId && promptEl) {
    activeSource = parseInt(config.prefill.sourcePostId, 10) || null;
    var label = config.prefill.sourceTitle || "";
    if (config.prefill.sourceAuthor) label += " · @" + config.prefill.sourceAuthor;
    if (refText && label) refText.textContent = label;
    promptEl.focus();
  }
})();
