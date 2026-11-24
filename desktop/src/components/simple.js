import { html, nothing } from 'lit'
import { z } from 'zod'
import {
  A2uiLitElement,
  DynamicNumberSchema,
  DynamicStringSchema,
  DynamicValueSchema,
  WeightSchema,
  injectBasicCatalogStyles,
  spec,
} from '@a2ui/web_core/v1_0'

// ---------------------------------------------------------------- helpers

export const MAX_ITEMS = 200

const COLORS = {
  text: 'var(--a2ui-color-on-surface, #E6EDF5)',
  muted: 'var(--a2ui-color-muted, #93A4B8)',
  surface: 'var(--a2ui-color-surface, #111821)',
  border: 'var(--a2ui-color-border, #243242)',
  good: 'var(--a2ui-color-good, #54D3A1)',
  warning: 'var(--a2ui-color-warning, #F0B86E)',
  critical: 'var(--a2ui-color-critical, #F2706B)',
  info: 'var(--a2ui-color-info, #7AA2F7)',
  neutral: 'var(--a2ui-color-neutral, #93A4B8)',
}

export function statusColor(status) {
  if (!["good", "warning", "critical", "info", "neutral"].includes(status)) return COLORS.neutral
  return COLORS[status]
}

const TONE_STATUS = { info: 'info', success: 'good', warning: 'warning', critical: 'critical' }
export function toneColor(tone) {
  return statusColor(TONE_STATUS[tone] || 'info')
}

const isNum = (n) => typeof n === 'number' && Number.isFinite(n)

export function numericSeries(values) {
  return Array.isArray(values) ? values.filter(isNum) : []
}

/** Returns an SVG polyline `points` string, or '' when fewer than 2 numbers. */
export function sparklinePoints(nums, w = 80, h = 24) {
  const v = numericSeries(nums)
  if (v.length < 2) return ''
  const min = Math.min(...v)
  const max = Math.max(...v)
  const span = max - min
  const pad = 2
  return v
    .map((n, i) => {
      const x = (i / (v.length - 1)) * w
      const y = span === 0 ? h / 2 : pad + (1 - (n - min) / span) * (h - 2 * pad)
      return `${+x.toFixed(2)},${+y.toFixed(2)}`
    })
    .join(' ')
}

/** Percent (0..100) of value/max, clamped; bad input gives 0. */
export function progressPercent(value, max = 100) {
  const m = isNum(max) ? max : 100
  if (!isNum(value) || m <= 0) return 0
  return Math.min(100, Math.max(0, (value / m) * 100))
}

export function trendGlyph(trend) {
  return trend === 'up' ? '▲' : trend === 'down' ? '▼' : '—'
}

const isObj = (o) => o !== null && typeof o === 'object' && !Array.isArray(o)
const str = (v) => (typeof v === 'string' ? v : isNum(v) ? String(v) : '')

export function validKeyValueItems(items) {
  if (!Array.isArray(items)) return []
  const out = []
  for (const it of items) {
    if (!isObj(it)) continue
    const key = str(it.key)
    if (!key) continue
    out.push({ key, value: str(it.value) })
    if (out.length >= MAX_ITEMS) break
  }
  return out
}

export function validTimelineItems(items) {
  if (!Array.isArray(items)) return []
  const out = []
  for (const it of items) {
    if (!isObj(it)) continue
    const title = str(it.title)
    if (!title) continue
    out.push({ date: str(it.date), title, detail: str(it.detail), status: str(it.status) })
    if (out.length >= MAX_ITEMS) break
  }
  return out
}

// ---------------------------------------------------------------- base

export class SimpleElement extends A2uiLitElement {
  createRenderRoot() {
    return this
  }

  connectedCallback() {
    super.connectedCallback()
    if (typeof injectBasicCatalogStyles === 'function') {
      try {
        injectBasicCatalogStyles()
      } catch {
        /* styling is best effort */
      }
    }
  }

  willUpdate(changed) {
    super.willUpdate(changed)
    const props = this.controller?.props
    if (props && props.weight !== undefined) this.style.flex = String(props.weight)
    else this.style.removeProperty('flex')
  }
}

const font = 'font-family:var(--a2ui-font-family,inherit);color:' + COLORS.text + ';'

// ---------------------------------------------------------------- APIs

export const MetricApi = {
  name: 'Metric',
  schema: spec(
    z
      .object({
        label: DynamicStringSchema,
        value: DynamicStringSchema,
        delta: DynamicStringSchema.optional(),
        trend: z.enum(['up', 'down', 'flat']).optional(),
        status: z.enum(['good', 'warning', 'critical', 'neutral']).default('neutral').optional(),
        sparkline: DynamicValueSchema.optional(),
        weight: WeightSchema.optional(),
      })
      .strict(),
    { mixins: [] },
  ),
}

export const ProgressApi = {
  name: 'Progress',
  schema: spec(
    z
      .object({
        value: DynamicNumberSchema,
        max: DynamicNumberSchema.optional(),
        label: DynamicStringSchema.optional(),
        status: z.enum(['good', 'warning', 'critical', 'neutral']).default('neutral').optional(),
        weight: WeightSchema.optional(),
      })
      .strict(),
    { mixins: [] },
  ),
}

export const BadgeApi = {
  name: 'Badge',
  schema: spec(
    z
      .object({
        text: DynamicStringSchema,
        status: z.enum(['good', 'warning', 'critical', 'neutral', 'info']).default('neutral').optional(),
        weight: WeightSchema.optional(),
      })
      .strict(),
    { mixins: [] },
  ),
}

export const CalloutApi = {
  name: 'Callout',
  schema: spec(
    z
      .object({
        text: DynamicStringSchema,
        tone: z.enum(['info', 'success', 'warning', 'critical']).default('info').optional(),
        title: DynamicStringSchema.optional(),
        weight: WeightSchema.optional(),
      })
      .strict(),
    { mixins: [] },
  ),
}

export const KeyValueListApi = {
  name: 'KeyValueList',
  schema: spec(
    z.object({ items: DynamicValueSchema, weight: WeightSchema.optional() }).strict(),
    { mixins: [] },
  ),
}

export const TimelineApi = {
  name: 'Timeline',
  schema: spec(
    z.object({ items: DynamicValueSchema, weight: WeightSchema.optional() }).strict(),
    { mixins: [] },
  ),
}

export const CodeBlockApi = {
  name: 'CodeBlock',
  schema: spec(
    z
      .object({
        code: DynamicStringSchema,
        language: z.string().optional(),
        weight: WeightSchema.optional(),
      })
      .strict(),
    { mixins: [] },
  ),
}

// ---------------------------------------------------------------- elements

export class UirizzMetricElement extends SimpleElement {
  render() {
    const p = this.controller?.props
    if (!p) return nothing
    const color = statusColor(p.status)
    const points = sparklinePoints(p.sparkline, 80, 24)
    const delta = str(p.delta)
    return html`<div style="${font}display:flex;flex-direction:column;gap:4px;padding:12px 14px;background:${COLORS.surface};border:1px solid ${COLORS.border};border-radius:10px;">
      <div style="font-size:12px;color:${COLORS.muted};">${str(p.label)}</div>
      <div style="font-size:28px;font-weight:600;line-height:1.1;">${str(p.value)}</div>
      ${delta
        ? html`<div style="font-size:13px;color:${color};">${trendGlyph(p.trend)} ${delta}</div>`
        : nothing}
      ${points
        ? html`<svg width="80" height="24" viewBox="0 0 80 24" aria-hidden="true" style="margin-top:4px;"><polyline points=${points} fill="none" stroke=${color} stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"></polyline></svg>`
        : nothing}
    </div>`
  }
}
UirizzMetricElement.tagName = 'uirizz-metric'

export class UirizzProgressElement extends SimpleElement {
  render() {
    const p = this.controller?.props
    if (!p) return nothing
    const max = isNum(p.max) ? p.max : 100
    const pct = progressPercent(p.value, max)
    const label = str(p.label)
    const now = isNum(p.value) ? p.value : 0
    return html`<div style="${font}display:flex;flex-direction:column;gap:4px;">
      <div style="display:flex;justify-content:space-between;font-size:13px;">
        <span style="color:${COLORS.muted};">${label}</span><span>${Math.round(pct)}%</span>
      </div>
      <div role="progressbar" aria-valuenow=${String(now)} aria-valuemin="0" aria-valuemax=${String(max)} aria-label=${label || nothing} style="height:8px;border-radius:4px;background:${COLORS.border};overflow:hidden;">
        <div style="height:100%;width:${pct}%;background:${statusColor(p.status)};border-radius:4px;"></div>
      </div>
    </div>`
  }
}
UirizzProgressElement.tagName = 'uirizz-progress'

export class UirizzBadgeElement extends SimpleElement {
  render() {
    const p = this.controller?.props
    if (!p) return nothing
    const color = statusColor(p.status)
    return html`<span style="${font}display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid ${color};color:${color};background:${COLORS.surface};">${str(p.text)}</span>`
  }
}
UirizzBadgeElement.tagName = 'uirizz-badge'

export class UirizzCalloutElement extends SimpleElement {
  render() {
    const p = this.controller?.props
    if (!p) return nothing
    const title = str(p.title)
    return html`<div role="note" style="${font}padding:10px 14px;background:${COLORS.surface};border:1px solid ${COLORS.border};border-left:4px solid ${toneColor(p.tone)};border-radius:6px;">
      ${title ? html`<div style="font-weight:700;margin-bottom:2px;">${title}</div>` : nothing}
      <div style="white-space:pre-wrap;">${str(p.text)}</div>
    </div>`
  }
}
UirizzCalloutElement.tagName = 'uirizz-callout'

export class UirizzKeyValueListElement extends SimpleElement {
  render() {
    const p = this.controller?.props
    if (!p) return nothing
    const items = validKeyValueItems(p.items)
    return html`<dl style="${font}display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:0;font-size:14px;">
      ${items.map(
        (it) => html`<dt style="color:${COLORS.muted};">${it.key}</dt><dd style="margin:0;">${it.value}</dd>`,
      )}
    </dl>`
  }
}
UirizzKeyValueListElement.tagName = 'uirizz-key-value-list'

export class UirizzTimelineElement extends SimpleElement {
  render() {
    const p = this.controller?.props
    if (!p) return nothing
    const items = validTimelineItems(p.items)
    return html`<ol style="${font}list-style:none;margin:0;padding:0;font-size:14px;">
      ${items.map(
        (it) => html`<li style="display:flex;gap:10px;padding:0 0 12px 0;">
          <span aria-hidden="true" style="flex:none;width:10px;height:10px;margin-top:5px;border-radius:50%;background:${statusColor(it.status)};"></span>
          <div>
            ${it.date ? html`<div style="font-size:12px;color:${COLORS.muted};">${it.date}</div>` : nothing}
            <div style="font-weight:600;">${it.title}</div>
            ${it.detail ? html`<div style="color:${COLORS.muted};">${it.detail}</div>` : nothing}
          </div>
        </li>`,
      )}
    </ol>`
  }
}
UirizzTimelineElement.tagName = 'uirizz-timeline'

export class UirizzCodeBlockElement extends SimpleElement {
  static properties = { _copied: { state: true } }

  constructor() {
    super()
    this._copied = false
    this._timer = undefined
  }

  disconnectedCallback() {
    super.disconnectedCallback()
    clearTimeout(this._timer)
  }

  async _copy() {
    const code = str(this.controller?.props?.code)
    try {
      await navigator.clipboard?.writeText(code)
    } catch {
      return
    }
    if (!navigator.clipboard) return
    this._copied = true
    clearTimeout(this._timer)
    this._timer = setTimeout(() => {
      this._copied = false
    }, 1500)
  }

  render() {
    const p = this.controller?.props
    if (!p) return nothing
    const lang = typeof p.language === 'string' ? p.language : ''
    return html`<div style="${font}background:${COLORS.surface};border:1px solid ${COLORS.border};border-radius:8px;overflow:hidden;">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 10px;border-bottom:1px solid ${COLORS.border};font-size:12px;color:${COLORS.muted};">
        <span>${lang}</span>
        <button type="button" @click=${() => this._copy()} style="background:none;border:1px solid ${COLORS.border};color:${COLORS.text};border-radius:4px;font-size:12px;padding:1px 8px;cursor:pointer;">${this._copied ? 'Copied' : 'Copy'}</button>
      </div>
      <pre style="margin:0;padding:10px 12px;overflow:auto;font-size:13px;"><code>${str(p.code)}</code></pre>
    </div>`
  }
}
UirizzCodeBlockElement.tagName = 'uirizz-code-block'

// ---------------------------------------------------------------- entries

const entry = (api, element) => ({ ...api, tagName: element.tagName, element })

export const MetricEntry = entry(MetricApi, UirizzMetricElement)
export const ProgressEntry = entry(ProgressApi, UirizzProgressElement)
export const BadgeEntry = entry(BadgeApi, UirizzBadgeElement)
export const CalloutEntry = entry(CalloutApi, UirizzCalloutElement)
export const KeyValueListEntry = entry(KeyValueListApi, UirizzKeyValueListElement)
export const TimelineEntry = entry(TimelineApi, UirizzTimelineElement)
export const CodeBlockEntry = entry(CodeBlockApi, UirizzCodeBlockElement)

export const SIMPLE_ENTRIES = [
  MetricEntry,
  ProgressEntry,
  BadgeEntry,
  CalloutEntry,
  KeyValueListEntry,
  TimelineEntry,
  CodeBlockEntry,
]
