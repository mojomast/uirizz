import fontUrl from './assets/material-icons.woff2'

const STYLE_ATTR = 'data-uirizz-icon-font'

const FONT_FACE = `@font-face {
  font-family: 'Material Icons';
  font-style: normal;
  font-weight: 400;
  font-display: block;
  src: url(${fontUrl}) format('woff2');
}`

export function installIconFont(documentRef) {
  const doc = documentRef || (typeof document !== 'undefined' ? document : null)
  if (!doc || typeof doc.createElement !== 'function') return
  if (typeof doc.querySelector === 'function' && doc.querySelector(`style[${STYLE_ATTR}]`)) return

  const root = doc.head || doc.documentElement
  if (!root || typeof root.appendChild !== 'function') return

  const style = doc.createElement('style')
  style.setAttribute(STYLE_ATTR, '')
  style.textContent = FONT_FACE
  root.appendChild(style)
}
