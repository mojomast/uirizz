import { describe, expect, it } from 'vitest'
import { rendererCatalogs, UIRIZZ_CATALOG_ID, UIRIZZ_ENTRIES } from './uirizz-catalog.js'

describe('rendererCatalogs', () => {
  it('serves the basic catalog and a uirizz/1 superset with all nine components', () => {
    const [basic, uirizz] = rendererCatalogs()
    expect(basic.id).toBe('https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json')
    expect(uirizz.id).toBe(UIRIZZ_CATALOG_ID)
    const names = [...uirizz.components.keys()]
    for (const n of ['Chart', 'DataTable', 'Metric', 'Progress', 'Badge', 'Callout', 'KeyValueList', 'Timeline', 'CodeBlock', 'Text', 'Slider', 'Button']) {
      expect(names).toContain(n)
    }
    expect(UIRIZZ_ENTRIES).toHaveLength(9)
    expect(new Set(UIRIZZ_ENTRIES.map((e) => e.tagName)).size).toBe(9)
    // openUrl stays disabled in both catalogs
    expect(uirizz.functions.get('openUrl')?.description || '').toContain('disabled')
  })
})
