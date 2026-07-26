import { onMounted, onUnmounted, ref, watch, type Ref } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { TransformControls } from 'three/addons/controls/TransformControls.js'
import { ViewHelper } from 'three/addons/helpers/ViewHelper.js'
import { ProxyObject } from '@/scene/ProxyObject'
import { RenderProxy } from '@/scene/RenderProxy'
import { trsFromObject } from '@/trs'
import type { FourdesignerSession } from './useFourdesignerSession'
import { useUiChrome } from './useUiChrome'
import type { GizmoOrigin, TransformMode, TransformSpace } from '@/types'

/** Matches Three.js ViewHelper corner size (bottom-right). */
const VIEW_HELPER_DIM = 128

type SceneProxy = ProxyObject | RenderProxy

/** Apply dummy world TRS (at local pivot) back onto the proxy Group origin. */
function applyPivotDummyToProxy(
  proxy: SceneProxy,
  dummy: THREE.Object3D,
  localPivot: THREE.Vector3,
) {
  const scaled = localPivot.clone().multiply(dummy.scale)
  scaled.applyQuaternion(dummy.quaternion)
  proxy.position.copy(dummy.position).sub(scaled)
  proxy.quaternion.copy(dummy.quaternion)
  proxy.scale.copy(dummy.scale)
}

function localPivotFor(proxy: SceneProxy, originMode: GizmoOrigin): THREE.Vector3 {
  return originMode === 'bounds' ? proxy.localBoundsCenter() : new THREE.Vector3(0, 0, 0)
}

export function useEditorScene(
  canvasHost: Ref<HTMLElement | null>,
  session: FourdesignerSession,
  mode: Ref<TransformMode>,
  space: Ref<TransformSpace>,
  origin: Ref<GizmoOrigin>,
) {
  const ready = ref(false)
  const ui = useUiChrome()
  let renderer: THREE.WebGLRenderer | null = null
  let scene: THREE.Scene | null = null
  let camera: THREE.PerspectiveCamera | null = null
  let orbit: OrbitControls | null = null
  let transform: TransformControls | null = null
  let viewHelper: ViewHelper | null = null
  let raf = 0
  const clock = new THREE.Clock()
  const proxies = new Map<string, SceneProxy>()
  let dragging = false
  /** True while pointer is down in the ViewHelper hit region (block orbit/grab). */
  let viewHelperPointer = false
  let ro: ResizeObserver | null = null
  let lastViewMode = session.viewMode
  let grid: THREE.GridHelper | null = null
  let ambLight: THREE.AmbientLight | null = null
  let dirLight: THREE.DirectionalLight | null = null
  const AMB_ON = 0.55
  const AMB_FLAT = 1.15
  const DIR_ON = 0.85

  function inViewHelperCorner(ev: PointerEvent): boolean {
    if (!renderer) return false
    const rect = renderer.domElement.getBoundingClientRect()
    const x = ev.clientX - rect.left
    const y = ev.clientY - rect.top
    return x >= rect.width - VIEW_HELPER_DIM && y >= rect.height - VIEW_HELPER_DIM
  }

  function applyLightsFill(on: boolean) {
    if (ambLight) ambLight.intensity = on ? AMB_ON : AMB_FLAT
    if (dirLight) {
      dirLight.intensity = on ? DIR_ON : 0
      dirLight.visible = on
    }
  }

  const pivotDummy = new THREE.Object3D()
  pivotDummy.name = 'fd_pivot_dummy'
  let attachedProxy: SceneProxy | null = null
  let attachedLocalPivot = new THREE.Vector3()

  // Grab drag state
  let grabProxy: SceneProxy | null = null
  let grabLocalPivot = new THREE.Vector3()
  let grabPlane = new THREE.Plane()
  let grabOffset = new THREE.Vector3()
  const _raycaster = new THREE.Raycaster()
  const _mouse = new THREE.Vector2()
  const _hit = new THREE.Vector3()
  const _worldPivot = new THREE.Vector3()

  function isGrabMode() {
    return mode.value === 'grab'
  }

  function clearAllProxies() {
    if (!scene) return
    for (const proxy of proxies.values()) {
      scene.remove(proxy)
      proxy.dispose()
    }
    proxies.clear()
    detachGizmo()
  }

  function syncDummyFromProxy(proxy: SceneProxy) {
    const lp = localPivotFor(proxy, origin.value)
    attachedLocalPivot.copy(lp)
    proxy.updateWorldMatrix(true, false)
    _worldPivot.copy(lp).applyMatrix4(proxy.matrixWorld)
    pivotDummy.position.copy(_worldPivot)
    pivotDummy.quaternion.copy(proxy.quaternion)
    pivotDummy.scale.copy(proxy.scale)
  }

  function pushTrsFromProxy(proxy: SceneProxy, commit: boolean) {
    const trs = trsFromObject(proxy)
    if (commit) void session.commitTransform(proxy.objectId, trs)
    else session.sendTransformDelta(proxy.objectId, trs)
  }

  function applyDummyToAttached(commit: boolean) {
    if (!attachedProxy) return
    applyPivotDummyToProxy(attachedProxy, pivotDummy, attachedLocalPivot)
    pushTrsFromProxy(attachedProxy, commit)
  }

  function detachGizmo() {
    transform?.detach()
    attachedProxy = null
  }

  function attachGizmo(proxy: SceneProxy) {
    if (!transform || !scene) return
    if (isGrabMode()) {
      detachGizmo()
      transform.enabled = false
      return
    }
    transform.enabled = true
    transform.setMode(mode.value === 'grab' ? 'translate' : mode.value)
    const same = attachedProxy === proxy && transform.object === pivotDummy
    attachedProxy = proxy
    syncDummyFromProxy(proxy)
    // Re-attach resets TransformControls internal state and breaks local-space
    // pivot feel; only attach when the target actually changes.
    if (!same) transform.attach(pivotDummy)
  }

  function makeProxy(obj: (typeof session.visibleObjects)[number], color: string): SceneProxy {
    if (session.viewMode === 'render') {
      return new RenderProxy(obj, color)
    }
    return new ProxyObject(obj, color)
  }

  function syncProxies() {
    if (!scene) return
    if (session.viewMode !== lastViewMode) {
      clearAllProxies()
      lastViewMode = session.viewMode
    }
    const showGeometry = ui.state.showGeometry
    const showLights = ui.state.showLights
    const visibleIds = new Set(session.visibleObjects.map((o) => o.id))
    for (const [id, proxy] of [...proxies.entries()]) {
      const stillThere =
        visibleIds.has(id) &&
        (session.viewMode === 'render'
          ? !!session.renderState.objects[id]
          : !!session.state.objects[id])
      if (!stillThere) {
        scene.remove(proxy)
        proxy.dispose()
        proxies.delete(id)
        if (attachedProxy === proxy) detachGizmo()
      }
    }
    for (const obj of session.visibleObjects) {
      const color = session.layerColor(obj.layer)
      let proxy = proxies.get(obj.id)
      if (!proxy) {
        proxy = makeProxy(obj, color)
        proxies.set(obj.id, proxy)
        scene.add(proxy)
      }
      if (!dragging) {
        // While a local delta is queued for this id, keep the interactive pose —
        // applying the echo would yank the gizmo off the bounds/local pivot.
        const skipTrs = session.hasPendingTransform?.(obj.id) === true
        if (proxy instanceof RenderProxy) {
          proxy.updateFromState(obj, color, showGeometry, showLights, skipTrs)
        } else {
          proxy.updateFromState(obj, color, showGeometry, skipTrs)
        }
        if (session.isUiHidden(obj.id)) proxy.visible = false
      }
      proxy.setSelected(session.selectedId === obj.id)
    }
    if (dragging) return
    const sel = session.selectedId
    if (sel && proxies.has(sel) && transform) {
      const p = proxies.get(sel)!
      if (isGrabMode()) {
        detachGizmo()
        transform.enabled = false
      } else if (attachedProxy !== p) {
        attachGizmo(p)
      } else if (!session.hasPendingTransform?.(sel)) {
        // Same selection: refresh pivot from proxy without re-attach.
        syncDummyFromProxy(p)
      }
    } else if (transform) {
      detachGizmo()
    }
  }

  function ndcFromEvent(ev: PointerEvent) {
    if (!renderer) return
    const rect = renderer.domElement.getBoundingClientRect()
    _mouse.set(
      ((ev.clientX - rect.left) / rect.width) * 2 - 1,
      -((ev.clientY - rect.top) / rect.height) * 2 + 1,
    )
  }

  function pickProxy(ev: PointerEvent): SceneProxy | null {
    if (!camera || !scene) return null
    ndcFromEvent(ev)
    _raycaster.setFromCamera(_mouse, camera)
    const hits = _raycaster.intersectObjects([...proxies.values()], true)
    if (!hits.length) return null
    let obj: THREE.Object3D | null = hits[0].object
    while (obj && !(obj instanceof ProxyObject) && !(obj instanceof RenderProxy)) {
      obj = obj.parent
    }
    return obj instanceof ProxyObject || obj instanceof RenderProxy ? obj : null
  }

  function beginGrab(proxy: SceneProxy, ev: PointerEvent) {
    if (!camera || !orbit) return
    grabProxy = proxy
    grabLocalPivot = localPivotFor(proxy, origin.value)
    dragging = true
    orbit.enabled = false
    proxy.updateWorldMatrix(true, false)
    _worldPivot.copy(grabLocalPivot).applyMatrix4(proxy.matrixWorld)
    const camDir = new THREE.Vector3()
    camera.getWorldDirection(camDir)
    grabPlane.setFromNormalAndCoplanarPoint(camDir, _worldPivot)
    ndcFromEvent(ev)
    _raycaster.setFromCamera(_mouse, camera)
    if (_raycaster.ray.intersectPlane(grabPlane, _hit)) {
      grabOffset.copy(_worldPivot).sub(_hit)
    } else {
      grabOffset.set(0, 0, 0)
    }
  }

  function moveGrab(ev: PointerEvent) {
    if (!grabProxy || !camera) return
    ndcFromEvent(ev)
    _raycaster.setFromCamera(_mouse, camera)
    if (!_raycaster.ray.intersectPlane(grabPlane, _hit)) return
    const worldPivot = _hit.clone().add(grabOffset)
    const scaled = grabLocalPivot.clone().multiply(grabProxy.scale)
    scaled.applyQuaternion(grabProxy.quaternion)
    grabProxy.position.copy(worldPivot).sub(scaled)
    pushTrsFromProxy(grabProxy, false)
  }

  function endGrab() {
    if (grabProxy) {
      pushTrsFromProxy(grabProxy, true)
    }
    grabProxy = null
    dragging = false
    if (orbit) orbit.enabled = true
  }

  function onPointerDown(ev: PointerEvent) {
    if (!renderer || !camera || !scene) return
    if (ev.button !== 0) return
    if (transform?.dragging) return

    if (viewHelper && inViewHelperCorner(ev)) {
      viewHelperPointer = true
      if (orbit) orbit.enabled = false
      ev.preventDefault()
      return
    }

    const hit = pickProxy(ev)
    if (hit) session.select(hit.objectId)

    if (isGrabMode() && hit) {
      beginGrab(hit, ev)
      renderer.domElement.setPointerCapture(ev.pointerId)
      ev.preventDefault()
    }
  }

  function onPointerMove(ev: PointerEvent) {
    if (!grabProxy) return
    moveGrab(ev)
  }

  function endViewHelperPointer(ev: PointerEvent) {
    if (!viewHelperPointer) return false
    viewHelperPointer = false
    if (orbit && !dragging && !grabProxy) orbit.enabled = true
    if (viewHelper && orbit && !dragging && !transform?.dragging) {
      viewHelper.center.copy(orbit.target)
      viewHelper.handleClick(ev)
    }
    return true
  }

  function onPointerUp(ev: PointerEvent) {
    if (endViewHelperPointer(ev)) return
    if (!grabProxy) return
    try {
      renderer?.domElement.releasePointerCapture(ev.pointerId)
    } catch {
      /* ignore */
    }
    endGrab()
  }

  function onResize() {
    const host = canvasHost.value
    if (!host || !renderer || !camera) return
    const w = host.clientWidth || 1
    const h = host.clientHeight || 1
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }

  onMounted(() => {
    const host = canvasHost.value
    if (!host) return
    scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0e0f12)
    camera = new THREE.PerspectiveCamera(50, 1, 0.05, 200)
    camera.position.set(2.5, 2.0, 3.5)
    renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    host.appendChild(renderer.domElement)

    ambLight = new THREE.AmbientLight(0xffffff, AMB_ON)
    dirLight = new THREE.DirectionalLight(0xffffff, DIR_ON)
    dirLight.position.set(3, 5, 2)
    scene.add(ambLight, dirLight)
    applyLightsFill(ui.state.showLights)
    grid = new THREE.GridHelper(10, 10, 0x333840, 0x22262c)
    grid.visible = ui.state.showGrid
    scene.add(grid)
    scene.add(pivotDummy)

    orbit = new OrbitControls(camera, renderer.domElement)
    orbit.enableDamping = true
    transform = new TransformControls(camera, renderer.domElement)
    if (mode.value !== 'grab') transform.setMode(mode.value)
    transform.setSpace(space.value)
    transform.addEventListener('dragging-changed', (e) => {
      dragging = !!(e as { value?: boolean }).value
      if (orbit) orbit.enabled = !dragging && !viewHelperPointer
      if (!dragging) {
        applyDummyToAttached(true)
        if (attachedProxy) syncDummyFromProxy(attachedProxy)
      }
    })
    transform.addEventListener('objectChange', () => {
      applyDummyToAttached(false)
    })
    scene.add(transform.getHelper())

    viewHelper = new ViewHelper(camera, renderer.domElement)
    viewHelper.setLabels('X', 'Y', 'Z')
    viewHelper.setLabelStyle('12px sans-serif', '#f2ebe3', 14)

    ro = new ResizeObserver(onResize)
    ro.observe(host)
    onResize()

    const el = renderer.domElement
    el.addEventListener('pointerdown', onPointerDown)
    el.addEventListener('pointermove', onPointerMove)
    el.addEventListener('pointerup', onPointerUp)
    el.addEventListener('pointercancel', onPointerUp)

    clock.start()
    const tick = () => {
      raf = requestAnimationFrame(tick)
      const delta = clock.getDelta()
      if (viewHelper && orbit) {
        viewHelper.center.copy(orbit.target)
        if (viewHelper.animating) viewHelper.update(delta)
      }
      orbit?.update()
      if (renderer && scene && camera) {
        renderer.autoClear = true
        renderer.render(scene, camera)
        if (viewHelper) {
          renderer.autoClear = false
          viewHelper.render(renderer)
          renderer.autoClear = true
        }
      }
    }
    tick()
    ready.value = true
    syncProxies()
  })

  onUnmounted(() => {
    cancelAnimationFrame(raf)
    ro?.disconnect()
    const el = renderer?.domElement
    el?.removeEventListener('pointerdown', onPointerDown)
    el?.removeEventListener('pointermove', onPointerMove)
    el?.removeEventListener('pointerup', onPointerUp)
    el?.removeEventListener('pointercancel', onPointerUp)
    transform?.dispose()
    orbit?.dispose()
    viewHelper?.dispose()
    viewHelper = null
    for (const p of proxies.values()) {
      scene?.remove(p)
      p.dispose()
    }
    proxies.clear()
    if (grid) {
      scene?.remove(grid)
      grid.geometry.dispose()
      const mat = grid.material
      if (Array.isArray(mat)) mat.forEach((m) => m.dispose())
      else mat.dispose()
      grid = null
    }
    ambLight = null
    dirLight = null
    scene?.remove(pivotDummy)
    const host = canvasHost.value
    if (renderer && host && renderer.domElement.parentElement === host) {
      host.removeChild(renderer.domElement)
    }
    renderer?.dispose()
    renderer = null
    scene = null
  })

  watch(
    () =>
      [
        session.visibleObjects,
        session.selectedId,
        session.state,
        session.renderState,
        session.viewMode,
        ui.state.showGeometry,
        ui.state.showLights,
        session.uiHidden,
      ] as const,
    () => syncProxies(),
    { deep: true },
  )

  watch(
    () => ui.state.showGrid,
    (on) => {
      if (grid) grid.visible = on
    },
  )

  watch(
    () => ui.state.showLights,
    (on) => {
      applyLightsFill(on)
    },
  )

  watch(mode, (m) => {
    if (!transform) return
    if (m === 'grab') {
      detachGizmo()
      transform.enabled = false
    } else {
      transform.enabled = true
      transform.setMode(m)
      const sel = session.selectedId
      if (sel && proxies.has(sel)) attachGizmo(proxies.get(sel)!)
    }
  })

  watch(space, (s) => {
    transform?.setSpace(s)
    if (!dragging && attachedProxy) syncDummyFromProxy(attachedProxy)
  })

  watch(origin, () => {
    if (dragging) return
    const sel = session.selectedId
    if (sel && proxies.has(sel) && !isGrabMode()) {
      attachGizmo(proxies.get(sel)!)
    }
  })

  return { ready }
}
