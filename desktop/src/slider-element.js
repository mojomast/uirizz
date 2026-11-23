import { basicCatalog } from '@a2ui/web_core/v1_0'
import { sliderInputAttrs, sliderProgress } from './slider-math.js'

function officialSliderEntry() {
  if (!basicCatalog || !basicCatalog.components || typeof basicCatalog.components.get !== 'function') return null
  const entry = basicCatalog.components.get('Slider')
  if (!entry || typeof entry.element !== 'function') return null
  return entry
}

const FallbackBase = typeof HTMLElement !== 'undefined' ? HTMLElement : class {}
const OfficialSlider = officialSliderEntry()
const SliderBase = OfficialSlider ? OfficialSlider.element : FallbackBase

function syncSliderInput(host, inputAttrs) {
  if (!host || !host.controller || !host.controller.props) return
  const props = host.controller.props
  const attrs = inputAttrs({
    min: props.min,
    max: props.max,
    value: props.value,
    steps: props.steps,
  })

  const input = typeof host.querySelector === 'function' ? host.querySelector('input[type="range"]') : null
  if (!input) return

  input.min = String(attrs.min)
  input.max = String(attrs.max)
  input.step = String(attrs.step)
  input.value = String(attrs.value)

  if (typeof host.style.setProperty === 'function') {
    const progress = sliderProgress({ min: attrs.min, max: attrs.max, value: attrs.value })
    host.style.setProperty('--uirizz-slider-progress', String(progress))
  }
}

export class UirizzSliderElement extends SliderBase {
  updated(changedProperties) {
    if (typeof super.updated === 'function') super.updated(changedProperties)
    syncSliderInput(this, this.constructor.sliderInputAttrs || sliderInputAttrs)
  }
}

export function createSliderEntry(inputAttrs = sliderInputAttrs) {
  const entry = officialSliderEntry()
  if (!entry) return null

  class EntrySlider extends UirizzSliderElement {}
  EntrySlider.sliderInputAttrs = inputAttrs
  // The base element caches its light-DOM stylesheet per constructor. Give the
  // replacement its own cache so :host rules are rewritten for uirizz-slider
  // instead of inheriting selectors for the original tag.
  EntrySlider._processedSheet = undefined
  EntrySlider._processedCss = undefined
  EntrySlider._processedStyle = undefined
  EntrySlider._adoptedRoots = undefined

  return {
    ...entry,
    tagName: 'uirizz-slider',
    element: EntrySlider,
  }
}
