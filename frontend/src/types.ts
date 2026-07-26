export type Vec3 = [number, number, number]

export interface Trs {
  t: Vec3
  r: Vec3
  s: Vec3
}

export interface Bounds {
  min: Vec3
  max: Vec3
}

export type ProxyMode = 'mask' | 'mesh'
export type ViewMode = 'marshaled' | 'render'
export type PlateKind = 'marshal' | 'geo' | 'light' | 'env_light' | 'camera'
export type LightType = 'point' | 'cone' | 'distant'

export interface ProxyMeta {
  format: string
  url: string
  fingerprint: string
  verts: number
  tris: number
  rev: number
}

/** Shared plate object — marshal or render snapshot entry. */
export interface FdObject {
  id: string
  name: string
  layer: number
  visible: boolean
  trs: Trs
  bounds: Bounds
  td_path: string
  kind?: PlateKind
  light_type?: LightType | string
  cone_angle?: number
  proxy_mode?: ProxyMode
  proxy?: ProxyMeta | null
  op_type?: string
}

export interface FdLayer {
  name: string
  visible: boolean
  color: string
}

export interface FdState {
  schema_version: number
  layers: Record<string, FdLayer>
  objects: Record<string, FdObject>
  selection: string[]
  td_connected?: boolean
  slug?: string
}

export interface RenderTopInfo {
  path: string
  name: string
}

export interface RenderState {
  render_path: string
  tops: RenderTopInfo[]
  objects: Record<string, FdObject>
  selection: string[]
  status?: string
  counts?: { geo: number; light: number; camera: number }
}

export type TransformMode = 'translate' | 'rotate' | 'scale' | 'grab'
export type TransformSpace = 'local' | 'world'
export type GizmoOrigin = 'origin' | 'bounds'
