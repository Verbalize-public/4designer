<script setup lang="ts">
import { QaIconButton, QaMdiIcon } from '@quantumaudio/ableton-extension-sdk/vue'
import Eye from 'vue-material-design-icons/Eye.vue'
import EyeOff from 'vue-material-design-icons/EyeOff.vue'
import type { FourdesignerSession } from '@/composables/useFourdesignerSession'
import { useUiChrome } from '@/composables/useUiChrome'
import PanelDockToggle from '@/components/panels/PanelDockToggle.vue'
import type { PlateKind } from '@/types'

const props = defineProps<{
  session: FourdesignerSession
}>()

const ui = useUiChrome()

function onDelete(ev: Event, id: string) {
  ev.stopPropagation()
  void props.session.deleteObject(id)
}

function onToggleEye(ev: Event, id: string) {
  ev.stopPropagation()
  props.session.toggleUiHidden(id)
}

function kindLabel(kind?: PlateKind): string {
  if (!kind || kind === 'marshal') return ''
  if (kind === 'env_light') return 'Env'
  if (kind === 'camera') return 'Cam'
  if (kind === 'light') return 'Light'
  if (kind === 'geo') return 'Geo'
  return kind
}
</script>

<template>
  <aside class="fd-panel fd-outliner" data-testid="fd-outliner">
    <div class="fd-panel-header fd-panel-header--dock-left">
      <PanelDockToggle side="left" :open="true" @click="ui.toggleOutliner()" />
      <h2 class="fd-panel-title">Outliner</h2>
    </div>
    <div class="fd-panel-body fd-scroll">
      <ul>
        <li
          v-for="obj in session.visibleObjects"
          :key="obj.id"
          :class="{ selected: session.selectedId === obj.id, dim: session.isUiHidden(obj.id) }"
          @click="session.select(obj.id)"
        >
          <span class="swatch" :style="{ background: session.layerColor(obj.layer) }" />
          <span class="name">{{ obj.name }}</span>
          <span v-if="session.viewMode === 'render' && kindLabel(obj.kind)" class="kind">
            {{ kindLabel(obj.kind) }}
          </span>
          <span v-else class="layer">L{{ obj.layer }}</span>
          <QaIconButton
            class="eye"
            :title="session.isUiHidden(obj.id) ? 'Show in viewport' : 'Hide in viewport'"
            :aria-label="session.isUiHidden(obj.id) ? 'Show in viewport' : 'Hide in viewport'"
            @click="onToggleEye($event, obj.id)"
          >
            <QaMdiIcon :icon="session.isUiHidden(obj.id) ? EyeOff : Eye" :size="14" />
          </QaIconButton>
          <button
            v-if="session.viewMode !== 'render'"
            type="button"
            class="del"
            title="Delete marshal"
            @click="onDelete($event, obj.id)"
          >
            ×
          </button>
        </li>
      </ul>
      <p v-if="session.visibleObjects.length === 0" class="empty">
        <template v-if="session.viewMode === 'render'">Select a Render TOP and Refresh</template>
        <template v-else>No objects</template>
      </p>
    </div>
  </aside>
</template>

<style scoped>
.fd-outliner {
  border-right: 1px solid var(--fd-panel-border);
}
ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
li {
  display: grid;
  grid-template-columns: 8px 1fr auto auto auto;
  gap: 4px;
  align-items: center;
  padding: 4px 6px;
  border-radius: var(--fd-radius-sm);
  cursor: pointer;
  font-size: var(--fd-font-ui);
}
li:hover {
  background: var(--fd-control-bg);
}
li.selected {
  background: #2a2418;
  outline: 1px solid var(--fd-accent);
}
li.dim .name {
  opacity: 0.45;
}
.swatch {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.layer,
.kind {
  color: var(--fd-muted);
  font-size: var(--fd-font-micro);
}
.kind {
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 600;
  color: var(--fd-accent);
}
.eye {
  justify-self: end;
}
.fd-outliner :deep(.qa-icon-button.eye) {
  width: 20px;
  height: 20px;
  min-height: 20px;
  padding: 0;
  color: var(--fd-muted);
}
.fd-outliner :deep(.qa-icon-button.eye:hover) {
  color: var(--fd-accent);
}
li.dim :deep(.qa-icon-button.eye) {
  color: var(--fd-muted);
  opacity: 0.7;
}
.del {
  border: none;
  background: transparent;
  color: var(--fd-muted);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
}
.del:hover {
  color: var(--fd-danger);
}
.empty {
  color: var(--fd-muted);
  font-size: var(--fd-font-micro);
  margin: var(--fd-space-2) 0 0;
}
</style>
