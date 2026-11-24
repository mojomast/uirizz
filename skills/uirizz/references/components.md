# uirizz components

This reference lists the nine uirizz components an agent can place in an Express response, with a signature and a short example for each.

## Chart

Use for: comparing a numeric measure across categories or over time.

Signature: Chart(type (static), data, x (static), series (static), title?, format? (static), currency? (static), height? (static), selection?, action? (static), weight? (static))

```express
$/sales = [{month: "Jan", revenue: 120, cost: 80}, {month: "Feb", revenue: 150, cost: 85}, {month: "Mar", revenue: 170, cost: 90}]
root = Card(Chart("line", $/sales, "month", [{field: "revenue", label: "Revenue"}, {field: "cost", label: "Cost"}], title="Revenue vs cost", format="currency", currency="USD", selection=$/ui/month, action=Event("drill_month", {month: $/ui/month, read_only: true})))
```

## DataTable

Use for: listing records with several fields that the reader may sort or page through.

Signature: DataTable(data, columns (static), title?, pageSize? (static), sortable? (static), currency? (static), selection?, action? (static), weight? (static))

```express
$/rows = [{id: "INC-881", title: "Checkout 502s", sev: "SEV2"}, {id: "INC-879", title: "Slow search", sev: "SEV3"}]
root = Card(DataTable($/rows, [{field: "id", label: "ID"}, {field: "title", label: "Title"}, {field: "sev", label: "Severity"}], title="Open incidents", pageSize=10, selection=$/ui/row, action=Event("open_incident", {row: $/ui/row, read_only: true})))
```

## Metric

Use for: a single headline number with an optional change and status.

Signature: Metric(label, value, delta?, trend? (static), status? (static), sparkline?, weight? (static))

```express
root = Card(Metric("Uptime", "99.95%", delta="+0.02%", trend="up", status="good"))
```

## Progress

Use for: showing how far a value has moved toward a maximum.

Signature: Progress(value, max?, label?, status? (static), weight? (static))

```express
root = Card(Progress(34, max=40, label="Sprint progress", status="good"))
```

## Badge

Use for: a short status label such as a severity or state.

Signature: Badge(text, status? (static), weight? (static))

```express
root = Card(Badge("SEV2 open", status="critical"))
```

## Callout

Use for: a message the reader must not miss, such as a warning or a finding.

Signature: Callout(text, tone? (static), title?, weight? (static))

```express
root = Card(Callout("Deploys are frozen until the rollback finishes.", tone="warning", title="Change freeze"))
```

## KeyValueList

Use for: a short set of labelled facts about one item.

Signature: KeyValueList(items, weight? (static))

```express
$/owner = [{key: "Team", value: "Payments"}, {key: "On-call", value: "rotation-a"}]
root = Card(KeyValueList($/owner))
```

## Timeline

Use for: an ordered sequence of dated events.

Signature: Timeline(items, weight? (static))

```express
$/events = [{date: "2026-11-20", title: "Deploy 4.2", detail: "Canary passed", status: "good"}, {date: "2026-11-21", title: "Rollback", status: "critical"}]
root = Card(Timeline($/events))
```

## CodeBlock

Use for: showing a command, snippet, or configuration exactly as written.

Signature: CodeBlock(code, language? (static), weight? (static))

```express
root = Card(CodeBlock("npm run build", language="bash"))
```
