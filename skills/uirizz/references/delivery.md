# Delivery — a stored surface is not a drawn card

Authoring (components, Express, layout) is in the main skill and the other
references. This file is the other half: `a2ui_render` returned `ok=true` and the
user sees nothing, or sees something that does not line up.

## Triage, in this order

1. **Prove the surface.** Replay its stored envelopes through the client's real
   `@a2ui/web_core` `MessageProcessor` with `rendererCatalogs()`:

   ```
   node <skill>/scripts/verify-surface.mjs ~/.hermes/plugin-data/uirizz/surfaces/<id>.json
   ```

   `surface_found: true`, `root_ok: true`, `errors: 0` ⇒ the content renders and
   every remaining suspect is client-side. An error here is the answer: fix the
   card, not the gallery.
2. **Read the gateway log** for
   `[Local] send_document fallback: native file send unavailable for .../surfaces/<id>.md`.
   That line means no renderer claimed the `MEDIA:` file and the reply degraded to
   a plain attachment attempt. A missing card and a missing file are ONE failure.
3. **Locate the renderer.** The drawing code is the desktop half,
   `~/.hermes/desktop-plugins/uirizz/plugin.js` (a copy of this plugin's
   `desktop/` half; `.hermes-package.json` records `source` and `sourceMtimeMs`).
   The Webapp fetches it over `/api/desktop-plugins/{root,list,read}`; native
   Electron reads its own disk. It registers a `transcript.toolMedia` contribution
   and is **evaluated once per page or app start**.
4. **Report the split.** Say what you proved (surface valid, tool ok) and what you
   did not (the client). "Reload the tab" is a hypothesis about the client, not
   proof the card now draws. If it is still blank, ask for the browser console
   line starting `[plugins]` — it names the skip reason.

Never re-present or rebuild the card as a first response to "I see no card": a
second surface makes the state worse and hides the real fault.

## The three failure shapes

| Symptom | Cause | Move |
|---|---|---|
| Nothing at all, not even a file | no renderer claimed the media (log line above); the tab/app predates the bundle | reload; if it persists, read the `[plugins]` console line |
| Empty frame, or "Loading surface" | surface fetched but rendering threw (catalog id, bad enum, chart runtime) | verify-surface.mjs, then the console stack |
| Drawn but ragged | CSS from the host chat leaking into the card | the prose trap below |

Timing facts that cost real time:

- A rebuilt desktop half is **not** in an already-open page. Element code lives in
  the page's bundle; `op=update` refreshes data only and never re-evaluates JS.
- A shell without `readPluginSource` truncates plugin sources at 512 KiB and
  refuses the bundle with an explicit message ("plugin.js exceeds this shell's
  512 KiB read limit"); the REST route raises the cap to 16 MiB. A ~1.4 MB bundle
  loads fine over `/api/desktop-plugins/read`, so that message pins an old client.
- Webapp and Electron differ only in where `plugin.js` comes from; both need the
  reload/restart before new code runs.

## The prose trap — the card lives inside the chat's typography scope

The card mounts in the transcript, inside Tailwind Typography's `prose` scope,
which styles `dt` (`margin-top: 1.25em`, `font-weight: 600`), `li`, `pre`,
`blockquote` and `h*`. A component that resets `dl`/`dd` but not `dt` spends that
margin **inside its own grid cell**: every label sits about 16 px below its value
on every row while the surface still replays clean.

Reset inline — the only thing that outranks a class-based prose rule on markup the
plugin injects into someone else's transcript:

- `dt`: `margin:0; font-weight:400; line-height:1.5`
- `dd`: `margin:0; line-height:1.5`
- grid container: `align-items:start`
- `li`: `margin:0`

Measure, do not squint: threshold a screenshot, sum ink per row in the label
column and the value column, compare each row's first-ink y. A *constant* offset
means a margin/line-height leak; a *growing* one means wrapping or a font-size
change.

## Authoring traps that look like delivery faults

- **`op=update` appends envelopes.** The previous surface's components stay
  defined, so a new `root` that no longer references one fails
  `Component 'x' is not reachable from 'root'`. Send data-only lines
  (`$/path = value`); to change layout or retire a component, present a new
  `surface_id`.
- **Enums, not pixels.** `Chart(height=)` takes `small`/`medium`/`large`; spacing
  is `weight=` on the `Row` child.
- **One child per `Card`.** A stray `)` before `, weight=` surfaces as a syntax
  error far from the real spot.
- **Long `Metric` values shrink.** Keep KPI values short; one long string renders
  at a different optical size than its neighbours.

## Rebuild loop when the fix is in the plugin

```
cd desktop && npx vitest run       # RED test first, then GREEN
npm run build                       # writes desktop/plugin.js
npm run check-bundle                # CI gate: bundle matches sources
cp plugin.js ~/.hermes/desktop-plugins/uirizz/plugin.js
sha256sum plugin.js ~/.hermes/desktop-plugins/uirizz/plugin.js   # must match
```

The repo commits the built bundle with its sources; `check-bundle` fails CI when
they drift. After the copy the user still has to reload (see timing facts).

The skill body has a token cap (`tests/test_skill_layout.py`), so keep long-lived
detail in this references/ directory and leave a short pointer in SKILL.md.
