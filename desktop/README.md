# uirizz Desktop card

This package registers a `TOOL_MEDIA_RENDERER_AREA` renderer for `a2ui_render`.
Desktop and Webapp draw the official `@a2ui/react` surface in place of the
built-in player. CLI and other clients still see `fallback_text` from the
`MEDIA:` file.

Rebuild after source changes (from this directory):

```
npm ci
npm test
npm run build
```

Commit `desktop/plugin.js` and `desktop/package-lock.json` with the sources.
`npm run check-bundle` fails if the committed bundle is stale.

The bundle imports only `@hermes/plugin-sdk`, `react`, and `react/jsx-runtime`
from the host. `@a2ui/react`, `@a2ui/web_core`, and their runtime deps are
inlined. `openUrl` is registered as a no-op so the card never navigates.
Live refresh uses `ctx.rest('/surfaces/<id>')` every few seconds (and a
socket listener when the host offers one). Clicks POST to `ctx.rest('/actions')`.
Never open `file.path`; never attach authorization headers.

`.npmrc` sets `legacy-peer-deps=true` because `@a2ui/markdown-it@0.2.2` still
declares a peer on `@a2ui/web_core@^0.14.0` while `@a2ui/react@0.15.0` depends
on `@a2ui/web_core@^0.15.0`.
