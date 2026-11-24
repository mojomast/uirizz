# Declared actions

Declared actions let you wire a card button to something real (a deploy, a
Slack post, a ticket, a snooze) by writing a little config. The approval gate
then authorizes **one exact tool call**, not a vague intent.

```
click ──► params validated ──► uirizz confirm panel ──► typed yes ──► only that call runs, once ──► outcome recorded
```

Free-form `Event(...)` buttons keep working exactly as before. Declared actions
are an opt-in upgrade.

## Why

The gate used to approve an *event name*. After the user's yes, the model
decided which tool to call and with which arguments, wrote the confirm text
itself, and reported the outcome itself. Current guidance for human-in-the-loop
agents asks for more:

- Bind each approval to the exact validated arguments, the conversation, and
  an expiry, and require a new review if the action or its arguments change
  ([Vercel](https://vercel.com/kb/prompts/add-human-approval-to-agent-actions)).
- Treat approval as a server-enforced decision at the real execution boundary;
  never accept model text or a client "approved" flag (same source).
- Reject altered, expired, unknown or already-used approvals. Make concurrent
  submissions one atomic transition. A denial runs nothing and does not re-ask.
  If the outcome is unknown, show that instead of retrying blindly (same source).
- Approval attaches to a tool call, and can be decided per call from its
  parsed parameters ([OpenAI Agents SDK](https://openai.github.io/openai-agents-python/human_in_the_loop/)).
- Use human-in-the-loop control for high-impact actions, and prefer narrow,
  specific extensions over open-ended ones
  ([OWASP LLM06 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)).

Declared actions apply all of that inside Hermes, using hooks Hermes already
provides: `pre_tool_call` receives `tool_name`, `args` and `tool_call_id` and
can block, and `post_tool_call` reports `status` (`ok`, `error`, `blocked`,
`cancelled`), including for blocked calls
([Hermes observer hooks](https://hermes-agent.nousresearch.com/docs/developer-guide/observer-hooks)).

## Set up

1. Copy [`actions.example.yaml`](actions.example.yaml) to the plugin data
   directory as `actions.yaml` (or `actions.json`). On a default install that
   is `~/.hermes/plugin-data/uirizz/actions.yaml`.
2. Set `tool:` to a tool that exists in your Hermes profile (built-in, plugin
   or MCP). Credentials stay in that tool's configuration.
3. Check it: `python -m uirizz_plugin.bindings check`. Exit code 1 means a
   definition has an error. Valid definitions still load; broken ones are
   skipped and reported.
4. Ask Hermes for a card. The model sees your actions via
   `a2ui_render op=describe topic=actions` and wires buttons as
   `Event("deploy_service", {service: "checkout-api", version: $/form/version, env: "production"})`.

The file is re-read when it changes; no restart is needed.

## Definition reference

| Key | Required | Meaning |
|---|---|---|
| `title` | yes | What will happen, with `{param}` placeholders. Shown on the confirm panel and to the model. |
| `tool` | yes | The Hermes tool name to call. `a2ui_render` is not allowed. |
| `args` | no | The tool's arguments. A value that is exactly `"{param}"` keeps the param's type (number, list, boolean); placeholders inside longer strings are filled in as text. |
| `params` | no | What the button may send. Each param: `type` (`string`, `integer`, `number`, `boolean`, `array`), plus optional `enum`, `pattern` (full match), `minLength`/`maxLength`, `minimum`/`maximum`, `items` (for arrays), `default`, `optional: true`, `description`. |
| `risk` | no | `low`, `medium` (default), or `high`. |
| `auto_approve` | no | `true` lets the click approve. Only allowed with `risk: low`. |
| `limits.per_hour` | no | Max approved or run clicks per hour; extra clicks are rejected. |
| `description` | no | One line for the model. |

`{operation_id}` is reserved: it is replaced with the action's stable id
(`act-…`). Pass it to the destination's idempotency key if it has one, so a
retried request cannot run twice there.

### Risk tiers

| Risk | Approval |
|---|---|
| `low` + `auto_approve` | The click approves. Still bound to the exact call, still single-use, still logged with `decision_by=policy:auto_approve`. Refused for shell, exec and code-execution tools (`terminal`, `execute_code`, `process_manage`, or any tool name containing a word such as shell, bash, exec, run, code, python, ssh): those always need a typed yes. |
| `low` | The user types `yes` (or `yes <code>`) in chat. A bare `yes` counts only when this is the one open question. |
| `medium` / `high` | The user must type `yes <code>`. A bare `yes` is ignored, so a "yes" meant for another question cannot approve it. |

Free-form (undeclared) side-effect clicks follow the `medium` rule: `yes <code>`.
When more than one action is open, a bare `yes` decides nothing; the notice
asks for the code. A bare `no` still cancels every open action (fail-closed).

## What happens on a click

1. **Validate.** Unknown, missing or invalid params reject the click
   (`status=rejected`) with a precise reason. Nothing can be approved, and the
   card and model both say why. Rate limits reject the same way.
2. **Bind.** uirizz renders the exact tool call and stores the tool name and a
   SHA-256 hash of the canonical arguments (sorted keys; integral floats
   treated as ints) in the hash-chained audit log.
3. **Confirm.** The card shows uirizz's own panel: the title, the tool, the
   risk, and the reply to type. The model is told to relay exactly that title.
4. **Approve.** Only the user's typed reply counts, under the same rules as
   before (shown first, session-scoped, single-use, 10-minute expiry).
5. **Enforce.** While the approval is open, `pre_tool_call` lets through only
   that tool with those exact arguments, once. Marking it used and the check
   happen under one lock, so concurrent calls cannot both pass. Any other tool,
   or the same tool with different arguments, is blocked with a message naming
   the approved call. The model can cancel with
   `op=update action_id=… action_outcome=cancelled`.
6. **Record.** `post_tool_call` closes the call: `ok` → `completed`, `error` →
   `failed` (with `error_type`), `cancelled` → `unknown`, and `blocked` (another
   hook vetoed it) → back to `approved`. The card follows along; the model gets
   one notice and does not report the outcome itself.
7. **No replays.** For 10 minutes, an exact repeat of a call that already ran,
   or that the user denied, is blocked. Doing it again needs a new click and a
   new yes.

## Plugin API

Another Hermes plugin can contribute actions:

```python
from uirizz_plugin.bindings import register_action

register_action(
    "open_ticket",
    title="Open a {priority} ticket: {summary}",
    tool="linear_create_issue",
    args={"title": "{summary}", "priority": "{priority}"},
    params={
        "summary": {"type": "string", "maxLength": 120},
        "priority": {"type": "string", "enum": ["low", "high"]},
    },
    risk="medium",
)
```

The user's own `actions.yaml` wins on a name collision (the shadowed name is
listed in `op=describe topic=actions`).

## Limits and threat model

- The gate covers calls that come from a card click. It does not stop the
  model from calling tools on its own initiative outside a card flow; use
  Hermes' own tool approval settings for that.
- Enforcement needs the host to pass `args` to `pre_tool_call` (Hermes does).
  If a host does not, bound calls are blocked, never waved through.
- Another plugin's `pre_tool_call` could rewrite arguments after uirizz checks
  them (Hermes documents `{"action": "modify"}`). uirizz detects this in
  `post_tool_call` and records the outcome as `unknown` with
  `error_type=args_changed_after_approval`; it cannot undo the call.
- The single-use check is atomic across processes on POSIX hosts: every
  read-decide-write step holds an exclusive lock on `audit/actions.lock`
  (`flock`). On a host without `fcntl` (Windows) it falls back to a lock
  inside one process only.
- When the log passes 5 MB it rolls over to `actions.jsonl.1`. The new file
  starts with a `rotated` entry linked to the old chain and carries every
  open action and everything inside the per-hour and 10-minute replay
  windows, so rotation does not reset limits or approvals.
- The card and its labels are still model-authored. The confirm panel is not:
  it comes from your definition and the validated params.
- Never put secrets in `actions.yaml`. Audit and card views redact
  secret-looking keys, but the hash is computed on the real arguments.
