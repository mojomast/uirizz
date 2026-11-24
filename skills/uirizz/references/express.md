# A2UI Express cheat sheet (Basic Catalog v1.0)

Load this when a compile error mentions syntax, an enum, or a signature, or
before your first non-trivial surface. Send the source in `express` without
`<a2ui>` tags (tags are accepted but not needed).

## Grammar

- One statement per line. `name = Component(...)`. Exactly one `root = ...`.
- Children can be inline (`Row([Text("a"), Text("b")])`) or named variables.
- Positional args follow the signature order below; keyword args
  (`weight=1`, `variant="primary"`) always work and are safer.
- Strings use `"..."`; `"""..."""` for multi-line. Booleans `true`/`false`, `null`.
- Lists `[a, b]`. Maps `{title: "Overview", child: col}` (unquoted keys).
- Data: `$/abs/path` binds to the data model; `$field` is relative inside a
  `_template`. Initialise with `$/path = value` lines (value may be a map or list).
- Text interpolation: `formatString("${/kpi/count} open")`. There is no `+`.
- Checks on inputs (positional args only, message last): `?required("msg")`,
  `?email("msg")`, `?regex("^[0-9]{5}$", "msg")`, `?length(2, 40, "msg")`,
  `?numeric(0, 100, "msg")`. Keywords inside a check (`min=2`) are a syntax error.
- Actions: `Event("name", {key: $/path, read_only: true})`. Every Button needs one.
- Lists from data: `List(_template($/rows, rowTemplate))`.

## Signatures (`?` = optional; prefer keywords for optional args)

| Component | Signature |
|---|---|
| Text | `Text(text, variant?)` variant: `caption`, `body` only |
| Icon | `Icon(name)` (camelCase name from the list below) |
| Image | `Image(url, description?, fit?, variant?)` https only; variant `icon` `avatar` `smallFeature` `mediumFeature` `largeFeature` `header` |
| Row / Column | `Row(children, justify?, align?)` justify `start` `center` `end` `spaceBetween` `spaceAround` `spaceEvenly` `stretch`; align `start` `center` `end` `stretch` |
| List | `List(children, direction?, align?)` direction `vertical` `horizontal` |
| Card | `Card(child)` one child; wrap several in a Column |
| Tabs | `Tabs([{title: "A", child: a}, ...])` |
| Divider | `Divider(axis?)` |
| Modal | `Modal(trigger, content)` trigger is usually a Button |
| Button | `Button(child, variant?, action)` variant `default` `primary` `borderless` |
| TextField | `TextField(label, value, placeholder?, variant?)` variant `shortText` `longText` `number` `obscured` |
| CheckBox | `CheckBox(label, value)` value is a boolean or `$/bool` |
| ChoicePicker | `ChoicePicker(label?, variant?, options, value, displayStyle?, filterable?)` variant `mutuallyExclusive` `multipleSelection`; displayStyle `checkbox` `chips`; value binds a string list |
| Slider | `Slider(label?, min?, max, value, steps?)` steps = number of divisions |
| DateTimeInput | `DateTimeInput(value, enableDate?, enableTime?, min?, max?, label?)` RFC 3339 with offset |

Any component can take `weight=N` when it is a direct child of a Row or Column.

## Icon names (exact, camelCase)

accountCircle add arrowBack arrowForward attachFile calendarToday call camera
check close delete download edit event error fastForward favorite favoriteOff
folder help home info locationOn lock lockOpen mail menu moreVert moreHoriz
notificationsOff notifications pause payment person phone photo play print
refresh rewind search send settings share shoppingCart skipNext skipPrevious
star starHalf starOff stop upload visibility visibilityOff volumeDown
volumeMute volumeOff volumeUp warning

Snake_case Material names (`check_circle`, `trending_up`) are rejected.

## Formatting functions

`formatNumber(value, decimals?, grouping?)`, `formatCurrency(value, "USD", decimals?)`,
`formatDate(value, "MMM d, yyyy")`, `pluralize(count, one="item", other="items")`,
`and([...])`, `or([...])`, `not(x)`. `openUrl` is disabled in uirizz.

## Notes from the skill index

- One `root`; children in `[...]`. `Card` takes one child.
- `Text` variants are only `caption`/`body`; headings are Markdown in the
  string: `Text("## Title")`. Bind values as `$/path`, not `"${/path}"`
  (interpolate with `formatString("${/n} open")`).
- Icon names are camelCase (`check`, `warning`), never snake_case.
- Checks are positional: `?required("msg")`, `?length(2, 40, "msg")`.
- Update values only: `$/kpi/rps = "1,310"` becomes `updateDataModel`.

## Gotchas found in testing

- Headings: Text has no `h1`-`h5` variant. Use Markdown in the string:
  `Text("## Title")`, `Text("**bold** and normal")`. Keep Markdown simple.
- Tables, charts, metrics and progress bars are uirizz components
  (`DataTable`, `Chart`, `Metric`, `Progress`): see `op=describe topic=components`.
- Card takes one child. `Card(Text("a"), Text("b"))` fails; use `Card(Column([...]))`.
- `weight` only does something on a direct Row/Column child. The compiler
  accepts it elsewhere, so a "narrow card" usually means a missing weight.
- Form values reach you only through the action context (`{email: $/form/email}`).
- Express always compiles to surface "main"; uirizz renames it to the returned
  `surface_id`. Do not rely on the name "main".
