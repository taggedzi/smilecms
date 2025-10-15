import { initializeRenderer } from "./renderer.js";

const MANIFEST_BASES = ["./manifests/content", "/site/manifests/content"];

const config = {
  manifestUrl: buildManifestCandidates(MANIFEST_BASES),
  siteConfigUrl: "./config/site.json",
};

document.addEventListener("DOMContentLoaded", () => {
  initializeRenderer(config);
});

function buildManifestCandidates(bases = [], page = 1) {
  const index = String(page).padStart(3, "0");
  return bases.map((base) => `${base}-${index}.json`);
}
