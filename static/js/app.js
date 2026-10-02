/* Promptya — frontend app JS */
(function () {
  "use strict";

  const CSRF = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1];

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CSRF,
      },
      credentials: "same-origin",
      body: JSON.stringify(body || {}),
    }).then((r) => (r.ok ? r.json() : r.json().then(Promise.reject.bind(Promise))));
  }

  /* ---------------- Toast ---------------- */
  const toastEl = document.getElementById("toast");
  let toastTimer = null;
  function toast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2200);
  }

  /* ---------------- i18n helper ---------------- */
  function t(key, params) {
    return window.PromptyaI18n ? window.PromptyaI18n.t(key, params) : key;
  }

  /* ---------------- Language-aware page paths ---------------- */
  /* Every page URL is /en/… or /fa/…. Client-side code that builds a link has to
     land on the same language version the reader is on: an unprefixed /post/12/
     still resolves (the unprefixed paths are kept as aliases) but drops the
     reader onto a page whose canonical points elsewhere, which is both a worse
     experience and a weaker internal link. */
  const LANG = window.PROMPTYA_LANG === "fa" ? "fa" : "en";
  function pagePath(path) {
    return "/" + LANG + (path.startsWith("/") ? path : "/" + path);
  }
  /* The same prefix stripped back off, for matching the current location against
     known routes. */
  function neutralPath(pathname) {
    const stripped = pathname.replace(/^\/(en|fa)(?=\/|$)/, "");
    return stripped || "/";
  }

  /* ---------------- Like / Save toggles ---------------- */
  document.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    const postId = btn.dataset.postId;

    if (action === "like" || action === "save") {
      e.preventDefault();
      post(`/api/posts/${postId}/${action}/`)
        .then((data) => {
          const countEl = btn.querySelector("[data-count]");
          if (countEl) countEl.textContent = action === "like" ? data.like_count : data.save_count;
          btn.classList.toggle("is-active", action === "like" ? data.liked : data.saved);
          if (action === "save") toast(data.saved ? t("saved_toast") : t("removed_from_saved"));
        })
        .catch((err) => {
          if (err && err.status === 403) {
            toast(t("login_to_do_that"));
            setTimeout(() => (window.location.href = "/login/"), 900);
          } else {
            toast(t("something_wrong"));
          }
        });
    }

    if (action === "follow") {
      e.preventDefault();
      post(`/api/posts/users/${btn.dataset.username}/follow/`)
        .then((data) => {
          btn.classList.toggle("is-active", data.following);
          btn.textContent = data.following ? t("following_btn") : t("follow");
        })
        .catch(() => toast(t("follow_error")));
    }

    if (action === "copy") {
      e.preventDefault();
      const card = btn.closest("[data-post-id]");
      const pre = document.querySelector(".prompt-box pre");
      const text = pre ? pre.textContent.trim() : "";
      copyText(text || postId).then(() => {
        const original = btn.textContent;
        btn.textContent = t("copied");
        toast(t("copy_toast"));
        post(`/api/posts/${postId}/copy/`).catch(() => {});
        setTimeout(() => (btn.textContent = original), 1500);
      });
    }
  });

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise((resolve) => {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
      resolve();
    });
  }

  /* ---------------- View tracking on post detail ---------------- */
  const detail = document.querySelector(".post-detail");
  if (detail) {
    fetch(`/api/posts/${detail.dataset.postId}/view/`, {
      method: "POST",
      headers: { "X-CSRFToken": CSRF },
      credentials: "same-origin",
    }).catch(() => {});
  }

  /* ---------------- Shared avatar builder (mirrors partials/avatar.html) ---------------- */
  function buildAvatar(user, cls) {
    const shell = document.createElement("span");
    shell.className = "avatar-shell " + cls;
    const initial = document.createElement("span");
    initial.className = "avatar-initial";
    initial.setAttribute("aria-hidden", "true");
    initial.textContent = ((user.display_name || user.username || "?").charAt(0) || "?").toUpperCase();
    shell.appendChild(initial);
    if (user.profile_picture) {
      const img = document.createElement("img");
      img.className = "avatar-img";
      img.src = user.profile_picture;
      img.alt = "";
      img.loading = "lazy";
      img.addEventListener("error", () => (img.style.display = "none"));
      shell.appendChild(img);
    }
    return shell;
  }

  /* ---------------- Comments ---------------- */
  const commentList = document.querySelector(".comment-list");
  if (commentList) {
    const postId = detail ? detail.dataset.postId : null;
    const endpoint = commentList.dataset.endpoint;

    function renderComment(c) {
      const el = document.createElement("div");
      el.className = "comment";
      const row = document.createElement("div");
      row.className = "comment-row";
      row.appendChild(buildAvatar(c.user, "comment-avatar comment-avatar-fallback"));
      const main = document.createElement("div");
      main.className = "comment-main";
      main.innerHTML =
        '<div class="comment-head"><span class="creator-name">@' +
        escapeHtml(c.user.username) +
        "</span><span>" +
        '<span class="comment-time">' + new Date(c.created_at).toLocaleString(PromptyaI18n.dateLocale()) + "</span>" +
        (window.IS_OWNER
          ? ' <button class="comment-delete" data-comment-id="' + c.id + '">' + t("delete") + '</button>'
          : "") +
        "</span></div><p>" +
        escapeHtml(c.content) +
        "</p>";
      row.appendChild(main);
      el.appendChild(row);
      return el;
    }

    function escapeHtml(str) {
      return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    fetch(endpoint, { credentials: "same-origin" })
      .then((r) => r.json())
      .then((data) => {
        (data.results || []).forEach((c) => commentList.appendChild(renderComment(c)));
        commentList.dataset.loaded = "true";
      })
      .catch(() => {});

    const form = document.querySelector(".comment-form");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        const textarea = form.querySelector("textarea");
        const content = textarea.value.trim();
        if (!content) return;
        post(`/api/posts/${postId}/comments/create/`, { content })
          .then((c) => {
            commentList.insertBefore(renderComment(c), commentList.firstChild);
            textarea.value = "";
            toast(t("comment_posted"));
          })
          .catch(() => toast(t("comment_error")));
      });
    }

    commentList.addEventListener("click", function (e) {
      const del = e.target.closest(".comment-delete");
      if (!del) return;
      fetch(`/api/posts/comments/${del.dataset.commentId}/delete/`, {
        method: "DELETE",
        headers: { "X-CSRFToken": CSRF },
        credentials: "same-origin",
      }).then((r) => {
        if (r.ok) del.closest(".comment").remove();
      });
    });
  }

  /* ---------------- Create post form ---------------- */
  const createForm = document.getElementById("create-form");
  if (createForm) {
    const postTypeSelect = document.getElementById("id_post_type");
    const mediaFields = document.getElementById("media-upload-fields");
    const imageField = document.getElementById("image-field");
    const videoField = document.getElementById("video-field");
    const audioField = document.getElementById("audio-field");

    function updateMediaFields() {
      const type = postTypeSelect?.value;
      if (type === "image" || type === "video" || type === "audio") {
        mediaFields.hidden = false;
        imageField.hidden = type !== "image";
        videoField.hidden = type !== "video";
        audioField.hidden = type !== "audio";
      } else {
        mediaFields.hidden = true;
        imageField.hidden = true;
        videoField.hidden = true;
        audioField.hidden = true;
      }
    }

    if (postTypeSelect) {
      postTypeSelect.addEventListener("change", updateMediaFields);
      updateMediaFields();
    }

    createForm.addEventListener("submit", function (e) {
      e.preventDefault();
      const fd = new FormData(createForm);
      fd.set("category_id", parseInt(fd.get("category_id"), 10));
      const errorBox = document.getElementById("create-error");

      fetch("/api/posts/create/", {
        method: "POST",
        headers: { "X-CSRFToken": CSRF },
        credentials: "same-origin",
        body: fd,
      })
        .then((r) => (r.ok ? r.json() : r.json().then(Promise.reject.bind(Promise))))
        .then((data) => {
          toast(t("published_toast"));
          setTimeout(() => (window.location.href = `/post/${encodeURIComponent(data.post.slug)}/`), 700);
        })
        .catch((err) => {
          if (errorBox) {
            errorBox.hidden = false;
            errorBox.textContent = err && err.errors
              ? Object.values(err.errors).join(" ")
              : t("publish_error");
          }
        });
    });
  }

  /* ---------------- Notifications page ---------------- */
  const markAll = document.getElementById("mark-all-read");
  if (markAll) {
    markAll.addEventListener("click", function () {
      post("/api/notifications/read-all/").then(() => {
        document.querySelectorAll(".notification.unread").forEach((el) => el.classList.remove("unread"));
        toast(t("caught_up_toast"));
      });
    });
  }

  /* ---------------- Infinite scroll ---------------- */
  const grid = document.querySelector(".post-grid");
  const loadMore = document.querySelector(".load-more");
  if (grid && loadMore && loadMore.dataset.nextCursor) {
    /* Matched against the *neutral* path: with the site now served at /en/… and
       /fa/…, comparing the raw location meant every prefixed feed fell through
       to the trending endpoint and "For You" paged in trending results. */
    const feedPath = neutralPath(window.location.pathname);
    let apiUrl;
    if (feedPath === "/") {
      apiUrl = "/api/posts/feed/recommended/";
    } else if (feedPath.startsWith("/feed/")) {
      apiUrl = `/api/posts/feed/${feedPath.split("/")[2]}/`;
    } else if (feedPath.startsWith("/category/")) {
      apiUrl = `/api/posts/categories/${feedPath.split("/")[2]}/`;
    } else if (feedPath === "/search/") {
      apiUrl = `/api/posts/search/?q=${encodeURIComponent(
        new URLSearchParams(window.location.search).get("q") || ""
      )}`;
    } else {
      apiUrl = "/api/posts/feed/trending/";
    }

    let loading = false;
    let cursor = loadMore.dataset.nextCursor;

    const observer = new IntersectionObserver((entries) => {
      if (!entries[0].isIntersecting || loading || !cursor) return;
      loading = true;
      const sep = apiUrl.includes("?") ? "&" : "?";
      fetch(`${apiUrl}${sep}cursor=${encodeURIComponent(cursor)}&page_size=12`, {
        credentials: "same-origin",
      })
        .then((r) => r.json())
        .then((data) => {
          cursor = data.next_cursor;
          if (!data.results || !data.results.length) {
            observer.disconnect();
            return;
          }
          data.results.forEach((p) => grid.appendChild(buildCard(p)));
          if (!cursor) observer.disconnect();
          loading = false;
        })
        .catch(() => (loading = false));
    }, { rootMargin: "400px" });
    observer.observe(loadMore);

    /* Infinite scroll appends cards client-side, so this builder has to
       produce the *same* markup as partials/post_grid.html — otherwise page 2
       of the feed stops looking like page 1. It previously did not: it reached
       for "♥" and "🔖" emoji where the server renders SVG icons, skipped the
       media-type badge, the verified mark and every aria-label, and forced
       dir="ltr" on the creator link. Everything user-authored still goes in via
       textContent; only the fixed icon shell is markup.

       It also has to match on the *link* targets: server-rendered cards point at
       /en/post/12/, so cards built here have to point at the same address rather
       than the unprefixed alias. */
    const SVG = {
      like: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M19 14c1.5-1.6 2-3.3 2-5a5 5 0 0 0-9.6-1.8A5 5 0 0 0 3 9c0 1.7.5 3.4 2 5l7 7z"/></svg>',
      save: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M19 21 12 16 5 21V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>',
      play: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="m7 4 13 8-13 8z"/></svg>',
      music: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/></svg>',
      frame: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2"/><path d="M8 12h8"/></svg>',
      sparkle: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3.5 13.9 9l5.6 1.9-5.6 2L12 18.5l-1.9-5.6L4.5 11 10.1 9z"/><path d="M18.5 3.5v3M20 5h-3"/></svg>',
      verified: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="currentColor"/><path d="m7.5 12.4 2.9 2.9 6-6.4" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    };

    // Mirrors the waveform in partials/post_grid.html so audio previews match.
    const WAVEFORM =
      '<svg class="audio-wave" viewBox="0 0 128 34" preserveAspectRatio="none" aria-hidden="true">' +
      '<g fill="currentColor">' +
      [13, 9, 4, 11, 2, 14, 7, 12, 1, 10, 15, 5, 12, 8, 14, 11]
        .map((y, i) => '<rect x="' + i * 8 + '" y="' + y + '" width="4" height="' + (34 - y * 2) + '" rx="2"/>')
        .join("") +
      "</g></svg>";

    function svgEl(markup, cls) {
      const holder = document.createElement("span");
      holder.innerHTML = markup;
      const node = holder.firstChild;
      if (cls) node.setAttribute("class", cls);
      return node;
    }

    function badge(markup, label) {
      const el = document.createElement("span");
      el.className = "media-badge";
      el.appendChild(svgEl(markup, "icon"));
      el.appendChild(document.createTextNode(" " + label));
      return el;
    }

    function statButton(action, iconMarkup, postId, count, active) {
      const btn = document.createElement("button");
      btn.className = "stat-btn " + action + "-btn" + (active ? " is-active" : "");
      btn.dataset.action = action;
      btn.dataset.postId = postId;
      const label = t(action === "like" ? "like_action" : "save_action");
      btn.setAttribute("aria-label", label);
      btn.setAttribute("title", label);
      btn.appendChild(svgEl(iconMarkup, "icon"));
      const value = document.createElement("span");
      value.dataset.count = action;
      value.textContent = count;
      btn.appendChild(value);
      return btn;
    }

    function buildCard(post) {
      const article = document.createElement("article");
      article.className = "post-card";
      article.dataset.postId = post.id;

      const media = document.createElement("a");
      media.className = "post-card-media " + (post.image || post.video ? "has-media" : "is-prompt");
      media.href = pagePath(`/post/${encodeURIComponent(post.slug)}/`);
      // The card body already prints the title as its own link; naming it here
      // too is what makes the media area a usable target for a screen reader.
      media.setAttribute("aria-label", post.title);

      if (post.image) {
        const img = document.createElement("img");
        // Prefer the WebP derivative, exactly as the server-rendered card does.
        img.src = post.image_webp || post.image;
        img.alt = post.title;
        /* Cards appended by infinite scroll are never the LCP candidate — the
           server-rendered ones above already are — so everything here defers.
           The intrinsic size still matters: it is what stops the masonry from
           reflowing as the image arrives. */
        if (post.image_width) img.width = post.image_width;
        if (post.image_height) img.height = post.image_height;
        img.loading = "lazy";
        img.decoding = "async";
        media.appendChild(img);
      } else if (post.video) {
        const video = document.createElement("video");
        video.src = post.video;
        video.muted = true;
        video.preload = "metadata";
        video.playsInline = true;
        media.appendChild(video);
        media.appendChild(badge(SVG.play, t("video")));
      } else if (post.audio) {
        const preview = document.createElement("div");
        preview.className = "prompt-preview audio-preview";
        preview.appendChild(svgEl(WAVEFORM));
        preview.appendChild(badge(SVG.music, t("audio")));
        media.appendChild(preview);
      } else {
        const preview = document.createElement("div");
        preview.className = "prompt-preview";
        preview.appendChild(svgEl(SVG.frame, "icon"));
        const p = document.createElement("p");
        p.textContent = (post.prompt || post.title).slice(0, 180);
        preview.appendChild(p);
        preview.appendChild(badge(SVG.frame, t("prompt")));
        media.appendChild(preview);
      }

      const body = document.createElement("div");
      body.className = "post-card-body";
      const title = document.createElement("a");
      title.className = "post-card-title";
      title.href = pagePath(`/post/${encodeURIComponent(post.slug)}/`);
      title.textContent = post.title;
      body.appendChild(title);

      const meta = document.createElement("div");
      meta.className = "post-card-meta";
      const creator = document.createElement("a");
      creator.className = "creator";
      creator.href = pagePath(`/profile/${encodeURIComponent(post.author.username)}/`);
      creator.appendChild(buildAvatar(post.author, "creator-avatar"));
      const creatorName = document.createElement("span");
      creatorName.className = "creator-name";
      creatorName.textContent = "@" + post.author.username;
      creator.appendChild(creatorName);
      if (post.author.is_verified) {
        const tick = svgEl(SVG.verified);
        tick.className = "verified";
        creator.appendChild(tick);
      }
      const stats = document.createElement("div");
      stats.className = "stats";
      stats.appendChild(statButton("like", SVG.like, post.id, post.like_count, post.is_liked));
      stats.appendChild(statButton("save", SVG.save, post.id, post.save_count, post.is_saved));
      meta.appendChild(creator);
      meta.appendChild(stats);
      body.appendChild(meta);

      // Image posts carry their prompt into the studio (mirrors post_grid.html).
      if (post.post_type === "image" && post.prompt) {
        const use = document.createElement("a");
        use.className = "use-prompt-btn";
        use.href = pagePath("/studio/?source=" + post.id);
        use.title = t("studio_use_prompt_title");
        use.appendChild(svgEl(SVG.sparkle, "icon"));
        const label = document.createElement("span");
        label.textContent = t("studio_use_prompt");
        use.appendChild(label);
        body.appendChild(use);
      }

      article.appendChild(media);
      article.appendChild(body);
      return article;
    }
  }

  /* ---------------- Keyboard shortcut ---------------- */
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement.tagName !== "INPUT" &&
        document.activeElement.tagName !== "TEXTAREA") {
      const searchInput = document.querySelector(".search input");
      if (searchInput) {
        e.preventDefault();
        searchInput.focus();
      }
    }
  });

  /* ---------------- PWA ---------------- */
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/static/sw.js").catch(() => {});
    });
  }
})();
