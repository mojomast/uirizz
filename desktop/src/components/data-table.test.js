import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  DataTableApi,
  DataTableEntry,
  UirizzDataTableElement,
  nextSort,
  pageRange,
  sortRows,
} from './data-table.js'

const columns = [
  { field: 'name', label: 'Name' },
  { field: 'qty', label: 'Qty', align: 'end', format: 'number' },
  { field: 'price', label: 'Price', align: 'end', format: 'currency' },
  { field: 'share', format: 'percent', align: 'center' },
]
const data = [
  { name: 'b', qty: 10, price: 5, share: 0.25 },
  { name: 'a', qty: 9, price: 1234.5, share: 0.5 },
  { name: 'c', qty: 100, price: null, share: 'x' },
]

describe('schema and entry', () => {
  it('matches the contract', () => {
    expect(DataTableEntry.tagName).toBe('uirizz-data-table')
    expect(DataTableEntry.name).toBe('DataTable')
    expect(DataTableApi.schema.safeParse({ data: [], columns: [{ field: 'a' }] }).success).toBe(true)
    expect(DataTableApi.schema.safeParse({ data: [], columns: [] }).success).toBe(false)
    expect(DataTableApi.schema.safeParse({ data: [], columns: [{ field: 'a', align: 'left' }] }).success).toBe(false)
    expect(DataTableApi.schema.safeParse({ data: [], columns: [{ field: 'a' }], pageSize: 0 }).success).toBe(false)
  })
})

describe('sortRows / nextSort / pageRange', () => {
  it('sorts numbers numerically and strings naturally', () => {
    expect(sortRows(data, 'qty', 'asc').map((r) => r.qty)).toEqual([9, 10, 100])
    expect(sortRows(data, 'qty', 'desc').map((r) => r.qty)).toEqual([100, 10, 9])
    expect(sortRows(data, 'name', 'asc').map((r) => r.name)).toEqual(['a', 'b', 'c'])
  })
  it('puts missing values last and leaves input untouched', () => {
    expect(sortRows(data, 'price', 'asc').map((r) => r.name)).toEqual(['b', 'a', 'c'])
    expect(sortRows(data, 'price', 'desc').map((r) => r.name)).toEqual(['a', 'b', 'c'])
    expect(sortRows(data, 'qty', 'none')).toEqual(data)
    expect(data.map((r) => r.name)).toEqual(['b', 'a', 'c'])
  })
  it('cycles none, asc, desc, none', () => {
    let s = { field: null, dir: 'none' }
    s = nextSort(s, 'a')
    expect(s).toEqual({ field: 'a', dir: 'asc' })
    s = nextSort(s, 'a')
    expect(s).toEqual({ field: 'a', dir: 'desc' })
    s = nextSort(s, 'a')
    expect(s.dir).toBe('none')
    expect(nextSort({ field: 'a', dir: 'desc' }, 'b')).toEqual({ field: 'b', dir: 'asc' })
  })
  it('builds range text', () => {
    expect(pageRange(42, 0, 10).text).toBe('1–10 of 42')
    expect(pageRange(42, 4, 10).text).toBe('41–42 of 42')
    expect(pageRange(42, 99, 10).page).toBe(4)
    expect(pageRange(0, 0, 10).text).toBe('No rows')
  })
})

describe('uirizz-data-table element', () => {
  let n = 0
  function mount(props) {
    const tag = `uirizz-table-test-${++n}`
    customElements.define(tag, class extends UirizzDataTableElement {})
    const el = document.createElement(tag)
    el._controller = { props, dispose() {} }
    document.body.appendChild(el)
    return el
  }
  const bodyText = (el) =>
    [...el.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((c) => c.textContent.trim()))

  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('renders a real table with caption, formats and alignment', async () => {
    const el = mount({ data, columns, title: 'Items', currency: 'USD' })
    await el.updateComplete
    expect(el.querySelector('caption').textContent).toBe('Items')
    expect(el.querySelector('thead')).not.toBeNull()
    expect(bodyText(el)[0]).toEqual(['b', '10', '$5.00', '25%'])
    expect(bodyText(el)[1][2]).toBe('$1,234.50')
    expect(bodyText(el)[2]).toEqual(['c', '100', '—', '—'])
    const tds = el.querySelectorAll('tbody tr:first-child td')
    expect(tds[0].style.textAlign).toBe('start')
    expect(tds[1].style.textAlign).toBe('end')
    expect(tds[3].style.textAlign).toBe('center')
  })

  it('sorts via header buttons with aria-sort', async () => {
    const el = mount({ data, columns })
    await el.updateComplete
    const th = () => el.querySelectorAll('thead th')[1]
    expect(th().getAttribute('aria-sort')).toBe('none')
    th().querySelector('button').click()
    await el.updateComplete
    expect(th().getAttribute('aria-sort')).toBe('ascending')
    expect(bodyText(el).map((r) => r[1])).toEqual(['9', '10', '100'])
    th().querySelector('button').click()
    await el.updateComplete
    expect(th().getAttribute('aria-sort')).toBe('descending')
    expect(bodyText(el).map((r) => r[1])).toEqual(['100', '10', '9'])
    th().querySelector('button').click()
    await el.updateComplete
    expect(th().getAttribute('aria-sort')).toBe('none')
    expect(bodyText(el).map((r) => r[0])).toEqual(['b', 'a', 'c'])
  })

  it('has no sort buttons when sortable is false', async () => {
    const el = mount({ data, columns, sortable: false })
    await el.updateComplete
    expect(el.querySelector('thead button')).toBeNull()
    expect(el.querySelector('thead th').hasAttribute('aria-sort')).toBe(false)
  })

  it('pages with Prev/Next and range text', async () => {
    const many = Array.from({ length: 42 }, (_, i) => ({ name: `r${i}`, qty: i }))
    const el = mount({ data: many, columns: [{ field: 'name' }, { field: 'qty' }] })
    await el.updateComplete
    const range = () => el.querySelector('.uirizz-table-range').textContent
    const prev = () => el.querySelector('.uirizz-table-prev')
    const next = () => el.querySelector('.uirizz-table-next')
    expect(range()).toBe('1–10 of 42')
    expect(el.querySelectorAll('tbody tr')).toHaveLength(10)
    expect(prev().disabled).toBe(true)
    next().click()
    await el.updateComplete
    expect(range()).toBe('11–20 of 42')
    for (let i = 0; i < 3; i++) {
      next().click()
      await el.updateComplete
    }
    expect(range()).toBe('41–42 of 42')
    expect(el.querySelectorAll('tbody tr')).toHaveLength(2)
    expect(next().disabled).toBe(true)
    prev().click()
    await el.updateComplete
    expect(range()).toBe('31–40 of 42')
  })

  it('honours pageSize', async () => {
    const many = Array.from({ length: 12 }, (_, i) => ({ name: `r${i}` }))
    const el = mount({ data: many, columns: [{ field: 'name' }], pageSize: 5 })
    await el.updateComplete
    expect(el.querySelector('.uirizz-table-range').textContent).toBe('1–5 of 12')
  })

  it('rows are inert without an action', async () => {
    const el = mount({ data, columns })
    await el.updateComplete
    expect(el.querySelector('tbody tr').hasAttribute('tabindex')).toBe(false)
  })

  it('row click and keyboard write selection then fire action', async () => {
    const calls = []
    const el = mount({
      data,
      columns,
      setSelection: (r) => calls.push(['sel', r.name]),
      action: () => calls.push(['act']),
    })
    await el.updateComplete
    const row = el.querySelector('tbody tr')
    expect(row.getAttribute('tabindex')).toBe('0')
    row.click()
    expect(calls).toEqual([['sel', 'b'], ['act']])
    calls.length = 0
    row.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    row.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }))
    row.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }))
    expect(calls).toEqual([['sel', 'b'], ['act'], ['sel', 'b'], ['act']])
  })

  it('selection receives the original row after sorting', async () => {
    const setSelection = vi.fn()
    const el = mount({ data, columns, setSelection, action: () => {} })
    await el.updateComplete
    el.querySelectorAll('thead button')[0].click()
    await el.updateComplete
    el.querySelector('tbody tr').click()
    expect(setSelection).toHaveBeenCalledWith(data[1])
  })

  it('shows No rows for empty data', async () => {
    const el = mount({ data: [], columns })
    await el.updateComplete
    expect(el.querySelector('tbody').textContent).toContain('No rows')
    const el2 = mount({ data: undefined, columns })
    await el2.updateComplete
    expect(el2.querySelector('tbody').textContent).toContain('No rows')
  })
})
