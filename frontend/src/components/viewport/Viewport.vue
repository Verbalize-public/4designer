<script setup lang="ts">
import { computed, ref } from 'vue'
import type { FourdesignerSession } from '@/composables/useFourdesignerSession'
import { useEditorScene } from '@/composables/useEditorScene'
import ViewportToolStrip from './ViewportToolStrip.vue'
import RenderPreviewPanel from './RenderPreviewPanel.vue'
import ConnectionHero from '@/components/shell/ConnectionHero.vue'
import type { GizmoOrigin, TransformMode, TransformSpace } from '@/types'

const props = defineProps<{
  session: FourdesignerSession
  mode: TransformMode
  space: TransformSpace
  origin: GizmoOrigin
}>()

const emit = defineEmits<{
  'update:mode': [TransformMode]
  'update:space': [TransformSpace]
  'update:origin': [GizmoOrigin]
}>()

const host = ref<HTMLElement | null>(null)

const modeRef = computed({
  get: () => props.mode,
  set: (v: TransformMode) => emit('update:mode', v),
})
const spaceRef = computed({
  get: () => props.space,
  set: (v: TransformSpace) => emit('update:space', v),
})
const originRef = computed({
  get: () => props.origin,
  set: (v: GizmoOrigin) => emit('update:origin', v),
})

useEditorScene(host, props.session, modeRef, spaceRef, originRef)
</script>

<template>
  <div class="fd-viewport">
    <div ref="host" class="fd-canvas-host" />
    <ViewportToolStrip
      :session="session"
      :mode="mode"
      :space="space"
      :origin="origin"
      @update:mode="emit('update:mode', $event)"
      @update:space="emit('update:space', $event)"
      @update:origin="emit('update:origin', $event)"
    />
    <div
      v-if="session.viewMode === 'render' && session.visibleObjects.length === 0"
      class="fd-empty-render"
    >
      Select a Render TOP and Refresh
    </div>
    <RenderPreviewPanel :session="session" />
    <ConnectionHero :session="session" />
  </div>
</template>

<style scoped>
.fd-viewport {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--fd-viewport-bg);
}
.fd-canvas-host {
  width: 100%;
  height: 100%;
}
.fd-canvas-host :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}
.fd-empty-render {
  position: absolute;
  inset: 0;
  padding-top: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  color: var(--fd-muted);
  font-size: var(--fd-font-ui);
  letter-spacing: 0.02em;
}
</style>
