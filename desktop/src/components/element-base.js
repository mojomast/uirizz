import { A2uiLitElement, injectBasicCatalogStyles } from '@a2ui/web_core/v1_0'

// Base for uirizz-specific elements: light DOM, `weight` applied as flex, and
// the basic catalog stylesheet injected so tokens like --a2ui-color-* resolve.
export class UirizzElement extends A2uiLitElement {
  createRenderRoot() {
    return this
  }

  connectedCallback() {
    super.connectedCallback()
    if (typeof injectBasicCatalogStyles === 'function') {
      try {
        injectBasicCatalogStyles()
      } catch {
        // Constructable stylesheets are missing (e.g. jsdom); the card still works unstyled.
      }
    }
  }

  willUpdate(changedProperties) {
    super.willUpdate(changedProperties)
    const props = this.controller?.props
    if (props && props.weight !== undefined) {
      this.style.flex = String(props.weight)
    } else {
      this.style.removeProperty('flex')
    }
  }
}

export function entry(Element, api) {
  return { ...api, tagName: Element.tagName, element: Element }
}
