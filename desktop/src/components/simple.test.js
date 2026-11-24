import { describe, expect, it, vi } from 'vitest'
import { render } from 'lit'
import {
  SIMPLE_ENTRIES,
  MetricApi,
  ProgressApi,
  BadgeApi,
  CalloutApi,
  KeyValueListApi,
  TimelineApi,
  CodeBlockApi,
  sparklinePoints,
  progressPercent,
  trendGlyph,
  validKeyValueItems,
  validTimelineItems,
  statusColor,
  UirizzProgressElement,
  UirizzCalloutElement,
  UirizzMetricElement,
  UirizzCodeBlockElement,
  UirizzKeyValueListElement,
  UirizzTimelineElement,
} from './simple.js'

const ok = (api, v) => api.schema.safeParse(v).success

describe('schemas', () => {
  it('accept contract examples', () => {
    expect(ok(MetricApi, { label: 'MRR', value: '$1k', delta: '+4%', trend: 'up', status: 'good', sparkline: [1, 2, 3], weight: 1 })).toBe(true)
    expect(ok(MetricApi, { label: 'MRR', value: { path: '/v' }, sparkline: { path: '/s' } })).toBe(true)
    expect(ok(ProgressApi, { value: 40, max: 80, label: 'Upload', status: 'warning' })).toBe(true)
    expect(ok(ProgressApi, { value: { path: '/p' } })).toBe(true)
    expect(ok(BadgeApi, { text: 'Live', status: 'info' })).toBe(true)
    expect(ok(CalloutApi, { text: 'Heads up', tone: 'success', title: 'Note' })).toBe(true)
    expect(ok(KeyValueListApi, { items: [{ key: 'a', value: 'b' }] })).toBe(true)
    expect(ok(KeyValueListApi, { items: { path: '/kv' } })).toBe(true)
    expect(ok(TimelineApi, { items: [{ date: 'x', title: 'y' }] })).toBe(true)
    expect(ok(CodeBlockApi, { code: 'print(1)', language: 'python' })).toBe(true)
  })
  it('reject unknown props and bad enums', () => {
    expect(ok(MetricApi, { label: 'a', value: 'b', bogus: 1 })).toBe(false)
    expect(ok(ProgressApi, { value: 1, bogus: 1 })).toBe(false)
    expect(ok(BadgeApi, { text: 'a', bogus: 1 })).toBe(false)
    expect(ok(CalloutApi, { text: 'a', bogus: 1 })).toBe(false)
    expect(ok(KeyValueListApi, { items: [], bogus: 1 })).toBe(false)
    expect(ok(TimelineApi, { items: [], bogus: 1 })).toBe(false)
    expect(ok(CodeBlockApi, { code: 'a', bogus: 1 })).toBe(false)
    expect(ok(BadgeApi, { text: 'a', status: 'nope' })).toBe(false)
    expect(ok(CalloutApi, { text: 'a', tone: 'good' })).toBe(false)
    expect(ok(MetricApi, { label: 'a', value: 'b', status: 'info' })).toBe(false)
    expect(ok(MetricApi, { value: 'b' })).toBe(false)
  })
})

describe('helpers', () => {
  it('sparklinePoints', () => {
    expect(sparklinePoints([], 80, 24)).toBe('')
    expect(sparklinePoints([5], 80, 24)).toBe('')
    expect(sparklinePoints('x')).toBe('')
    expect(sparklinePoints([1, 'a', NaN, 2, Infinity, null])).not.toBe('')
    expect(sparklinePoints([1, 'a', NaN])).toBe('')
    const pts = sparklinePoints([0, 10], 80, 24).split(' ')
    expect(pts).toHaveLength(2)
    expect(pts[0].startsWith('0,')).toBe(true)
    expect(pts[1].startsWith('80,')).toBe(true)
    expect(sparklinePoints([3, 3, 3], 80, 24)).toBe('0,12 40,12 80,12')
  })
  it('progressPercent', () => {
    expect(progressPercent(50, 100)).toBe(50)
    expect(progressPercent(50)).toBe(50)
    expect(progressPercent(150, 100)).toBe(100)
    expect(progressPercent(-5, 100)).toBe(0)
    expect(progressPercent(5, 0)).toBe(0)
    expect(progressPercent(5, -1)).toBe(0)
    expect(progressPercent(NaN, 10)).toBe(0)
    expect(progressPercent('3', 10)).toBe(0)
    expect(progressPercent(5, NaN)).toBe(5)
    expect(progressPercent(1, 4)).toBe(25)
  })
  it('trendGlyph and statusColor', () => {
    expect(trendGlyph('up')).toBe('▲')
    expect(trendGlyph('down')).toBe('▼')
    expect(trendGlyph('flat')).toBe('—')
    expect(trendGlyph(undefined)).toBe('—')
    expect(statusColor('good')).toContain('#54D3A1')
    expect(statusColor('weird')).toContain('#93A4B8')
  })
  it('validKeyValueItems', () => {
    expect(validKeyValueItems(undefined)).toEqual([])
    expect(validKeyValueItems([])).toEqual([])
    expect(validKeyValueItems([null, 1, 'x', [], { value: 'v' }, { key: '' }, { key: 'a', value: 2 }])).toEqual([{ key: 'a', value: '2' }])
    const many = Array.from({ length: 500 }, (_, i) => ({ key: `k${i}`, value: 'v' }))
    expect(validKeyValueItems(many)).toHaveLength(200)
  })
  it('validTimelineItems', () => {
    expect(validTimelineItems(null)).toEqual([])
    expect(validTimelineItems([{ date: 'd' }, { title: '' }, 5])).toEqual([])
    expect(validTimelineItems([{ title: 't', status: 'good' }])).toEqual([{ date: '', title: 't', detail: '', status: 'good' }])
    const many = Array.from({ length: 500 }, (_, i) => ({ title: `t${i}` }))
    expect(validTimelineItems(many)).toHaveLength(200)
  })
})

describe('entries', () => {
  it('has 7 entries with unique tags and names', () => {
    expect(SIMPLE_ENTRIES).toHaveLength(7)
    expect(SIMPLE_ENTRIES.map((e) => e.name)).toEqual(['Metric', 'Progress', 'Badge', 'Callout', 'KeyValueList', 'Timeline', 'CodeBlock'])
    expect(SIMPLE_ENTRIES.map((e) => e.tagName)).toEqual([
      'uirizz-metric', 'uirizz-progress', 'uirizz-badge', 'uirizz-callout', 'uirizz-key-value-list', 'uirizz-timeline', 'uirizz-code-block',
    ])
    expect(new Set(SIMPLE_ENTRIES.map((e) => e.tagName)).size).toBe(7)
    for (const e of SIMPLE_ENTRIES) {
      expect(e.element.tagName).toBe(e.tagName)
      expect(e.schema).toBeTruthy()
    }
  })
})

// Render an element's template directly with stubbed props (no catalog plumbing).
function renderWith(Ctor, props) {
  const tag = Ctor.tagName + '-test'
  if (!customElements.get(tag)) customElements.define(tag, class extends Ctor {})
  const el = document.createElement(tag)
  el._controller = { props }
  const host = document.createElement('div')
  render(el.render(), host)
  return { el, host }
}

describe('rendering', () => {
  it('Progress exposes ARIA attributes and clamps', () => {
    const { host } = renderWith(UirizzProgressElement, { value: 250, max: 200, label: 'Disk', status: 'critical' })
    const bar = host.querySelector('[role="progressbar"]')
    expect(bar.getAttribute('aria-valuenow')).toBe('250')
    expect(bar.getAttribute('aria-valuemin')).toBe('0')
    expect(bar.getAttribute('aria-valuemax')).toBe('200')
    expect(bar.firstElementChild.getAttribute('style')).toContain('width:100%')
    expect(host.textContent).toContain('100%')
  })
  it('Callout renders text as plain text with role=note', () => {
    const { host } = renderWith(UirizzCalloutElement, { text: '<img src=x onerror=alert(1)>', title: 'T', tone: 'warning' })
    expect(host.querySelector('[role="note"]')).toBeTruthy()
    expect(host.querySelector('img')).toBeNull()
    expect(host.textContent).toContain('<img src=x')
  })
  it('Metric sparkline is aria-hidden and skipped with <2 numbers', () => {
    const a = renderWith(UirizzMetricElement, { label: 'L', value: 'V', delta: '+1', trend: 'up', status: 'good', sparkline: [1, 2, 3] })
    expect(a.host.querySelector('svg').getAttribute('aria-hidden')).toBe('true')
    expect(a.host.textContent).toContain('▲')
    const b = renderWith(UirizzMetricElement, { label: 'L', value: 'V', sparkline: [1, 'x'] })
    expect(b.host.querySelector('svg')).toBeNull()
  })
  it('KeyValueList and Timeline reset the prose margins that break row alignment', () => {
    const kv = renderWith(UirizzKeyValueListElement, { items: [{ key: 'Prompt cache', value: 'unchanged' }] })
    expect(kv.host.querySelector('dt').getAttribute('style')).toContain('margin:0')
    expect(kv.host.querySelector('dd').getAttribute('style')).toContain('margin:0')
    expect(kv.host.querySelector('dl').getAttribute('style')).toContain('align-items:start')

    const tl = renderWith(UirizzTimelineElement, { items: [{ date: '01', title: 'Receive' }] })
    expect(tl.host.querySelector('li').getAttribute('style')).toContain('margin:0')
  })
  it('CodeBlock copies and shows Copied for 1.5s, failing silently', async () => {
    vi.useFakeTimers()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const { el } = renderWith(UirizzCodeBlockElement, { code: 'abc', language: 'js' })
    await el._copy()
    expect(writeText).toHaveBeenCalledWith('abc')
    expect(el._copied).toBe(true)
    vi.advanceTimersByTime(1500)
    expect(el._copied).toBe(false)
    writeText.mockRejectedValue(new Error('denied'))
    await expect(el._copy()).resolves.toBeUndefined()
    expect(el._copied).toBe(false)
    vi.useRealTimers()
  })
})
