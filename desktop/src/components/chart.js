import { html, nothing } from 'lit'
import { z } from 'zod'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import {
  ActionSchema,
  DynamicStringSchema,
  DynamicValueSchema,
  WeightSchema,
  spec,
} from '@a2ui/web_core/v1_0'
import { UirizzElement, entry } from './element-base.js'
import { formatValue } from './format.js'

echarts.use([LineChart, BarChart, ScatterChart, PieChart, GridComponent, TooltipComponent, LegendComponent, SVGRenderer])

export const MAX_ROWS = 2000
export const PALETTE = ['#5AA9FF', '#F5A524', '#3DD68C', '#F871A0', '#B392F0', '#2DD4D4', '#F2E05A', '#FF7A59']
export const HEIGHTS = { small: 160, medium: 260, large: 380 }
const FALLBACK_TEXT = '#E6EDF5'

export const ChartApi = {
  name: 'Chart',
  schema: spec(
    z
      .object({
        type: z
          .enum(['line', 'area', 'bar', 'stackedBar', 'horizontalBar', 'scatter', 'pie', 'donut'])
          .describe('Chart type.'),
        data: DynamicValueSchema.describe('REF:#/$defs/DynamicValue|Bind to an array of row objects in the data model, e.g. $/sales.'),
        x: z.string().describe('Row field used for the x axis, the bar categories, or the slice names.'),
        series: z
          .array(
            z
              .object({
                field: z.string().describe('Numeric row field to plot.'),
                label: z.string().describe('Legend label.').optional(),
              })
              .strict(),
          )
          .min(1)
          .max(12)
          .describe('Numeric row fields to plot, one per series. pie/donut use only the first.'),
        title: DynamicStringSchema.describe('REF:#/$defs/DynamicString|Short title shown above the chart.').optional(),
        format: z
          .enum(['number', 'percent', 'currency', 'compact'])
          .default('number')
          .describe('How values are shown on the axis and in tooltips.')
          .optional(),
        currency: z.string().describe('ISO 4217 code when format is currency, e.g. USD.').optional(),
        height: z.enum(['small', 'medium', 'large']).default('medium').describe('Chart height.').optional(),
        // Typed as a dynamic union (not the plain DataBindingSchema object) so the binder
        // treats it as DYNAMIC and exposes props.setSelection(); the wire format is still a DataBinding.
        selection: DynamicValueSchema.describe('REF:#/$defs/DataBinding|Data path where the clicked row is written, e.g. $/ui/picked.').optional(),
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

export function toNumberOrNull(v) {
  if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number(v.trim()) : NaN
  return Number.isFinite(n) ? n : null
}

export function seriesList(props) {
  const list = Array.isArray(props.series) ? props.series : []
  return list.map((s) => ({ field: s.field, label: s.label || s.field }))
}

export function summarize(props) {
  const rows = toRows(props.data)
  const names = seriesList(props).map((s) => s.label)
  const parts = []
  if (props.title) parts.push(String(props.title))
  parts.push(`${props.type || 'chart'} chart of ${names.join(', ') || 'no series'}, ${rows.length} ${rows.length === 1 ? 'row' : 'rows'}`)
  return parts.join('. ')
}

function tooltipFormatter(props, fmt) {
  const type = props.type
  return (params) => {
    const list = Array.isArray(params) ? params : [params]
    if (type === 'pie' || type === 'donut') {
      const p = list[0] || {}
      return `${p.name}: ${fmt(p.value)}`
    }
    if (type === 'scatter') {
      const p = list[0] || {}
      const [x, y] = Array.isArray(p.value) ? p.value : []
      return `${p.seriesName}\n${props.x}: ${formatValue(x, 'number')}\n${fmt(y)}`
    }
    const head = list[0] ? String(list[0].name ?? list[0].axisValue ?? '') : ''
    return [head, ...list.map((p) => `${p.seriesName}: ${fmt(p.value)}`)].join('\n')
  }
}

export function buildOption(props, { textColor = FALLBACK_TEXT } = {}) {
  const type = props.type
  const format = props.format || 'number'
  const fmt = (v) => formatValue(v, format, props.currency)
  const rows = toRows(props.data)
  const series = seriesList(props)
  const base = {
    color: PALETTE,
    animation: false,
    textStyle: { color: textColor },
    tooltip: {
      renderMode: 'richText',
      confine: true,
      trigger: type === 'pie' || type === 'donut' || type === 'scatter' ? 'item' : 'axis',
      formatter: tooltipFormatter(props, fmt),
    },
  }

  if (type === 'pie' || type === 'donut') {
    const first = series[0] || { field: '', label: '' }
    return {
      ...base,
      legend: { show: true, bottom: 0, textStyle: { color: textColor } },
      series: [
        {
          type: 'pie',
          name: first.label,
          radius: type === 'donut' ? ['55%', '80%'] : '70%',
          label: { color: textColor },
          data: rows.map((r) => ({ name: String(r[props.x] ?? ''), value: toNumberOrNull(r[first.field]) })),
        },
      ],
    }
  }

  const categories = rows.map((r) => String(r[props.x] ?? ''))
  const valueAxis = {
    type: 'value',
    axisLabel: { color: textColor, formatter: (v) => fmt(v) },
    splitLine: { lineStyle: { color: 'rgba(128,128,128,0.25)' } },
  }
  const categoryAxis = { type: 'category', data: categories, axisLabel: { color: textColor }, axisLine: { lineStyle: { color: textColor } } }
  const scatterXAxis = { type: 'value', scale: true, axisLabel: { color: textColor }, splitLine: { show: false } }
  const horizontal = type === 'horizontalBar'
  const multi = series.length > 1

  const out = {
    ...base,
    grid: { left: 8, right: 16, top: multi ? 36 : 16, bottom: 8, containLabel: true },
    legend: { show: multi, top: 0, textStyle: { color: textColor } },
    xAxis: type === 'scatter' ? scatterXAxis : horizontal ? valueAxis : categoryAxis,
    yAxis: horizontal ? { ...categoryAxis, inverse: true } : valueAxis,
    series: series.map((s) => {
      const values = rows.map((r) => toNumberOrNull(r[s.field]))
      if (type === 'scatter') {
        return { type: 'scatter', name: s.label, data: rows.map((r, i) => [toNumberOrNull(r[props.x]), values[i]]) }
      }
      if (type === 'line' || type === 'area') {
        const item = { type: 'line', name: s.label, data: values, smooth: false, showSymbol: rows.length <= 60 }
        if (type === 'area') item.areaStyle = { opacity: 0.25 }
        return item
      }
      const item = { type: 'bar', name: s.label, data: values }
      if (type === 'stackedBar') item.stack = 'total'
      return item
    }),
  }
  return out
}

export class UirizzChartElement extends UirizzElement {
  static tagName = 'uirizz-chart'
  static properties = { _showTable: { state: true } }

  constructor() {
    super()
    this._showTable = false
    this._chart = null
    this._chartEl = null
    this._observer = null
  }

  connectedCallback() {
    super.connectedCallback()
    if (this.hasUpdated) this.requestUpdate()
  }

  disconnectedCallback() {
    super.disconnectedCallback()
    this._teardown()
  }

  _teardown() {
    if (this._observer) {
      this._observer.disconnect()
      this._observer = null
    }
    if (this._chart) {
      this._chart.dispose()
      this._chart = null
    }
    this._chartEl = null
  }

  _textColor() {
    if (typeof getComputedStyle !== 'function') return FALLBACK_TEXT
    const cs = getComputedStyle(this)
    for (const name of ['--foreground', '--ui-foreground']) {
      const v = cs.getPropertyValue(name)
      if (v && v.trim()) return v.trim()
    }
    return FALLBACK_TEXT
  }

  _toggle() {
    this._showTable = !this._showTable
  }

  _onClick(params) {
    const props = this.controller?.props
    if (!props || !params) return
    const row = toRows(props.data)[params.dataIndex]
    if (row === undefined) return
    props.setSelection?.(row)
    props.action?.()
  }

  render() {
    const props = this.controller?.props
    if (!props) return nothing
    const rows = toRows(props.data)
    const height = HEIGHTS[props.height] || HEIGHTS.medium
    const label = summarize(props)
    return html`
      <div class="uirizz-chart" style="display:block;width:100%">
        <div class="uirizz-chart-head" style="display:flex;align-items:center;justify-content:space-between;gap:8px">
          ${props.title ? html`<div class="uirizz-chart-title" style="font-weight:600">${String(props.title)}</div>` : html`<span></span>`}
          <button type="button" class="uirizz-chart-toggle" aria-pressed=${this._showTable ? 'true' : 'false'} @click=${() => this._toggle()}>
            ${this._showTable ? 'View as chart' : 'View as table'}
          </button>
        </div>
        ${this._showTable
          ? this._renderTable(props, rows)
          : html`<div class="uirizz-chart-canvas" role="img" aria-label=${label} style="width:100%;height:${height}px"></div>`}
      </div>
    `
  }

  _renderTable(props, rows) {
    const series = seriesList(props)
    const fmt = (v) => formatValue(v, props.format || 'number', props.currency)
    return html`
      <div style="overflow:auto;max-height:${HEIGHTS[props.height] || HEIGHTS.medium}px">
        <table class="uirizz-chart-table">
          <thead>
            <tr>
              <th scope="col">${props.x}</th>
              ${series.map((s) => html`<th scope="col">${s.label}</th>`)}
            </tr>
          </thead>
          <tbody>
            ${rows.map(
              (r) => html`<tr>
                <th scope="row">${String(r[props.x] ?? '—')}</th>
                ${series.map((s) => html`<td>${fmt(toNumberOrNull(r[s.field]))}</td>`)}
              </tr>`,
            )}
          </tbody>
        </table>
      </div>
    `
  }

  updated(changed) {
    if (typeof super.updated === 'function') super.updated(changed)
    const props = this.controller?.props
    if (this._showTable || !props) {
      if (this._chart) this._teardown()
      return
    }
    const el = this.querySelector('.uirizz-chart-canvas')
    if (!el) return
    if (this._chart && this._chartEl !== el) this._teardown()
    if (!this._chart) {
      this._chartEl = el
      this._chart = echarts.init(el, null, { renderer: 'svg' })
      this._chart.on('click', (params) => this._onClick(params))
      if (typeof ResizeObserver !== 'undefined') {
        this._observer = new ResizeObserver(() => this._chart && this._chart.resize())
        this._observer.observe(el)
      }
    }
    this._chart.setOption(buildOption(props, { textColor: this._textColor() }), true)
  }
}

export const ChartEntry = entry(UirizzChartElement, ChartApi)
