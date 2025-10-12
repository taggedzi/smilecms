import { initializeRenderer } from "./renderer.js";

const config = {
  manifestUrl: "/site/manifests/content-001.json",
  navConfigUrl: "/site/navigation.json", // future placeholder
};

document.addEventListener("DOMContentLoaded", () => {
  initializeRenderer(config);
});
