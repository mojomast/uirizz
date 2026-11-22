# Desktop half

`plugin.js` is a feature-detecting stub. It registers
`TOOL_MEDIA_RENDERER_AREA` for `a2ui_render` and returns the host fallback
until the official `@a2ui/react` renderer is bundled.

The committed production bundle must be built from sources plus a lockfile,
import only `@hermes/plugin-sdk`, and call the host through `ctx.rest`.
Do not load React from a CDN or pass absolute `https:` URLs to
`SDK.authedFetch`.
