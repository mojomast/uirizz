import { createHash } from 'node:crypto'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { installIconFont } from './icon-font.js'

const here = dirname(fileURLToPath(import.meta.url))
const FONT_SHA256 = '8265f64786397d6b832d1ca0aafdf149ad84e72759fffa9f7272e91a0fb015d1'
const CDN_RE = /fonts\.googleapis\.com|fonts\.gstatic\.com|esm\.sh|cdn\.jsdelivr\.net|unpkg\.com/i

describe('vendored Material Icons font', () => {
  it('is a local woff2 with the pinned checksum, not a remote file', () => {
    const buf = readFileSync(resolve(here, 'assets/material-icons.woff2'))
    expect(buf.subarray(0, 4).toString()).toBe('wOF2')
    expect(createHash('sha256').update(buf).digest('hex')).toBe(FONT_SHA256)
  })
})

describe('installIconFont', () => {
  afterEach(() => {
    document.querySelectorAll('[data-uirizz-icon-font]').forEach((n) => n.remove())
  })

  it('injects a self-hosted Material Icons @font-face with no remote URL', () => {
    installIconFont(document)
    const style = document.querySelector('style[data-uirizz-icon-font]')
    expect(style).toBeTruthy()
    const css = style.textContent || ''
    expect(css).toMatch(/@font-face/)
    expect(css).toMatch(/font-family:\s*['"]Material Icons['"]/)
    expect(css).toMatch(/src:\s*url\(data:font\/woff2;base64,/)
    expect(css).not.toMatch(/https?:\/\//)
    expect(css).not.toMatch(CDN_RE)
  })

  it('is idempotent', () => {
    installIconFont(document)
    installIconFont(document)
    expect(document.querySelectorAll('style[data-uirizz-icon-font]').length).toBe(1)
  })
})

describe('plugin wiring and no-CDN policy', () => {
  it('plugin.jsx installs the icon font on register', () => {
    const src = readFileSync(resolve(here, 'plugin.jsx'), 'utf8')
    expect(src).toMatch(/installIconFont/)
  })

  it('desktop/src never references a font or script CDN', () => {
    const skip = new Set(['icon-font.test.js', 'slider-position.test.js'])
    const hits = []
    const walk = (dir) => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name)
        const st = statSync(path)
        if (st.isDirectory()) {
          if (name === 'assets') continue
          walk(path)
          continue
        }
        if (skip.has(name)) continue
        if (!/\.(js|jsx|mjs|css|md)$/.test(name)) continue
        const text = readFileSync(path, 'utf8')
        if (CDN_RE.test(text)) hits.push(path.slice(here.length + 1))
      }
    }
    walk(here)
    expect(hits).toEqual([])
  })
})
