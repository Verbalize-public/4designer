<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { QaButton, QaSegmented, QaValueField } from '@quantumaudio/ableton-extension-sdk/vue'
import type { FourdesignerSession } from '@/composables/useFourdesignerSession'
import { useUiChrome } from '@/composables/useUiChrome'
import PanelDockToggle from '@/components/panels/PanelDockToggle.vue'
import Vec3Field from '@/components/shared/Vec3Field.vue'
import type { ProxyMode, Trs, Vec3 } from '@/types'

const props = defineProps<{
  session: FourdesignerSession
}>()

const ui = useUiChrome()

const obj = computed(() => props.session.selected)
const isRender = computed(() => props.session.viewMode === 'render')

const proxyModeOptions = [
  { value: 'mask', label: 'Mask' },
  { value: 'mesh', label: 'Mesh' },
]

const proxyModeModel = computed({
  get: () => (obj.value?.proxy_mode === 'mesh' ? 'mesh' : 'mask'),
  set: (v: string) => {
    const mode = (v === 'mesh' ? 'mesh' : 'mask') as ProxyMode
    if (mode === 'mesh') ui.setShowGeometry(true)
    void props.session.setProxyMode(mode)
  },
})

async function onRefreshProxy() {
  ui.setShowGeometry(true)
  await props.session.refreshSelectedProxy()
}

async function setT(t: Vec3) {
  if (!obj.value) return
  const trs: Trs = { ...obj.value.trs, t }
  await props.session.commitTransform(obj.value.id, trs)
}

async function setR(r: Vec3) {
  if (!obj.value) return
  const trs: Trs = { ...obj.value.trs, r }
  await props.session.commitTransform(obj.value.id, trs)
}

async function setS(s: Vec3) {
  if (!obj.value) return
  const trs: Trs = { ...obj.value.trs, s }
  await props.session.commitTransform(obj.value.id, trs)
}

const layerDraft = ref(0)
let layerTimer: ReturnType<typeof setTimeout> | null = null

watch(
  () => obj.value?.layer,
  (layer) => {
    if (layer !== undefined) layerDraft.value = layer
  },
  { immediate: true },
)

async function flushLayer() {
  if (layerTimer) {
    clearTimeout(layerTimer)
    layerTimer = null
  }
  if (!obj.value || isRender.value) return
  if (obj.value.layer === layerDraft.value) return
  await props.session.patchSelected({ layer: layerDraft.value })
}

function onLayer(n: number) {
  layerDraft.value = n
  if (layerTimer) clearTimeout(layerTimer)
  layerTimer = setTimeout(() => {
    layerTimer = null
    void flushLayer()
  }, 120)
}

onUnmounted(() => {
  if (layerTimer) clearTimeout(layerTimer)
})

function kindLabel(kind?: string) {
  if (!kind) return '—'
  if (kind === 'env_light') return 'Env light'
  return kind
}

function lightCue(obj: { light_type?: string; cone_angle?: number; kind?: string }) {
  if (obj.kind === 'env_light') return 'env'
  if (!obj.light_type) return ''
  if (obj.light_type === 'cone') return `cone ${Number(obj.cone_angle ?? 30).toFixed(0)}°`
  return obj.light_type
}
</script>

<template>
  <aside class="fd-panel fd-inspector">
    <div class="fd-panel-header fd-panel-header--dock-right">
      <h2 class="fd-panel-title">Inspector</h2>
      <PanelDockToggle side="right" :open="true" @click="ui.toggleInspector()" />
    </div>
    <div class="fd-panel-body fd-scroll">
      <template v-if="obj">
        <div class="row">
          <span>Name</span>
          <span class="ro">{{ obj.name }}</span>
        </div>
        <div v-if="isRender" class="row">
          <span>Kind</span>
          <span class="ro">{{ kindLabel(obj.kind) }}</span>
        </div>
        <div v-if="isRender && lightCue(obj)" class="row">
          <span>Light</span>
          <span class="ro">{{ lightCue(obj) }}</span>
        </div>
        <div v-if="!isRender" class="row" @pointerup="flushLayer" @pointercancel="flushLayer">
          <span>Layer</span>
          <QaValueField
            :model-value="layerDraft"
            :min="0"
            :max="7"
            integer
            :default-value="layerDraft"
            width="100%"
            @update:model-value="onLayer"
          />
        </div>
        <div v-if="!isRender" class="proxy-block">
          <div class="row">
            <span>Proxy</span>
            <QaSegmented v-model="proxyModeModel" size="sm" :options="proxyModeOptions" />
          </div>
          <QaButton
            :disabled="session.busy"
            title="Cook / refresh decimated GLB from TD (mesh mode)"
            @click="onRefreshProxy"
          >
            Refresh proxy
          </QaButton>
          <p v-if="obj.proxy" class="meta">
            Mesh rev {{ obj.proxy.rev }} · {{ obj.proxy.verts }}v / {{ obj.proxy.tris }}t
          </p>
          <p v-else-if="obj.proxy_mode === 'mesh'" class="meta">No GLB yet — Refresh proxy</p>
        </div>
        <p v-if="!isRender && obj.bounds" class="meta">
          Bounds
          {{ (obj.bounds.max[0] - obj.bounds.min[0]).toFixed(3) }}
          × {{ (obj.bounds.max[1] - obj.bounds.min[1]).toFixed(3) }}
          × {{ (obj.bounds.max[2] - obj.bounds.min[2]).toFixed(3) }}
        </p>
        <div class="block">
          <h3>Translate</h3>
          <Vec3Field
            :model-value="obj.trs.t"
            :min="-1e5"
            :max="1e5"
            :step="0.01"
            @update:model-value="setT"
          />
        </div>
        <div class="block">
          <h3>Rotate (deg XYZ)</h3>
          <Vec3Field
            :model-value="obj.trs.r"
            :min="-1800"
            :max="1800"
            :step="0.1"
            @update:model-value="setR"
          />
        </div>
        <div class="block">
          <h3>Scale</h3>
          <Vec3Field
            :model-value="obj.trs.s"
            :min="0.001"
            :max="1000"
            :step="0.01"
            @update:model-value="setS"
          />
        </div>
        <p class="path">{{ obj.td_path }}</p>
      </template>
      <p v-else class="empty">Select an object</p>
    </div>
  </aside>
</template>

<style scoped>
.fd-inspector {
  border-left: 1px solid var(--fd-panel-border);
}
h3 {
  margin: 0 0 var(--fd-space-1);
  font-size: var(--fd-font-micro);
  color: var(--fd-muted);
  font-weight: 600;
}
.row {
  display: grid;
  grid-template-columns: 52px 1fr;
  gap: var(--fd-space-2);
  align-items: center;
  margin-bottom: var(--fd-space-2);
  font-size: var(--fd-font-micro);
  color: var(--fd-muted);
}
.row .ro {
  color: var(--fd-text);
  font-size: var(--fd-font-ui);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row :deep(.qa-value-field) {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  flex: 1 1 auto;
}
.row :deep(.qa-value-field__box) {
  display: flex;
  width: 100% !important;
  min-width: 0 !important;
  max-width: none;
  overflow: hidden;
  text-overflow: ellipsis;
  box-sizing: border-box;
}
.block {
  margin: var(--fd-space-3) 0;
  width: 100%;
  min-width: 0;
}
.path {
  margin-top: var(--fd-space-3);
  font-size: 9px;
  color: var(--fd-muted);
  word-break: break-all;
}
.meta {
  font-size: var(--fd-font-micro);
  color: var(--fd-muted);
  margin: 0 0 var(--fd-space-2);
}
.proxy-block {
  display: flex;
  flex-direction: column;
  gap: var(--fd-space-2);
  margin-bottom: var(--fd-space-2);
}
.proxy-block :deep(.qa-button) {
  height: var(--fd-control-h);
  align-self: stretch;
}
.empty {
  color: var(--fd-muted);
  font-size: var(--fd-font-micro);
  margin: 0;
}
</style>
