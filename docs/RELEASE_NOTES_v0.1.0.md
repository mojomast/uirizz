# uirizz 0.1.0

**Release SHA:** not tagged yet.

Tag only after Kyle says yes. Recommended target: the merge commit of the catalog-screenshots PR, so the tag tree includes `docs/banner-catalog.png` and `docs/screenshots/catalog/`. The catalog loader requires a 40-character commit SHA, not a tag name; once `v0.1.0` exists, pin `git rev-parse 'v0.1.0^{commit}'`.

This file is draft release notes only. The `v0.1.0` tag, the GitHub release, and the Hermes catalog PR have **not** been created.

## Highlights

uirizz is a native Hermes plugin that renders official [A2UI](https://a2ui.org/specification/v1.0-a2ui/) v1.0 Basic Catalog cards in Desktop and Webapp chat, with a typed approval gate, declared actions, and CLI fallback text.

- One tool, `a2ui_render`, with `present`, `update`, `delete`, `describe`, and `audit`.
- Official `@a2ui/react` widgets (Night Hive, always dark). Live updates reuse a stable `surface_id` and prefer `updateDataModel`.
- Required `fallback_text` plus a `MEDIA:` line so CLI, Telegram, and the classic dashboard stay usable.
- A click is never approval. High-risk declared actions require a typed `yes <code>` in chat (bare “yes” is ignored). Approval is single-use, session-scoped, and expires after 600 seconds. `pre_tool_call` lets only the bound call through, once; altered arguments and replays are blocked. `post_tool_call` records completed or failed. The audit log is append-only and hash-chained (`op=audit`).
- Declared actions (`actions.yaml` or `register_action`) bind a card button to one exact Hermes tool call. See `docs/ACTIONS.md`.
- Bundled skill `uirizz:uirizz` (1365 o200k tokens, budget 2000). Tool schema is 447 o200k tokens (budget 500). Measured on `d877051f305be652ae946860428d037d4cdbab13`.
- Public-https media only. No credentials, no `requires_env`, no runtime subprocesses, no plugin network. Does not register `transform_llm_output`, so it can sit beside hermes-a2ui.

Requires Hermes **0.23.0** or newer and Python 3.10+.

## Install

After the tag exists:

```bash
hermes plugins install mojomast/uirizz --ref v0.1.0 --enable
hermes plugins doctor uirizz --ci
```

To pin a commit instead: `hermes plugins install mojomast/uirizz --ref <40-char-sha> --enable`.

The plugin is not in the Hermes catalog yet.

## Known issues

- Public `https` images often do not render in official widgets. Omit the image and say so in `fallback_text`.
- View buttons wrapping at typical card widths.
- Tall cards may clip under the composer or in the viewport.
- Re-presenting instead of `update` still creates a new surface if the model calls `present` again for the same view. Presenting a new unrelated card without `surface_id` now gets a distinct id.
- A data-only `op=update` without a second `MEDIA:` line was observed to refresh the first card in place. A second `MEDIA:` line can still mount a second copy.

## Changelog

See [CHANGELOG.md](https://github.com/mojomast/uirizz/blob/main/CHANGELOG.md) for the 0.1.0 line, including #20 (skill and Express authoring fixes), #21 (declared actions and the `yes <code>` gate), and #22 (README and screenshots).
