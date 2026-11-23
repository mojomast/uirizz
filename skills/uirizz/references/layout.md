# Wide layout example (Express)

Read this only when you need a worked A2UI Express layout. Official Basic
Catalog v1.0 only. Bind values to the data model so later `op=update`
calls can send `updateDataModel` instead of a new card. CI compiles this block.

```express
$/kpi = {error: "0.4%", canary: "10%", budget: "82%"}
$/detail = {ships: "v24: new checkout retry policy", gates: "Error rate < 1%, p95 < 300 ms"}
root = Column([kpis, detail, deploy])
kpis = Row([k1, k2, k3])
k1 = Card(Column([Text("Error rate", "caption"), Text($/kpi/error)]), weight=1)
k2 = Card(Column([Text("Canary", "caption"), Text($/kpi/canary)]), weight=1)
k3 = Card(Column([Text("Budget left", "caption"), Text($/kpi/budget)]), weight=1)
detail = Row([ships, gates])
ships = Card(Column([Text("**What ships**"), Text($/detail/ships)]), weight=2)
gates = Card(Column([Text("**Gate checks**"), Text($/detail/gates)]), weight=3)
deploy = Button(Text("Deploy to production"), "primary", Event("deploy_prod", {side_effect: true}))
```

Notes:

- The root is a `Column`. `weight` only takes effect on a direct child of a
  `Row` or `Column`.
- Children go in a list: `Column([a, b])`, not `Column(a, b)`. Positional
  arguments after the list are `justify` and `align`.
- `Text($/kpi/error)` binds the value. `Text("${/kpi/error}")` would show the
  literal string; use `formatString("${/kpi/error} errors")` to interpolate.
- Keep component names stable across updates. To change values only, send
  Express data lines with `op=update`; uirizz compiles them to
  `updateDataModel`:

```express-update
$/kpi/canary = "50%"
```

- Always include `fallback_text` on `present` that carries the same numbers
  in plain text.
