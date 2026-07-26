import type { KeyBinding, KeymapConfig } from './types'

/** Blender object-mode style defaults (Translate=T is a 4designer extension). */
export function blenderDefaults(): KeymapConfig {
  return {
    grab: { key: 'g' },
    rotate: { key: 'r' },
    scale: { key: 's' },
    translate: { key: 't' },
    undo: { key: 'z', ctrl: true },
    redo: { key: 'z', ctrl: true, shift: true },
    delete: { key: 'x' },
    deleteAlt: { key: 'delete' },
    spaceWorld: null,
    spaceLocal: null,
    originOrigin: null,
    originBounds: null,
    toggleOutliner: { key: '[' },
    toggleInspector: { key: ']' },
    toggleGrid: { key: "'" },
    toggleRenderPreview: { key: 'p' },
  }
}

export function bindingLabel(b: KeyBinding | null | undefined): string {
  if (!b || !b.key) return '—'
  const parts: string[] = []
  if (b.ctrl || b.meta) parts.push('Ctrl')
  if (b.shift) parts.push('Shift')
  if (b.alt) parts.push('Alt')
  const k = b.key.length === 1 ? b.key.toUpperCase() : capitalize(b.key)
  parts.push(k)
  return parts.join('+')
}

function capitalize(s: string): string {
  if (!s) return s
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export function bindingsEqual(a: KeyBinding | null, b: KeyBinding | null): boolean {
  if (!a && !b) return true
  if (!a || !b) return false
  return (
    normalizeKey(a.key) === normalizeKey(b.key) &&
    !!a.ctrl === !!b.ctrl &&
    !!a.shift === !!b.shift &&
    !!a.alt === !!b.alt &&
    !!a.meta === !!b.meta
  )
}

export function normalizeKey(key: string): string {
  const k = key.length === 1 ? key.toLowerCase() : key.toLowerCase()
  if (k === 'backspace') return 'backspace'
  if (k === ' ') return 'space'
  return k
}

export function bindingFromEvent(ev: KeyboardEvent): KeyBinding {
  let key = ev.key
  if (key === ' ') key = 'space'
  else if (key.length === 1) key = key.toLowerCase()
  else key = key.toLowerCase()
  // Ignore pure modifier presses
  return {
    key,
    ctrl: ev.ctrlKey || ev.metaKey,
    shift: ev.shiftKey,
    alt: ev.altKey,
    meta: false,
  }
}
