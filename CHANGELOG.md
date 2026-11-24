# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- A bare `yes` now approves only a lone `risk: low` declared action. Medium,
  high and free-form side-effect clicks need `yes <code>`; with more than one
  open action a bare `yes` decides nothing and the notice asks for the code.
  Cards show `code_required` accordingly. (rizzstack review, Track C #14)
- `auto_approve` is refused for shell, exec and code-execution tools, both when
  the definition loads and again at click time. (Track C #19)

### Fixed

- Express presents without `surface_id` no longer collide on the compiler's
  default id `main`; a fresh id is minted.
- Express compile errors return the compiler's message (line, column, allowed
  values) so the model can fix the exact line.
- Data-only Express updates (`$/path = value`) compile against the stored
  surface and become `updateDataModel` instead of failing.
- Non-gated card clicks are injected into the next turn once, not every turn.
- `references/layout.md` example did not compile (children outside lists,
  `"${/path}"` used as a binding); rewritten and now compiled in CI.
- `compile_express` now normalizes `surface_id` before interpolating the
  auto-added `surface(..., update=true)` header, and compiler error details
  redact paths and tracebacks.
- Audit log rotation (5 MB) no longer resets the gate: the new file carries
  every open action plus anything inside the per-hour and replay windows, and
  links to the old chain with a `rotated` entry. Rotation now happens under
  the lock. (rizzstack review, Track C #16)
- Read-decide-write in the gate (clicks, typed replies, tool consumption,
  outcomes) now holds one cross-process lock (`audit/actions.lock`), so one
  approval can no longer run once per Hermes process and concurrent clicks on
  one control leave exactly one pending. Per-hour limits are re-checked when
  the user approves, not only at click time. (Track C #17)

### Added

- Declared actions: `actions.yaml` (or `register_action`) binds a card button
  to one exact Hermes tool call. Params are validated on click; uirizz renders
  its own confirm panel; approval covers that tool name plus a hash of its
  canonical arguments; `pre_tool_call` lets only that call through, once
  (atomic); `post_tool_call` records completed / failed / unknown. Risk tiers
  (`low` + optional `auto_approve`, `medium`, `high` needing `yes <code>`),
  per-hour limits, replay blocking, detection of arguments rewritten after
  approval, `op=describe topic=actions`, present-time warnings, and
  `python -m uirizz_plugin.bindings check`. See docs/ACTIONS.md.
- `op=describe topic=recipes|express` and `skills/uirizz/references/`: eight
  tested Express recipes and a cheat sheet, compiled in CI.
- `evals/behavior_scenarios.json`: model-in-the-loop scenarios and checks.
- `docs/IMPROVEMENTS.md`: review findings and next steps.
- docs/ACTIONS.md "What the gate is, and what it is not": free-form approvals
  are not enforced in code, the gate is not a boundary against a compromised
  agent or shell access, `POST /actions` trusts its `session_id`, and the
  audit chain has no key (catches accidental edits, not rewrites). Same in
  README and the skill. (rizzstack review, Track C #15, #19, #20)

### Changed

- Skill rewritten around a card-or-prose decision rule, a reply contract,
  Express gotchas, form context binding, and data-only updates.
- Tool description now carries the trigger and points at the skill, since
  plugin skills are not listed in the Hermes skill index.
- README how-it-works shots retaken after these fixes: two cards with
  distinct ids, an in-place data-only update with no duplicate, compiler
  recovery, a prose-only turn, and the approval-gate flow.
- Read-only clicks waiting for the agent now come from the audit log on disk
  instead of process memory, so a click recorded by the dashboard process
  reaches an agent in another process (for example `hermes dashboard` and
  `hermes gateway` run as separate services). Each click is delivered once,
  at most the newest 20 per turn and only within 10 minutes, and its context
  is the audit log's sanitized, secret-redacted copy. (rizzstack review,
  Track C #18)

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
