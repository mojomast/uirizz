# uirizz

A native [Hermes](https://github.com/NousResearch/hermes-agent) plugin that
renders [A2UI](https://a2ui.org/specification/v1.0-a2ui/) v1.0 surfaces in
Hermes Desktop and Webapp chat replies.

This is an early scaffold. The tool, skill, and Desktop renderer are being
built on feature branches. It is **not** in the Hermes plugin catalog, and it
is **not** a drop-in clone of hermes-a2ui.

## What it is for

When the user needs a form, card, or other structured view in the chat, the
agent calls one tool, `a2ui_render`, with `op=present|update|delete|describe`.
The plugin validates official Basic Catalog v1.0, stores the surface under a
stable `surface_id`, and returns a `MEDIA:` line plus required
`fallback_text`. Desktop and Webapp draw the official `@a2ui/react` widgets
(Night Hive, always dark). CLI, Telegram, and the classic dashboard TUI show
only the fallback text. An `op=update` refreshes the same card. Clicks become
structured actions; the card stays editable.

It does **not** register `transform_llm_output`, so it can be installed beside
hermes-a2ui without fighting over that hook.

Best-practice research, with sources, is in [docs/RESEARCH.md](docs/RESEARCH.md).

## Requirements

- Hermes **0.23.0** or newer (`requires_hermes: ">=0.23.0"`), for
  `TOOL_MEDIA_RENDERER_AREA` and Desktop `ctx.rest`.
- Python 3.10 or newer.

## Install (from a checkout)

```bash
hermes plugins install /path/to/uirizz --enable
hermes plugins doctor uirizz --ci
```

Catalog install is not available yet. Do not submit a catalog PR without an
explicit yes from the maintainer.

Skill id: `uirizz:uirizz`. Pass that exact string to `skill_view` (no
`plugin:` prefix).

## Tool

| Tool | Ops | Purpose |
|---|---|---|
| `a2ui_render` | `present`, `update`, `delete`, `describe` | Admit or patch an A2UI v1.0 surface, or report catalog and limits |

`fallback_text` is required on `present`. Media URLs must be public `https`
only. The plugin will not read model-chosen local files and will not accept
`http` or `data:` image URLs (including SVG).

On this scaffold, `describe` works. `present`, `update`, and `delete` return a
structured `not_implemented` error until the admission and store land.

## Disclosure

- No credentials and no `requires_env`.
- No subprocesses at runtime.
- No network from the plugin except, once implemented, loading an already
  admitted public https image through the host.
- Surface records will be stored in the Hermes plugin data directory, not in
  the install checkout.
- The Desktop half uses only `@hermes/plugin-sdk` and `ctx.rest`. It does not
  patch the host, eval code, or load React from a CDN.
- The classic Hermes dashboard chat page is a terminal. This plugin cannot
  draw in-message widgets there.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
# if a local Hermes 0.23+ is on PATH:
hermes plugins doctor . --ci
hermes plugins validate . --install-deps
```

Measure skill and schema tokens with `python scripts/measure_tokens.py`.
The skill must stay well under 2,000 o200k tokens.

## License

MIT. See [LICENSE](LICENSE). A2UI is a separate project under Apache License
2.0. This repository does not copy hermes-a2ui source; that project is also
MIT-licensed, and is cited only as prior art in the research notes.
