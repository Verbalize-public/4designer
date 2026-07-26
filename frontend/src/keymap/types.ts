/** Configurable keyboard shortcuts for 4designer. */

export type ShortcutAction =
  | 'grab'
  | 'rotate'
  | 'scale'
  | 'translate'
  | 'undo'
  | 'redo'
  | 'delete'
  | 'deleteAlt'
  | 'spaceWorld'
  | 'spaceLocal'
  | 'originOrigin'
  | 'originBounds'
  | 'toggleOutliner'
  | 'toggleInspector'
  | 'toggleGrid'
  | 'toggleRenderPreview'

export interface KeyBinding {
  /** KeyboardEvent.key, lowercased for letters (e.g. "g", "z", "delete") */
  key: string
  ctrl?: boolean
  shift?: boolean
  alt?: boolean
  meta?: boolean
}

/** Primary binding per action (one chord each). */
export type KeymapConfig = Record<ShortcutAction, KeyBinding | null>

export const ACTION_LABELS: Record<ShortcutAction, string> = {
  grab: 'Grab (move)',
  rotate: 'Rotate',
  scale: 'Scale',
  translate: 'Translate gizmo',
  undo: 'Undo',
  redo: 'Redo',
  delete: 'Delete',
  deleteAlt: 'Delete (alt)',
  spaceWorld: 'Space: World',
  spaceLocal: 'Space: Local',
  originOrigin: 'Pivot: Origin',
  originBounds: 'Pivot: Bounds',
  toggleOutliner: 'Toggle Outliner',
  toggleInspector: 'Toggle Inspector',
  toggleGrid: 'Toggle Grid',
  toggleRenderPreview: 'Toggle Render Preview',
}

export const ALL_ACTIONS: ShortcutAction[] = [
  'grab',
  'rotate',
  'scale',
  'translate',
  'undo',
  'redo',
  'delete',
  'deleteAlt',
  'spaceWorld',
  'spaceLocal',
  'originOrigin',
  'originBounds',
  'toggleOutliner',
  'toggleInspector',
  'toggleGrid',
  'toggleRenderPreview',
]
