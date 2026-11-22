// Minimal Desktop half. Feature-detect TOOL_MEDIA_RENDERER_AREA and no-op
// until the official @a2ui/react bundle lands on a feature branch.
// Import from @hermes/plugin-sdk only. No eval, no host patching, no CDN.
import * as sdk from '@hermes/plugin-sdk'

export default {
  id: 'uirizz',
  register(ctx) {
    if (typeof sdk.TOOL_MEDIA_RENDERER_AREA !== 'string') return
    ctx.register({
      id: 'uirizz-surface',
      area: sdk.TOOL_MEDIA_RENDERER_AREA,
      data: {
        tools: ['a2ui_render'],
        render: (props) => (props && props.fallback) || null,
      },
    })
  },
}
