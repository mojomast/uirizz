# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-11-23

First tagged-ready release of the uirizz Hermes plugin (A2UI v1.0 Basic
Catalog cards in Desktop and Webapp chat). This changelog covers the work on
`feat/mvp` up to and including the approval gate. A GitHub release and catalog
pin are **not** cut in this commit; they need an explicit maintainer yes.

### Added

- One composable tool, `a2ui_render`, with `present`, `update`, `delete`,
  `describe`, and `audit`.
- Official Basic Catalog v1.0 admission, Express compilation, and a required
  `fallback_text` for CLI and other non-Desktop clients.
- Desktop / Webapp card renderer using official `@a2ui/react` widgets, a
  bundled icon font, and `ctx.rest` live refresh (`requires_hermes: ">=0.23.0"`).
- Structured card actions, logged to an append-only, hash-chained audit log
  (`op=audit`, `GET /audit`).
- Approval gate: a click is never approval. Fail-closed classification, a
  typed yes in chat, single-use session-scoped approval with a 600 s TTL, and
  a `pre_tool_call` veto of other tools while an action is pending.
- Bundled skill `uirizz:uirizz`, with when-to-use / when-not-to-use rules,
  error recovery, and a progressive-disclosure layout example in
  `skills/uirizz/references/layout.md`.
- README with a Night Hive banner, how-it-works screenshots, and a
  quickstart.
- pytest and vitest suites, strict `plugin.yaml` parsing, o200k token-budget
  tests, and CI for Python 3.11/3.12 plus the desktop bundle.

### Changed

- Renamed desktop unit tests and the Vitest config to `.mjs` so
  `hermes plugins validate` does not treat `node:` imports in test files
  as Desktop renderer-surface violations.

### Security

- Public-https media only; no model-chosen local file reads; no `http` or
  `data:` image URLs.
- No credentials, no `requires_env`, no runtime subprocesses.
- Does not register `transform_llm_output`.

[0.1.0]: https://github.com/mojomast/uirizz/tree/main
