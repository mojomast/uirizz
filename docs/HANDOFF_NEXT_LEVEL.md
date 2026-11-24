# Handoff: finishing the "next level" plan

The branch `next-level` (PR "uirizz/1 data components, live cards, canvas")
delivers phase 1, phase 2 and most of phases 3 and 4 of the plan. Everything
below could not be done or verified where it was built: no live Hermes
Desktop, no real model runs, no Nous-side answers. Each item says what
"done" means.

## Verify live first (blocking for release)

Install the PR head on a test profile (`hermes plugins install mojomast/uirizz --ref <40-char sha> --enable`) and check in Desktop or Webapp, dark mode:

1. **Components render.** Present the Express example in
   skills/uirizz/references/components.md for each of the nine components.
   Every one draws (the Lit elements were only tested in jsdom). Chart:
   hover tooltips, the "View as table" toggle, resize. DataTable: sort, paging,
   row click.
2. **Selection.** Clicking a chart point or table row writes `selection` and
   the agent receives the row in the action context.
3. **Push socket.** In devtools, the card opens
   `/api/plugins/uirizz/surfaces/ws?surface_id=...`. Check the real prefix
   `ctx.socket` uses. An `op=update` refreshes the card in about 1 s, and
   polling backs off to 30 s.
4. **Highest revision wins.** Make the model paste a second `MEDIA:` line for
   an update. The older card collapses to "Updated below (revision N)".
5. **Canvas.** "Open in canvas" opens a workspace tab with the same live card.
6. **Card-started turns.** A read-only button with
   `Event("refresh", {read_only: true}, userMessage="Refresh the numbers")`
   sends `[card] Refresh the numbers` as a user turn. A gated or declared
   action never does. Typing nothing else, the gate must not treat it as a yes.
7. **Active-card hint.** In a chat with two cards, ask for "update the
   revenue". The agent calls `op=update`, not `present`.
8. **Generated fallback.** Present without `fallback_text` and check CLI or
   Telegram shows sensible text.

Record screenshots and a short results table in the PR.

## Open work

| Item | Why open | Done when |
|---|---|---|
| Bundle size | 858 KB → 1.46 MB, almost all ECharts | Kyle sets a budget; if over, swap to uPlot plus small SVG pie/donut, keeping `buildOption` tests |
| Self-refreshing cards | Unknown whether a plugin can run a read-only tool without a model turn | Spike `host.request` / gateway JSON-RPC; write up yes/no; if yes, add `refresh` to declared actions with `risk: none` |
| Image proxy | Images often fail to load | Plugin route that fetches admitted https images with the DNS-pinned guard in `urls.py`; card loads via `ctx.rest` |
| MCP Apps bridge | Needs MCP `resources/read` through Hermes | Spike; render a `ui://` resource in `SandboxedFrame`, or document why not |
| Export | No CSV/PNG yet | DataTable "Download CSV" and Chart "Save PNG" via the host save API |
| Behavior evals | Model use is unmeasured | Run evals/behavior_scenarios.json (add chart/table scenarios) on 2+ models; table of pass rates |
| Old surfaces | Surfaces stored with the basic catalog id cannot take data-only Express updates (stateless fallback) | Migrate on first update, or document |
| CI coverage | `tests/test_surface_socket.py` skips without fastapi | Add `fastapi` and `httpx` to the `dev` extra |
| Token budgets | Skill is 5,000 chars; could not run tiktoken here | CI green on `tests/test_tokens.py` and `tests/test_skill_layout.py` |
| Callout Markdown | Rendered as plain text | Use the configured A2UI markdown renderer, or document plain text |

## Prompt for the next agent

```markdown
You maintain uirizz (github.com/mojomast/uirizz). PR "uirizz/1 data
components, live cards, canvas" is open. Read docs/HANDOFF_NEXT_LEVEL.md and
docs/IMPROVEMENTS.md first.

1. Do the eight live checks in "Verify live first" on a test profile (never
   Kyle's main machine without his yes). Fix what breaks in small commits on
   the PR branch, with a test for each fix. Post results and dark-mode
   screenshots as a PR comment. Then stop and ask Kyle to review.
2. After Kyle merges, take the "Open work" items one PR each, in table order,
   skipping any that need his decision (bundle budget, MCP Apps scope) until
   he answers.

Rules: never loosen the approval gate, media policy or catalog allowlist;
every Express example goes in an ```express fence so CI compiles it; change
component props in uirizz_plugin/catalogs/uirizz_components.json first, then
`python scripts/build_catalog.py`, then the renderer; no release, tag or
catalog PR without Kyle's yes.
```
