<script setup lang="ts">
import { computed } from 'vue'
import { useKeymap } from '@/keymap'

const props = defineProps<{
  /** Which dock edge this control belongs to */
  side: 'left' | 'right'
  open: boolean
  /** Extra class for floating edge mode */
  floating?: boolean
}>()

const emit = defineEmits<{
  click: [ev: MouseEvent]
}>()

const keymap = useKeymap()

const action = computed(() => (props.side === 'left' ? 'toggleOutliner' : 'toggleInspector'))
const panelName = computed(() => (props.side === 'left' ? 'Outliner' : 'Inspector'))

const title = computed(() => {
  const verb = props.open ? 'Hide' : 'Show'
  return `${verb} ${panelName.value} (${keymap.label(action.value)})`
})

/** Open → chevron toward screen edge (collapse). Closed → chevron inward (expand). */
const pointsLeft = computed(() => {
  if (props.side === 'left') return props.open
  return !props.open
})
</script>

<template>
  <button
    type="button"
    class="fd-dock-toggle"
    :class="[{ floating, 'points-left': pointsLeft }, side]"
    :title="title"
    :aria-label="title"
    :aria-pressed="open"
    @click="emit('click', $event)"
  >
    <!-- Collapsed: bare grip only. Open: chevron to collapse. -->
    <span v-if="floating" class="grip" aria-hidden="true" />
    <svg
      v-else
      class="chev"
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M15.41 16.58 10.83 12l4.58-4.59L14 6l-6 6 6 6 1.41-1.42Z"
      />
    </svg>
  </button>
</template>

<style scoped>
/* Header (open panel): fixed icon button */
.fd-dock-toggle {
  box-sizing: border-box;
  flex: 0 0 20px;
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  min-width: 20px;
  max-width: 20px;
  min-height: 20px;
  max-height: 20px;
  padding: 0;
  margin: 0;
  border: 1px solid transparent;
  border-radius: var(--fd-radius-sm);
  background: transparent;
  color: var(--fd-muted);
  cursor: pointer;
  line-height: 0;
  appearance: none;
  -webkit-appearance: none;
  overflow: hidden;
}
.fd-dock-toggle .chev {
  width: 14px;
  height: 14px;
  display: block;
  transform-origin: center;
}
.fd-dock-toggle:not(.points-left) .chev {
  transform: scaleX(-1);
}
.fd-dock-toggle:hover {
  color: var(--fd-accent);
  border-color: color-mix(in srgb, var(--fd-panel-border) 80%, var(--fd-accent));
}

/*
 * Collapsed: empty ghost tab — thin grip on the screen edge.
 * No icon; reads as a tiny drag/pull handle.
 */
.fd-dock-toggle.floating {
  position: absolute;
  z-index: 6;
  top: 6px;
  width: 8px;
  min-width: 8px;
  max-width: 8px;
  height: 28px;
  min-height: 28px;
  max-height: 28px;
  flex: none;
  border: none;
  border-radius: 0;
  background: transparent;
  opacity: 0.35;
  overflow: visible;
}
.fd-dock-toggle.floating.left {
  left: 0;
}
.fd-dock-toggle.floating.right {
  right: 0;
}
.fd-dock-toggle.floating .grip {
  display: block;
  width: 3px;
  height: 16px;
  border-radius: 2px;
  background: color-mix(in srgb, var(--fd-muted) 70%, transparent);
  box-shadow: none;
}
.fd-dock-toggle.floating:hover {
  opacity: 0.9;
  border: none;
  background: transparent;
  color: var(--fd-accent);
}
.fd-dock-toggle.floating:hover .grip {
  background: var(--fd-accent);
}
</style>
