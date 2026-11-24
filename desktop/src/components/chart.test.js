import { beforeEach, describe, expect, it, vi } from 'vitest'

const fake = vi.hoisted(() => ({ charts: [] }))

vi.mock('echarts/core', () => ({
  use: vi.fn(),
  init: vi.fn(() => {
    const chart = {
      handlers: {},
      options: [],
      setOption: vi.fn((o) => chart.options.push(o)),
      on: vi.fn((name, fn) => {
        chart.handlers[name] = fn
      }),
      resize: vi.fn(),
      dispose: vi.fn(),
    }
    fake.charts.push(chart)
    return chart
  }),
}))

import * as echarts from 'echarts/core'
import { scrapeSchemaBehavior } from '@a2ui/web_core/v1_0'
import { ChartApi, ChartEntry, UirizzChartElement, buildOption, summarize, PALETTE } from './chart.js'

const rows = [
  { month: 'Jan', sales: 10, cost: '4' },
  { month: 'Feb', sales: 'n/a', cost: 6 },
  { month: 'Mar', sales: 30, cost: null },
]
const base = { type: 'line', data: rows, x: 'month', series: [{ field: 'sales', label: 'Sales' }, { field: 'cost' }] }

describe('ChartApi / ChartEntry', () => {
  it('binds selection as dynamic so props.setSelection exists, and action as ACTION', () => {
    const shape = scrapeSchemaBehavior(ChartApi.schema).shape
    expect(shape.selection.type).toBe('DYNAMIC')
    expect(shape.action.type).toBe('ACTION')
    expect(ChartApi.schema.safeParse({ type: 'bar', data: { '@path': '/s' }, x: 'a', series: [{ field: 'b' }], selection: { '@path': '/ui/p' } }).success).toBe(true)
  })
  it('has the contract shape', () => {
    expect(ChartApi.name).toBe('Chart')
    expect(ChartEntry.tagName).toBe('uirizz-chart')
    expect(ChartEntry.element).toBe(UirizzChartElement)
    const ok = ChartApi.schema.safeParse({ type: 'pie', data: [], x: 'a', series: [{ field: 'b' }] })
    expect(ok.success).toBe(true)
    expect(ChartApi.schema.safeParse({ type: 'radar', data: [], x: 'a', series: [{ field: 'b' }] }).success).toBe(false)
    expect(ChartApi.schema.safeParse({ type: 'bar', data: [], x: 'a', series: [] }).success).toBe(false)
    expect(ChartApi.schema.safeParse({ type: 'bar', data: [], x: 'a', series: [{ field: 'b' }], extra: 1 }).success).toBe(false)
  })
})

describe('buildOption', () => {
  it('line maps categories and series, non-numeric becomes null', () => {
    const o = buildOption(base)
    expect(o.xAxis.type).toBe('category')
    expect(o.xAxis.data).toEqual(['Jan', 'Feb', 'Mar'])
    expect(o.series.map((s) => s.type)).toEqual(['line', 'line'])
    expect(o.series[0].name).toBe('Sales')
    expect(o.series[1].name).toBe('cost')
    expect(o.series[0].data).toEqual([10, null, 30])
    expect(o.series[1].data).toEqual([4, 6, null])
    expect(o.color).toEqual(PALETTE)
    expect(PALETTE).toHaveLength(8)
  })

  it('area adds areaStyle', () => {
    const o = buildOption({ ...base, type: 'area' })
    expect(o.series[0].type).toBe('line')
    expect(o.series[0].areaStyle).toBeTruthy()
  })

  it('bar and stackedBar', () => {
    expect(buildOption({ ...base, type: 'bar' }).series[0]).toMatchObject({ type: 'bar' })
    expect(buildOption({ ...base, type: 'bar' }).series[0].stack).toBeUndefined()
    const s = buildOption({ ...base, type: 'stackedBar' })
    expect(s.series.every((x) => x.type === 'bar' && x.stack === 'total')).toBe(true)
  })

  it('horizontalBar swaps the axes', () => {
    const o = buildOption({ ...base, type: 'horizontalBar' })
    expect(o.yAxis.type).toBe('category')
    expect(o.yAxis.data).toEqual(['Jan', 'Feb', 'Mar'])
    expect(o.xAxis.type).toBe('value')
  })

  it('scatter uses a numeric x axis', () => {
    const o = buildOption({
      type: 'scatter',
      x: 'a',
      series: [{ field: 'b' }],
      data: [{ a: 1, b: 2 }, { a: 'x', b: 3 }],
    })
    expect(o.xAxis.type).toBe('value')
    expect(o.series[0].type).toBe('scatter')
    expect(o.series[0].data).toEqual([[1, 2], [null, 3]])
  })

  it('pie and donut use only the first series', () => {
    const pie = buildOption({ ...base, type: 'pie' })
    expect(pie.series).toHaveLength(1)
    expect(pie.series[0].type).toBe('pie')
    expect(pie.series[0].data).toEqual([
      { name: 'Jan', value: 10 },
      { name: 'Feb', value: null },
      { name: 'Mar', value: 30 },
    ])
    const donut = buildOption({ ...base, type: 'donut' })
    expect(donut.series).toHaveLength(1)
    expect(donut.series[0].radius).toEqual(['55%', '80%'])
    expect(donut.series[0].name).toBe('Sales')
  })

  it('caps rows at 2000', () => {
    const data = Array.from({ length: 2500 }, (_, i) => ({ month: String(i), sales: i }))
    expect(buildOption({ ...base, data }).xAxis.data).toHaveLength(2000)
  })

  it('tooltips are rich text and use format.js', () => {
    const o = buildOption({ ...base, format: 'currency', currency: 'USD' })
    expect(o.tooltip.renderMode).toBe('richText')
    const text = o.tooltip.formatter([{ seriesName: 'Sales', name: 'Jan', value: 1234.5 }])
    expect(text).toContain('$1,234.50')
    expect(o.yAxis.axisLabel.formatter(5)).toBe('$5.00')
    const pie = buildOption({ ...base, type: 'pie', format: 'percent' })
    expect(pie.tooltip.formatter({ name: 'Jan', value: 0.5 })).toBe('Jan: 50%')
  })

  it('uses the given text colour', () => {
    expect(buildOption(base, { textColor: '#123456' }).textStyle.color).toBe('#123456')
    expect(buildOption(base).textStyle.color).toBe('#E6EDF5')
  })

  it('summarizes for aria-label', () => {
    expect(summarize({ ...base, title: 'Revenue' })).toBe('Revenue. line chart of Sales, cost, 3 rows')
  })
})

describe('uirizz-chart element', () => {
  let n = 0
  function mount(props) {
    const tag = `uirizz-chart-test-${++n}`
    customElements.define(tag, class extends UirizzChartElement {})
    const el = document.createElement(tag)
    el._controller = { props, dispose() {} }
    document.body.appendChild(el)
    return el
  }

  beforeEach(() => {
    fake.charts.length = 0
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('renders title, labelled canvas, height and sets the option', async () => {
    const el = mount({ ...base, title: 'Revenue', height: 'large' })
    await el.updateComplete
    expect(el.querySelector('.uirizz-chart-title').textContent).toBe('Revenue')
    const canvas = el.querySelector('.uirizz-chart-canvas')
    expect(canvas.getAttribute('role')).toBe('img')
    expect(canvas.getAttribute('aria-label')).toContain('Revenue')
    expect(canvas.style.height).toBe('380px')
    expect(echarts.init).toHaveBeenCalledWith(canvas, null, { renderer: 'svg' })
    expect(fake.charts[0].options[0].series).toHaveLength(2)
  })

  it('defaults to medium height', async () => {
    const el = mount(base)
    await el.updateComplete
    expect(el.querySelector('.uirizz-chart-canvas').style.height).toBe('260px')
  })

  it('click writes selection then fires action, in that order', async () => {
    const calls = []
    const el = mount({
      ...base,
      setSelection: (r) => calls.push(['sel', r]),
      action: () => calls.push(['act']),
    })
    await el.updateComplete
    fake.charts[0].handlers.click({ dataIndex: 2 })
    expect(calls).toEqual([['sel', rows[2]], ['act']])
  })

  it('click without setSelection or action does not throw', async () => {
    const el = mount(base)
    await el.updateComplete
    expect(() => fake.charts[0].handlers.click({ dataIndex: 0 })).not.toThrow()
  })

  it('toggles to a plain table and back', async () => {
    const el = mount({ ...base, format: 'number' })
    await el.updateComplete
    const btn = el.querySelector('.uirizz-chart-toggle')
    expect(btn.textContent.trim()).toBe('View as table')
    btn.click()
    await el.updateComplete
    expect(el.querySelector('.uirizz-chart-canvas')).toBeNull()
    expect(fake.charts[0].dispose).toHaveBeenCalled()
    const cells = [...el.querySelectorAll('table tbody tr')].map((tr) => [...tr.children].map((c) => c.textContent.trim()))
    expect(cells).toEqual([
      ['Jan', '10', '4'],
      ['Feb', '—', '6'],
      ['Mar', '30', '—'],
    ])
    expect([...el.querySelectorAll('thead th')].map((t) => t.textContent.trim())).toEqual(['month', 'Sales', 'cost'])
    el.querySelector('.uirizz-chart-toggle').click()
    await el.updateComplete
    expect(el.querySelector('.uirizz-chart-canvas')).not.toBeNull()
    expect(fake.charts).toHaveLength(2)
  })

  it('resizes via ResizeObserver and disposes on disconnect', async () => {
    let cb
    const disconnect = vi.fn()
    vi.stubGlobal('ResizeObserver', class {
      constructor(f) { cb = f }
      observe() {}
      disconnect() { disconnect() }
    })
    try {
      const el = mount(base)
      await el.updateComplete
      cb()
      expect(fake.charts[0].resize).toHaveBeenCalled()
      el.remove()
      expect(fake.charts[0].dispose).toHaveBeenCalled()
      expect(disconnect).toHaveBeenCalled()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('applies weight to flex', async () => {
    const el = mount({ ...base, weight: 2 })
    await el.updateComplete
    el.requestUpdate()
    await el.updateComplete
    expect(el.style.flex).toContain('2')
  })
})
