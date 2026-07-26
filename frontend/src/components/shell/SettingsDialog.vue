<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { QaButton, QaDialog } from '@quantumaudio/ableton-extension-sdk/vue'
import { useUiChrome } from '@/composables/useUiChrome'
import {
  ACTION_LABELS,
  ALL_ACTIONS,
  bindingFromEvent,
  bindingLabel,
  useKeymap,
  type ShortcutAction,
} from '@/keymap'

const ui = useUiChrome()
const keymap = useKeymap()

const recording = defineModel<boolean>('recording', { default: false })

const recordingAction = ref<ShortcutAction | null>(null)
const conflictMsg = ref('')

function startRecord(action: ShortcutAction) {
  recordingAction.value = action
  recording.value = true
  conflictMsg.value = ''
}

function cancelRecord() {
  recordingAction.value = null
  recording.value = false
  conflictMsg.value = ''
}

function onCapture(ev: KeyboardEvent) {
  if (!recordingAction.value) return
  ev.preventDefault()
  ev.stopPropagation()
  if (ev.key === 'Escape') {
    cancelRecord()
    return
  }
  // Skip bare modifiers
  if (['Control', 'Shift', 'Alt', 'Meta'].includes(ev.key)) return
  const binding = bindingFromEvent(ev)
  const result = keymap.setBinding(recordingAction.value, binding)
  if (!result.ok && result.conflict) {
    conflictMsg.value = `Conflicts with ${ACTION_LABELS[result.conflict]}`
    return
  }
  cancelRecord()
}

function clearBinding(action: ShortcutAction) {
  keymap.setBinding(action, null)
  conflictMsg.value = ''
}

function onReset() {
  keymap.resetToDefaults()
  conflictMsg.value = ''
  cancelRecord()
}

onMounted(() => window.addEventListener('keydown', onCapture, true))
onUnmounted(() => window.removeEventListener('keydown', onCapture, true))
</script>

<template>
  <QaDialog
    v-if="ui.state.settingsOpen"
    :open="ui.state.settingsOpen"
    title="Keyboard shortcuts"
    @close="ui.closeSettings(); cancelRecord()"
  >
    <template #default>
      <p class="intro">
        Defaults follow Blender (G/R/S, Ctrl+Z / Ctrl+Shift+Z). Click Record, then press a key.
        Escape cancels.
      </p>
      <p v-if="conflictMsg" class="conflict">{{ conflictMsg }}</p>
      <ul class="rows">
        <li v-for="action in ALL_ACTIONS" :key="action">
          <span class="name">{{ ACTION_LABELS[action] }}</span>
          <span class="chord">{{
            recordingAction === action ? 'Press key…' : bindingLabel(keymap.state.map[action])
          }}</span>
          <QaButton variant="ghost" @click="startRecord(action)">Record</QaButton>
          <QaButton variant="ghost" @click="clearBinding(action)">Clear</QaButton>
        </li>
      </ul>
    </template>
    <template #footer>
      <QaButton @click="onReset">Reset to Blender defaults</QaButton>
      <QaButton :accent="true" @click="ui.closeSettings(); cancelRecord()">Done</QaButton>
    </template>
  </QaDialog>
</template>

<style scoped>
.intro {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--fd-muted);
}
.conflict {
  color: #e85d75;
  font-size: 12px;
  margin: 0 0 8px;
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 360px;
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--fd-panel-border) transparent;
}
.rows li {
  display: grid;
  grid-template-columns: 1fr auto auto auto;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid var(--fd-panel-border);
  font-size: 13px;
}
.name {
  color: var(--fd-text);
}
.chord {
  font-family: ui-monospace, monospace;
  color: var(--fd-accent);
  min-width: 7em;
  text-align: right;
}
.rows :deep(.qa-button) {
  font-size: 12px;
  padding: 2px 6px;
  min-height: 0;
  height: auto;
}
</style>
