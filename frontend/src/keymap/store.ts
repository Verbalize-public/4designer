import { reactive } from 'vue'
import { bindingLabel, bindingsEqual, blenderDefaults } from './defaults'
import type { KeyBinding, KeymapConfig, ShortcutAction } from './types'
import { ALL_ACTIONS } from './types'

const STORAGE_KEY = 'fourdesigner.keymap.v1'

const state = reactive<{
  map: KeymapConfig
}>({
  map: blenderDefaults(),
})

function cloneMap(src: KeymapConfig): KeymapConfig {
  const out = blenderDefaults()
  for (const a of ALL_ACTIONS) {
    const b = src[a]
    out[a] = b ? { ...b } : null
  }
  return out
}

function load(): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      state.map = blenderDefaults()
      return
    }
    const parsed = JSON.parse(raw) as Partial<KeymapConfig>
    const next = blenderDefaults()
    for (const a of ALL_ACTIONS) {
      if (a in parsed) {
        const v = parsed[a]
        next[a] = v && typeof v === 'object' && 'key' in v ? { ...(v as KeyBinding) } : null
      }
    }
    state.map = next
  } catch {
    state.map = blenderDefaults()
  }
}

function save(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.map))
  } catch {
    /* ignore */
  }
}

load()

export function useKeymap() {
  function getBinding(action: ShortcutAction): KeyBinding | null {
    return state.map[action]
  }

  function label(action: ShortcutAction): string {
    return bindingLabel(state.map[action])
  }

  function findConflict(binding: KeyBinding, except?: ShortcutAction): ShortcutAction | null {
    for (const a of ALL_ACTIONS) {
      if (a === except) continue
      if (bindingsEqual(state.map[a], binding)) return a
    }
    return null
  }

  function setBinding(action: ShortcutAction, binding: KeyBinding | null): { ok: boolean; conflict?: ShortcutAction } {
    if (binding) {
      const conflict = findConflict(binding, action)
      if (conflict) return { ok: false, conflict }
    }
    state.map[action] = binding ? { ...binding } : null
    save()
    return { ok: true }
  }

  function resetToDefaults() {
    state.map = blenderDefaults()
    save()
  }

  return {
    state,
    getBinding,
    label,
    setBinding,
    findConflict,
    resetToDefaults,
    cloneMap,
  }
}
