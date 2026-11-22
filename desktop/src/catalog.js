/** Official Basic Catalog with openUrl navigation disabled (MVP policy). */

import {
  basicCatalog,
  createFunctionImplementation,
} from '@a2ui/web_core/v1_0'

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

export function catalogWithOpenUrlOff() {
  const replacement = disabledOpenUrl()
  if (!replacement) return basicCatalog
  return basicCatalog.derive({ functions: [replacement] })
}
