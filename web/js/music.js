const TRACKS_META_SOURCES = ["../data/music/manifest.json", "/site/data/music/manifest.json"];
const TRACKS_SOURCES = ["../data/music/tracks.jsonl", "/site/data/music/tracks.jsonl"];
const SITE_CONFIG_SOURCES = ["../config/site.json", "/site/config/site.json"];

const state = {
  mediaBasePath: "/media/derived",
  tracks: [],
  filteredTracks: [],
  renderedCount: 0,
  query: "",
  sort: "newest",
  chunkSize: 24,
  observer: null,
  sentinel: null,
  dom: {},
  modal: null,
  lastFocus: null,
  activeTrackId: null,
  routeListenerAttached: false,
};

let isSyncingRoute = false;

document.addEventListener("DOMContentLoaded", () => {
  initializeMusic().catch((error) => {
    console.error("[music] initialization failed", error);
  });
});

async function initializeMusic() {
  const main = document.getElementById("main");
  if (!main) return;

  renderLoading(main, "Loading music catalog...");

  try {
    const [siteConfig, manifest, tracksText] = await Promise.all([
      fetchFirstJson(SITE_CONFIG_SOURCES),
      fetchFirstJson(TRACKS_META_SOURCES),
      fetchFirstText(TRACKS_SOURCES),
    ]);

    renderSiteChrome(siteConfig || {});
    state.mediaBasePath = (siteConfig?.mediaBasePath || "/media/derived").replace(/\/$/, "");

    const tracks = parseTrackPayload(tracksText);
    state.tracks = tracks;
    applyFilters({ query: "", sort: "newest" });
    renderCatalog(main, manifest || {});

    await syncRouteFromLocation({ initialLoad: true });
    if (!state.routeListenerAttached) {
      window.addEventListener("popstate", () => {
        syncRouteFromLocation().catch((popError) => {
          console.error("[music] popstate sync failed", popError);
        });
      });
      state.routeListenerAttached = true;
    }
  } catch (error) {
    console.error("[music] failed to load catalog", error);
    renderError(main, "We couldn't load the music catalog right now. Please try again soon.");
  }
}

function parseTrackPayload(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      try {
        const record = JSON.parse(line);
        const search = typeof record.search === "string" ? record.search : "";
        const title = record.title || record.slug || "";
        const description = record.description || record.summary || "";
        const lyrics = typeof record.lyrics === "string" ? record.lyrics.trim() : "";
        const summary = record.summary || truncate(description, 180);
        const sortDate = record.published_at ? Date.parse(record.published_at) : 0;
        const tags = Array.isArray(record.tags) ? record.tags : [];
        const searchIndex = [
          title,
          record.summary,
          description,
          tags.join(" "),
          lyrics,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return {
          ...record,
          title,
          summary,
          sortDate,
          tags,
          searchIndex: searchIndex || search || "",
          lyrics,
        };
      } catch (error) {
        console.warn("[music] failed to parse track record", error);
        return null;
      }
    })
    .filter(Boolean);
}

function renderCatalog(main, manifest) {
  main.innerHTML = "";

  const hero = document.createElement("section");
  hero.className = "music-hero";
  const total = manifest?.tracks ?? state.tracks.length;
  hero.innerHTML = `
    <div>
      <span class="pill pill--light">Music Catalog</span>
      <h1 class="headline-2">Listen & Discover</h1>
      <p>Stream ${total} track${total === 1 ? "" : "s"} crafted for the SmileCMS studio. Search, sort, and share your favorites.</p>
    </div>
    <div class="music-hero__meta" aria-live="polite">
      <span>Shareable deep links</span>
      <span>Infinite scroll</span>
      <span>Download optional</span>
    </div>
  `;

  const toolbar = document.createElement("section");
  toolbar.className = "music-toolbar";
  toolbar.innerHTML = `
    <div class="music-toolbar__group music-search">
      <label class="visually-hidden" for="music-search">Search tracks</label>
      <input id="music-search" type="search" placeholder="Search title, tags, or description..." autocomplete="off" />
    </div>
    <div class="music-toolbar__group">
      <label class="visually-hidden" for="music-sort">Sort tracks</label>
      <select id="music-sort">
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
        <option value="title-asc">Title A - Z</option>
        <option value="title-desc">Title Z - A</option>
      </select>
      <span class="music-count" data-music-count></span>
    </div>
  `;

  const grid = document.createElement("section");
  grid.className = "music-catalog";
  grid.setAttribute("role", "list");
  grid.id = "music-catalog";

  const sentinel = document.createElement("div");
  sentinel.className = "music-sentinel";

  main.appendChild(hero);
  main.appendChild(toolbar);
  main.appendChild(grid);
  main.appendChild(sentinel);

  const searchInput = toolbar.querySelector("#music-search");
  const sortSelect = toolbar.querySelector("#music-sort");

  if (searchInput) {
    searchInput.addEventListener(
      "input",
      debounce((event) => {
        applyFilters({ query: event.target.value });
        resetRenderedGrid();
      }, 120)
    );
  }
  if (sortSelect) {
    sortSelect.addEventListener("change", (event) => {
      applyFilters({ sort: event.target.value });
      resetRenderedGrid();
    });
  }

  state.dom = {
    grid,
    count: toolbar.querySelector("[data-music-count]"),
    search: searchInput,
    sort: sortSelect,
  };
  state.sentinel = sentinel;
  state.renderedCount = 0;

  renderFilteredTracks();
  setupObserver();
}

function applyFilters({ query, sort }) {
  if (typeof query === "string") {
    state.query = query.trim().toLowerCase();
  }
  if (typeof sort === "string") {
    state.sort = sort;
  }

  let filtered = [...state.tracks];
  if (state.query) {
    filtered = filtered.filter((track) => track.searchIndex.includes(state.query));
  }

  filtered.sort((a, b) => {
    switch (state.sort) {
      case "oldest":
        return (a.sortDate || 0) - (b.sortDate || 0);
      case "title-asc":
        return a.title.localeCompare(b.title);
      case "title-desc":
        return b.title.localeCompare(a.title);
      case "newest":
      default:
        return (b.sortDate || 0) - (a.sortDate || 0);
    }
  });

  state.filteredTracks = filtered;
  state.renderedCount = 0;
}

function renderFilteredTracks() {
  if (!state.dom.grid) return;
  state.dom.grid.innerHTML = "";
  state.renderedCount = 0;
  updateCount();
  renderNextChunk();
}

function renderNextChunk() {
  const start = state.renderedCount;
  const end = Math.min(start + state.chunkSize, state.filteredTracks.length);
  if (!state.dom.grid) return;

  const fragment = document.createDocumentFragment();
  for (let index = start; index < end; index += 1) {
    const track = state.filteredTracks[index];
    const card = createTrackCard(track, index);
    fragment.appendChild(card);
  }

  state.dom.grid.appendChild(fragment);
  state.renderedCount = end;

  if (state.renderedCount >= state.filteredTracks.length) {
    destroyObserver();
  }
}

function createTrackCard(track, index) {
  const article = document.createElement("article");
  article.className = "music-card";
  article.setAttribute("role", "listitem");
  article.tabIndex = 0;
  article.dataset.index = String(index);
  article.dataset.trackId = track.id;

  const cover = document.createElement("div");
  cover.className = "music-card__cover";
  const coverImagePath =
    resolveMediaVariant(track.cover?.variants, ["thumb", "thumbnail", "web", "large"]) ||
    (track.cover?.path ? resolveMediaPath(track.cover.path) : null);
  if (coverImagePath) {
    const img = document.createElement("img");
    img.src = coverImagePath;
    img.alt = track.cover?.alt || track.cover?.title || `${track.title} cover art`;
    img.loading = "lazy";
    cover.appendChild(img);
  } else {
    cover.innerHTML = `<span class="pill pill--light">No artwork</span>`;
  }

  const body = document.createElement("div");
  body.className = "music-card__body";
  body.innerHTML = `
    <div>
      <h2>${escapeHtml(track.title)}</h2>
      ${track.summary ? `<p class="music-card__summary">${escapeHtml(track.summary)}</p>` : ""}
    </div>
  `;

  const meta = document.createElement("div");
  meta.className = "music-card__meta";
  const duration = formatDuration(track.duration);
  if (duration) meta.appendChild(createMetaBadge(duration));
  if (track.published_at) meta.appendChild(createMetaBadge(formatDate(track.published_at)));
  body.appendChild(meta);

  if (track.tags?.length) {
    const tags = document.createElement("div");
    tags.className = "music-card__tags";
    track.tags.slice(0, 3).forEach((tag) => {
      const pill = document.createElement("span");
      pill.className = "pill pill--light";
      pill.textContent = `#${tag}`;
      tags.appendChild(pill);
    });
    body.appendChild(tags);
  }

  const actions = document.createElement("div");
  actions.className = "music-card__actions";
  const playButton = document.createElement("button");
  playButton.type = "button";
  playButton.className = "button button--primary";
  playButton.textContent = "Play track";
  playButton.addEventListener("click", (event) => {
    event.stopPropagation();
    openModal(track);
  });
  actions.appendChild(playButton);

  article.appendChild(cover);
  article.appendChild(body);
  article.appendChild(actions);

  article.addEventListener("click", (event) => {
    if (event.target instanceof HTMLElement && event.target.closest("button")) {
      return;
    }
    openModal(track);
  });
  article.addEventListener("keypress", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openModal(track);
    }
  });

  return article;
}

function createMetaBadge(text) {
  const span = document.createElement("span");
  span.textContent = text;
  return span;
}

function updateCount() {
  if (!state.dom.count) return;
  const total = state.filteredTracks.length;
  const remaining = Math.max(total - state.renderedCount, 0);
  state.dom.count.textContent = `${total} track${total === 1 ? "" : "s"} - ${remaining} remaining`;
}

function resetRenderedGrid() {
  destroyObserver();
  renderFilteredTracks();
  setupObserver();
}

function setupObserver() {
  if (!state.sentinel) return;
  state.observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        renderNextChunk();
        updateCount();
      }
    });
  });
  state.observer.observe(state.sentinel);
}

function destroyObserver() {
  if (state.observer) {
    state.observer.disconnect();
    state.observer = null;
  }
}

function openModal(track, options = {}) {
  const { skipRouteUpdate = false } = options;
  if (!state.modal) {
    state.modal = createModal();
    document.body.appendChild(state.modal.root);
  }

  const {
    root,
    dialog,
    titleEl,
    subtitleEl,
    audioEl,
    coverEl,
    tagsEl,
    metaEl,
    descriptionEl,
    lyricsSection,
    lyricsBody,
    downloadLink,
  } =
    state.modal;

  titleEl.textContent = track.title;
  const duration = formatDuration(track.duration);
  const published = track.published_at ? formatDate(track.published_at) : null;
  subtitleEl.textContent = [duration, published].filter(Boolean).join(" • ");

  const coverPath =
    resolveMediaVariant(track.cover?.variants, ["large", "web", "thumb", "thumbnail"]) ||
    (track.cover?.path ? resolveMediaPath(track.cover.path) : null);
  if (coverPath) {
    coverEl.src = coverPath;
    coverEl.alt = track.cover?.alt || track.cover?.title || `${track.title} cover art`;
    coverEl.removeAttribute("hidden");
  } else {
    coverEl.setAttribute("hidden", "true");
  }

  if (Array.isArray(track.tags) && track.tags.length) {
    tagsEl.innerHTML = track.tags
      .map((tag) => `<span class="pill pill--light">#${escapeHtml(tag)}</span>`)
      .join("");
  } else {
    tagsEl.innerHTML = `<span class="pill pill--light">No tags</span>`;
  }

  const extras = [];
  if (track.updated_at && track.updated_at !== track.published_at) {
    extras.push(`Updated ${formatDate(track.updated_at)}`);
  }
  if (track.audio?.mime_type) {
    extras.push(track.audio.mime_type);
  }
  metaEl.textContent = extras.join(" • ");

  descriptionEl.textContent =
    track.description?.trim() || track.summary?.trim() || "No description available for this track.";

  if (track.lyrics && lyricsSection && lyricsBody) {
    lyricsBody.textContent = track.lyrics;
    lyricsSection.removeAttribute("hidden");
  } else if (lyricsSection && lyricsBody) {
    lyricsSection.setAttribute("hidden", "true");
    lyricsBody.textContent = "";
  }

  const audioSrc = track.audio?.src ? resolveMediaPath(track.audio.src) : null;
  if (audioSrc) {
    audioEl.src = audioSrc;
    audioEl.load();
    audioEl.play().catch(() => {
      /* autoplay might be blocked */
    });
  }

  if (track.download?.enabled && track.download?.src) {
    downloadLink.href = resolveMediaPath(track.download.src);
    const candidate =
      typeof track.download.src === "string" ? track.download.src.split("/").pop() : "";
    const fallbackName =
      track.download.filename || candidate || `${track.id || "track"}.mp3`;
    downloadLink.download = fallbackName;
    downloadLink.removeAttribute("aria-disabled");
  } else {
    downloadLink.removeAttribute("href");
    downloadLink.setAttribute("aria-disabled", "true");
    downloadLink.removeAttribute("download");
  }

  root.classList.add("is-open");
  root.removeAttribute("hidden");
  dialog.scrollTop = 0;
  state.lastFocus = document.activeElement;
  dialog.focus({ preventScroll: true });

  const handleKey = (event) => {
    if (event.key === "Escape") {
      closeModal();
    }
  };
  root.addEventListener("keydown", handleKey, { once: false });
  state.modal.handleKey = handleKey;
  state.activeTrackId = track.id;

  if (!skipRouteUpdate) {
    updateRoute({ trackId: track.id });
  }
}

function closeModal(options) {
  let skipRouteUpdate = false;
  if (options instanceof Event) {
    options.preventDefault?.();
  } else if (options && typeof options === "object") {
    skipRouteUpdate = Boolean(options.skipRoute);
  }
  if (!state.modal) return;

  const { root, handleKey, closeButton, audioEl } = state.modal;
  root.classList.remove("is-open");
  root.setAttribute("hidden", "true");
  if (handleKey) {
    root.removeEventListener("keydown", handleKey);
    state.modal.handleKey = null;
  }
  audioEl.pause();
  audioEl.currentTime = 0;
  if (state.lastFocus instanceof HTMLElement) {
    state.lastFocus.focus();
  } else {
    closeButton.focus();
  }
  state.activeTrackId = null;
  if (!skipRouteUpdate) {
    updateRoute({ trackId: null }, { replace: true });
  }
}

function createModal() {
  const root = document.createElement("div");
  root.className = "music-modal";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.setAttribute("hidden", "true");

  const overlay = document.createElement("div");
  overlay.className = "music-modal__overlay";

  const dialog = document.createElement("div");
  dialog.className = "music-modal__dialog";
  dialog.tabIndex = -1;

  const header = document.createElement("header");
  header.className = "music-modal__header";

  const titleEl = document.createElement("h2");
  titleEl.className = "headline-4";

  const subtitleEl = document.createElement("p");
  subtitleEl.className = "music-modal__subtitle";

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.className = "music-modal__close";
  closeButton.setAttribute("aria-label", "Close track details");
  closeButton.innerHTML = "&times;";
  closeButton.addEventListener("click", closeModal);

  header.appendChild(titleEl);
  header.appendChild(subtitleEl);
  header.appendChild(closeButton);

  const body = document.createElement("div");
  body.className = "music-modal__body";

  const media = document.createElement("div");
  media.className = "music-modal__media";

  const coverEl = document.createElement("img");
  coverEl.alt = "";
  coverEl.setAttribute("hidden", "true");
  media.appendChild(coverEl);

  const audioWrap = document.createElement("div");
  audioWrap.className = "music-modal__audio";
  const audioEl = document.createElement("audio");
  audioEl.controls = true;
  audioEl.preload = "metadata";
  audioWrap.appendChild(audioEl);
  media.appendChild(audioWrap);

  const metaEl = document.createElement("div");
  metaEl.className = "music-modal__meta";

  const tagsEl = document.createElement("div");
  tagsEl.className = "music-modal__tags";

  const descriptionEl = document.createElement("div");
  descriptionEl.className = "music-modal__description";

  const lyricsSection = document.createElement("section");
  lyricsSection.className = "music-modal__lyrics";
  lyricsSection.setAttribute("hidden", "true");

  const lyricsHeading = document.createElement("h3");
  lyricsHeading.className = "music-modal__lyrics-heading";
  lyricsHeading.textContent = "Lyrics";

  const lyricsBody = document.createElement("div");
  lyricsBody.className = "music-modal__lyrics-body";

  lyricsSection.appendChild(lyricsHeading);
  lyricsSection.appendChild(lyricsBody);

  body.appendChild(media);
  body.appendChild(metaEl);
  body.appendChild(tagsEl);
  body.appendChild(descriptionEl);
  body.appendChild(lyricsSection);

  const footer = document.createElement("footer");
  footer.className = "music-modal__footer";

  const actions = document.createElement("div");
  actions.className = "music-modal__actions";

  const downloadLink = document.createElement("a");
  downloadLink.className = "button button--secondary music-modal__download";
  downloadLink.textContent = "Download";
  downloadLink.setAttribute("aria-disabled", "true");
  downloadLink.setAttribute("target", "_blank");
  downloadLink.setAttribute("rel", "noopener noreferrer");

  actions.appendChild(downloadLink);
  footer.appendChild(actions);

  dialog.appendChild(header);
  dialog.appendChild(body);
  dialog.appendChild(footer);

  root.appendChild(overlay);
  root.appendChild(dialog);

  root.addEventListener("click", (event) => {
    if (event.target === root || event.target === overlay) {
      closeModal();
    }
  });

  return {
    root,
    overlay,
    dialog,
    titleEl,
    subtitleEl,
    audioEl,
    coverEl,
    tagsEl,
    metaEl,
    descriptionEl,
    lyricsSection,
    lyricsBody,
    downloadLink,
    closeButton,
    handleKey: null,
  };
}

function normalizeRoute(route = {}) {
  const trackId =
    typeof route.trackId === "string" && route.trackId.trim() ? route.trackId.trim() : null;
  return { trackId };
}

function getRouteFromLocation() {
  try {
    const url = new URL(window.location.href);
    return normalizeRoute({
      trackId: url.searchParams.get("track"),
    });
  } catch {
    return normalizeRoute();
  }
}

function routesEqual(a, b) {
  return a.trackId === b.trackId;
}

function updateRoute(route, options = {}) {
  if (typeof window === "undefined" || !window.history || !window.history.pushState) return;
  const { replace = false } = options;
  const nextRoute = normalizeRoute(route);
  const currentRoute = getRouteFromLocation();
  if (routesEqual(currentRoute, nextRoute)) return;

  const url = new URL(window.location.href);
  if (nextRoute.trackId) {
    url.searchParams.set("track", nextRoute.trackId);
  } else {
    url.searchParams.delete("track");
  }
  const target = `${url.pathname}${url.search}${url.hash}`;
  const method = replace ? "replaceState" : "pushState";
  window.history[method]({ music: true, route: nextRoute }, "", target);
}

async function syncRouteFromLocation(options = {}) {
  if (isSyncingRoute) return;
  if (!state.tracks.length) return;
  const { initialLoad = false } = options;
  isSyncingRoute = true;
  try {
    const route = getRouteFromLocation();
    const trackId = route.trackId;
    if (!trackId) {
      if (state.modal && state.activeTrackId !== null) {
        closeModal({ skipRoute: true });
      }
      return;
    }

    const track =
      state.filteredTracks.find((item) => item.id === trackId) ||
      state.tracks.find((item) => item.id === trackId);
    if (!track) {
      if (!initialLoad) {
        updateRoute({ trackId: null }, { replace: true });
      }
      return;
    }

    openModal(track, { skipRouteUpdate: true });
  } finally {
    isSyncingRoute = false;
  }
}

function renderLoading(container, message) {
  container.innerHTML = `
    <section class="loading-state" aria-live="polite">
      <p>${escapeHtml(message)}</p>
    </section>
  `;
}

function renderError(container, message) {
  container.innerHTML = `
    <section class="loading-state" role="alert">
      <p>${escapeHtml(message)}</p>
    </section>
  `;
}

async function fetchFirstJson(urls) {
  return fetchFirst(urls, async (response) => response.json());
}

async function fetchFirstText(urls) {
  return fetchFirst(urls, async (response) => response.text());
}

async function fetchFirst(urls, parser) {
  for (const url of urls) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) continue;
      return await parser(response);
    } catch (error) {
      console.warn("[music] fetch failed for", url, error);
    }
  }
  throw new Error("No sources responded");
}

function renderSiteChrome(siteConfig) {
  const header = document.getElementById("site-header");
  const nav = document.getElementById("site-nav");
  const footer = document.getElementById("site-footer");

  const site = siteConfig?.site ?? {};
  const navigation = Array.isArray(siteConfig?.navigation) ? siteConfig.navigation : [];
  const footerConfig = siteConfig?.footer ?? {};

  if (header) {
    header.innerHTML = `
      <div class="site-brand">
        <span class="pill">${escapeHtml(site.tagline || "Music Catalog")}</span>
        <h1 class="headline-3">${escapeHtml(site.title || "SmileCMS")}</h1>
      </div>
      <div class="site-actions">
        <button class="button button--secondary" data-theme-toggle aria-pressed="false">
          Toggle theme
        </button>
      </div>
    `;
  }

  if (nav) {
    nav.innerHTML = "";
    const currentPath = window.location.pathname.replace(/index\.html$/, "");
    const normalizedCurrent = normalizeNavPath(currentPath);

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "nav-toggle";
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-controls", "nav-menu");
    toggle.innerHTML = `
      <span class="nav-toggle__label">Menu</span>
      <span class="nav-toggle__icon" aria-hidden="true"></span>
    `;

    const list = document.createElement("ul");
    list.className = "nav-list";
    list.id = "nav-menu";
    list.setAttribute("role", "menubar");
    list.dataset.open = "false";

    navigation.forEach((entry) => {
      const href = entry.href || "#";
      const label = entry.label || "Link";
      const normalizedHref = normalizeNavPath(href);
      const li = document.createElement("li");
      li.setAttribute("role", "none");
      const link = document.createElement("a");
      link.className = "nav-link";
      link.setAttribute("role", "menuitem");
      link.href = href;
      link.textContent = label;
      if (
        normalizedHref === normalizedCurrent ||
        entry.active ||
        label.toLowerCase() === "music"
      ) {
        link.setAttribute("aria-current", "page");
      }
      li.appendChild(link);
      list.appendChild(li);
    });

    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      list.dataset.open = String(!expanded);
    });

    list.addEventListener("click", (event) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.matches(".nav-link")) {
        toggle.setAttribute("aria-expanded", "false");
        list.dataset.open = "false";
      }
    });

    nav.appendChild(toggle);
    nav.appendChild(list);
  }

  if (footer) {
    footer.innerHTML = `
      <p>${escapeHtml(footerConfig.copy || "")}</p>
      <div class="footer-links">
        ${(footerConfig.links || [])
          .map(
            (entry) =>
              `<a href="${escapeHtml(entry.href || "#")}" target="_blank" rel="noopener">${escapeHtml(
                entry.label || "Link"
              )}</a>`
          )
          .join("")}
      </div>
    `;
  }

  attachThemeToggle(header);
}

function attachThemeToggle(header) {
  if (!header) return;
  const shell = document.getElementById("app-shell");
  if (!shell) return;

  header.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.matches("[data-theme-toggle]")) {
      const next = shell.dataset.theme === "dark" ? "light" : "dark";
      shell.dataset.theme = next;
      document.documentElement.dataset.theme = next;
      target.setAttribute("aria-pressed", String(next === "dark"));
    }
  });
}

function resetThemeToggle() {
  const shell = document.getElementById("app-shell");
  if (shell && shell.dataset.theme) {
    document.documentElement.dataset.theme = shell.dataset.theme;
  }
}

function resolveMediaVariant(variants = {}, preferred = []) {
  if (!variants || typeof variants !== "object") return null;
  for (const profile of preferred) {
    if (variants[profile]) {
      return resolveMediaPath(variants[profile]);
    }
  }
  const values = Object.values(variants);
  if (values.length) {
    return resolveMediaPath(values[0]);
  }
  return null;
}

function resolveMediaPath(path) {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  const normalized = path.startsWith("/") ? path.slice(1) : path;
  return `${state.mediaBasePath}/${normalized}`;
}

function normalizeNavPath(path) {
  if (typeof path !== "string" || !path) return "/";
  const trimmed = path.replace(/index\.html$/, "");
  if (!trimmed || trimmed === ".") return "/";
  return trimmed.endsWith("/") ? trimmed : `${trimmed}/`;
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatDate(value) {
  if (!value) return "";
  try {
    const date = new Date(value);
    return new Intl.DateTimeFormat("en", {
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(date);
  } catch {
    return value;
  }
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  const remaining = rounded % 60;
  return `${minutes}:${remaining.toString().padStart(2, "0")}`;
}

function truncate(text, length) {
  if (!text) return "";
  const clean = String(text).trim();
  if (clean.length <= length) return clean;
  return `${clean.slice(0, length - 1).trim()}…`;
}

resetThemeToggle();
