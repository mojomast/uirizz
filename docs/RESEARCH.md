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

## 10. Layout best practice

Researched 22 November 2026 for the advanced-layout pass. Every claim below
cites a page that was open that day. Items marked **(uirizz)** were checked
against the live Desktop renderer on Hermes v0.23.0.

### 10.1 Compose with Row, Column and `weight`; do not expect a grid

- The Basic Catalog has no grid. A grid is `Column` of `Row`s, or `Row` of
  `Column`s ([component reference](https://github.com/a2ui-project/a2ui/blob/main/docs/public/reference/components.md),
  [Basic Catalog guide](https://a2ui.org/specification/v1.0-basic-catalog-implementation-guide/)).
- `weight` is the CSS `flex-grow` analogue and is only legal on a **direct
  child** of a `Row` or `Column` ([Basic Catalog guide](https://a2ui.org/specification/v1.0-basic-catalog-implementation-guide/),
  [Android `A2uiBasicCatalogV1` reference](https://developer.android.com/reference/kotlin/androidx/a2ui/compose/ui/catalog/A2uiBasicCatalogV1)).
  A `Row` of `Card(..., weight=1)` makes equal-width KPI tiles; `weight=2` next
  to `weight=3` gives a 2:3 master/detail split. Without weights, children
  shrink to content and a "wide" surface looks narrow **(uirizz)**.
- Spacing multiplication: invisible containers (`Row`, `Column`, `List`) carry
  zero padding and margin; leaves and bordered containers (`Text`, `Image`,
  `Card`, `Button`, inputs) carry the margin. Nest rows and columns freely
  without extra spacers ([Basic Catalog guide, Layout Spacing](https://a2ui.org/specification/v1.0-basic-catalog-implementation-guide/)).
- `justify` (main axis) and `align` (cross axis) default to `start`; use
  `spaceBetween` plus `align=center` for toolbars and label/value rows
  ([component reference](https://github.com/a2ui-project/a2ui/blob/main/docs/public/reference/components.md)).

### 10.2 Density and hierarchy: replace markdown with structure

Google's contributed `enterprise_dashboard` write-up (closed unmerged, so cite
it as community practice, not spec) gives a data-type to component recipe
that matches what the official catalog is good at
([a2ui-project/a2ui #1467](https://github.com/a2ui-project/a2ui/pull/1467)):

| Data | Use |
|---|---|
| KPI metrics | `Row` of `Card`, one bold `Text` plus a caption each |
| Comparisons | `Row` of `Card` side by side |
| Rankings | `List` of `Card` or `Row` |
| Multi-section | `Tabs` |
| Separators | `Divider` |
| Status | `Icon` (`check`, `warning`, `error`) |

The same write-up reports that anti-markdown rules in the prompt cut the
rate of markdown fallbacks from roughly 30-40% to under 5% on its own
agents; treat that as an author-reported number. The takeaway for the uirizz
skill is to say plainly: structured data goes in components, prose goes in
the chat reply.

### 10.3 When to use Tabs, Modal, List, and when to go bigger

- **Inline card (host guidance):** one decision or a small structured result;
  OpenAI recommends no tabs, no deep navigation and no nested scrolling inside
  an inline card, with at most one primary and one secondary action
  ([OpenAI UI guidelines](https://developers.openai.com/plugins/concepts/ui-guidelines));
  Claude's MCP Apps guide says the same and adds 4-5 data points at most
  ([Claude design guidelines](https://claude.com/docs/connectors/building/mcp-apps/design-guidelines)).
- **Carousel:** 3-8 comparable items, each with an image, a title and at most
  three lines of metadata, one CTA per item (same two pages).
- **Fullscreen / side panel:** dashboards, boards, editors; "use collapsible
  sidebars, tabs, or pagination to disclose details" and avoid floating
  panels ([Claude design guidelines](https://claude.com/docs/connectors/building/mcp-apps/design-guidelines)).
  Lay out by **container width**, not by display mode.
- **Implication for uirizz:** measured on the live Hermes Desktop (Webapp,
  1500 px viewport, sidebar open, dark): the thread is 1240 px wide and the
  rendered uirizz card is 1180 px, with no `max-width` anywhere in its
  ancestor chain (`none` / `100%`). The plugin does not cap or column-force
  the card; the host transcript column is the only limit. uirizz has no
  fullscreen mode, so a surface is an *inline wide card*. Narrow-looking cards
  seen earlier were an authoring problem (no `weight`, so every child shrank
  to content), not a container limit. Use
  `Tabs` only for peer views of one object (Summary / Timeline / Runbook),
  never as navigation between tasks. Use `Modal` for a detail that would
  otherwise need a second surface, with a visible trigger; both hosts warn
  that menus and popovers clip, so prefer visible controls over dropdowns.
  Use `List` for homogeneous rows and for template-driven rows from the data
  model.

### 10.4 Live data: update the data model, not the component tree

- A2UI separates structure from state. `updateDataModel` upserts at a JSON
  Pointer `path`; omitted path replaces the root; `value: null` deletes. Only
  components bound to the changed path re-render
  ([Data model and data binding](https://a2ui.org/concepts/data-binding/)).
- Two-way inputs (`TextField`, `CheckBox`, `Slider`, `ChoicePicker`) write the
  local model immediately and are **not** sent to the agent until an action
  carries them in `context` (as `{"@path": "/form/x"}`) or the surface sets
  `sendDataModel: true` ([Data model and data binding](https://a2ui.org/concepts/data-binding/)).
- Lists can be template-driven: `children: {path, componentId}` repeats a
  template per array item with relative paths; Express spells this
  `_template($/items, rowTemplate)` ([Data model and data binding](https://a2ui.org/concepts/data-binding/),
  `a2ui-agent-sdk` Express prompt contract, rule 11).
- Streaming has replace semantics only; an append operation is a proposal,
  not protocol ([discussion #727](https://github.com/a2ui-project/a2ui/discussions/727),
  [discussion #1253](https://github.com/a2ui-project/a2ui/discussions/1253)).
  Push whole arrays or small objects.
- **(uirizz)** Consequence: a monitor, a wizard or a counter should be one
  `present` with bound components, then `update` calls that carry only
  `updateDataModel` JSONL. That is cheaper for the model than re-sending
  components and refreshes the card in place.

### 10.5 Where the other stacks sit

- CopilotKit frames generative UI as controlled, declarative and open-ended;
  A2UI is "declarative", "creativity inside a guardrail", and fits the long
  tail of secondary interactions and internal enterprise tools
  ([CopilotKit overview](https://docs.copilotkit.ai/agent-spec/concepts/generative-ui-overview),
  [Generative UI spectrum](https://www.copilotkit.ai/generative-ui-spectrum)).
- AG-UI is the bidirectional agent/app runtime, not a UI spec; it carries
  A2UI, MCP-UI and Open-JSON-UI ([AG-UI generative UI specs](https://docs.ag-ui.com/concepts/generative-ui-specs)).
- Vercel AI SDK renders a React component from a typed tool part
  (`tool-<name>`, states `input-available` / `output-available`), i.e. a
  *controlled* pattern: the app owns every component
  ([AI SDK generative UI](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces)).
  uirizz is the declarative counterpart: the model composes from the Basic
  Catalog, the host owns every pixel.
- MCP Apps / MCP-UI ship sandboxed HTML; a talk at AI Engineer estimates
  predefined UI suits most cases, with declarative UI helping hosts keep a
  consistent look ([MCP-UI talk](https://ai.engineer/talks/o-zkvb0iFDQ-mcp-ui-extending-frontier)).
- Demos worth studying: restaurant finder (forms, time pickers, confirmation
  flows), contact lookup (search form plus result list), the component
  gallery and the Composer (live data-model, events and error panes)
  ([google/A2UI quickstart](https://github.com/google/A2UI/blob/81783227/docs/quickstart.md),
  [samples registry](https://github.com/google/A2UI/blob/main/samples/README.md),
  [Composer](https://github.com/a2ui-project/a2ui/blob/main/docs/public/composer/index.md)).

### 10.6 What the Basic Catalog cannot do (do not fake it)

No `Chart`, `Table`, `Progress`, `Badge`, `Tag`, `Map`, `Code`, `Markdown`
block, accordion, conditional visibility, or fullscreen mode. In the Hermes
Desktop renderer the `Icon` component also draws its ligature **name as text**
(for example `warning`, `lock_open`) because the Material Symbols font is not
loaded there **(uirizz)**; use a text glyph (`✓`, `⚠`) until that is fixed. Workarounds
that stay honest: `Slider` for a read-only progress bar, `Row`s of `Text` for
a table, `Icon` plus caption for status, `Tabs` or a swapped `updateComponents`
for stepwise flows. `Video` and `AudioPlayer` exist in the catalog but uirizz
admission rejects them for now.

### 10.7 Authoring rules this implies for the uirizz skill

1. Wrap the whole surface in a `Column`; split wide content with a `Row` and
   give each child a `weight`.
2. KPI row: 3-5 `Card`s, `weight=1`, label caption over value.
3. Master/detail: left `Column` or `Card` `weight=2`, right `weight=3`.
4. Keep one primary `Button` per card region; put per-row actions in the row,
   `borderless`.
5. Bind anything that changes to the data model and update with
   `updateDataModel`; resend components only when structure changes.
6. Stay under the 100-component and 256 KiB caps; template lists for repeats.
7. Always send a plain-text `fallback_text` that carries the same numbers.

### 10.8 Sources opened for this section

- [A2UI v1.0 Basic Catalog guide](https://a2ui.org/specification/v1.0-basic-catalog-implementation-guide/)
- [A2UI components reference](https://github.com/a2ui-project/a2ui/blob/main/docs/public/reference/components.md)
- [A2UI data model and data binding](https://a2ui.org/concepts/data-binding/)
- [A2UI discussion #727](https://github.com/a2ui-project/a2ui/discussions/727), [#1253](https://github.com/a2ui-project/a2ui/discussions/1253)
- [A2UI PR #1467 enterprise_dashboard](https://github.com/a2ui-project/a2ui/pull/1467) (closed, not merged)
- [google/A2UI samples](https://github.com/google/A2UI/blob/main/samples/README.md), [quickstart](https://github.com/google/A2UI/blob/81783227/docs/quickstart.md), [Composer](https://github.com/a2ui-project/a2ui/blob/main/docs/public/composer/index.md)
- [OpenAI UI guidelines](https://developers.openai.com/plugins/concepts/ui-guidelines), [Apps SDK UI](https://developers.openai.com/plugins/build/chatgpt-ui)
- [Claude MCP Apps design guidelines](https://claude.com/docs/connectors/building/mcp-apps/design-guidelines)
- [CopilotKit generative UI](https://docs.copilotkit.ai/agent-spec/concepts/generative-ui-overview), [spectrum](https://www.copilotkit.ai/generative-ui-spectrum)
- [AG-UI generative UI specs](https://docs.ag-ui.com/concepts/generative-ui-specs)
- [Vercel AI SDK generative UI](https://ai-sdk.dev/docs/ai-sdk-ui/generative-user-interfaces)
- [MCP-UI talk, AI Engineer](https://ai.engineer/talks/o-zkvb0iFDQ-mcp-ui-extending-frontier)

### 10.9 Verified live on Hermes Desktop (v0.23.0, dark mode)

Four Express demos run end to end through the real `a2ui_render` tool, using
only Basic Catalog components (`Row`, `Column`, `Card`, `Text`, `Button`,
`Tabs`, `List` with `_template`, `Divider`, `Slider`, `TextField`,
`ChoicePicker`, `CheckBox`, `formatString`):

- The card container is not capped: at a 1500 px viewport the thread is
  1240 px and the card 1180 px, with no `max-width` in the ancestor chain. A
  card that looks narrow is an authoring problem (no `weight`), not a renderer
  limit.
- `weight` works on `Row` and `Column` children: a 4-up KPI row, a 2:3
  list/detail split and a 4-column board all lay out as specified.
- `Tabs` switch client-side with no model round trip; tab selection survived a
  later `updateComponents` on the same surface.
- Re-sending a same-structure tree to the same `surface_id` refreshes the
  already-rendered cards in place, including cards from earlier turns, so a
  thread shows the latest state everywhere.
- `updateDataModel`-only updates (raw JSONL) moved a monitor card through four
  revisions with no component resend.
- `TextField`, `ChoicePicker` and `CheckBox` write to the data model on the
  client, so a `formatString` summary pane updates as the user types; the
  `Event` context carried the current values to the agent.

Known renderer issues seen: `Icon` names render as literal ligature text
(Material Symbols font not loaded), so use glyph `Text`; `Slider` with a
non-zero `min` (1..12) drew its thumb at the left edge for value 3 (not
root-caused). Neither is a uirizz bug.

## 11. Approval for real actions (declared actions)

Researched on 23 November 2026 for the declared-actions feature
([docs/ACTIONS.md](ACTIONS.md)). Sources were open that day.

### 11.1 What current practice asks for

- **Bind approval to a specific call.** Agent SDKs attach approval to a tool
  call, not to a conversation or an intent. The OpenAI Agents SDK lets
  `needs_approval` decide per call from the run context, the parsed tool
  parameters, and the call id
  ([OpenAI Agents SDK, human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/)).
  The Vercel AI SDK pauses a tool with `needsApproval` until the user approves
  or denies it ([AI SDK tool approval](https://chatbot.ai-sdk.dev/docs/customization/tool-approval)).
- **Server-enforced, argument-bound, single-use.** Vercel's guidance binds
  each pending approval to the user, conversation, tool call, exact validated
  arguments, and an expiry. It requires a new review whenever the action or
  its arguments change, enforcement at the real execution boundary, rejection
  of altered, expired, unknown or consumed approvals, and atomic handling of
  concurrent submissions
  ([Add human approval before your agent takes action](https://vercel.com/kb/prompts/add-human-approval-to-agent-actions), updated 7 Nov 2026).
  The same page: a denial runs nothing and must not trigger a re-request;
  give external writes a stable operation id for the destination's
  idempotency; when a timeout leaves the outcome unknown, show a
  reconciliation state instead of retrying blindly.
- **Least agency.** OWASP LLM06 (Excessive Agency) names excessive
  functionality, permissions and autonomy as root causes. It recommends narrow
  extensions over open-ended ones, and human approval for high-impact actions
  inside the extension that performs them
  ([OWASP LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)).

### 11.2 What Hermes provides (verified in its docs)

- `pre_tool_call` receives `tool_name`, `args`, `task_id`, `session_id`,
  `tool_call_id`, `turn_id`, `api_request_id`. It may return
  `{"action": "block", "message": ...}`, or `{"action": "modify", "args": ...}`
  to rewrite arguments.
- `post_tool_call` has the same identity fields plus `result`, `duration_ms`,
  `status`, `error_type`, `error_message`. Common `status` values are `ok`,
  `error`, `blocked` (a `pre_tool_call` hook vetoed it) and `cancelled`. It is
  emitted for blocked and cancelled paths too
  ([Hermes observer hooks](https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks)).

### 11.3 uirizz decisions

| Practice | uirizz |
|---|---|
| Approval bound to exact arguments | Tool name + SHA-256 of canonical JSON args, stored in the hash-chained log |
| New review when args change | Different args are blocked; changing them needs a new click and yes |
| Enforced at the execution boundary | `pre_tool_call` allows only the bound call while the approval is open |
| Single-use, atomic | Check and "consumed" record happen under one lock; replays are blocked |
| Expiry | Unchanged 10-minute window; an unused approval expires |
| Denial runs nothing, no re-ask | The exact denied call is blocked; the model is told not to ask again |
| Unknown outcome | `cancelled` or no report within 1 h → `unknown`; the model is told not to retry |
| Idempotency | `{operation_id}` template variable = stable action id |
| Trustworthy confirm text | The card's confirm panel comes from the definition, not the model |
| Least agency | Typed `params` with enums, patterns and bounds; per-hour limits; `high` needs `yes <code>` |
| `modify` by another plugin | Detected in `post_tool_call` → `unknown`, `args_changed_after_approval` |

Not done here: dry-run previews (the plugin cannot call tools itself, so a
preview would need the model to make a second, read-only call) and approval
from another device or channel.
