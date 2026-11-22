# uirizz best-practice research

Researched on 22 November 2026, America/Toronto, before any implementation
beyond this repository's scaffold. Prefer the live sources below if they
disagree with this file; the "Verified against" line records what was read.

**Verified against:** A2UI v1.0 specification (status Current, last updated
8 June 2026); official A2UI docs on catalogs, inference formats, agent
integration, client integration, and the Basic Catalog implementation guide;
`@a2ui/agent` / `a2ui-agent-sdk` guidance as published on a2ui.org and npm;
Hermes Agent v0.23.0 at `2bd378ed1b8d` local checkout (`website/docs/developer-guide/plugins/index.md`
and `desktop-plugin-sdk.md`); Hermes plugin-development skill plus
`references/catalog-review-lessons.md` (catalog contracts from 8–10 November
2026); WCAG 2.2 and W3C ARIA rules; hermes-a2ui at pin
`98d3f29337e9ab2b1651e047914d7363f89782c9` (layout, license, and manifest only
— no source was copied).

## 1. A2UI v1.0 protocol

A2UI is a declarative, catalog-constrained UI protocol. The agent streams JSON
envelopes; a trusted client renderer draws native widgets. No HTML, CSS, or
scripts travel on the wire
([v1.0 specification](https://a2ui.org/specification/v1.0-a2ui/)).

v1.0 wire messages (agent → renderer): `createSurface`, `updateComponents`,
`updateDataModel`, `deleteSurface`, `callRendererFunction`,
`agentFunctionResponse`. Renderer → agent: `action`, `callAgentFunction`,
`rendererFunctionResponse`, and (confirm at schema time) `error`. Every
envelope has `version` set to `"1.0"` and exactly one message key. Envelopes
are named `agent_to_renderer` and `renderer_to_agent`. Dynamic bindings use
`@path` and `@call`. Component extras use `@catalogId`, `@accessibility`,
`@metadata`, and `@checks`. A v1.0 `createSurface` must not carry `theme`;
styling belongs to the host. Older names (`surfaceUpdate`, `beginRendering`,
`userAction`) are v0.8 vocabulary and are out of scope for this plugin.

The official Basic Catalog id is
`https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json`. That string
is a catalog identifier, not a URL the plugin should fetch at runtime
([Catalogs](https://a2ui.org/concepts/catalogs/)). v1.0 Basic Catalog
components: Text, Image, Icon, Video, AudioPlayer, Row, Column, List, Card,
Tabs, Divider, Modal, Button, TextField, CheckBox, ChoicePicker, Slider,
DateTimeInput
([Basic Catalog guide](https://a2ui.org/specification/v1.0-basic-catalog-implementation-guide/)).
Functions include validation (`required`, `regex`, `length`, `numeric`,
`email`), formatting (`formatString`, `formatNumber`, `formatCurrency`,
`formatDate`, `pluralize`), logic (`and`, `or`, `not`), and `openUrl`.
Function calls are gated by `allowedCallers` and `requiresUserActivation`.

**uirizz decision:** admit official Basic Catalog v1.0 only. Keep `openUrl`
off in MVP. Defer Video and AudioPlayer until the same public-https guard is
proven on Image. Do not invent a custom 30-plus component catalog for v1.

## 2. Official agent SDK and prompting practice

The Agent SDKs are `@a2ui/agent` (TypeScript) and `a2ui-agent-sdk` (Python).
Recommended startup pattern
([Agent integration](https://a2ui.org/guides/agent-integration/),
[npm `@a2ui/agent`](https://www.npmjs.com/package/@a2ui/agent)):

1. Load catalogs once (`CatalogConfig` / `BasicCatalog(ProtocolVersion.V1_0)`).
2. Build a long-lived `A2uiGenerator`.
3. Per turn, create a processor for the client's `supportedCatalogIds`.
4. Append `processor.prompt_snippet` (Python) / `processor.promptSnippet`
   (TypeScript) to the system prompt. That snippet is generated from the
   catalog's component signatures, function signatures, and the catalog's
   Markdown `instructions` field.
5. Parse the model reply with `parse_response` / `parseResponse`. Invalid
   blocks raise and must not be applied to renderer state.

Inference formats
([Inference formats](https://a2ui.org/concepts/inference-formats/)):

- **Express** (default): compact positional DSL in sentinel tags, compiled on
  the server to flat v1.0 JSON. Official evals (`core_v1_0`, gemini-3.8-flash)
  report about 45% fewer prompt tokens and about 3× fewer generated UI tokens
  than raw JSON at the same accuracy.
- **Direct JSON:** the model emits wire JSON. Useful for debugging or
  JSONL-only fallbacks.
- Compilation is server-side, so every client still receives standard A2UI
  JSON. Do not ask the Desktop renderer to parse Express.

Official guidance for multi-turn UIs: keep `RendererState` per session and
tell the model to update an existing surface in place (`surface("id",
update=true)` in Express) rather than recreating it. Prune catalogs and attach
few-shot examples as validated wire JSON (the SDK decompiles them into the
active format). Do not paste a full JSON Schema dump of the catalog into every
Hermes turn — that is the expensive path the SDK is designed to avoid.

**uirizz decision:** accept Express (preferred, compiled with the official
Python SDK when present) and raw v1.0 JSONL. If the Express SDK is missing,
fail closed with `express_unavailable` and tell the model to send `jsonl`.
Keep the always-on Hermes skill far under 2,000 o200k tokens. Do not inject a
large catalog or `prompt_snippet` on every `pre_llm_call`. Teach `op=update`
on a stable `surface_id`.

## 3. A2UI security, tightened for Hermes catalog review

A2UI's trust model is a host-owned catalog: the agent may only name component
types, properties, data, and functions the renderer already implements
([Catalogs](https://a2ui.org/concepts/catalogs/),
[defining a catalog](https://a2ui.org/guides/defining-a-catalog/)). Official
media URL rules for Image, Video, and AudioPlayer allow `http`, `https`,
`data`, and same-host relative paths, and reject `javascript`, `file`,
`content`, `blob`, and `ftp`. Official `openUrl` allows `http`/`https` after a
real user gesture, with `noopener,noreferrer`
([Basic Catalog guide](https://a2ui.org/specification/v1.0-basic-catalog-implementation-guide/)).
Those official rules are **not** sufficient for a Hermes catalog plugin.

Hermes catalog SSRF contracts (plugin-development skill, 8–10 November 2026
reviews) require: HTTPS for untrusted URLs, no credentials in the URL, resolve
every A/AAAA address and reject non-global addresses (private, loopback,
link-local/metadata, CGNAT, multicast, reserved, unspecified, IPv4-mapped
IPv6), pin the connection to vetted addresses (a second DNS lookup permits
rebinding), disable ambient proxies, bound redirects and bytes, and test
adversarial hosts without contacting them. A scheme check alone is not enough.

**uirizz media policy (stricter than official A2UI and than hermes-a2ui at
98d3f29):**

- `https` only. No `http`, no `data:` (including `image/svg+xml`), no `blob`,
  `file`, `javascript`, or relative paths that can escape to another host.
- No URL credentials. Public-address DNS pin, bounded redirects, byte cap.
- No model-chosen local file reads. If local images are ever added later,
  they must resolve inside an explicit user-configured directory after
  symlink resolution — never from a model path alone.
- Image loads, when implemented, go through the host (`ctx.rest` / plugin
  routes), not a raw `fetch` of an agent-supplied URL from the Desktop
  bundle, and never through `SDK.authedFetch` with an absolute `https:` URL.
- Validate before mutating stored state. Unknown components, extra
  properties, missing roots, oversize payloads, and bad URLs fail closed with
  a structured JSON error (`ok`, `error`, `code`, `fix`). Nothing is stored
  or rendered.
- Size caps used by prior art and kept here: 256 KiB payload, 100 components,
  plus an LRU on stored surfaces.
- Untrusted surface text (labels, values, action names) is data, not
  instructions. Strip controls when injecting into `pre_llm_call` context.
  Never tell the model to "trust" user or feed text.

## 4. Hermes plugin surfaces and hooks

A native plugin is `plugin.yaml` + `__init__.py` `register(ctx)`, optional
`desktop/plugin.js`, optional `dashboard/`, optional bundled `skills/`.
Third-party plugins ship as standalone repos, not PRs into `hermes-agent`
(`website/docs/developer-guide/plugins/index.md`, Hermes v0.23.0).

Desktop / Webapp in-chat rendering uses
`TOOL_MEDIA_RENDERER_AREA` (`transcript.toolMedia`), documented in
`desktop-plugin-sdk.md`. When a reply contains a `MEDIA:` line, the host finds
the producing tool call and, if this package registered a renderer for that
tool name, draws the plugin component. Other clients still see the ordinary
file or text. Feature-detect `typeof sdk.TOOL_MEDIA_RENDERER_AREA !== 'string'`
and keep a fallback on older Desktops. Do not open `file.path` in the
renderer; use `file.resolveUrl()` or, for structured state, `ctx.rest` to a
plugin route. `host.composer.submit(sessionId, text)` is fail-closed: if that
chat has no visible composer it returns false and must not be broadcast to
some other session.

`transform_llm_output` can append a forgotten `MEDIA:` line, but Hermes can
keep only one such hook. hermes-a2ui and hermes-openui already compete for
that slot. **uirizz must not register `transform_llm_output`.** The tool
result itself includes the `MEDIA:` line and `fallback_text`. Teach that in
the skill. `pre_llm_call` is used only to inject structured action context,
must accept `**kwargs`, and must not police other sessions or tools.

Desktop host calls go through `ctx.rest` only. `requires_hermes: ">=0.23.0"`
is required for this transport and for `TOOL_MEDIA_RENDERER_AREA`. Import
from `@hermes/plugin-sdk` only: no prototype patching, no `eval` / `new
Function`, no app-chunk imports, no DOM scraping, no CDN React. Commit a
reproducible `desktop/plugin.js` bundle and lockfile when the official
`@a2ui/react` renderer is added. The classic web dashboard `/chat` page is a
PTY; do not promise in-message widgets there.

Every registered tool handler returns `json.dumps(...)` on success and on
every error. Call `register_tool` with keyword arguments only and tolerate
hosts that reject `output_schema`. `provides_tools` / `provides_hooks` must
match `register()`. Parse `plugin.yaml` with `ruamel.yaml` and
`allow_duplicate_keys = False`.

## 5. Generative-UI accessibility and authoring

Generated surfaces must meet the same bar as hand-authored UI.

- Prefer native widgets from `@a2ui/react` / the official Basic Catalog so
  accessibility is carried by the catalog implementation, not invented ARIA
  from the model ([W3C Using ARIA](https://www.w3.org/TR/using-aria/), first
  rule: use a native element when it already has the semantics; "no ARIA is
  better than bad ARIA"). All interactive ARIA would still need keyboard
  support (third rule).
- WCAG 2.2 SC 1.4.3 Contrast (Minimum), Level AA: 4.5:1 for normal text, 3:1
  for large text ([Understanding 1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum)).
  SC 2.4.7 Focus Visible: a keyboard focus indicator must be visible
  ([Understanding 2.4.7](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html)).
  SC 1.4.11 Non-text Contrast: 3:1 for component boundaries and focus
  indicators.
- Night Hive tokens, measured 22 November 2026 with the WCAG relative
  luminance formula (sRGB):

  | Pair | Ratio | AA normal text |
  |---|---:|---|
  | text `#E6EDF5` on base `#0B0F14` | 16.29:1 | pass |
  | text `#E6EDF5` on surface `#111821` | 15.13:1 | pass |
  | muted `#93A4B8` on base / surface | 7.54 / 7.01:1 | pass |
  | honey `#F0B86E` on base / surface | 10.79 / 10.02:1 | pass |
  | mint `#54D3A1` on base / surface | 10.26 / 9.53:1 | pass |
  | red `#F2706B` on base / surface | 6.69 / 6.21:1 | pass |
  | dark text `#0B0F14` on honey / mint / red | 10.79 / 10.26 / 6.69:1 | pass |

  Border `#243242` on base is 1.47:1 and is not used as text. Keep focus
  rings at least 3:1 against the adjacent background. Always dark: Geist and
  Geist Mono, never a light theme.
- Do not steal focus when a live `op=update` refreshes a card. Announce
  material changes through a polite live region, not per-token chatter
  (production-readiness practice for streamed UI).
- Required `fallback_text` is the accessible copy for CLI, Telegram, the
  classic dashboard TUI, and Desktop with the plugin off. The tool fails
  closed if it is missing on `present`.
- Keep the tool schema small (`op` enum, not many tools). Official A2UI
  already recommends compact Express signatures over dumping JSON Schema into
  the prompt. Measure schemas and the skill with tiktoken `o200k_base`.
  Target: skill well under 2,000 o200k tokens; schema left lean (a few
  hundred tokens).

## 6. Hermes catalog review lessons applied here

From `references/catalog-review-lessons.md` and the skill's safety contracts,
the items that apply to an in-chat UI plugin:

- Fail-closed public-address URL guard; test localhost, metadata, mixed DNS,
  mapped IPv6, rebinding, and public-to-private redirects without contacting
  those hosts.
- No credentials. No `os.environ` fallback, no reading `~/.hermes/.env`.
  This plugin should need no `requires_env`.
- No subprocesses, so no child-environment leakage path. If Node is ever
  used to build the desktop bundle, that is a maintainer command, not a
  runtime tool.
- Desktop: `ctx.rest` only, committed bundle + lockfile, `requires_hermes:
  ">=0.23.0"`. Never pass an absolute `http(s):` URL to `authedFetch`.
- Every handler returns a JSON string. Tests check `isinstance(result, str)`
  then `json.loads`.
- Hooks accept `**kwargs` and stay scoped to this plugin's surfaces. Do not
  register a global `transform_llm_output`.
- Untrusted labels in `pre_llm_call` are quoted data, never "trust"ed.
- Actions that navigate or have side effects require a real user gesture in
  the card; the model does not trigger `openUrl`.
- Unit tests and `hermes plugins doctor --ci` are necessary but not live
  Desktop proof. Live acceptance (card in the correct session, click lands
  there, update refreshes that card, fallback-only when the desktop half is
  off, coexistence with hermes-a2ui) needs Kyle's yes before a moltussy-1
  install or a catalog PR.
- YAML-only catalog PRs, at most 6 dark-mode screenshots, no self-update, no
  invented catalog SHA. Not in this phase.

## 7. Competitor license and what we take as ideas only

Revenue-Architect/hermes-kaizen-ui, package `packages/a2ui` (hermes-a2ui), pin
`98d3f29337e9ab2b1651e047914d7363f89782c9`, is licensed **MIT**, Copyright
(c) 2026 Revenue-Architect, both at the repo root and under
`packages/a2ui/LICENSE`. MIT allows reuse, but this project **does not copy
their source**. We independently implement a different tool shape and
security posture. Idea-level practices we agree with (and will write
ourselves): deliver a `MEDIA:` file plus required `fallback_text`; validate
before render; cap payload size and component count; prefer official Express
compilation; target Desktop/Webapp with `requires_hermes: ">=0.23.0"`.

Verified gaps we will not repeat: http and LAN image loads; `data:image`
including SVG; model-chosen local file reads; one-shot cards with no
`op=update`; lock-the-card-on-click (`markAnswered`) instead of a structured
action plus live update; registering `transform_llm_output`; a 7k+ token
skill plus a large reference dump; a custom catalog that drops official
Video/Audio and adds 32 extensions.

A second catalog entry that only repeats `a2ui_present` + `MEDIA:` is likely
to be asked to consolidate with hermes-a2ui / hermes-openui (NousResearch
hermes-agent PRs #151841 and #151842, still open on 22 November 2026).
uirizz should be pitched, if ever listed, on the gaps above, never as
another `hermes-a2ui`.

## 8. Locked MVP decisions

| Topic | Decision |
|---|---|
| Name | `uirizz` (not `hermes-a2ui`) |
| License | MIT, Copyright 2026 Kyle Durepos |
| Tool | one `a2ui_render` with `op` present, update, delete, describe |
| Catalog | official Basic Catalog v1.0 allowlist |
| Authoring | Express preferred, v1.0 JSONL accepted |
| Delivery | `MEDIA:` + required `fallback_text`; `TOOL_MEDIA_RENDERER_AREA` |
| Updates | same `surface_id`, live card refresh |
| Actions | structured event, `pre_llm_call` context, card stays editable |
| Hooks | `pre_llm_call` only; no `transform_llm_output` |
| Media | public https only; no local file reads; no svg data URLs |
| Theme | Night Hive, always dark, Geist / Geist Mono |
| Skill | tight, measured, well under 2,000 o200k tokens |
| Host floor | `requires_hermes: ">=0.23.0"` |
| Out of MVP | classic dashboard in-message widgets, mid-token streaming, `openUrl`, A2A/AG-UI, catalog PR, tags, deploys |

## 9. Sources

- [A2UI v1.0 protocol specification](https://a2ui.org/specification/v1.0-a2ui/) (updated 8 June 2026)
- [A2UI catalogs](https://a2ui.org/concepts/catalogs/)
- [A2UI inference formats](https://a2ui.org/concepts/inference-formats/)
- [How to integrate A2UI into an agent](https://a2ui.org/guides/agent-integration/)
- [How to integrate A2UI into a client](https://a2ui.org/guides/client-integration/)
- [How to define a catalog](https://a2ui.org/guides/defining-a-catalog/)
- [v1.0 Basic Catalog implementation guide](https://a2ui.org/specification/v1.0-basic-catalog-implementation-guide/)
- [Official SDKs](https://a2ui.org/concepts/sdks/)
- [npm `@a2ui/agent`](https://www.npmjs.com/package/@a2ui/agent)
- [google/A2UI](https://github.com/google/A2UI) (Apache License 2.0)
- Hermes v0.23.0 docs: `website/docs/developer-guide/plugins/index.md`, `website/docs/developer-guide/desktop-plugin-sdk.md` (also published at [Desktop Plugin SDK](https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk))
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/), [SC 1.4.3 Contrast (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum), [SC 2.4.7 Focus Visible](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html)
- [W3C Using ARIA](https://www.w3.org/TR/using-aria/)
- Catalog PRs [hermes-a2ui #151841](https://github.com/NousResearch/hermes-agent/pull/151841) and [hermes-openui #151842](https://github.com/NousResearch/hermes-agent/pull/151842)
- Competitor tree (read-only, MIT): [packages/a2ui @ 98d3f29](https://github.com/Revenue-Architect/hermes-kaizen-ui/tree/98d3f29337e9ab2b1651e047914d7363f89782c9/packages/a2ui)
