import { initializeRenderer } from "./renderer.js";

const config = {
  manifestUrl: ["./manifests/content-001.json", "/site/manifests/content-001.json"],
  siteConfigUrl: "./config/site.json",
};

document.addEventListener("DOMContentLoaded", () => {
  initializeRenderer(config);
});
