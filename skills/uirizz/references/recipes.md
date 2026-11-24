# uirizz recipes

Copy the closest recipe, change the labels and data, and send it as `express`.
Every block here is compiled and admitted by CI (`tests/test_recipes.py`), so
the syntax is known to work. Keep values that will change under `$/...` so a
later `op=update` can send only the new data.

Contents: 1 Status / KPI · 2 Compare options · 3 Form that submits ·
4 Pick one and continue · 5 Result list · 6 Confirm step (approval gate) ·
7 Progress monitor · 8 Peer views with Tabs · 9 Declared action · Updates

## 1. Status / KPI board

Use for: a service, deploy, account or order at a glance. 3-5 numbers on top,
detail underneath.

```express
$/kpi = {rps: "1,240", p95: "182 ms", errors: "0.2%"}
$/status = "Healthy. Last deploy v24 at 14:02."
root = Column([header, kpis, Divider(), Text($/status)])
header = Row([Icon("check"), Text("## checkout-api")], align="center")
kpis = Row([k1, k2, k3])
k1 = Card(Column([Text("Requests / s", "caption"), Text($/kpi/rps)]), weight=1)
k2 = Card(Column([Text("p95 latency", "caption"), Text($/kpi/p95)]), weight=1)
k3 = Card(Column([Text("Error rate", "caption"), Text($/kpi/errors)]), weight=1)
```

## 2. Compare options side by side

Use for: 2-4 items judged on the same attributes. One column per option, the
same rows in the same order, one button per option.

```express
root = Column([Text("## Pick an espresso machine"), Row([a, b, c])])
a = Card(Column([Text("**Breville Bambino**"), Text("$299 · 15 s heat-up"), Text("Best for: first machine", "caption"), Button(Text("Choose"), action=Event("choose", {option: "bambino", read_only: true}))]), weight=1)
b = Card(Column([Text("**Gaggia Classic Pro**"), Text("$449 · 5 min heat-up"), Text("Best for: tinkerers", "caption"), Button(Text("Choose"), action=Event("choose", {option: "gaggia", read_only: true}))]), weight=1)
c = Card(Column([Text("**Rancilio Silvia**"), Text("$890 · 8 min heat-up"), Text("Best for: long-term", "caption"), Button(Text("Choose"), action=Event("choose", {option: "silvia", read_only: true}))]), weight=1)
```

## 3. Form that submits its values

Use for: 3+ fields the user must fill. For one or two questions, ask in chat
instead. Inputs write to the data model on the card only; the agent sees them
**only** if the button's context carries them as `$/path` bindings.

```express
$/form = {name: "", email: "", topic: [], notes: ""}
root = Card(Column([Text("## Request a callback"), fields, send]))
fields = Row([left, right])
left = Column([TextField("Name", $/form/name, ?required("Name is required")), TextField("Email", $/form/email, ?email("Enter a valid email"))], weight=1)
right = Column([ChoicePicker("Topic", "mutuallyExclusive", [{label: "Billing", value: "billing"}, {label: "Technical", value: "tech"}], $/form/topic), TextField("Notes", $/form/notes, variant="longText")], weight=1)
send = Button(Text("Send request"), "primary", Event("send_callback", {name: $/form/name, email: $/form/email, topic: $/form/topic, notes: $/form/notes, side_effect: true}))
```

## 4. Pick one and continue

Use for: the user must choose before you can go on (plan, region, format).

```express
$/choice = []
root = Card(Column([Text("Which region should the new bucket live in?"), picker, go]))
picker = ChoicePicker("Region", "mutuallyExclusive", [{label: "Toronto (ca-central-1)", value: "ca-central-1"}, {label: "Virginia (us-east-1)", value: "us-east-1"}, {label: "Frankfurt (eu-central-1)", value: "eu-central-1"}], $/choice, displayStyle="chips")
go = Button(Text("Continue"), "primary", Event("pick_region", {region: $/choice, read_only: true}))
```

## 5. Result list from data

Use for: many rows of the same shape (tickets, files, search hits). Push the
rows as data; one template draws them all. Per-row buttons stay borderless.

```express
$/rows = [{id: "INC-881", title: "Checkout 502s", sev: "SEV2"}, {id: "INC-879", title: "Slow search", sev: "SEV3"}]
root = Column([Text("## Open incidents"), List(_template($/rows, row))])
row = Row([Text($id, "caption", weight=1), Text($title, weight=4), Text($sev, weight=1), Button(Text("Open"), "borderless", Event("open_incident", {id: $id, read_only: true}))], align="center")
```

## 6. Confirm step (after an approval-gate notice)

Use for: an `Approval gate: ... status=pending_confirmation` notice. Update the
same surface. Say exactly what will happen. The user must type yes in chat;
there is deliberately no Confirm button.

```express
root = Card(Column([Row([Icon("warning"), Text("**Waiting for your yes in chat**")], align="center"), Text("Deploy **v24** of checkout-api to **production** (3 regions, rolling, ~6 min)."), Text("Reply `yes` to go ahead or `no` to cancel. Clicking is not approval.", "caption")]))
```

## 7. Progress monitor

Use for: a job you will report on more than once. Present once, then send only
data with `op=update` (see Updates below). The Progress component draws the
progress bar.

```express
$/job = {pct: 35, step: "Migrating table 4 of 11", eta: "about 7 min"}
root = Card(Column([Text("## Database migration"), Progress($/job/pct, 100, "Progress"), Text($/job/step), Text(formatString("ETA ${/job/eta}"), "caption")]))
```

## 8. Peer views with Tabs

Use for: one object seen several ways (Summary / Timeline / Raw). Not for
navigation between unrelated tasks.

```express
root = Tabs([{title: "Summary", child: summary}, {title: "Timeline", child: timeline}, {title: "Next steps", child: next}])
summary = Text("Checkout 502s for 14 min after deploy v24. Rolled back at 14:21.")
timeline = Column([Text("14:02 deploy v24"), Text("14:07 alerts fire"), Text("14:21 rollback done")])
next = Column([CheckBox("Add canary stage", false), CheckBox("Alert on p95 > 300 ms", false)])
```

## 9. Declared action button

Use for: a button that should run a real tool the user has declared in their
actions file (`op=describe topic=actions` lists them). Use only listed action
names and params; bind form inputs as `$/path`. Markers are optional here: the
declaration sets the risk.

```express
$/release = {version: "v24"}
root = Card(Column([Text("## Ship checkout-api"), TextField("Version", $/release/version), Row([staging, prod])]))
staging = Button(Text("Deploy to staging"), action=Event("deploy_service", {service: "checkout-api", version: $/release/version, env: "staging", side_effect: true}))
prod = Button(Text("Deploy to production"), "primary", Event("deploy_service", {service: "checkout-api", version: $/release/version, env: "production", side_effect: true}))
```

## Updates

Change values only (cheapest, keeps the layout). With `op=update` you can send
just the data lines; uirizz targets the stored surface for you:

```express-update
$/job/pct = 80
$/job/step = "Migrating table 9 of 11"
```

Change structure: send a new `root` (and its children) with `op=update` on the
same `surface_id`. Reuse component names so the card patches instead of
redrawing.
