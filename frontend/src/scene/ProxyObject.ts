import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { withWorkspaceQuery } from '@/api'
import type { Bounds, FdObject } from '@/types'
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

export class ProxyObject extends THREE.Group {
  readonly objectId: string
  private boxMesh: THREE.Mesh
  private boxMat: THREE.MeshStandardMaterial
  private gltfRoot: THREE.Object3D | null = null
  private loadedRev = -1
  private loadedUrl = ''
  private disposed = false
  private lastBounds: Bounds = { min: [-0.5, -0.5, -0.5], max: [0.5, 0.5, 0.5] }
  private selected = false

  constructor(obj: FdObject, color: string) {
    super()
    this.objectId = obj.id
    this.lastBounds = obj.bounds
    this.boxMat = new THREE.MeshStandardMaterial({
      color,
      roughness: 0.55,
      metalness: 0.05,
      transparent: true,
      opacity: 0.55,
    })
    const geo = boxGeometryFromBounds(obj.bounds)
    this.boxMesh = new THREE.Mesh(geo, this.boxMat)
    this.add(this.boxMesh)
    this.updateFromState(obj, color, true)
  }

  /** Local-space AABB midpoint (same frame as TD null_rest / trs). */
  localBoundsCenter(): THREE.Vector3 {
    const b = this.lastBounds
    return new THREE.Vector3(
      (b.min[0] + b.max[0]) / 2,
      (b.min[1] + b.max[1]) / 2,
      (b.min[2] + b.max[2]) / 2,
    )
  }

  updateFromState(obj: FdObject, color: string, showGeometry: boolean, skipTrs = false) {
    this.lastBounds = obj.bounds
    if (!skipTrs) applyTrsToObject(this, obj.trs)
    this.boxMat.color.set(color)
    this.visible = obj.visible
    this._syncBox(obj.bounds)

    const wantMesh =
      showGeometry &&
      obj.proxy_mode === 'mesh' &&
      !!obj.proxy?.url &&
      (obj.proxy.rev ?? 0) > 0

    if (!wantMesh) {
      this._clearGltf()
      this.boxMesh.visible = true
      return
    }

    const url = obj.proxy!.url
    const rev = obj.proxy!.rev
    if (url === this.loadedUrl && rev === this.loadedRev && this.gltfRoot) {
      this.boxMesh.visible = false
      return
    }
    this._loadGltf(url, rev)
  }

  setSelected(selected: boolean) {
    if (this.selected === selected) return
    this.selected = selected
    this.boxMat.emissive.set(selected ? 0x332200 : 0x000000)
    this.boxMat.emissiveIntensity = selected ? 0.45 : 0
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
    this.boxMesh.geometry.dispose()
    this.boxMat.dispose()
  }

  private _syncBox(bounds: Bounds) {
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
          this.boxMesh.visible = false
          this.loadedUrl = url
          this.loadedRev = rev
        },
        undefined,
        () => {
          loadDone()
          if (!this.disposed) this.boxMesh.visible = true
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
