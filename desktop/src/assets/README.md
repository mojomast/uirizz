# Material Icons font (vendored)

`material-icons.woff2` is the official ligature font used by A2UI's `Icon`
component (`<i class="material-icons">name</i>`).

- Package: `material-icons@1.13.14` (https://www.npmjs.com/package/material-icons)
- Upstream: Google Material Design Icons
- License: Apache License 2.0 (see `MATERIAL-ICONS-LICENSE`)
- SHA-256: 8265f64786397d6b832d1ca0aafdf149ad84e72759fffa9f7272e91a0fb015d1

Vendored so the Desktop card can render icons without a remote font CDN
(catalog security: no esm.sh / Google Fonts / other CDN loads from the pane).
Do not replace this with a `fonts.googleapis.com` or `fonts.gstatic.com` link.
