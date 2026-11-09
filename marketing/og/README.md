# headshots — og:video

An 8-second silent clip and a matching still for link previews.

| File | Use | Spec |
|---|---|---|
| `og-video.mp4` | `og:video` | 1200×630, 8.0 s, 60 fps, H.264 High, yuv420p, BT.709, faststart, no audio, 1282 KB |
| `og-image.jpg` | `og:image` (the clip's end card) | 1200×630 JPEG |

- **Look:** a darkroom contact sheet: film strips snapping onto one grease-pencil eye line. It is drawn for this clip and deliberately does not copy the product's site styling.
- **Copy:** every word on screen was taken from this repository's own landing copy or README as of 2026-11-09. No numbers, scores, testimonials or customer names were added.
- **Status shown on screen:** “Example · AI-generated demo portraits”.
- **Shape:** the first three seconds carry the main motion idea; the last two hold the end card.
- `sha256(og-video.mp4)`: `c4da1e74c980a4276c1f1be5d47a67e6b2c034e14b1bb0ecb7726e7b81be0284`

## Using it

Nothing in this folder is wired into the site. To use it, host both files on the product's own domain and add, per page:

```html
<meta property="og:video" content="https://YOUR-DOMAIN/og/og-video.mp4">
<meta property="og:video:secure_url" content="https://YOUR-DOMAIN/og/og-video.mp4">
<meta property="og:video:type" content="video/mp4">
<meta property="og:video:width" content="1200">
<meta property="og:video:height" content="630">
<meta property="og:image" content="https://YOUR-DOMAIN/og/og-image.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
```

Most link previews show only the image, so set `og:image` wherever `og:video` is set. Change the file name when the clip changes, so cached previews refresh.

## Source

`source/` holds the film as code (`film.js`, `style.css`, `film.json`): one paused GSAP timeline rendered frame by frame in headless Chromium by the launch-film kit, then encoded with ffmpeg (`libx264 -crf 18 -pix_fmt yuv420p -movflags +faststart -an`). Re-rendering needs the kit; the files here are for review and for small copy edits.
