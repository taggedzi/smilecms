import { initializeRenderer } from "./renderer.js";

const DEFAULT_MANIFEST_BASES = ["./manifests/content", "/site/manifests/content"];
const DEFAULT_SITE_CONFIG_URLS = ["./config/site.json", "/site/config/site.json"];

document.addEventListener("DOMContentLoaded", () => {
  try {
    const main = document.getElementById("main");
    if (!shouldHydrateHome(main)) {
      return;
    }

    const data = window.__SMILE_DATA__ || {};

    const manifestBases = pickList(data.manifestBases, DEFAULT_MANIFEST_BASES);
    const siteConfigUrls = pickList(data.siteConfig, DEFAULT_SITE_CONFIG_URLS);
    const templateBases = pickList(data.templateBases, undefined);

    initializeRenderer({
      manifestUrl: buildManifestCandidates(manifestBases),
      siteConfigUrl: siteConfigUrls,
      templateBases,
    });
  } catch (error) {
    console.error("[app] failed to initialize", error);
  }
});

function buildManifestCandidates(bases = [], page = 1) {
  const index = String(page).padStart(3, "0");
  return bases.map((base) => `${trimTrailingSlash(base)}-${index}.json`);
}

function pickList(value, fallback) {
  if (Array.isArray(value) && value.length) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    return value
      .split(/\s+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return fallback;
}

function trimTrailingSlash(value) {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

function shouldHydrateHome(main) {
  if (!main) return false;
  if (!main.classList.contains("site-main")) {
    return false;
  }
  return main.classList.length === 1;
}
