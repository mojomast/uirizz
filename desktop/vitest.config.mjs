import { readFileSync } from 'node:fs'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    // .test.js under desktop/ is linted as renderer surface; node: test imports must use .mjs.
    include: ['src/**/*.test.{js,jsx,mjs}'],
  },
  plugins: [
    {
      name: 'woff2-dataurl',
      enforce: 'pre',
      load(id) {
        if (id.split('?')[0].endsWith('.woff2')) {
          const b64 = readFileSync(id.split('?')[0]).toString('base64')
          return { code: `export default "data:font/woff2;base64,${b64}"`, map: null }
        }
        return undefined
      },
    },
  ],
})
