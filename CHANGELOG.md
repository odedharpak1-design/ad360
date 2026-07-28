# Changelog
All notable changes to the AD360 website are documented in this file.

## [Unreleased]

### 2026-07-28 — Google Tag Manager: complete site-wide installation

**Type:** Technical / Tracking infrastructure
**Container ID:** `GTM-TQXBNP52`

#### Summary
Verified GTM installation across every HTML page in the project. `index.html` already
had the container installed correctly from a previous change. `404.html` did not —
this update brings it in line so tracking coverage is consistent across 100% of the
site's pages.

#### Changed files
- `404.html`
  - Added official GTM `<script>` snippet in `<head>`, immediately after the base
    `charset`/`viewport` meta tags (same position convention used in `index.html`).
  - Added official GTM `<noscript><iframe>` snippet immediately after the opening
    `<body>` tag.

#### Unchanged (verified, not modified)
- `index.html` — already had GTM correctly installed (1 script + 1 noscript, no
  duplicates); left untouched.
- All other files (`robots.txt`, `sitemap.xml`, `manifest.json`, `browserconfig.xml`,
  `humans.txt`, `assets/*`) — no changes.

#### Verification performed
- Confirmed `GTM-TQXBNP52` appears exactly twice in each HTML file (one `<script>` +
  one `<noscript>`) — no duplicate installations.
- Confirmed HTML tag balance (div/head/body/script/noscript/iframe/etc.) in `404.html`
  after the edit.
- Rendered `404.html` in a browser: page title, layout, and content unchanged;
  zero JavaScript console errors.

#### Impact
- **Visual/design:** None. Both snippets are invisible (background script +
  `0×0 display:none` iframe fallback).
- **SEO:** No impact — no meta/canonical/OG/heading changes.
- **Analytics (GA4):** No impact — GA4 was not added directly, per standing project
  rules. GA4 will only begin collecting data once a corresponding tag is configured
  inside this GTM container.
- **Netlify deployment:** No configuration changes required; deploys as a standard
  static file update.

---

## Previous entries

### 2026-07-27 — Google Tag Manager: initial installation (index.html)
- Added GTM `<script>` to `<head>` and `<noscript>` to `<body>` of `index.html`.
- Verified no pre-existing GTM code and no duplication.

### 2026-07-27 — Production readiness pass
- Extracted all inline Base64 images into real, named files under `/assets/img/`
  and `/assets/icons/`.
- Generated real favicon set (`favicon.ico`, Apple touch icon, Android icons,
  Windows tile) from the existing logo.
- Fixed non-functional contact form: converted to a real `<form>` with label,
  validation, and AJAX submission with success/error states
  (endpoint placeholder `YOUR_FORM_ID` still requires configuration before go-live).
- Fixed `og:image`/`twitter:image` to use a real absolute URL (1200×630 share image)
  instead of an unsupported data URI.
- Fixed WCAG AA color-contrast failures on small gold-colored labels.
- Added keyboard focus trap + `inert` background handling to the article modal.
- Added `<noscript>` fallback so content is not permanently invisible if JavaScript
  fails to load.
- Fixed 5 dead footer links to point to their corresponding sections.
- Generated `robots.txt`, `sitemap.xml`, `manifest.json`, `browserconfig.xml`,
  `humans.txt`, `404.html`.
