<script setup lang="ts">
import { computed } from 'vue'
import {
  QaButton,
  QaIconButton,
  QaLed,
  QaMdiIcon,
  QaSegmented,
  QaSelect,
} from '@quantumaudio/ableton-extension-sdk/vue'
import Cog from 'vue-material-design-icons/Cog.vue'
import type { FourdesignerSession } from '@/composables/useFourdesignerSession'
import { useUiChrome } from '@/composables/useUiChrome'
import type { ViewMode } from '@/types'

const props = defineProps<{
  session: FourdesignerSession
}>()

const ui = useUiChrome()

const modeOptions = [
  { value: 'marshaled', label: 'Marshaled · beta' },
  { value: 'render', label: 'Render' },
]

const viewMode = computed({
  get: () => props.session.viewMode,
  set: (v: string) => props.session.setViewMode(v as ViewMode),
})

const workspaceOptions = computed(() => {
  const list = props.session.workspaces || []
  const names = list.map((w) => w.project_name || w.id)
  const dup = new Set(names.filter((n, i) => names.indexOf(n) !== i))
  return list.map((w) => {
    const base = w.project_name || w.id.slice(0, 8)
    const folder = (w.project_folder || '').replace(/\\/g, '/')
    const short = folder.split('/').filter(Boolean).slice(-2).join('/')
    let label = base
    if (dup.has(base) && short) label = `${base} · ${short}`
    if (!w.connected) label = `${label} (offline)`
    return { value: w.id, label }
  })
})

const activeWorkspace = computed({
  get: () => props.session.activeWorkspaceId || '',
  set: (v: string) => {
    void props.session.setWorkspace(v || null)
  },
})

const workspaceTitle = computed(() => {
  const id = props.session.activeWorkspaceId
  const w = (props.session.workspaces || []).find((x) => x.id === id)
  return w ? `${w.project_name || id}\n${w.project_folder || ''}` : 'No workspace'
})

async function onNew() {
  if (!props.session.mutationsEnabled) return
  const ok = await ui.confirmDialog({
    title: 'New project',
    message: 'Clear all objects from the editor state? (TD Marshals stay; re-register on Active.)',
    danger: true,
  })
  if (!ok) return
  await props.session.newProject()
}
</script>

<template>
  <header class="fd-appbar">
    <div class="brand" data-testid="fd-brand">4designer</div>

    <div class="workspace" :title="workspaceTitle">
      <QaSelect
        v-model="activeWorkspace"
        :options="workspaceOptions"
        :disabled="!workspaceOptions.length"
        aria-label="Workspace"
      />
    </div>

    <div data-testid="fd-view-mode" title="Marshaled mode is beta in v1">
      <QaSegmented
        v-model="viewMode"
        class="fd-mode-seg"
        :options="modeOptions"
        aria-label="View mode"
      />
    </div>

    <div class="actions">
      <QaButton :disabled="!session.mutationsEnabled" @click="onNew">New</QaButton>
      <QaButton :disabled="!session.mutationsEnabled" @click="session.undo()">Undo</QaButton>
      <QaButton :disabled="!session.mutationsEnabled" @click="session.redo()">Redo</QaButton>
    </div>

    <div class="status-cluster" :title="workspaceTitle">
      <span v-if="session.statusText" class="status">{{ session.statusText }}</span>
      <span v-if="session.workspaceOffline && session.activeWorkspaceId" class="offline">offline</span>
      <span class="led-pair">
        <QaLed :on="session.daemonOk" :color="session.daemonOk ? 'green' : 'accent'" />
        Daemon
      </span>
      <span class="led-pair">
        <QaLed :on="session.tdOk" :color="session.tdOk ? 'green' : 'accent'" />
        TD
      </span>
    </div>

    <QaIconButton
      class="fd-settings"
      title="Keyboard shortcuts"
      aria-label="Settings"
      @click="ui.openSettings()"
    >
      <QaMdiIcon :icon="Cog" :size="16" />
    </QaIconButton>
  </header>
</template>

<style scoped>
.fd-appbar {
  flex: 0 0 var(--fd-appbar-h);
  height: var(--fd-appbar-h);
  display: flex;
  align-items: center;
  gap: var(--fd-space-3);
  padding: 0 var(--fd-space-3);
  background: var(--fd-panel-bg);
  border-bottom: 1px solid var(--fd-panel-border);
  overflow: hidden;
}
.brand {
  flex: 0 0 auto;
  font-weight: 700;
  font-size: var(--fd-font-ui);
  color: var(--fd-accent);
  letter-spacing: 0.04em;
}
.workspace {
  flex: 0 1 220px;
  min-width: 120px;
  max-width: 280px;
}
.workspace :deep(.qa-select) {
  width: 100%;
}
.actions {
  display: flex;
  align-items: center;
  gap: var(--fd-space-1);
  flex: 0 1 auto;
  min-width: 0;
}
/* Keep QA controls inside the 40px AppBar */
.fd-appbar :deep(.qa-button) {
  height: var(--fd-control-h);
  min-height: var(--fd-control-h);
  padding: 0 var(--fd-space-2);
  font-size: var(--fd-font-ui);
  line-height: 1;
}
.fd-appbar :deep(.qa-icon-button) {
  width: var(--fd-control-h);
  padding: 0;
  flex: 0 0 auto;
}
.fd-appbar :deep(.qa-segmented) {
  flex: 0 0 auto;
}
.fd-appbar :deep(.qa-segmented__item) {
  height: var(--fd-control-h);
  min-height: var(--fd-control-h);
  padding: 0 var(--fd-space-2);
  font-size: var(--fd-font-ui);
  line-height: 1;
}
.fd-appbar :deep(.qa-select),
.fd-appbar :deep(.qa-select__trigger) {
  height: var(--fd-control-h);
  min-height: var(--fd-control-h);
  font-size: var(--fd-font-ui);
}
.status-cluster {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--fd-space-3);
  font-size: var(--fd-font-micro);
  color: var(--fd-muted);
  min-width: 0;
}
.status {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--fd-accent);
  font-size: var(--fd-font-micro);
}
.offline {
  color: var(--fd-accent);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: var(--fd-font-micro);
}
.led-pair {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.fd-settings {
  margin-left: var(--fd-space-1);
}
</style>
