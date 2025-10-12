# Front-End Architecture Overview

This document captures the layout, design tokens, and rendering approach for the SmileCMS web front end.

## Directory Structure

```
web/
├── index.html          # Shell document and base layout regions
├── js/
│   ├── app.js          # Entry point wiring configuration + renderer bootstrap
│   └── renderer.js     # Manifest fetch + template hydration + interactions
├── styles/
│   ├── tokens.css      # Design tokens (colors, typography, spacing)
│   ├── base.css        # Global resets, background, accessibility affordances
│   ├── layout.css      # Grid & layout primitives (shell, sections, footer)
│   ├── typography.css  # Text styles, buttons, pills
│   └── components.css  # Cards, tiles, navigation, hero banner, sections
├── templates/          # HTML <template> files for modular sections/tiles
└── config/site.json    # Front-end configuration (nav, hero, sections, footer)
```

## Visual Direction

- **Theme**: Dark, moody canvas with soft gradients and luminous accents inspired by art gallery lighting.
- **Typography**: Sans-serif base (`Inter`) paired with a serif display (`DM Serif Display`) for headlines; uppercase pills for metadata.
- **Color Palette**:
  - Background: `#0f1117`
  - Surfaces: `#171b24` / `#1f2430`
  - Accent: `#8fbbff` → `#4f9dff`
  - Supporting: teal success (`#4ac9a5`), gold warning (`#f6c64b`), coral danger (`#ff7a7d`)
- **Depth**: Layered gradients and blurred glows (`var(--shadow-soft)`) to frame hero and tiles.

## Layout Shell

- Skip link for keyboard navigation.
- `#app-shell` grid with header → nav → main → footer.
- `main` will contain modular sections rendered from manifests (gallery, articles, audio).

## Next Steps

1. Build additional templates or variants as the content model evolves (e.g., video tiles, spotlight sections).
2. Extend `renderer.js` filters to support pagination or more complex rules when multiple manifest pages exist.
3. Add progressive enhancement hooks (intersection observers, smooth theme transitions) as needed.

The CSS files already include design tokens and base component styles, so subsequent work can focus on wiring data into templates while keeping accessibility and responsiveness intact.
