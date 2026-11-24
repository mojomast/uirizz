import { html, nothing } from 'lit'
import { z } from 'zod'
import {
  ActionSchema,
  DynamicStringSchema,
  DynamicValueSchema,
  WeightSchema,
  spec,
} from '@a2ui/web_core/v1_0'
import { UirizzElement, entry } from './element-base.js'
import { formatValue } from './format.js'

export const MAX_ROWS = 5000
export const DEFAULT_PAGE_SIZE = 10

export const DataTableApi = {
  name: 'DataTable',
  schema: spec(
    z
      .object({
        data: DynamicValueSchema.describe('REF:#/$defs/DynamicValue|Bind to an array of row objects in the data model.'),
        columns: z
          .array(
            z
              .object({
                field: z.string(),
                label: z.string().optional(),
                align: z.enum(['start', 'end', 'center']).optional(),
                format: z.enum(['text', 'number', 'percent', 'currency', 'date']).optional(),
              })
              .strict(),
          )
          .min(1)
          .max(20)
          .describe('Columns in display order.'),
        title: DynamicStringSchema.describe('REF:#/$defs/DynamicString|Short caption above the table.').optional(),
        pageSize: z.number().int().min(1).max(100).default(10).describe('Rows per page.').optional(),
        sortable: z.boolean().default(true).describe('Let the user sort by clicking a header.').optional(),
        currency: z.string().describe('ISO 4217 code for currency columns.').optional(),
        // Typed as a dynamic union (not the plain DataBindingSchema object) so the binder
        // treats it as DYNAMIC and exposes props.setSelection(); the wire format is still a DataBinding.
        selection: DynamicValueSchema.describe('REF:#/$defs/DataBinding|Data path where the clicked row is written.').optional(),
        action: ActionSchema.describe('REF:#/$defs/Action').optional(),
        weight: WeightSchema.optional(),
      })
      .strict(),
    { mixins: [] },
  ),
}

export function toRows(data) {
  if (!Array.isArray(data)) return []
  return data.slice(0, MAX_ROWS).map((r) => (r && typeof r === 'object' ? r : {}))
}

function numericOf(v) {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v.trim())
    return Number.isFinite(n) ? n : null
  }
  return null
}

function isMissing(v) {
  return v === null || v === undefined || v === ''
}

// Returns a new array. dir is 'asc' | 'desc' | 'none'. Missing values sort last.
export function sortRows(rows, field, dir) {
  const out = rows.slice()
  if (!field || (dir !== 'asc' && dir !== 'desc')) return out
  const sign = dir === 'asc' ? 1 : -1
  return out
    .map((row, i) => ({ row, i }))
    .sort((a, b) => {
      const av = a.row[field]
      const bv = b.row[field]
      const am = isMissing(av)
      const bm = isMissing(bv)
      if (am || bm) return am && bm ? a.i - b.i : am ? 1 : -1
      const an = numericOf(av)
      const bn = numericOf(bv)
      let c
      if (an !== null && bn !== null) c = an - bn
      else c = String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' })
      return c === 0 ? a.i - b.i : c * sign
    })
    .map((x) => x.row)
}

export function nextSort(current, field) {
  if (!current || current.field !== field) return { field, dir: 'asc' }
  if (current.dir === 'asc') return { field, dir: 'desc' }
  return { field: null, dir: 'none' }
}

export function pageRange(total, page, pageSize) {
  const size = Math.max(1, pageSize | 0)
  const pages = Math.max(1, Math.ceil(total / size))
  const p = Math.min(Math.max(0, page | 0), pages - 1)
  const start = total === 0 ? 0 : p * size
  const end = Math.min(total, start + size)
  const text = total === 0 ? 'No rows' : `${start + 1}–${end} of ${total}`
  return { page: p, pages, start, end, text }
}

const ALIGN = { start: 'start', end: 'end', center: 'center' }

export class UirizzDataTableElement extends UirizzElement {
  static tagName = 'uirizz-data-table'
  static properties = { _sort: { state: true }, _page: { state: true } }

  constructor() {
    super()
    this._sort = { field: null, dir: 'none' }
    this._page = 0
  }

  _activate(row) {
    const props = this.controller?.props
    if (!props) return
    props.setSelection?.(row)
    props.action?.()
  }

  _onSort(field) {
    this._sort = nextSort(this._sort, field)
    this._page = 0
  }

  _onRowKey(e, row) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      this._activate(row)
    }
  }

  render() {
    const props = this.controller?.props
    if (!props) return nothing
    const columns = Array.isArray(props.columns) ? props.columns : []
    const sortable = props.sortable !== false
    const clickable = Boolean(props.action)
    const rows = toRows(props.data)
    const sorted = sortRows(rows, this._sort.field, this._sort.dir)
    const pageSize = props.pageSize || DEFAULT_PAGE_SIZE
    const range = pageRange(sorted.length, this._page, pageSize)
    const visible = sorted.slice(range.start, range.end)
    const ariaSort = (field) => {
      if (!sortable) return nothing
      if (this._sort.field !== field) return 'none'
      return this._sort.dir === 'asc' ? 'ascending' : 'descending'
    }

    return html`
      <div class="uirizz-table-wrap" style="overflow:auto;width:100%">
        <table class="uirizz-table" style="width:100%;border-collapse:collapse">
          ${props.title ? html`<caption style="text-align:start;font-weight:600">${String(props.title)}</caption>` : nothing}
          <thead>
            <tr>
              ${columns.map((c) => {
                const label = c.label ?? c.field
                return html`<th scope="col" aria-sort=${ariaSort(c.field)} style="text-align:${ALIGN[c.align] || 'start'}">
                  ${sortable
                    ? html`<button type="button" class="uirizz-table-sort" @click=${() => this._onSort(c.field)}>${label}</button>`
                    : label}
                </th>`
              })}
            </tr>
          </thead>
          <tbody>
            ${visible.length === 0
              ? html`<tr><td colspan=${Math.max(1, columns.length)}>No rows</td></tr>`
              : visible.map(
                  (row) => html`<tr
                    tabindex=${clickable ? '0' : nothing}
                    style=${clickable ? 'cursor:pointer' : nothing}
                    @click=${clickable ? () => this._activate(row) : nothing}
                    @keydown=${clickable ? (e) => this._onRowKey(e, row) : nothing}
                  >
                    ${columns.map(
                      (c) => html`<td style="text-align:${ALIGN[c.align] || 'start'}">${formatValue(row[c.field], c.format || 'text', props.currency)}</td>`,
                    )}
                  </tr>`,
                )}
          </tbody>
        </table>
        ${sorted.length > 0
          ? html`<div class="uirizz-table-pager" style="display:flex;align-items:center;gap:8px;justify-content:flex-end">
              <span class="uirizz-table-range" aria-live="polite">${range.text}</span>
              <button type="button" class="uirizz-table-prev" ?disabled=${range.page <= 0} @click=${() => (this._page = range.page - 1)}>Prev</button>
              <button type="button" class="uirizz-table-next" ?disabled=${range.page >= range.pages - 1} @click=${() => (this._page = range.page + 1)}>Next</button>
            </div>`
          : nothing}
      </div>
    `
  }
}

export const DataTableEntry = entry(UirizzDataTableElement, DataTableApi)
