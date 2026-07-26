<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { QaIconButton, QaMdiIcon } from '@quantumaudio/ableton-extension-sdk/vue'
import Close from 'vue-material-design-icons/Close.vue'
import type { FourdesignerSession } from '@/composables/useFourdesignerSession'
import { useUiChrome } from '@/composables/useUiChrome'
import { api } from '@/api'

const props = defineProps<{
  session: FourdesignerSession
}>()

const ui = useUiChrome()
const POLL_MS = 500

const imgUrl = ref('')
const etag = ref('')
const status = ref('')
const busy = ref(false)

const visible = computed(
  () =>
    props.session.viewMode === 'render' &&
    ui.state.previewOpen &&
    !!props.session.renderPath,
)

const panelStyle = computed(() => ({
  right: `${ui.state.previewX}px`,
  bottom: `${ui.state.previewY}px`,
  width: `${ui.state.previewW}px`,
  height: `${ui.state.previewH}px`,
}))

let timer: ReturnType<typeof setInterval> | null = null
let drag: { startX: number; startY: number; origX: number; origY: number } | null = null
type ResizeEdge = 'e' | 's' | 'se' | 'w' | 'n' | 'nw' | 'ne' | 'sw'
let resize: {
  edge: ResizeEdge
  startX: number
  startY: number
  origW: number
  origH: number
  origX: number
  origY: number
  lockAspect: boolean
} | null = null

function revokeUrl() {
  if (imgUrl.value) {
    URL.revokeObjectURL(imgUrl.value)
    imgUrl.value = ''
  }
}

async function tick() {
  if (!visible.value || busy.value) return
  const path = (props.session.renderPath || '').trim()
  if (!path) return
  busy.value = true
  try {
    await api.requestRenderPreview(path)
    const got = await api.fetchRenderPreview(etag.value || undefined)
    if (got.status === 200 && got.blob) {
      revokeUrl()
      imgUrl.value = URL.createObjectURL(got.blob)
      etag.value = got.etag
      status.value = ''
    } else if (got.status === 204) {
      status.value = 'Waiting for frame…'
    }
  } catch (e) {
    status.value = e instanceof Error ? e.message.slice(0, 48) : 'preview fail'
  } finally {
    busy.value = false
  }
}

function startPoll() {
  stopPoll()
  void tick()
  timer = setInterval(() => void tick(), POLL_MS)
}

function stopPoll() {
  if (timer != null) {
    clearInterval(timer)
    timer = null
  }
  busy.value = false
}

watch(
  visible,
  (on) => {
    if (on) startPoll()
    else {
      stopPoll()
      revokeUrl()
      etag.value = ''
      status.value = ''
    }
  },
  { immediate: true },
)

watch(
  () => props.session.renderPath,
  () => {
    etag.value = ''
    if (visible.value) void tick()
  },
)

onUnmounted(() => {
  stopPoll()
  revokeUrl()
})

function hide() {
  ui.setPreviewOpen(false)
}

function onHeaderDown(ev: PointerEvent) {
  const t = ev.target as HTMLElement | null
  if (t?.closest('button') || t?.closest('.fd-preview__handle')) return
  drag = {
    startX: ev.clientX,
    startY: ev.clientY,
    origX: ui.state.previewX,
    origY: ui.state.previewY,
  }
  ;(ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId)
}

function onHeaderMove(ev: PointerEvent) {
  if (!drag) return
  const dx = drag.startX - ev.clientX
  const dy = drag.startY - ev.clientY
  ui.setPreviewPos(drag.origX + dx, drag.origY + dy)
}

function onHeaderUp() {
  drag = null
}

function onResizeDown(edge: ResizeEdge, ev: PointerEvent) {
  ev.preventDefault()
  ev.stopPropagation()
  resize = {
    edge,
    startX: ev.clientX,
    startY: ev.clientY,
    origW: ui.state.previewW,
    origH: ui.state.previewH,
    origX: ui.state.previewX,
    origY: ui.state.previewY,
    // Default lock 16:9; Shift = free resize
    lockAspect: !ev.shiftKey,
  }
  ;(ev.currentTarget as HTMLElement).setPointerCapture(ev.pointerId)
}

function onResizeMove(ev: PointerEvent) {
  if (!resize) return
  const dx = ev.clientX - resize.startX
  const dy = ev.clientY - resize.startY
  // Panel uses CSS right/bottom (previewX/Y). Move the grabbed edge; keep the
  // opposite edge fixed, then re-derive anchors from the clamped size.
  let w = resize.origW
  let h = resize.origH
  const edge = resize.edge

  if (edge.includes('e')) w = resize.origW + dx
  if (edge.includes('w')) w = resize.origW - dx
  if (edge.includes('s')) h = resize.origH + dy
  if (edge.includes('n')) h = resize.origH - dy

  if (resize.lockAspect) {
    const aspect = 16 / 9
    if (edge === 'e' || edge === 'w') {
      h = Math.round(w / aspect)
    } else if (edge === 's' || edge === 'n') {
      w = Math.round(h * aspect)
    } else if (Math.abs(dx) >= Math.abs(dy)) {
      h = Math.round(w / aspect)
    } else {
      w = Math.round(h * aspect)
    }
  }

  w = Math.round(Math.min(ui.previewMaxW(), Math.max(ui.PREVIEW_MIN_W, w)))
  h = Math.round(Math.min(ui.previewMaxH(), Math.max(ui.PREVIEW_MIN_H, h)))

  // e/s: keep left/top fixed → adjust right/bottom offsets from clamped size
  // w/n: keep right/bottom fixed → leave previewX/Y on that axis
  let x = resize.origX
  let y = resize.origY
  if (edge.includes('e')) x = resize.origX + resize.origW - w
  if (edge.includes('s')) y = resize.origY + resize.origH - h

  ui.setPreviewRect(Math.max(0, x), Math.max(0, y), w, h)
}

function onResizeUp() {
  resize = null
}
</script>

<template>
  <div
    v-if="session.viewMode === 'render' && ui.state.previewOpen"
    class="fd-preview"
    data-testid="fd-render-preview"
    :style="panelStyle"
    role="dialog"
    aria-label="Render TOP preview"
  >
    <div
      class="fd-preview__head"
      @pointerdown="onHeaderDown"
      @pointermove="onHeaderMove"
      @pointerup="onHeaderUp"
      @pointercancel="onHeaderUp"
    >
      <span class="fd-preview__title">Preview</span>
      <span class="fd-preview__path" :title="session.renderPath">{{
        session.renderPath || '—'
      }}</span>
      <QaIconButton title="Hide preview (P)" aria-label="Hide preview" @click="hide">
        <QaMdiIcon :icon="Close" :size="14" />
      </QaIconButton>
    </div>
    <div class="fd-preview__body">
      <img v-if="imgUrl" :src="imgUrl" alt="Render TOP preview" class="fd-preview__img" />
      <div v-else class="fd-preview__empty">{{ status || 'No frame yet' }}</div>
    </div>
    <!-- Edge / corner resize handles (d&d window borders) -->
    <div
      class="fd-preview__handle fd-preview__handle--e"
      title="Drag to resize"
      @pointerdown="onResizeDown('e', $event)"
      @pointermove="onResizeMove"
      @pointerup="onResizeUp"
      @pointercancel="onResizeUp"
    />
    <div
      class="fd-preview__handle fd-preview__handle--s"
      title="Drag to resize"
      @pointerdown="onResizeDown('s', $event)"
      @pointermove="onResizeMove"
      @pointerup="onResizeUp"
      @pointercancel="onResizeUp"
    />
    <div
      class="fd-preview__handle fd-preview__handle--w"
      title="Drag to resize"
      @pointerdown="onResizeDown('w', $event)"
      @pointermove="onResizeMove"
      @pointerup="onResizeUp"
      @pointercancel="onResizeUp"
    />
    <div
      class="fd-preview__handle fd-preview__handle--n"
      title="Drag to resize"
      @pointerdown="onResizeDown('n', $event)"
      @pointermove="onResizeMove"
      @pointerup="onResizeUp"
      @pointercancel="onResizeUp"
    />
    <div
      class="fd-preview__handle fd-preview__handle--se"
      title="Drag to resize (Shift = free aspect)"
      @pointerdown="onResizeDown('se', $event)"
      @pointermove="onResizeMove"
      @pointerup="onResizeUp"
      @pointercancel="onResizeUp"
    />
    <div
      class="fd-preview__handle fd-preview__handle--sw"
      title="Drag to resize (Shift = free aspect)"
      @pointerdown="onResizeDown('sw', $event)"
      @pointermove="onResizeMove"
      @pointerup="onResizeUp"
      @pointercancel="onResizeUp"
    />
    <div
      class="fd-preview__handle fd-preview__handle--ne"
      title="Drag to resize (Shift = free aspect)"
      @pointerdown="onResizeDown('ne', $event)"
      @pointermove="onResizeMove"
      @pointerup="onResizeUp"
      @pointercancel="onResizeUp"
    />
    <div
      class="fd-preview__handle fd-preview__handle--nw"
      title="Drag to resize (Shift = free aspect)"
      @pointerdown="onResizeDown('nw', $event)"
      @pointermove="onResizeMove"
      @pointerup="onResizeUp"
      @pointercancel="onResizeUp"
    />
  </div>
</template>

<style scoped>
.fd-preview {
  position: absolute;
  z-index: 5;
  min-width: 200px;
  min-height: 120px;
  background: var(--fd-glass);
  border: 1px solid var(--fd-panel-border);
  border-radius: var(--fd-radius-md);
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
  overflow: hidden;
  pointer-events: auto;
  display: flex;
  flex-direction: column;
}
.fd-preview__head {
  display: flex;
  align-items: center;
  gap: var(--fd-space-1);
  height: var(--fd-control-h);
  padding: 0 var(--fd-space-1) 0 var(--fd-space-2);
  border-bottom: 1px solid var(--fd-panel-border);
  cursor: grab;
  user-select: none;
  flex-shrink: 0;
}
.fd-preview__head:active {
  cursor: grabbing;
}
.fd-preview__title {
  font-size: var(--fd-font-micro);
  color: var(--fd-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  flex-shrink: 0;
}
.fd-preview__path {
  flex: 1;
  min-width: 0;
  font-size: var(--fd-font-micro);
  color: var(--fd-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fd-preview__body {
  flex: 1;
  min-height: 0;
  position: relative;
  background: #0a0a0a;
}
.fd-preview__img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.fd-preview__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--fd-font-micro);
  color: var(--fd-muted);
  padding: var(--fd-space-2);
  text-align: center;
}

/* Resize handles — subtle amber hover ring for discoverability */
.fd-preview__handle {
  position: absolute;
  z-index: 6;
  background: transparent;
  transition: box-shadow 0.12s ease;
}
.fd-preview__handle:hover {
  box-shadow: inset 0 0 0 1px var(--fd-accent);
}
.fd-preview__handle--e {
  top: 8px;
  right: 0;
  bottom: 8px;
  width: 6px;
  cursor: ew-resize;
}
.fd-preview__handle--w {
  top: 8px;
  left: 0;
  bottom: 8px;
  width: 6px;
  cursor: ew-resize;
}
.fd-preview__handle--s {
  left: 8px;
  right: 8px;
  bottom: 0;
  height: 6px;
  cursor: ns-resize;
}
.fd-preview__handle--n {
  left: 8px;
  right: 8px;
  top: 0;
  height: 6px;
  cursor: ns-resize;
}
.fd-preview__handle--se {
  right: 0;
  bottom: 0;
  width: 12px;
  height: 12px;
  cursor: nwse-resize;
}
.fd-preview__handle--nw {
  left: 0;
  top: 0;
  width: 12px;
  height: 12px;
  cursor: nwse-resize;
}
.fd-preview__handle--sw {
  left: 0;
  bottom: 0;
  width: 12px;
  height: 12px;
  cursor: nesw-resize;
}
.fd-preview__handle--ne {
  right: 0;
  top: 0;
  width: 12px;
  height: 12px;
  cursor: nesw-resize;
}
</style>
