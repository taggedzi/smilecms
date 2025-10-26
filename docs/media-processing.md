# Media Processing

This document explains how SmileCMS generates image derivatives and how to configure watermarking and embedded copyright/licensing metadata.

## Overview

- The build collects media references in your content and generates one or more image derivatives per asset (by default: `thumb` and `large`).
- Generation happens in `src/media/processor.py` and is driven by `media_processing` in `smilecms.yml`.
- The pipeline resizes images, writes them in the configured format/quality, and can optionally:
  - Overlay a subtle, tiled watermark across the image.
  - Embed copyright/licensing metadata into the output file (EXIF for JPEG/TIFF and tEXt chunks for PNG).

All image derivatives (including thumbnails) receive the watermark and embedded metadata when enabled.

## Derivative Profiles

Profiles define the variant set (size/format/quality). Defaults are:

- `thumb`: 320×320 max, WEBP at quality 75.
- `large`: 1920px wide (auto height), JPEG at quality 85.

You can customize or add profiles under `media_processing.profiles` in `smilecms.yml`.

## Watermarking

When enabled, a semi-transparent text watermark is tiled across the image and rotated for a subtle but visible pattern. The overlay alpha, color, density, and rotation are configurable.

YAML example:

```yaml
media_processing:
  watermark:
    enabled: true
    text: "© Your Site Name"
    opacity: 32          # 0–255; higher = more visible
    color: "#FFFFFF"     # hex color
    angle: 30            # degrees
    font_path: "media/fonts/YourFont.ttf"  # optional
    font_size_ratio: 0.05 # as fraction of min(image width,height)
    spacing_ratio: 0.6    # controls tiling density
    min_size: 256         # skip very small images
```

Notes:

- If `font_path` is not set, Pillow’s default font is used (works, but a TTF is recommended for predictable sizing).
- `min_size` prevents watermarking tiny images; thumbnails will still be watermarked if they exceed this threshold.

## Embedded Metadata

When enabled, basic copyright/licensing details are embedded in each output file:

- JPEG/TIFF: EXIF tags
  - Artist (0x013B)
  - Copyright (0x8298)
  - ImageDescription (0x010E) – used to store License and URL if provided
- PNG: tEXt chunks
  - Author, Copyright, License, URL
- Other formats (WEBP, GIF, BMP) are skipped to avoid compatibility issues.

YAML example:

```yaml
media_processing:
  embed_metadata:
    enabled: true
    artist: "Your Name or Org"
    copyright: "© 2025 Your Name or Org"
    license: "CC BY-NC-SA 4.0"
    url: "https://example.com"
```

Values are optional; only provided fields are written.

## Caching and Rebuilds

Derivative caching is based on source/destination timestamps. Changing watermark or metadata settings does not automatically invalidate previously generated files. To reprocess everything with new settings, run:

```bash
smilecms clean         # removes site/ and media/derived/
smilecms build
```

Alternatively, touch/replace the original source images to force regeneration.

### Gallery integration and sidecars

- Gallery sidecars are treated as user-owned metadata files. During a normal build, existing sidecars are not modified; only missing sidecars are generated for new images.
- ML captioning/tagging (when enabled) runs only for images missing sidecars to keep large galleries fast.
- To regenerate one image’s sidecar, delete its sidecar file and run `smilecms build`. To refresh all gallery sidecars at once, run `smilecms build --refresh-gallery`.

## Troubleshooting

- Watermark not visible: increase `opacity`, reduce `spacing_ratio`, or lower `min_size` to include thumbnails.
- Font not applied: verify `font_path` exists and is readable; otherwise the default font is used.
- Metadata missing in viewers: support varies by viewer and format. Prefer JPEG/TIFF for EXIF and PNG for tEXt chunks.

## Related Files

- `src/config.py` — configuration models (`MediaWatermarkConfig`, `MediaMetadataEmbedConfig`).
- `src/media/processor.py` — resize, watermark overlay, and metadata embedding.

