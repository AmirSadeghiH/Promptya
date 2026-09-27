/* Promptly — frontend app JS */
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
    return window.PromptlyI18n ? window.PromptlyI18n.t(key, params) : key;
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
        '<span class="comment-time">' + new Date(c.created_at).toLocaleString(PromptlyI18n.dateLocale()) + "</span>" +
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
          setTimeout(() => (window.location.href = `/post/${data.post.id}/`), 700);
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
    const feedPath = window.location.pathname;
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

    function buildCard(post) {
      const article = document.createElement("article");
      article.className = "post-card";
      article.dataset.postId = post.id;

      const media = document.createElement("a");
      media.className = "post-card-media " + (post.image || post.video ? "has-media" : "is-prompt");
      media.href = `/post/${post.id}/`;
      if (post.image) {
        const img = document.createElement("img");
        img.src = post.image;
        img.alt = post.title;
        img.loading = "lazy";
        media.appendChild(img);
      } else if (post.video) {
        const video = document.createElement("video");
        video.src = post.video;
        video.muted = true;
        video.preload = "metadata";
        video.playsInline = true;
        media.appendChild(video);
      } else {
        const preview = document.createElement("div");
        preview.className = "prompt-preview";
        const p = document.createElement("p");
        p.textContent = (post.prompt || post.title).slice(0, 180);
        p.style.unicodeBidi = "plaintext";
        preview.appendChild(p);
        media.appendChild(preview);
      }

      const body = document.createElement("div");
      body.className = "post-card-body";
      const title = document.createElement("a");
      title.className = "post-card-title";
      title.href = `/post/${post.id}/`;
      title.textContent = post.title;
      body.appendChild(title);

      const meta = document.createElement("div");
      meta.className = "post-card-meta";
      const creator = document.createElement("a");
      creator.className = "creator";
      creator.href = `/profile/${encodeURIComponent(post.author.username)}/`;
      creator.setAttribute("dir", "ltr");
      creator.appendChild(buildAvatar(post.author, "creator-avatar"));
      const creatorName = document.createElement("span");
      creatorName.className = "creator-name";
      creatorName.textContent = "@" + post.author.username;
      creator.appendChild(creatorName);
      const stats = document.createElement("div");
      stats.className = "stats";
      stats.innerHTML =
        '<button class="stat-btn like-btn' + (post.is_liked ? " is-active" : "") +
        '" data-action="like" data-post-id="' + post.id + '">♥ <span data-count="like">' + post.like_count + "</span></button>" +
        '<button class="stat-btn save-btn' + (post.is_saved ? " is-active" : "") +
        '" data-action="save" data-post-id="' + post.id + '">🔖 <span data-count="save">' + post.save_count + "</span></button>";
      meta.appendChild(creator);
      meta.appendChild(stats);
      body.appendChild(meta);

      // Image posts carry their prompt into the studio (mirrors post_grid.html).
      if (post.post_type === "image" && post.prompt) {
        const use = document.createElement("a");
        use.className = "use-prompt-btn";
        use.href = "/studio/?source=" + post.id;
        use.title = t("studio_use_prompt_title");
        use.innerHTML =
          '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3.5 13.9 9l5.6 1.9-5.6 2L12 18.5l-1.9-5.6L4.5 11 10.1 9z"/><path d="M18.5 3.5v3M20 5h-3"/></svg><span></span>';
        use.querySelector("span").textContent = t("studio_use_prompt");
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
