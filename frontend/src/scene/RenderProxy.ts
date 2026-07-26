import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { withWorkspaceQuery } from '@/api'
import type { Bounds, FdObject, PlateKind } from '@/types'
import { applyTrsToObject } from '@/trs'

const loader = new GLTFLoader()
let activeLoads = 0
const loadQueue: Array<() => void> = []
const MAX_CONCURRENT = 4

function enqueueLoad(fn: () => void) {
  if (activeLoads < MAX_CONCURRENT) {
    activeLoads++
    fn()
  } else {
    loadQueue.push(fn)
  }
}

function loadDone() {
  activeLoads = Math.max(0, activeLoads - 1)
  const next = loadQueue.shift()
  if (next) {
    activeLoads++
    next()
  }
}

const KIND_COLOR: Record<string, number> = {
  geo: 0x4aa3ff,
  light: 0xf0c040,
  env_light: 0xe8a020,
  camera: 0x3ecf8e,
}

/** Lightweight plate proxy for Render view — type icons + opt-in geo GLB. */
export class RenderProxy extends THREE.Group {
  readonly objectId: string
  private root: THREE.Object3D
  private boxMesh: THREE.Mesh | null = null
  private mat: THREE.MeshStandardMaterial
  private wireMat: THREE.LineBasicMaterial | null = null
  private gltfRoot: THREE.Object3D | null = null
  private loadedRev = -1
  private loadedUrl = ''
  private disposed = false
  private lastBounds: Bounds = { min: [-0.5, -0.5, -0.5], max: [0.5, 0.5, 0.5] }
  private kind: PlateKind = 'geo'
  private lightType = 'point'
  private coneAngle = 30
  private selected = false

  constructor(obj: FdObject, color: string) {
    super()
    this.objectId = obj.id
    this.kind = (obj.kind as PlateKind) || 'geo'
    this.lightType = String(obj.light_type || (this.kind === 'env_light' ? 'env' : 'point'))
    this.coneAngle = Number(obj.cone_angle ?? 30)
    this.lastBounds = obj.bounds
    const base = KIND_COLOR[this.kind] ?? new THREE.Color(color).getHex()
    this.mat = new THREE.MeshStandardMaterial({
      color: base,
      roughness: 0.45,
      metalness: 0.1,
      transparent: true,
      opacity: this.kind === 'geo' ? 0.5 : 0.85,
      emissive: this.kind === 'geo' ? 0x000000 : 0x221100,
      emissiveIntensity: this.kind === 'geo' ? 0 : 0.25,
    })
    this.root = this._buildVisual()
    this.add(this.root)
    this.updateFromState(obj, color, true, true)
  }

  localBoundsCenter(): THREE.Vector3 {
    const b = this.lastBounds
    return new THREE.Vector3(
      (b.min[0] + b.max[0]) / 2,
      (b.min[1] + b.max[1]) / 2,
      (b.min[2] + b.max[2]) / 2,
    )
  }

  updateFromState(
    obj: FdObject,
    _color: string,
    showGeometry: boolean,
    showLights = true,
    skipTrs = false,
  ) {
    this.lastBounds = obj.bounds
    if (!skipTrs) applyTrsToObject(this, obj.trs)
    const nextKind = (obj.kind as PlateKind) || 'geo'
    const nextLt = String(obj.light_type || (nextKind === 'env_light' ? 'env' : 'point'))
    const nextAng = Number(obj.cone_angle ?? 30)
    const needsRebuild =
      nextKind !== this.kind ||
      (nextKind !== 'geo' &&
        nextKind !== 'camera' &&
        (nextLt !== this.lightType || Math.abs(nextAng - this.coneAngle) > 0.5))

    if (needsRebuild) {
      this._clearGltf()
      this._disposeRoot()
      this.kind = nextKind
      this.lightType = nextLt
      this.coneAngle = nextAng
      const base = KIND_COLOR[this.kind] ?? 0x888888
      this.mat.color.setHex(base)
      this.mat.opacity = this.kind === 'geo' ? 0.5 : 0.85
      this.root = this._buildVisual()
      this.add(this.root)
    } else if (this.kind === 'geo' && this.boxMesh) {
      this._syncGeoBox(obj.bounds)
    }

    const isLightKind = this.kind === 'light' || this.kind === 'env_light'
    if (isLightKind) {
      this.visible = obj.visible && showLights
      return
    }

    this.visible = obj.visible

    if (this.kind !== 'geo') return

    const wantMesh =
      showGeometry &&
      obj.proxy_mode === 'mesh' &&
      !!obj.proxy?.url &&
      (obj.proxy.rev ?? 0) > 0

    if (!wantMesh) {
      this._clearGltf()
      if (this.boxMesh) this.boxMesh.visible = true
      return
    }

    const url = obj.proxy!.url
    const rev = obj.proxy!.rev
    if (url === this.loadedUrl && rev === this.loadedRev && this.gltfRoot) {
      if (this.boxMesh) this.boxMesh.visible = false
      return
    }
    this._loadGltf(url, rev)
  }

  setSelected(selected: boolean) {
    if (this.selected === selected) return
    this.selected = selected
    this.mat.emissive.set(selected ? 0x332200 : this.kind === 'geo' ? 0x000000 : 0x221100)
    this.mat.emissiveIntensity = selected ? 0.5 : this.kind === 'geo' ? 0 : 0.25
    if (this.wireMat) {
      this.wireMat.color.set(selected ? 0xffcc66 : 0xa0e8c0)
    }
    if (this.gltfRoot) {
      this.gltfRoot.traverse((o) => {
        const m = (o as THREE.Mesh).material
        if (m && !Array.isArray(m) && 'emissive' in m) {
          const mat = m as THREE.MeshStandardMaterial
          mat.emissive.set(selected ? 0x332200 : 0x000000)
          mat.emissiveIntensity = selected ? 0.35 : 0
        }
      })
    }
  }

  dispose() {
    this.disposed = true
    this._clearGltf()
    this._disposeRoot()
    this.mat.dispose()
    this.wireMat?.dispose()
  }

  private _disposeRoot() {
    if (!this.root) return
    this.remove(this.root)
    this.root.traverse((o) => {
      const mesh = o as THREE.Mesh
      if (mesh.geometry) mesh.geometry.dispose()
      const mat = mesh.material
      if (mat && mat !== this.mat && mat !== this.wireMat) {
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose())
        else mat.dispose()
      }
    })
    this.boxMesh = null
    this.wireMat = null
  }

  private _buildVisual(): THREE.Object3D {
    if (this.kind === 'geo') {
      const geo = boxGeometryFromBounds(this.lastBounds)
      this.boxMesh = new THREE.Mesh(geo, this.mat)
      return this.boxMesh
    }
    if (this.kind === 'camera') {
      return this._cameraFrustum()
    }
    if (this.kind === 'env_light' || this.lightType === 'env') {
      return this._envHemisphere()
    }
    if (this.lightType === 'cone') {
      return this._coneLight(this.coneAngle)
    }
    if (this.lightType === 'distant') {
      return this._distantLight()
    }
    return this._pointLight()
  }

  /** Point: emissive sphere + short XYZ ticks. */
  private _pointLight(): THREE.Object3D {
    const g = new THREE.Group()
    g.add(new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 12), this.mat))
    this.wireMat = new THREE.LineBasicMaterial({ color: 0xffdd88 })
    const axes: [THREE.Vector3, THREE.Vector3][] = [
      [new THREE.Vector3(-0.22, 0, 0), new THREE.Vector3(0.22, 0, 0)],
      [new THREE.Vector3(0, -0.22, 0), new THREE.Vector3(0, 0.22, 0)],
      [new THREE.Vector3(0, 0, -0.22), new THREE.Vector3(0, 0, 0.22)],
    ]
    const pos: number[] = []
    for (const [a, b] of axes) {
      pos.push(a.x, a.y, a.z, b.x, b.y, b.z)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3))
    g.add(new THREE.LineSegments(geo, this.wireMat))
    return g
  }

  /** Cone along -Z; apex at origin; opening ≈ coneangle. */
  private _coneLight(angleDeg: number): THREE.Object3D {
    const g = new THREE.Group()
    const ang = Math.max(5, Math.min(80, angleDeg)) * (Math.PI / 180)
    const len = 0.55
    const r = Math.tan(ang) * len
    // ConeGeometry points +Y; rotate to -Z
    const cone = new THREE.Mesh(new THREE.ConeGeometry(r, len, 20, 1, true), this.mat)
    cone.rotation.x = Math.PI / 2
    cone.position.z = -len / 2
    g.add(cone)
    this.wireMat = new THREE.LineBasicMaterial({ color: 0xffe0a0 })
    const axisGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 0, -len),
    ])
    g.add(new THREE.Line(axisGeo, this.wireMat))
    // Apex pick sphere
    g.add(new THREE.Mesh(new THREE.SphereGeometry(0.05, 10, 8), this.mat))
    return g
  }

  /** Distant: disk + arrow along -Z. */
  private _distantLight(): THREE.Object3D {
    const g = new THREE.Group()
    const disk = new THREE.Mesh(new THREE.CircleGeometry(0.18, 24), this.mat)
    disk.rotation.x = Math.PI / 2
    g.add(disk)
    this.wireMat = new THREE.LineBasicMaterial({ color: 0xffe0a0 })
    const shaft = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0.05),
      new THREE.Vector3(0, 0, -0.45),
    ])
    g.add(new THREE.Line(shaft, this.wireMat))
    const head = new THREE.Mesh(new THREE.ConeGeometry(0.07, 0.14, 10), this.mat)
    head.rotation.x = -Math.PI / 2
    head.position.z = -0.5
    g.add(head)
    return g
  }

  /** Env: hemisphere wire sky cue. */
  private _envHemisphere(): THREE.Object3D {
    const g = new THREE.Group()
    this.wireMat = new THREE.LineBasicMaterial({ color: 0xe8a020 })
    const hemi = new THREE.WireframeGeometry(new THREE.SphereGeometry(0.35, 12, 8, 0, Math.PI * 2, 0, Math.PI / 2))
    g.add(new THREE.LineSegments(hemi, this.wireMat))
    g.add(new THREE.Mesh(new THREE.SphereGeometry(0.08, 10, 8), this.mat))
    return g
  }

  private _cameraFrustum(): THREE.Object3D {
    const group = new THREE.Group()
    const pts = [
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(-0.2, -0.12, -0.35),
      new THREE.Vector3(0.2, -0.12, -0.35),
      new THREE.Vector3(0.2, 0.12, -0.35),
      new THREE.Vector3(-0.2, 0.12, -0.35),
    ]
    const edges = [
      [0, 1],
      [0, 2],
      [0, 3],
      [0, 4],
      [1, 2],
      [2, 3],
      [3, 4],
      [4, 1],
    ]
    const positions: number[] = []
    for (const [a, b] of edges) {
      positions.push(pts[a].x, pts[a].y, pts[a].z, pts[b].x, pts[b].y, pts[b].z)
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    this.wireMat = new THREE.LineBasicMaterial({ color: 0xa0e8c0 })
    group.add(new THREE.LineSegments(geo, this.wireMat))
    const tip = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.08, 0.08), this.mat)
    group.add(tip)
    return group
  }

  private _syncGeoBox(bounds: Bounds) {
    if (!this.boxMesh) return
    const next = boxGeometryFromBounds(bounds)
    const prev = this.boxMesh.geometry as THREE.BoxGeometry
    const p = prev.parameters
    const n = next.parameters
    if (
      Math.abs(p.width - n.width) > 1e-6 ||
      Math.abs(p.height - n.height) > 1e-6 ||
      Math.abs(p.depth - n.depth) > 1e-6
    ) {
      this.boxMesh.geometry.dispose()
      this.boxMesh.geometry = next
    } else {
      next.dispose()
    }
  }

  private _clearGltf() {
    if (this.gltfRoot) {
      this.remove(this.gltfRoot)
      this.gltfRoot.traverse((o) => {
        const mesh = o as THREE.Mesh
        if (mesh.geometry) mesh.geometry.dispose()
        const mat = mesh.material
        if (mat) {
          if (Array.isArray(mat)) mat.forEach((m) => m.dispose())
          else mat.dispose()
        }
      })
      this.gltfRoot = null
    }
    this.loadedRev = -1
    this.loadedUrl = ''
  }

  private _loadGltf(url: string, rev: number) {
    const scoped = withWorkspaceQuery(url)
    const full = `${scoped}${scoped.includes('?') ? '&' : '?'}rev=${rev}`
    enqueueLoad(() => {
      loader.load(
        full,
        (gltf) => {
          loadDone()
          if (this.disposed) {
            gltf.scene.traverse((o) => {
              const mesh = o as THREE.Mesh
              if (mesh.geometry) mesh.geometry.dispose()
            })
            return
          }
          this._clearGltf()
          this.gltfRoot = gltf.scene
          this.add(gltf.scene)
          if (this.boxMesh) this.boxMesh.visible = false
          this.loadedUrl = url
          this.loadedRev = rev
        },
        undefined,
        () => {
          loadDone()
          if (!this.disposed && this.boxMesh) this.boxMesh.visible = true
        },
      )
    })
  }
}

function boxGeometryFromBounds(bounds: Bounds): THREE.BoxGeometry {
  const sx = Math.max(0.05, bounds.max[0] - bounds.min[0])
  const sy = Math.max(0.05, bounds.max[1] - bounds.min[1])
  const sz = Math.max(0.05, bounds.max[2] - bounds.min[2])
  const geo = new THREE.BoxGeometry(sx, sy, sz)
  const cx = (bounds.min[0] + bounds.max[0]) / 2
  const cy = (bounds.min[1] + bounds.max[1]) / 2
  const cz = (bounds.min[2] + bounds.max[2]) / 2
  geo.translate(cx, cy, cz)
  return geo
}
