import type { KeyBinding } from './types'
import { normalizeKey } from './defaults'

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (target.isContentEditable) return true
  return !!target.closest('[contenteditable="true"]')
}

/** Match event to binding. Ctrl and Meta are treated as equivalent (Mac). */
export function eventMatches(ev: KeyboardEvent, binding: KeyBinding | null): boolean {
  if (!binding || !binding.key) return false
  const wantCtrl = !!(binding.ctrl || binding.meta)
  const hasCtrl = ev.ctrlKey || ev.metaKey
  if (wantCtrl !== hasCtrl) return false
  if (!!binding.shift !== ev.shiftKey) return false
  if (!!binding.alt !== ev.altKey) return false
  return normalizeKey(ev.key === ' ' ? 'space' : ev.key) === normalizeKey(binding.key)
}
