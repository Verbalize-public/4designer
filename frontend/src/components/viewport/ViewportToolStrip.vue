<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  QaButton,
  QaIconButton,
  QaMdiIcon,
  QaSegmented,
  QaSelect,
} from '@quantumaudio/ableton-extension-sdk/vue'
import AxisArrow from 'vue-material-design-icons/AxisArrow.vue'
import Rotate3d from 'vue-material-design-icons/Rotate3d.vue'
import ArrowExpandAll from 'vue-material-design-icons/ArrowExpandAll.vue'
import CursorDefaultClick from 'vue-material-design-icons/CursorDefaultClick.vue'
import CubeOutline from 'vue-material-design-icons/CubeOutline.vue'
import Lightbulb from 'vue-material-design-icons/Lightbulb.vue'
import Monitor from 'vue-material-design-icons/Monitor.vue'
import type { FourdesignerSession } from '@/composables/useFourdesignerSession'
import { api } from '@/api'
import { useKeymap } from '@/keymap'
import { useUiChrome } from '@/composables/useUiChrome'
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

const keymap = useKeymap()
const ui = useUiChrome()
const tip = computed(() => ({
  translate: `Translate gizmo (${keymap.label('translate')})`,
  rotate: `Rotate (${keymap.label('rotate')})`,
  scale: `Scale (${keymap.label('scale')})`,
  grab: `Grab / drag (${keymap.label('grab')})`,
  world: `World space (${keymap.label('spaceWorld')})`,
  local: `Local space (${keymap.label('spaceLocal')})`,
  origin: `Gizmo at object origin (${keymap.label('originOrigin')})`,
  bounds: `Gizmo at AABB center (${keymap.label('originBounds')})`,
  grid: `Show / hide ground grid (${keymap.label('toggleGrid')})`,
  geometry: 'Show beauty GLB when Proxy=Mesh has a cooked file (Inspector)',
  lights: 'Show lights (keyed fill + light icons in Render)',
  preview: `Show / hide Render TOP pixel preview (${keymap.label('toggleRenderPreview')})`,
  auto: 'Auto-refresh scene plate (~750ms debounce). Load meshes stays manual.',
}))

const autoChipLabel = computed(() => {
  if (!ui.state.autoRefresh) return 'Auto'
  const s = ui.state.autoRefreshStatus
  if (s === 'refreshing') return 'Auto · …'
  if (s === 'pending') return `Auto · ${ui.state.autoRefreshIntervalMs}ms`
  return 'Auto · idle'
})

const spaceOptions = [
  { value: 'world', label: 'World' },
  { value: 'local', label: 'Local' },
]
const originOptions = [
  { value: 'origin', label: 'Origin' },
  { value: 'bounds', label: 'Bounds' },
]

const spaceModel = computed({
  get: () => props.space,
  set: (v: string) => emit('update:space', v as TransformSpace),
})
const originModel = computed({
  get: () => props.origin,
  set: (v: string) => emit('update:origin', v as GizmoOrigin),
})

const layerEntries = computed(() =>
  Object.entries(props.session.state.layers).sort((a, b) => Number(a[0]) - Number(b[0])),
)

function selectAllLayers() {
  props.session.layerFilter = 'all'
}

function selectLayer(key: string) {
  props.session.layerFilter = Number(key)
}

async function toggleEye(key: string, visible: boolean) {
  await api.patchLayer(Number(key), { visible: !visible })
}

const manualPath = ref('')
const selectedPath = computed({
  get: () => props.session.renderPath || '',
  set: (v: string) => {
    props.session.setRenderPath(v)
  },
})

watch(
  () => props.session.renderPath,
  (p) => {
    if (p && !manualPath.value) manualPath.value = p
  },
)

const tops = computed(() => props.session.renderTops || [])
const isRender = computed(() => props.session.viewMode === 'render')

const topOptions = computed(() => [
  { value: '', label: '— detect —' },
  ...tops.value.map((t) => ({ value: t.path, label: t.name })),
])

function onTopSelect(v: string) {
  selectedPath.value = v
  manualPath.value = v
  // Immediate refresh on TOP change (no debounce) — same as picking a new path.
  if (v.trim()) {
    props.session.setRenderPath(v.trim())
    void props.session.refreshRender()
  }
}

async function onRefresh() {
  const path = (manualPath.value || selectedPath.value).trim()
  if (!path) {
    props.session.statusText = 'Pick or type a Render TOP path'
    return
  }
  props.session.setRenderPath(path)
  await props.session.refreshRender()
}

function onToggleAuto() {
  ui.toggleAutoRefresh()
}

async function onLoadMeshes() {
  await props.session.requestRenderProxies()
}

async function onRefreshMarshalProxy() {
  ui.setShowGeometry(true)
  if (props.session.selectedId) {
    await props.session.refreshSelectedProxy()
  } else {
    await props.session.refreshMeshProxies()
  }
}

async function onRequestTops() {
  await props.session.requestRenderTops()
}
</script>

<template>
  <div class="fd-vtoolbar" role="toolbar" aria-label="Viewport tools">
    <div class="row">
      <div class="group tools">
        <QaIconButton
          :active="mode === 'translate'"
          :highlight="mode === 'translate'"
          :title="tip.translate"
          aria-label="Translate"
          @click="emit('update:mode', 'translate')"
        >
          <QaMdiIcon :icon="AxisArrow" :size="15" />
        </QaIconButton>
        <QaIconButton
          :active="mode === 'rotate'"
          :highlight="mode === 'rotate'"
          :title="tip.rotate"
          aria-label="Rotate"
          @click="emit('update:mode', 'rotate')"
        >
          <QaMdiIcon :icon="Rotate3d" :size="15" />
        </QaIconButton>
        <QaIconButton
          :active="mode === 'scale'"
          :highlight="mode === 'scale'"
          :title="tip.scale"
          aria-label="Scale"
          @click="emit('update:mode', 'scale')"
        >
          <QaMdiIcon :icon="ArrowExpandAll" :size="15" />
        </QaIconButton>
        <QaIconButton
          :active="mode === 'grab'"
          :highlight="mode === 'grab'"
          :title="tip.grab"
          aria-label="Grab"
          @click="emit('update:mode', 'grab')"
        >
          <QaMdiIcon :icon="CursorDefaultClick" :size="15" />
        </QaIconButton>
      </div>
      <span class="sep" />
      <QaSegmented
        v-model="spaceModel"
        class="fd-seg-compact"
        :options="spaceOptions"
        :aria-label="`${tip.world} / ${tip.local}`"
      />
      <span class="sep" />
      <QaSegmented
        v-model="originModel"
        class="fd-seg-compact"
        :options="originOptions"
        :aria-label="`${tip.origin} / ${tip.bounds}`"
      />
      <span class="sep" />
      <div class="group">
        <button
          type="button"
          class="tool"
          :class="{ active: ui.state.showGrid }"
          :title="tip.grid"
          @click="ui.toggleShowGrid()"
        >
          Grid
        </button>
      </div>
      <span class="sep" />
      <div class="group layers">
        <button
          type="button"
          class="chip"
          :class="{ active: session.layerFilter === 'all' }"
          @click="selectAllLayers"
        >
          All
        </button>
        <button
          v-for="[key, layer] in layerEntries"
          :key="key"
          type="button"
          class="chip"
          :class="{ active: session.layerFilter === Number(key) }"
          :title="layer.name"
          @click="selectLayer(key)"
        >
          <span class="dot" :style="{ background: layer.color }" />
          <span>{{ key }}</span>
          <span
            class="eye"
            :class="{ off: !layer.visible }"
            @click.stop="toggleEye(key, layer.visible)"
          >
            {{ layer.visible ? '●' : '○' }}
          </span>
        </button>
      </div>

      <div class="group view-opts">
        <QaIconButton
          :active="ui.state.showGeometry"
          :highlight="ui.state.showGeometry"
          :title="tip.geometry"
          aria-label="Show geometry"
          @click="ui.toggleShowGeometry()"
        >
          <QaMdiIcon :icon="CubeOutline" :size="15" />
        </QaIconButton>
        <QaIconButton
          :active="ui.state.showLights"
          :highlight="ui.state.showLights"
          :title="tip.lights"
          aria-label="Show lights"
          @click="ui.toggleShowLights()"
        >
          <QaMdiIcon :icon="Lightbulb" :size="15" />
        </QaIconButton>
      </div>
    </div>

    <div v-if="!isRender" class="row marshal">
      <QaButton
        :disabled="session.busy"
        title="Cook / refresh mesh proxy for selection (or all mesh-mode objects)"
        @click="onRefreshMarshalProxy"
      >
        Refresh proxy
      </QaButton>
    </div>

    <div v-if="isRender" class="row render">
      <button
        type="button"
        class="chip auto-chip"
        :class="{ active: ui.state.autoRefresh }"
        :title="tip.auto"
        aria-label="Toggle auto-refresh"
        @click="onToggleAuto"
      >
        {{ autoChipLabel }}
      </button>
      <div class="field" @focusin="onRequestTops">
        <QaSelect
          :model-value="selectedPath"
          :options="topOptions"
          aria-label="Render TOP"
          @update:model-value="onTopSelect"
        />
      </div>
      <!-- Native input + qa-input: QaTextInput autofocuses on mount and steals viewport focus -->
      <input
        v-model="manualPath"
        class="qa-input path"
        type="text"
        placeholder="/project1/render1"
        aria-label="Render TOP path"
        spellcheck="false"
        @keydown.enter="onRefresh"
      />
      <QaButton
        v-if="!ui.state.autoRefresh"
        :accent="true"
        :disabled="session.busy"
        @click="onRefresh"
      >
        Refresh
      </QaButton>
      <QaButton
        :disabled="session.busy"
        :title="
          ui.state.autoRefresh
            ? 'Opt-in GLB beauty (manual — never auto)'
            : 'Opt-in GLB beauty for geos (capped; not on every Refresh)'
        "
        :class="{ ghost: ui.state.autoRefresh }"
        @click="onLoadMeshes"
      >
        Load meshes
      </QaButton>
      <QaIconButton
        :active="ui.state.previewOpen"
        :highlight="ui.state.previewOpen"
        :title="tip.preview"
        aria-label="Render TOP preview"
        @click="ui.toggleRenderPreview()"
      >
        <QaMdiIcon :icon="Monitor" :size="15" />
      </QaIconButton>
    </div>
  </div>
</template>

<style scoped>
.fd-vtoolbar {
  --fd-vt-h: 22px;
  position: absolute;
  top: var(--fd-space-2);
  left: var(--fd-space-2);
  right: var(--fd-space-2);
  z-index: 4;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 6px;
  background: var(--fd-glass);
  border: 1px solid var(--fd-panel-border);
  border-radius: var(--fd-radius-md);
  backdrop-filter: blur(8px);
  pointer-events: auto;
}
.row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.row.render {
  padding-top: 4px;
  border-top: 1px solid var(--fd-panel-border);
}
.row.marshal {
  padding-top: 4px;
  border-top: 1px solid var(--fd-panel-border);
}
.row.marshal :deep(.qa-button) {
  height: var(--fd-control-h);
}
.group {
  display: inline-flex;
  align-items: center;
  gap: 1px;
}
.group.layers {
  flex-wrap: wrap;
}
.group.view-opts {
  margin-left: auto;
  gap: 2px;
}
.tool {
  box-sizing: border-box;
  background: transparent;
  border: none;
  color: var(--fd-muted);
  height: var(--fd-vt-h);
  padding: 0 7px;
  border-radius: var(--fd-radius-sm);
  cursor: pointer;
  font-size: var(--fd-font-ui);
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  min-width: var(--fd-vt-h);
}
.tool.active {
  background: var(--fd-control-bg-active);
  color: var(--fd-accent);
}
.tool:hover:not(.active) {
  color: var(--fd-text);
}
.sep {
  width: 1px;
  height: 14px;
  align-self: center;
  background: var(--fd-panel-border);
  margin: 0 2px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: var(--fd-vt-h);
  padding: 0 7px;
  background: var(--fd-control-bg);
  border: 1px solid var(--fd-panel-border);
  border-radius: var(--fd-radius-pill);
  color: var(--fd-muted);
  font-size: var(--fd-font-micro);
  cursor: pointer;
}
.chip.active {
  border-color: var(--fd-accent);
  color: var(--fd-text);
}
.auto-chip.active {
  background: color-mix(in srgb, var(--fd-accent) 18%, transparent);
  color: var(--fd-accent);
  font-weight: 600;
}
.fd-vtoolbar :deep(.qa-button.ghost) {
  opacity: 0.72;
  border: 1px dashed var(--fd-panel-border);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.eye.off {
  opacity: 0.4;
}
.field {
  display: inline-flex;
  align-items: center;
  min-width: 0;
}
.path {
  flex: 1 1 140px;
  min-width: 120px;
  height: var(--fd-vt-h);
  font-size: var(--fd-font-micro);
}
.fd-vtoolbar :deep(.qa-button) {
  height: var(--fd-vt-h);
  min-height: var(--fd-vt-h);
  padding: 0 8px;
  font-size: var(--fd-font-micro);
  line-height: 1;
}
.fd-vtoolbar :deep(.qa-icon-button) {
  width: var(--fd-vt-h);
  min-width: var(--fd-vt-h);
  padding: 0;
}
.group.tools {
  gap: 2px;
}
.fd-vtoolbar :deep(.qa-segmented__item) {
  height: var(--fd-vt-h);
  min-height: var(--fd-vt-h);
  padding: 0 7px;
  font-size: var(--fd-font-micro);
  line-height: 1;
}
.fd-vtoolbar :deep(.qa-select-wrap) {
  display: inline-flex;
  align-items: center;
}
.fd-vtoolbar :deep(.qa-select) {
  min-width: 100px;
  max-width: 150px;
  height: var(--fd-vt-h);
  font-size: var(--fd-font-micro);
}
</style>
