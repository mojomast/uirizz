# uirizz: review and improvement plan (23 Nov 2026)

Scope: make Hermes use A2UI well. That means choosing when a card helps,
authoring it right on the first try, keeping it live, and staying safe. Method:
read every module, run the suite, drive `a2ui_render` with the real
`a2ui-agent-sdk` 0.12.1 compiler using the mistakes models typically make, and
check the findings against current A2UI, Hermes, and agent-tooling guidance.

## 1. Bugs found and fixed in this branch

| # | Problem (reproduced) | Effect on the model | Fix |
|---|---|---|---|
| 1 | Express always compiles to surface `"main"`, and `present` used that as the id. The **second** Express card ever presented, with no `surface_id`, failed with `surface_id main already exists`, and the `fix` told the model to update `main`. | Cards after the first one fail. The model is steered into patching an older card, possibly from another chat. This likely explains part of the "duplicate copies" and "re-present" known issues. | Ignore the Express default id; mint one unless the model passed `surface_id` (raw JSONL ids still honoured). Clearer `fix`. |
| 2 | Every Express failure returned "could not be compiled" with no detail. The SDK raises precise messages (line/column, the allowed enum values, unknown component). | The model can only guess, so retries are blind. Anthropic's tool guidance is to make errors specific and actionable. | `error` now carries the sanitized compiler message (≤600 chars), with a targeted `fix` for a missing `root`. |
| 3 | A data-only Express update (`$/kpi/rps = 42`), the pattern the skill recommends, **always failed** with "Surface not found". Each compile started from an empty state. | Every live update had to resend the whole tree, or fall back to hand-written JSONL. | Updates compile against a `RendererState` seeded from the stored surface (the SDK's "canvas" pattern), and `surface(id, update=true)` is added automatically. One line now becomes one `updateDataModel`. |
| 4 | `actions._PENDING` was never drained, so every non-gated click was re-injected on **every later turn**, along with "Call a2ui_render op=update". | Phantom updates on unrelated turns, plus slow memory growth. | Each click is delivered once. Gated clicks are unaffected, because the gate re-reads them from the audit log. |

Regression tests: `tests/test_authoring_fixes.py` (13 cases).

Also fixed after rebasing on `c62b38c`: the new `references/layout.md`
example did not compile (children outside `[...]`, so a positional argument
landed in `justify`; and `"${/kpi/error}"` would show literally instead of
binding). It is rewritten and now compiled by `tests/test_recipes.py`.

## 2. Skill and prompt changes in this branch

**Tool description is now the trigger.** Hermes plugin skills are read-only,
load via `skill_view("plugin:skill")`, and are *not* listed in the
system-prompt skill index. The model only finds the skill if the tool
description sends it there. The new description says when to use a card,
when not to, where the recipes are, and the MEDIA/update contract, and keeps
the hard rules from `c62b38c`.

**SKILL.md merged** with the When to use / When not to use / Hard rules /
Errors structure from `c62b38c`, and now shorter than before:

- A **card-or-prose decision rule**: scan, compare, fill in, choose or watch
  gets a card; explanations, code, single facts, one or two questions and
  sensitive talk stay in prose; when unsure, prose. Host guidelines from
  OpenAI, Microsoft and Google all warn against trivial or duplicative widgets.
- A **reply contract**: the MEDIA line plus one or two sentences, without
  restating the card. Hosts recommend a short follow-up that is not redundant
  with the card.
- **Express essentials the model could not have known**, all found by
  probing the compiler: `Text` has only `caption`/`body` (headings are Markdown
  inside the string), icon names are camelCase (`trending_up` is rejected),
  `Card` takes one child, input checks are positional only, and there is no
  `+` (use `formatString`).
- **Forms**: inputs reach the agent only if the button's context binds them
  (`{email: $/form/email}`). The old skill never said this, so submitted forms
  arrived empty.
- **Updates**: data-only lines, no second MEDIA line, never re-present.
- **Error recovery**: read `error`, fix that line, at most two retries, then
  prose.

**Progressive disclosure.** Details moved to `references/recipes.md` (8
tested recipes: status/KPI, compare, form, pick, list, confirm, progress,
tabs, plus update snippets) and `references/express.md` (grammar,
signatures, the full icon enum, gotchas). Both are served through
`op=describe topic=recipes|express`, so they work even where `skill_view` with
a file path does not resolve for plugin skills.

**Examples are tested in CI.** `tests/test_recipes.py` presents every
` ```express ` block in the skill and references, applies the update
snippets, and checks that every `Event` is marked `read_only` or
`side_effect`. A recipe that stops compiling breaks the build instead of
silently teaching a broken pattern.

**Behavior evals.** `evals/behavior_scenarios.json` has 16 scenarios with
deterministic checks: prose-only cases, KPI, compare, form, pick, list,
progress then update, restructure, gate click, typed yes, an injection label,
and error recovery. The current harness only proves the validator. These
scenarios test what the model does. Run them across the models your users
pick, and track pass rate, first-try admission, retries, tool calls and
tokens, as Anthropic's tool-writing guide recommends.

## 3. Recommended next steps (not in this branch)

Ordered by user impact.

1. **Fix duplicate cards in the renderer: the highest revision wins.** Every
   mounted card polls the same surface, so a second MEDIA line gives two live
   copies. In `card.jsx`, keep a module-level `Map<surfaceId, maxRevision>`
   fed by `parsedResult.revision`. A mount whose revision is lower renders a
   one-line stub ("Updated below, rev N"). This is deterministic even when the
   transcript virtualizes and re-mounts. I could not verify whether Desktop
   mounts from the tool result alone, so the branch only stops the model from
   pasting the line again.
2. **Make read-only clicks start a turn.** Today a click waits until the user
   types something. A2UI 1.0 `Event(..., userMessage=...)` plus Hermes
   `host.composer.submit(sessionId, text)` (fail-closed) could send a
   message on the user's behalf for `read_only` clicks only. Prefix it, for
   example `[card] Refresh the numbers`, so `gate._parse_reply` can never read
   it as a typed yes. Never auto-submit for gated clicks.
3. **Key state on `conversation_id`, not `session_id`.** The Hermes docs
   recommend `conversation_id` for per-conversation state because
   `session_id` can rotate when context compression runs. Pending approvals
   and surfaces keyed on the old id would be orphaned. Tool handlers receive
   both ids if they accept `**kwargs`.
4. **Scope surfaces to their conversation.** `GET /surfaces/{id}` and `op=update`
   accept any id in the store. Record the owning conversation on `present` and
   refuse cross-conversation reads and updates.
5. **Add an active-cards hint in `pre_llm_call`**, only when the conversation
   has cards, for example `uirizz cards here: surf-1a2b "checkout-api" rev 3`.
   Hermes appends hook context to the user message ephemerally, so it does not
   break prompt caching. It costs about 30 tokens and is the cheapest fix for
   "presented again instead of updating".
6. **Detect `fallback_text` drift, or auto-generate it.** Walk `Text` values and
   the data model on `present`. Warn (or fill in) when the card shows numbers
   the fallback lacks. CLI and Telegram users then read the same facts.
7. **Compact stored surfaces.** `messages` grows with every update and is
   resent on every poll. On update, fold history into one snapshot
   (`createSurface` with current components and data model) using the same
   `RendererState`. Measured while reviewing this PR: replaying 200 stored
   updates into `RendererState` took ~62 ms and a further data-only update
   took ~120 ms (200 sequential updates ~22 s). Replay is not a crash risk
   at that size, but history still grows linearly, so compaction remains
   worthwhile.
8. **Poll less.** Each card polls twice every 4 s for its whole lifetime. Back
   off when the revision is unchanged and nothing is pending, and pause
   off-screen cards (IntersectionObserver). The socket path already exists.
9. **Harden the yes for destructive verbs.** (Done: medium, high and free-form side effects require `yes <code>`; a bare `yes` approves only a lone `risk: low` declared action. See docs/ACTIONS.md.) A bare `yes` meant for another
   question can approve a pending action. For delete, pay, transfer, wipe or
   drop, require `yes <code>`; keep a bare `yes` for milder verbs.
10. **Images.** The known issue that "public https images often do not load"
    fits the plan in RESEARCH.md §3: serve admitted images through a plugin
    route (`ctx.rest`) with the DNS-pinned fetch, not straight from the bundle.
11. **Hermes-native learning.** Plugin skills are read-only, but Hermes can
    write user skills (`skill_manage`, `/learn`). Document a pattern such as
    "save this layout as a recipe", which writes a user-owned
    `uirizz-recipes` skill. Then the agent's card repertoire grows with the
    user without touching the plugin.
12. **Later: A2UI 1.0 function calls.** `callAgentFunction` lets a renderer ask
    the agent side for a value (typeahead, availability) without an LLM turn.
    This is worth a small allowlisted, read-only plugin function set once the
    basics above are solid.

## 4. Verification

- `pytest`: 139 passed. The 4 token-budget tests could not run in the review
  sandbox (the o200k vocabulary download was blocked). Run them locally.
  Both are smaller than on `main`: SKILL.md is 4,432 characters (was 4,935) and
  the compact schema is 1,853 characters (was 2,082).
- All 8 recipes and the update snippet compile and admit through the real
  tool. Gate classification was checked for every recipe event.

## 5. Sources

- A2UI 1.0 stable release, 11 Nov 2026 (bidirectional function calls,
  accessibility, swappable inference formats):
  <https://developers.googleblog.com/en/a2ui-10-build-delightful-fast-reliable-agentic-experiences/>
- A2UI v1.0 spec: <https://a2ui.org/specification/v1.0-a2ui/>; actions and
  `sendDataModel`: <https://a2ui.org/concepts/actions/>; `callAgentFunction`
  example: <https://docs.ag2.ai/docs/user-guide/a2ui/actions/>
- `a2ui-agent-sdk` 0.12.1 source: `RendererState` ("chat" vs "canvas"
  lifetimes) and the Express prompt contract (`processor.prompt_snippet`)
- Hermes plugin guide (handler kwargs, `conversation_id`, `pre_llm_call`
  injection into the user message, prompt caching, read-only plugin skills
  missing from the index): <https://hermes-agent.nousresearch.com/docs/developer-guide/plugins>
- Hermes skills (progressive disclosure, `skill_view(name, path)`, conditional
  activation): <https://hermes-agent.nousresearch.com/docs/user-guide/features/skills>
- Anthropic, Writing effective tools for agents (actionable errors, token
  efficiency, eval-driven iteration): <https://anthropic.com/engineering/writing-tools-for-agents>
- Anthropic, Skill authoring best practices (description says what and when;
  concise body; references one level deep): <https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>
- OpenAI UI guidelines (follow-up text should not repeat the card):
  <https://developers.openai.com/plugins/concepts/ui-guidelines>
- Microsoft 365 Copilot MCP Apps UX (complement the response, don't compete):
  <https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-mcp-apps-ui-guidelines>
- Google Connected Apps guidelines (no trivial single-button apps):
  <https://developers.google.com/connected-apps/mcp/guidelines>
- Leviathan et al., Generative UI: LLMs are Effective UI Generators
  (well-prompted generative UI is strongly preferred over markdown, ignoring
  latency): <https://arxiv.org/abs/2604.09577>
