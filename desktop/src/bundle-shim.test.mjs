import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const pluginJs = resolve(dirname(fileURLToPath(import.meta.url)), '../plugin.js')

describe('desktop/plugin.js host-react shim', () => {
  const source = readFileSync(pluginJs, 'utf8')

  it('defines an ESM require shim before esbuild\'s dynamic-require helper', () => {
    const shim = source.indexOf('var require = function __uirizzRequire')
    const helper = source.indexOf('Dynamic require of "')
    expect(shim).toBeGreaterThanOrEqual(0)
    expect(source.includes('import * as __uirizzReact from "react"')).toBe(true)
    if (helper >= 0) {
      expect(shim).toBeLessThan(helper)
    }
  })
})
