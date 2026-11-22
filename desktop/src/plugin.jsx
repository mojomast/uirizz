// uirizz Desktop half. Import only @hermes/plugin-sdk, react, and
// react/jsx-runtime from the host; @a2ui/react is bundled in this file.
import * as sdk from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'
import { renderMarkdown } from '@a2ui/markdown-it'
import { injectBasicCatalogStyles, setMarkdownRenderer } from '@a2ui/web_core/v1_0'
import { installIconFont } from './icon-font.js'
import { SurfaceCard } from './card.jsx'

export default {
  id: 'uirizz',
  register(ctx) {
    if (typeof sdk.TOOL_MEDIA_RENDERER_AREA !== 'string') return

    try {
      setMarkdownRenderer(renderMarkdown)
    } catch {
      // Markdown stays optional; text still renders.
    }
    if (typeof document !== 'undefined') {
      try {
        injectBasicCatalogStyles(document)
      } catch {
        // Official styles are best-effort.
      }
      try {
        installIconFont(document)
      } catch {
        // The icon font is best-effort; text still renders.
      }
    }

    ctx.register({
      id: 'uirizz-surface',
      area: sdk.TOOL_MEDIA_RENDERER_AREA,
      data: {
        tools: ['a2ui_render'],
        render: (props) => jsx(SurfaceCard, { ...props, ctx }),
      },
    })
  },
}
