/** Official Basic Catalog with openUrl navigation disabled (MVP policy). */

import {
  basicCatalog,
  createFunctionImplementation,
} from '@a2ui/web_core/v1_0'
import { createSliderEntry } from './slider-element.js'
import { sliderInputAttrs } from './slider-math.js'

function disabledOpenUrl() {
  const existing = basicCatalog.functions.get('openUrl')
  if (!existing) return null
  return createFunctionImplementation(
    {
      name: existing.name,
      returnType: existing.returnType,
      schema: existing.schema,
      allowedCallers: existing.allowedCallers,
      requiresUserActivation: existing.requiresUserActivation,
      description: 'openUrl is disabled in uirizz. Links are not opened by the card.',
    },
    () => {
      // Intentionally no window.open / navigation.
      return undefined
    },
  )
}

function componentsWithSliderFix() {
  const components = basicCatalog.components
  if (!components || typeof components.values !== 'function' || typeof components.get !== 'function') return null
  if (!components.get('Slider')) return null
  const replacement = createSliderEntry(sliderInputAttrs)
  if (!replacement) return null
  return [...components.values()].map((entry) => (entry.name === 'Slider' ? replacement : entry))
}

export function catalogWithOpenUrlOff() {
  const replacement = disabledOpenUrl()
  const components = componentsWithSliderFix()
  if (!replacement && !components) return basicCatalog
  // withEntries keeps the catalog id; derive() would mint a catalog with no id,
  // and createSurface then fails with "Catalog not found" (swallowed by
  // reportErrorsOnly), leaving the card on "Loading surface".
  const functions = replacement
    ? [...basicCatalog.functions.values()].map((fn) => (fn.name === replacement.name ? replacement : fn))
    : [...basicCatalog.functions.values()]
  return basicCatalog.withEntries(
    components || [...basicCatalog.components.values()],
    functions,
  )
}
