import { onMounted, onUnmounted, type Ref } from 'vue'
import { eventMatches, isEditableTarget, useKeymap } from '@/keymap'
import { useUiChrome } from '@/composables/useUiChrome'
import type { FourdesignerSession } from '@/composables/useFourdesignerSession'
import type { GizmoOrigin, TransformMode, TransformSpace } from '@/types'

export function useGlobalShortcuts(opts: {
  session: FourdesignerSession
  mode: Ref<TransformMode>
  space: Ref<TransformSpace>
  origin: Ref<GizmoOrigin>
  /** When true, skip matching (e.g. recording a new binding in Settings). */
  recording?: Ref<boolean>
}) {
  const keymap = useKeymap()
  const ui = useUiChrome()

  function onKey(ev: KeyboardEvent) {
    if (opts.recording?.value) return
    if (isEditableTarget(ev.target)) return

    const map = keymap.state.map

    if (eventMatches(ev, map.undo)) {
      ev.preventDefault()
      void opts.session.undo()
      return
    }
    if (eventMatches(ev, map.redo)) {
      ev.preventDefault()
      void opts.session.redo()
      return
    }
    if (eventMatches(ev, map.delete) || eventMatches(ev, map.deleteAlt)) {
      ev.preventDefault()
      void opts.session.deleteSelected()
      return
    }
    if (eventMatches(ev, map.grab)) {
      ev.preventDefault()
      opts.mode.value = 'grab'
      return
    }
    if (eventMatches(ev, map.rotate)) {
      ev.preventDefault()
      opts.mode.value = 'rotate'
      return
    }
    if (eventMatches(ev, map.scale)) {
      ev.preventDefault()
      opts.mode.value = 'scale'
      return
    }
    if (eventMatches(ev, map.translate)) {
      ev.preventDefault()
      opts.mode.value = 'translate'
      return
    }
    if (eventMatches(ev, map.spaceWorld)) {
      ev.preventDefault()
      opts.space.value = 'world'
      return
    }
    if (eventMatches(ev, map.spaceLocal)) {
      ev.preventDefault()
      opts.space.value = 'local'
      return
    }
    if (eventMatches(ev, map.originOrigin)) {
      ev.preventDefault()
      opts.origin.value = 'origin'
      return
    }
    if (eventMatches(ev, map.originBounds)) {
      ev.preventDefault()
      opts.origin.value = 'bounds'
      return
    }
    if (eventMatches(ev, map.toggleOutliner)) {
      ev.preventDefault()
      ui.toggleOutliner()
      return
    }
    if (eventMatches(ev, map.toggleInspector)) {
      ev.preventDefault()
      ui.toggleInspector()
      return
    }
    if (eventMatches(ev, map.toggleGrid)) {
      ev.preventDefault()
      ui.toggleShowGrid()
      return
    }
    if (eventMatches(ev, map.toggleRenderPreview)) {
      ev.preventDefault()
      if (opts.session.viewMode === 'render') ui.toggleRenderPreview()
    }
  }

  onMounted(() => window.addEventListener('keydown', onKey))
  onUnmounted(() => window.removeEventListener('keydown', onKey))
}
