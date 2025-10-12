export function initializeRenderer({ manifestUrl }) {
  const main = document.getElementById("main");
  if (!main) return;

  main.innerHTML = `
    <section class="loading-state" aria-live="polite">
      <p>Front-end renderer not yet implemented.</p>
    </section>
  `;
  console.debug("[renderer] initialize placeholder with manifest:", manifestUrl);
}
