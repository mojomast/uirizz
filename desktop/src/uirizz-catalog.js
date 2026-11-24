/** uirizz/1: the Basic Catalog (with uirizz's openUrl and Slider fixes) plus data components. */

import { catalogWithOpenUrlOff } from './catalog.js'
import { ChartEntry } from './components/chart.js'
import { DataTableEntry } from './components/data-table.js'
import { SIMPLE_ENTRIES } from './components/simple.js'

export const UIRIZZ_CATALOG_ID = 'https://github.com/mojomast/uirizz/catalogs/v1/catalog.json'

export const UIRIZZ_ENTRIES = [ChartEntry, DataTableEntry, ...SIMPLE_ENTRIES]

let cached = null

/**
 * Both catalogs, basic first. Surfaces stored before uirizz/1 keep the basic
 * catalog id and still render; new Express surfaces use the uirizz id.
 */
export function rendererCatalogs() {
  if (cached) return cached
  const basic = catalogWithOpenUrlOff()
  const uirizz = basic.derive({
    catalogId: UIRIZZ_CATALOG_ID,
    components: [...basic.components.values(), ...UIRIZZ_ENTRIES],
    functions: [...basic.functions.values()],
  })
  cached = [basic, uirizz]
  return cached
}
