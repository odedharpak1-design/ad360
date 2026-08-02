# Changelog
All notable changes to the AD360 website are documented in this file.

## [Unreleased]

### 2026-08-02 — Fix: "קביעת פגישה" nav button text wrapping

**Type:** Bug fix / CSS only
**Priority:** Low visual defect, no functional/tracking/SEO impact

#### Summary
The highlighted "קביעת פגישה" nav button could wrap onto two lines at certain
desktop widths (reproduced consistently around ~1024px), making it visually
inconsistent with the rest of the navigation. Root cause: the button had no
`white-space: nowrap` or `flex-shrink: 0`, so the flex nav layout could compress
it below its natural content width under specific viewport widths.

While investigating, also found and fixed an 8px vertical misalignment between
the button and the plain-text nav links, caused by `.nav-links` relying on the
flex default `align-items: stretch` instead of an explicit `center`.

#### Changed files
- `index.html`
  - `.nav-cta`: added `white-space: nowrap`, `flex-shrink: 0`, and
    `display: inline-flex; align-items: center; justify-content: center;`
    for reliable single-line rendering and vertical centering.
  - `.nav-links > li:last-child`: added `flex-shrink: 0` so the button's
    container doesn't get compressed by the flex layout.
  - `.nav-links`: added explicit `align-items: center` (previously relied on
    the flex default `stretch`, which caused the alignment issue above).

#### Verification performed
- Reproduced the original bug precisely at 1024px width (button measured
  63×52px — wrapped to two lines) before applying the fix.
- After the fix, verified single-line rendering (130×34px, no wrap) and 0px
  vertical-center misalignment against sibling nav links at seven widths:
  901, 1024, 1152, 1280, 1366, 1440, 1920px.
- Confirmed no horizontal overflow introduced at any tested width.
- Confirmed mobile hamburger menu behavior unchanged.
- No other nav items, colors, fonts, or functionality touched.

#### Impact
- **Visual:** Button is slightly wider (only as wide as its single-line text
  requires); same color, shape, hover animation. No other visual change.
- **SEO / Analytics / GTM / Netlify:** None — CSS-only fix, no markup, text,
  links, or tracking code changed.

---

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
