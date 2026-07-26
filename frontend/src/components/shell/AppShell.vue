<script setup lang="ts">
import { ref } from 'vue'
import { Splitpanes, Pane, type SplitpanesResizedPayload } from 'splitpanes'
import { useFourdesignerSession } from '@/composables/useFourdesignerSession'
import { useGlobalShortcuts } from '@/composables/useGlobalShortcuts'
import { useUiChrome } from '@/composables/useUiChrome'
import TopBar from './TopBar.vue'
import Viewport from '@/components/viewport/Viewport.vue'
import OutlinerPanel from '@/components/panels/OutlinerPanel.vue'
import InspectorPanel from '@/components/panels/InspectorPanel.vue'
import PanelDockToggle from '@/components/panels/PanelDockToggle.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import SettingsDialog from './SettingsDialog.vue'
import type { GizmoOrigin, TransformMode, TransformSpace } from '@/types'

const session = useFourdesignerSession()
const ui = useUiChrome()
const mode = ref<TransformMode>('grab')
const space = ref<TransformSpace>('world')
const origin = ref<GizmoOrigin>('origin')
const recordingShortcut = ref(false)

useGlobalShortcuts({
  session,
  mode,
  space,
  origin,
  recording: recordingShortcut,
})

type PaneSize = { min: number; max: number; size: number }

function onDockResized(payload: SplitpanesResizedPayload) {
  const panes: PaneSize[] = payload?.panes ?? []
  // Order matches visible panes only
  let i = 0
  let outlinerPct: number | null = null
  let inspectorPct: number | null = null
  if (ui.state.outlinerOpen && panes[i]) {
    outlinerPct = panes[i].size
    i++
  }
  // center pane
  i++
  if (ui.state.inspectorOpen && panes[i]) {
    inspectorPct = panes[i].size
  }
  ui.applyDockSizes(outlinerPct, inspectorPct)
}
</script>

<template>
  <div class="fd-shell">
    <TopBar :session="session" />
    <div class="fd-main">
      <Splitpanes class="fd-dock" @resized="onDockResized">
        <Pane
          v-if="ui.state.outlinerOpen"
          :size="ui.state.outlinerSize"
          :min-size="12"
          :max-size="36"
        >
          <OutlinerPanel :session="session" />
        </Pane>
        <Pane :min-size="30">
          <Viewport
            :session="session"
            v-model:mode="mode"
            v-model:space="space"
            v-model:origin="origin"
          />
        </Pane>
        <Pane
          v-if="ui.state.inspectorOpen"
          :size="ui.state.inspectorSize"
          :min-size="12"
          :max-size="36"
        >
          <InspectorPanel :session="session" />
        </Pane>
      </Splitpanes>
      <PanelDockToggle
        v-if="!ui.state.outlinerOpen"
        side="left"
        :open="false"
        floating
        @click="ui.toggleOutliner()"
      />
      <PanelDockToggle
        v-if="!ui.state.inspectorOpen"
        side="right"
        :open="false"
        floating
        @click="ui.toggleInspector()"
      />
    </div>
    <ConfirmDialog />
    <SettingsDialog v-model:recording="recordingShortcut" />
  </div>
</template>

<style scoped>
.fd-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 100%;
  overflow: hidden;
}
.fd-main {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.fd-dock {
  height: 100%;
  width: 100%;
}
.fd-dock :deep(> .splitpanes__pane) {
  overflow: hidden;
  background: transparent;
}
</style>
