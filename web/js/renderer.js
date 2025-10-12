const TEMPLATE_CACHE = new Map();
const TEMPLATE_SOURCES = [
  "./templates/header.html",
  "./templates/nav.html",
  "./templates/hero.html",
  "./templates/section.html",
  "./templates/tile-article.html",
  "./templates/tile-gallery.html",
  "./templates/tile-audio.html",
  "./templates/footer.html",
];

export async function initializeRenderer({
  manifestUrl,
  siteConfigUrl = "./config/site.json",
} = {}) {
  const main = document.getElementById("main");
  if (!main) return;

  renderLoading(main, "Loading content…");

  try {
    await loadTemplates();
    const [manifest, siteConfig] = await Promise.all([
      fetchJson(manifestUrl),
      fetchJson(siteConfigUrl),
    ]);

    renderSite({ manifest, siteConfig });
  } catch (error) {
    console.error("[renderer] Failed to initialize", error);
    renderError(
      main,
      "We hit a snag loading the site data. Please refresh or check the console for details."
    );
  }
}

function renderSite({ manifest, siteConfig }) {
  const headerEl = document.getElementById("site-header");
  const navEl = document.getElementById("site-nav");
  const mainEl = document.getElementById("main");
  const footerEl = document.getElementById("site-footer");

  if (!headerEl || !navEl || !mainEl || !footerEl) {
    console.warn("[renderer] Missing core layout containers.");
    return;
  }

  const items = manifest?.items ?? [];
  const mediaBasePath = siteConfig.mediaBasePath ?? "/media/derived";

  headerEl.innerHTML = "";
  navEl.innerHTML = "";
  mainEl.innerHTML = "";
  footerEl.innerHTML = "";

  attachThemeToggle(headerEl);
  renderHeader(headerEl, siteConfig.site);
  renderNavigation(navEl, siteConfig.navigation);
  renderHero(mainEl, siteConfig.hero);
  renderSections(mainEl, siteConfig.sections ?? [], items, mediaBasePath);
  renderFooter(footerEl, siteConfig.footer);
}

async function fetchJson(url) {
  if (!url) throw new Error("fetchJson requires a URL");
  const response = await fetch(url, { cache: "no-cache" });
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url} (${response.status})`);
  }
  return response.json();
}

function renderLoading(container, message) {
  container.innerHTML = `
    <section class="loading-state" aria-live="polite">
      <p>${message}</p>
    </section>
  `;
}

function renderError(container, message) {
  container.innerHTML = `
    <section class="loading-state" role="alert">
      <p>${message}</p>
    </section>
  `;
}

function renderHeader(container, site) {
  const template = useTemplate("tmpl-site-header");
  const node = template.cloneNode(true);
  const titleEl = node.querySelector("h1");
  const pill = node.querySelector(".pill");

  if (titleEl) {
    titleEl.textContent = site?.title ?? "SmileCMS";
  }
  if (pill && site?.tagline) {
    pill.textContent = site.tagline;
  }

  container.appendChild(node);
}

function renderNavigation(container, navigation = []) {
  const navTemplate = useTemplate("tmpl-site-nav");
  const itemTemplate = useTemplate("tmpl-nav-item");
  const navNode = navTemplate.cloneNode(true);
  const list = navNode.querySelector(".nav-list");
  const toggle = navNode.querySelector(".nav-toggle");

  if (!list) return;

  navigation.forEach((entry) => {
    const itemNode = itemTemplate.cloneNode(true);
    const link = itemNode.querySelector("[data-nav-target]");
    if (link) {
      link.textContent = entry.label;
      link.href = entry.href ?? "#";
      if (entry.active) {
        link.setAttribute("aria-current", "page");
      }
    }
    list.appendChild(itemNode);
  });

  if (toggle) {
    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      list.dataset.open = String(!expanded);
    });
  }

  container.appendChild(navNode);
}

function renderHero(container, hero = {}) {
  const template = useTemplate("tmpl-hero-banner");
  const actionTemplate = useTemplate("tmpl-hero-action");
  const node = template.cloneNode(true);

  const eyebrow = node.querySelector("[data-hero-eyebrow]");
  const title = node.querySelector("[data-hero-title]");
  const subtitle = node.querySelector("[data-hero-subtitle]");
  const actions = node.querySelector("[data-hero-actions]");

  if (eyebrow) eyebrow.textContent = hero.eyebrow ?? "Featured";
  if (title) title.textContent = hero.title ?? "Welcome to SmileCMS";
  if (subtitle) subtitle.textContent = hero.subtitle ?? "";

  if (actions && Array.isArray(hero.actions)) {
    hero.actions.forEach((action) => {
      const actionNode = actionTemplate.cloneNode(true);
      const link = actionNode.querySelector("[data-hero-action]");
      if (link) {
        link.textContent = action.label;
        link.href = action.href ?? "#";
      }
      actions.appendChild(actionNode);
    });
  }

  container.appendChild(node);
}

function renderSections(container, sections, items, mediaBasePath) {
  sections.forEach((sectionConfig) => {
    const template = useTemplate("tmpl-section");
    const actionTemplate = useTemplate("tmpl-section-action");
    const node = template.cloneNode(true);

    const eyebrow = node.querySelector("[data-section-eyebrow]");
    const title = node.querySelector("[data-section-title]");
    const actions = node.querySelector("[data-section-actions]");
    const grid = node.querySelector("[data-section-grid]");

    if (eyebrow) eyebrow.textContent = sectionConfig.eyebrow ?? "";
    if (title) title.textContent = sectionConfig.title ?? "";
    if (actions && Array.isArray(sectionConfig.actions)) {
      sectionConfig.actions.forEach((action) => {
        const actionNode = actionTemplate.cloneNode(true);
        const link = actionNode.querySelector("[data-section-action]");
        if (link) {
          link.textContent = action.label;
          link.href = action.href ?? "#";
        }
        actions.appendChild(actionNode);
      });
    }

    const filteredItems = filterItems(items, sectionConfig.filters).slice(
      0,
      sectionConfig.limit ?? items.length
    );

    if (!filteredItems.length) {
      const message = document.createElement("p");
      message.className = "body-text";
      message.textContent =
        sectionConfig.empty?.message ?? "No entries yet. Check back soon.";
      grid?.appendChild(message);
    } else {
      filteredItems.forEach((item) => {
        const tileNode = renderTile(sectionConfig.type, item, mediaBasePath);
        if (tileNode) {
          grid?.appendChild(tileNode);
        }
      });
    }

    node.id = sectionConfig.id ?? "";
    container.appendChild(node);
  });
}

function renderTile(type, item, mediaBasePath) {
  switch (type) {
    case "gallery":
      return renderGalleryTile(item, mediaBasePath);
    case "audio":
      return renderAudioTile(item, mediaBasePath);
    case "article":
    default:
      return renderArticleTile(item);
  }
}

function renderArticleTile(item) {
  const template = useTemplate("tmpl-tile-article");
  const node = template.cloneNode(true);

  const date = node.querySelector("[data-tile-date]");
  const tags = node.querySelector("[data-tile-tags]");
  const link = node.querySelector("[data-tile-link]");
  const excerpt = node.querySelector("[data-tile-excerpt]");
  const readingTime = node.querySelector("[data-tile-reading-time]");

  if (date && item.published_at) {
    date.textContent = formatDate(item.published_at);
  }
  if (tags) {
    tags.textContent = formatTags(item.tags);
  }
  if (link) {
    link.textContent = item.title ?? item.slug;
    link.href = item.canonical_url ?? `/posts/${item.slug}/`;
  }
  if (excerpt) {
    excerpt.textContent = item.excerpt ?? item.summary ?? "";
  }
  if (readingTime) {
    const time = item.reading_time_minutes ?? 0;
    readingTime.textContent =
      time > 0 ? `${time} min read` : "Quick read";
  }

  return node;
}

function renderGalleryTile(item, mediaBasePath) {
  const template = useTemplate("tmpl-tile-gallery");
  const node = template.cloneNode(true);

  const img = node.querySelector("[data-tile-image]");
  const caption = node.querySelector("[data-tile-caption]");
  const count = node.querySelector("[data-tile-count]");
  const tags = node.querySelector("[data-tile-tags]");
  const link = node.querySelector("[data-tile-link]");

  const heroVariant = selectVariant(item.hero_media, ["thumb", "large", "original"]);
  if (img && heroVariant) {
    img.src = resolveMediaPath(heroVariant.path, mediaBasePath);
    img.alt = item.hero_media?.alt_text ?? item.title ?? "";
  }
  if (caption && item.hero_media?.title) {
    caption.textContent = item.hero_media.title;
  }
  if (count) {
    count.textContent = `${item.asset_count ?? 0} assets`;
  }
  if (tags) {
    tags.textContent = formatTags(item.tags);
  }
  if (link) {
    link.textContent = item.title ?? item.slug;
    link.href = item.canonical_url ?? `/gallery/${item.slug}/`;
  }

  return node;
}

function renderAudioTile(item, mediaBasePath) {
  const template = useTemplate("tmpl-tile-audio");
  const node = template.cloneNode(true);

  const genre = node.querySelector("[data-tile-genre]");
  const title = node.querySelector("[data-tile-title]");
  const description = node.querySelector("[data-tile-description]");
  const audio = node.querySelector("[data-tile-audio]");
  const meta = node.querySelector("[data-tile-meta]");

  if (genre) {
    genre.textContent = formatTags(item.tags, 1) || "Audio";
  }
  if (title) {
    title.textContent = item.title ?? item.slug;
  }
  if (description) {
    description.textContent = item.summary ?? item.excerpt ?? "";
  }

  const variant = selectVariant(item.hero_media, ["original", "large", "thumb"]);
  if (audio && variant) {
    audio.src = resolveMediaPath(variant.path, mediaBasePath);
  }

  if (meta) {
    const parts = [];
    if (item.published_at) parts.push(formatDate(item.published_at));
    if (item.duration) parts.push(`${Math.round(item.duration)}s`);
    meta.textContent = parts.join(" • ");
  }

  return node;
}

function renderFooter(container, footer = {}) {
  const template = useTemplate("tmpl-site-footer");
  const linkTemplate = useTemplate("tmpl-footer-link");
  const node = template.cloneNode(true);

  const copy = node.querySelector("[data-footer-copy]");
  const links = node.querySelector("[data-footer-links]");

  if (copy) {
    copy.textContent = footer.copy ?? "";
  }

  if (links && Array.isArray(footer.links)) {
    footer.links.forEach((entry) => {
      const linkNode = linkTemplate.cloneNode(true);
      const link = linkNode;
      link.textContent = entry.label;
      link.href = entry.href ?? "#";
      links.appendChild(linkNode);
    });
  }

  container.appendChild(node);
}

function useTemplate(id) {
  if (TEMPLATE_CACHE.has(id)) {
    return TEMPLATE_CACHE.get(id);
  }
  const template = document.getElementById(id);
  if (!template) {
    throw new Error(`Template ${id} not found`);
  }
  TEMPLATE_CACHE.set(id, template.content || template);
  return TEMPLATE_CACHE.get(id);
}

async function loadTemplates() {
  if (document.getElementById("tmpl-site-header")) {
    return;
  }

  const host = document.getElementById("template-host") || document.body;
  const parser = new DOMParser();

  await Promise.all(
    TEMPLATE_SOURCES.map(async (path) => {
      const response = await fetch(path, { cache: "no-cache" });
      if (!response.ok) {
        throw new Error(`Failed to load template ${path}`);
      }
      const html = await response.text();
      const doc = parser.parseFromString(html, "text/html");
      doc.querySelectorAll("template").forEach((template) => {
        const imported = document.importNode(template, true);
        host.appendChild(imported);
      });
    })
  );
}

function filterItems(items, filters = {}) {
  return items.filter((item) => {
    if (filters.status && item.status !== filters.status) {
      return false;
    }
    if (filters.tagsAny && filters.tagsAny.length) {
      const itemTags = item.tags || [];
      if (!filters.tagsAny.some((tag) => itemTags.includes(tag))) {
        return false;
      }
    }
    if (filters.tagsAll && filters.tagsAll.length) {
      const itemTags = item.tags || [];
      if (!filters.tagsAll.every((tag) => itemTags.includes(tag))) {
        return false;
      }
    }
    return true;
  });
}

function selectVariant(media, preferredProfiles = []) {
  if (!media?.variants?.length) return null;
  for (const profile of preferredProfiles) {
    const match = media.variants.find((variant) => variant.profile === profile);
    if (match) return match;
  }
  return media.variants[0];
}

function resolveMediaPath(path, basePath) {
  if (!path) return "";
  if (path.startsWith("http")) return path;
  const normalized = path.startsWith("/") ? path.slice(1) : path;
  return `${basePath.replace(/\/$/, "")}/${normalized}`;
}

function formatDate(iso) {
  try {
    const date = new Date(iso);
    return new Intl.DateTimeFormat("en", {
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(date);
  } catch {
    return iso;
  }
}

function formatTags(tags = [], limit) {
  if (!tags.length) return "";
  const subset = limit ? tags.slice(0, limit) : tags;
  return subset.map((tag) => `#${tag}`).join(" ");
}

function attachThemeToggle(headerEl) {
  const shell = document.getElementById("app-shell");
  if (!shell) return;

  headerEl.addEventListener("click", (event) => {
    const target = event.target;
    if (
      target instanceof HTMLElement &&
      target.matches("[data-theme-toggle]")
    ) {
      const isDark = shell.dataset.theme !== "dark";
      shell.dataset.theme = isDark ? "dark" : "light";
      document.documentElement.dataset.theme = shell.dataset.theme;
      target.setAttribute("aria-pressed", String(isDark));
    }
  });
}
