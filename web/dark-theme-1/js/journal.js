const TEMPLATE_SOURCES = [
  "../templates/header.html",
  "../templates/nav.html",
  "../templates/footer.html",
];

const MANIFEST_URLS = ["../manifests/content-001.json", "/site/manifests/content-001.json"];
const SITE_CONFIG_URLS = ["../config/site.json", "/site/config/site.json"];

document.addEventListener("DOMContentLoaded", () => {
  initializeJournal();
});

async function initializeJournal() {
  const main = document.getElementById("main");
  if (!main) return;

  renderLoading(main, "Loading journal entries…");

  try {
    await loadTemplates();
    const [manifest, siteConfig] = await Promise.all([
      fetchJson(MANIFEST_URLS),
      fetchJson(SITE_CONFIG_URLS),
    ]);

      renderSiteChrome(siteConfig);
    const articles = (manifest?.items ?? []).filter(
      (item) => item.content_type === "article" && item.status === "published"
    );
    renderJournal(main, articles);
  } catch (error) {
    console.error("[journal] Failed to initialize", error);
    renderError(
      main,
      "We hit a snag loading the journal. Please refresh the page and try again."
    );
  }
}

function renderSiteChrome(siteConfig) {
  const headerEl = document.getElementById("site-header");
  const navEl = document.getElementById("site-nav");
  const footerEl = document.getElementById("site-footer");

  if (!headerEl || !navEl || !footerEl) return;

  headerEl.innerHTML = "";
  navEl.innerHTML = "";
  footerEl.innerHTML = "";

  renderHeader(headerEl, siteConfig.site);
  renderNavigation(navEl, siteConfig.navigation);
  renderFooter(footerEl, siteConfig.footer);
}

function renderJournal(container, articles) {
  container.innerHTML = "";

  const hero = document.createElement("section");
  hero.className = "journal-hero";
  hero.innerHTML = `
    <div class="journal-hero__content">
      <span class="pill pill--light">Browse Archives</span>
      <h1 class="headline-2">Journal & Articles</h1>
      <p>Search and sort published entries, then dive into the full story.</p>
    </div>
  `;

  const controls = document.createElement("section");
  controls.className = "journal-controls";
  controls.innerHTML = `
    <div class="journal-search">
      <label class="visually-hidden" for="journal-search">Search articles</label>
      <input
        type="search"
        id="journal-search"
        name="search"
        placeholder="Search by title, tags, or summary…"
        autocomplete="off"
      />
    </div>
    <div class="journal-sort">
      <label class="visually-hidden" for="journal-sort">Sort articles</label>
      <select id="journal-sort" name="sort">
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
        <option value="title-asc">Title A → Z</option>
        <option value="title-desc">Title Z → A</option>
        <option value="reading">Shortest read</option>
      </select>
    </div>
    <div class="journal-count" aria-live="polite"></div>
  `;

  const resultsSection = document.createElement("section");
  resultsSection.className = "journal-results";
  const grid = document.createElement("div");
  grid.className = "journal-grid";
  resultsSection.appendChild(grid);

  container.appendChild(hero);
  container.appendChild(controls);
  container.appendChild(resultsSection);

  const searchInput = controls.querySelector("#journal-search");
  const sortSelect = controls.querySelector("#journal-sort");
  const countEl = controls.querySelector(".journal-count");

  const state = {
    query: "",
    sort: "newest",
  };

  function applyFilters() {
    let results = [...articles];
    if (state.query) {
      const q = state.query.toLowerCase();
      results = results.filter((item) => {
        const haystack = [
          item.title,
          item.summary,
          item.excerpt,
          ...(item.tags ?? []),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(q);
      });
    }

    switch (state.sort) {
      case "oldest":
        results.sort((a, b) => compareDates(a, b));
        break;
      case "title-asc":
        results.sort((a, b) => a.title.localeCompare(b.title));
        break;
      case "title-desc":
        results.sort((a, b) => b.title.localeCompare(a.title));
        break;
      case "reading":
        results.sort(
          (a, b) =>
            (a.reading_time_minutes ?? Number.MAX_SAFE_INTEGER) -
            (b.reading_time_minutes ?? Number.MAX_SAFE_INTEGER)
        );
        break;
      case "newest":
      default:
        results.sort((a, b) => compareDates(b, a));
        break;
    }

    renderResults(results);
  }

  function renderResults(results) {
    grid.innerHTML = "";

    if (!results.length) {
      const empty = document.createElement("p");
      empty.className = "journal-empty";
      empty.textContent =
        state.query.length > 0
          ? `No articles match “${state.query}”. Try another search term.`
          : "No articles published yet. Check back soon.";
      grid.appendChild(empty);
      countEl.textContent = "0 results";
      return;
    }

    countEl.textContent =
      results.length === 1 ? "1 result" : `${results.length} results`;

    results.forEach((item) => {
      const card = document.createElement("article");
      card.className = "journal-card";
      card.innerHTML = `
        <header class="journal-card__header">
          <div class="journal-card__meta">
            ${item.published_at ? `<span>${formatDate(item.published_at)}</span>` : ""}
            ${
              item.reading_time_minutes
                ? `<span>${item.reading_time_minutes} min read</span>`
                : ""
            }
          </div>
          <h2 class="journal-card__title">
            <a href="../posts/${item.slug}/">${escapeHtml(item.title)}</a>
          </h2>
        </header>
        ${
          item.summary || item.excerpt
            ? `<p class="journal-card__excerpt">${escapeHtml(
                item.summary ?? item.excerpt ?? ""
              )}</p>`
            : ""
        }
        ${renderTags(item.tags)}
      `;
      grid.appendChild(card);
    });
  }

  searchInput.addEventListener("input", (event) => {
    state.query = event.target.value.trim();
    applyFilters();
  });

  sortSelect.addEventListener("change", (event) => {
    state.sort = event.target.value;
    applyFilters();
  });

  applyFilters();
}

function renderTags(tags = []) {
  if (!tags.length) return "";
  const tagMarkup = tags
    .map((tag) => `<li><span class="pill pill--light">#${escapeHtml(tag)}</span></li>`)
    .join("");
  return `<ul class="journal-card__tags">${tagMarkup}</ul>`;
}

function compareDates(a, b) {
  const aDate = Date.parse(a.published_at || a.updated_at || "");
  const bDate = Date.parse(b.published_at || b.updated_at || "");
  return (aDate || 0) - (bDate || 0);
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

async function fetchJson(urls) {
  const candidates = Array.isArray(urls) ? urls : [urls];
  let lastError;
  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      const response = await fetch(candidate, { cache: "no-cache" });
      if (!response.ok) {
        throw new Error(`Failed to fetch ${candidate} (${response.status})`);
      }
      return await response.json();
    } catch (error) {
      lastError = error;
      console.debug("[journal] fetch attempt failed", candidate, error);
    }
  }
  throw lastError ?? new Error("fetchJson requires at least one URL");
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

  const normalized = navigation.map((entry) => normalizeNavEntry(entry));

  normalized.forEach((entry) => {
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

function normalizeNavEntry(entry) {
  const label = entry.label ?? "";
  const result = { ...entry };
  const lower = label.toLowerCase();

  if (lower === "home") {
    result.href = "../index.html";
  } else if (lower === "journal") {
    result.href = "./";
    result.active = true;
  } else if (lower === "gallery") {
    result.href = "../index.html#gallery";
  } else if (lower === "audio") {
    result.href = "../index.html#audio";
  } else {
    result.href = entry.href;
  }

  return result;
}

function renderFooter(container, footer = {}) {
  if (!container) {
    return;
  }

  container.innerHTML = "";

  const template = useTemplate("tmpl-site-footer");
  const linkTemplate = useTemplate("tmpl-footer-link");

  let fragment;
  if (template) {
    fragment = template.cloneNode(true);
  } else {
    fragment = document.createDocumentFragment();
    const left = document.createElement("div");
    left.className = "footer-left";
    const copySpan = document.createElement("span");
    copySpan.className = "caption";
    left.appendChild(copySpan);

    const right = document.createElement("div");
    right.className = "footer-right";

    fragment.appendChild(left);
    fragment.appendChild(right);
  }

  const copyTarget =
    typeof fragment.querySelector === "function"
      ? fragment.querySelector("[data-footer-copy]")
      : null;
  if (copyTarget) {
    copyTarget.textContent = footer.copy || "";
  } else {
    const fallbackCopy = fragment.querySelector(".footer-left .caption");
    if (fallbackCopy) {
      fallbackCopy.textContent = footer.copy || "";
    }
  }

  const linksTarget =
    typeof fragment.querySelector === "function"
      ? fragment.querySelector("[data-footer-links]")
      : null;
  const linkContainer =
    linksTarget || fragment.querySelector(".footer-right") || container;

  if (linkContainer && Array.isArray(footer.links)) {
    footer.links.forEach((entry) => {
      const resolved = normalizeFooterEntry(entry);
      let linkFragment = null;
      let anchor = null;

      if (linkTemplate) {
        linkFragment = linkTemplate.cloneNode(true);
        anchor =
          typeof linkFragment.querySelector === "function"
            ? linkFragment.querySelector("a")
            : null;
      }

      if (!anchor) {
        anchor = document.createElement("a");
        anchor.className = "nav-link";
        linkFragment = anchor;
      }

      anchor.textContent = resolved.label;
      anchor.href = resolved.href;
      if (resolved.target) {
        anchor.target = resolved.target;
      }
      if (resolved.rel) {
        anchor.rel = resolved.rel;
      }

      if (linkFragment instanceof HTMLElement) {
        linkContainer.appendChild(linkFragment);
      } else if (linkFragment) {
        linkContainer.appendChild(linkFragment);
      } else {
        linkContainer.appendChild(anchor);
      }
    });
  }

  container.appendChild(fragment);
}

function useTemplate(id) {
  const template = document.getElementById(id);
  if (!template) {
    throw new Error(`Template ${id} not found`);
  }
  return template.content || template;
}

function normalizeFooterEntry(entry = {}) {
  const label = entry.label || "Link";
  const href = entry.href || "#";
  const isExternal = entry.external ?? /^https?:\/\//i.test(href);
  const target = entry.target || (isExternal ? "_blank" : undefined);
  const rel =
    entry.rel || (target === "_blank" ? "noreferrer noopener" : undefined);

  return {
    label,
    href,
    target,
    rel,
  };
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

function escapeHtml(value = "") {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
