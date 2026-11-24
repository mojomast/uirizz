VERDICT: APPROVE

# WA-T5B review: approval notice once, then a short reminder

Reviewed the tree at the PR head (`31ef4d19ddde72fa381b80f52c4def60e5981de3`, single squashed
commit `7c185e6`). The supplied "complete slice diff" does not match this checkout: it shows a
151-line `tests/test_notices_once.py` built on `gate.gate_begin` and a `fake_ctx` fixture, neither
of which exists here. The landed test file is 93 lines and uses `actions.record_action` /
`pre_llm_call` / `pre_tool_call`. I judged the actual files, not the pasted diff.

The frozen acceptance tests (AC-001..AC-004) are the four tests in `tests/test_notices_once.py`, and
all four pass against the tree (see Checks). The notice/reminder split is persisted through the
audit log's `announced` entry, tools remain blocked from `status == "pending_confirmation"` alone,
and `yes <code>` after a reminder still resolves the action. The hint cache correctly re-emits on a
revision change. Remaining issues are minor.

## Findings

1. **minor** — `uirizz_plugin/hints.py:14` and `uirizz_plugin/hints.py:68-72`
   `_last_hints` is a process-global dict keyed by `(surfaces_root, scope)` and is never pruned or
   persisted. Two consequences: (a) a long-lived host accumulates one entry per conversation ever
   seen (entries are written even when `items` is empty, because the store happens before the
   `if not items: return None` at line 73); (b) the cache dies with the process, so a host/plugin
   restart re-injects the hint even when the card set did not change — the one case the spec says
   must not repeat. Fix: persist the per-scope fingerprint (the gate already persists `announced`
   in the audit log) if "only when the cards change" must hold across restarts, and bound the
   in-memory map (e.g. an `OrderedDict` capped at N scopes with LRU eviction). If per-process
   semantics are intended, document that limitation next to the cache.

2. **minor** — `uirizz_plugin/hints.py:45-54` and `uirizz_plugin/hints.py:66-67`
   The fingerprint is built from `_items(..., limit=5)`, i.e. only the five newest matching cards.
   In a chat with more than five cards, a change to an older card never changes the fingerprint, so
   the hint is not repeated even though cards changed. The displayed hint only ever lists five, so
   the impact is low, but it weakens the stated "only when cards change" intent. Fix: fingerprint
   every matching card (`surface_id`, title, revision) and pass `limit` only when rendering.

3. **minor** — `uirizz_plugin/hints.py:29-35` and `uirizz_plugin/hints.py:68`
   The cache key switches on which id the host supplies: `conversation_id` when present, otherwise
   `session_id`. If the host passes `conversation_id` on some turns and only `session_id` on others
   for the same chat (both are accepted by callers), the two keys differ and the same unchanged card
   set is re-emitted. Fix: derive one stable scope for a chat (prefer `conversation_id`, fall back
   deterministically) and key the cache on that, or store the fingerprint under both ids.

4. **minor** — `uirizz_plugin/gate.py:917-925`
   The "<300 chars" reminder has no explicit bound. It stays under 300 only because `_log_action`
   caps `event` at 120 chars; the worst case measured here is 294 chars (a 120-char event plus the
   `needs_code` suffix), leaving six characters of margin. A future widening of the event cap, a
   longer `extra`, or a hand-written audit entry with a longer `event`/`action_id` silently breaks
   the contract. Fix: shorten the event in the reminder (e.g. 60 chars) or enforce a hard cap after
   construction while preserving the code/reply tail.

5. **minor** — `tests/test_notices_once.py:64-65`
   `gate_part = second[second.index("Approval gate"):]` measures the whole tail of the turn's
   context, not just the reminder. It passes only because the cards hint happens to be suppressed
   on the second turn; if the card set changed between the two turns the hint would be appended
   and the `< 300` assertion would be measuring the hint as well. Fix: isolate the reminder, e.g.
   split on the hint prefix `uirizz cards already in this chat` (or match `Approval gate: ... Reply
   .* to approve`) and measure only that slice.

6. **minor** — `tests/test_notices_once.py:55-59`
   AC-002 asserts the first turn contains `"not approval"`, but never asserts the first turn is the
   *full* notice. A regression that replaced the full notice with a different short notice still
   containing that phrase would pass. Fix: also assert a full-notice marker on `first`, e.g.
   `"Update the same surface" in first` (the exact phrase the reminder must not contain), or
   assert `len(first) > len(second)`.

No blocker or major findings. AC-001..AC-004 are met.

## Checks

| # | Check | Command | Exit |
|---|-------|---------|------|
| 1 | Target test file (literal pytest command) | `timeout 900 python3 -m pytest -q -p no:cacheprovider tests/test_notices_once.py` | 1 — `/usr/bin/python3: No module named pytest` (pytest is not installed in this sandbox) |
| 2 | Whole suite (literal pytest command) | `timeout 1200 python3 -m pytest -q -p no:cacheprovider tests` | 1 — `/usr/bin/python3: No module named pytest` |
| 3 | Target ACs via a pytest stand-in that supplies `tmp_path` and runs the autouse `_store` fixture | inline `python3 -` harness over `tests/test_notices_once.py` | 0 — 4 passed, 0 failed (`test_full_notice_once_then_a_short_reminder`, `test_yes_after_a_reminder_still_approves`, `test_tools_stay_blocked_while_only_the_reminder_shows`, `test_cards_hint_repeats_only_when_cards_change`) |
| 4 | Regression subset that only needs the `_store` fixture | inline `python3 -` harness over `test_notices_once`, `test_gate`, `test_actions`, `test_pending_clicks` | 0 — 59 passed, 0 failed, 3 skipped (tests requiring `monkeypatch`, which the stand-in does not implement) |
| 5 | Direct behavioural probes: hint on add/update/delete, top-5 cap, conversation/session scope fallback, reminder size with 120-char event + `needs_code` | inline `python3 -` probes | 0 — hint re-emits exactly on add/update/delete, stops on repeat, top-5 cap holds, reminder worst case 294 chars |
| 6 | Slop-lint ratchet (CI job `slop-lint`) | `env PYTHONPATH=tools/slop-lint python3 -m slop_lint check . --baseline slop-baseline.json --pass-on-unpruned` | 0 — no new findings above baseline |
| 7 | Vendored slop-lint integrity | `python3 scripts/vendor_slop_lint.py --check` | 0 — 7 files match pinned manifest |
| 8 | Catalog up-to-date (CI job `test`) | `python3 scripts/build_catalog.py --check` | 1 — `ModuleNotFoundError: No module named 'a2ui'` (missing optional dep in this sandbox; not touched by the slice) |

Environment limits: pytest, `a2ui-agent-sdk`, PyYAML and FastAPI are absent, so the literal pytest
commands and the a2ui/declared-action tests cannot run here. Check 3 is the authoritative run of the
four frozen ACs; it reproduces the autouse fixture exactly (fresh temp store dir per test, restore
`set_store_dir(None)` afterwards).
