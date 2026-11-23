# Wide layout example (Express)

Read this only when you need a worked A2UI Express layout. Official Basic
Catalog v1.0 only. Bind values to the data model so later `op=update`
calls can send `updateDataModel` instead of a new card.

```
Column(
  Row(
    Card(Column(Text("Error rate", variant="caption"), Text("${/kpi/error}")), weight=1),
    Card(Column(Text("Canary", variant="caption"), Text("${/kpi/canary}")), weight=1),
    Card(Column(Text("Budget left", variant="caption"), Text("${/kpi/budget}")), weight=1),
  ),
  Row(
    Card(Column(Text("What ships"), Text("${/detail/ships}")), weight=2),
    Card(Column(Text("Gate checks"), Text("${/detail/gates}")), weight=3),
  ),
  Button(Text("Deploy to production"), action=Event("deploy_prod", {"side_effect": true})),
)
```

Notes:

- The root is a `Column`. `weight` is only valid on a direct child of a
  `Row` or `Column`.
- Keep component ids stable across updates so `updateDataModel` can
  change `/kpi/error` and friends without redrawing the layout.
- On `op=update` for values only, send JSONL like:
  `{"version":"1.0","updateDataModel":{"surfaceId":"<id>","path":"/kpi/canary","value":"50%"}}`
- Always include `fallback_text` on `present` that carries the same
  numbers in plain text.
