/** Euler XYZ degrees — matches TD Geo default / Marshal SOT. */

import type { Trs, Vec3 } from './types'
import * as THREE from 'three'

export function identityTrs(): Trs {
  return { t: [0, 0, 0], r: [0, 0, 0], s: [1, 1, 1] }
}

export function trsFromObject(obj: THREE.Object3D): Trs {
  const e = new THREE.Euler().setFromQuaternion(obj.quaternion, 'XYZ')
  return {
    t: [obj.position.x, obj.position.y, obj.position.z],
    r: [THREE.MathUtils.radToDeg(e.x), THREE.MathUtils.radToDeg(e.y), THREE.MathUtils.radToDeg(e.z)],
    s: [obj.scale.x, obj.scale.y, obj.scale.z],
  }
}

export function applyTrsToObject(obj: THREE.Object3D, trs: Trs): void {
  obj.position.set(trs.t[0], trs.t[1], trs.t[2])
  obj.rotation.order = 'XYZ'
  obj.rotation.set(
    THREE.MathUtils.degToRad(trs.r[0]),
    THREE.MathUtils.degToRad(trs.r[1]),
    THREE.MathUtils.degToRad(trs.r[2]),
  )
  obj.scale.set(trs.s[0], trs.s[1], trs.s[2])
}

export function nearlyEqualVec3(a: Vec3, b: Vec3, eps = 1e-3): boolean {
  return (
    Math.abs(a[0] - b[0]) <= eps &&
    Math.abs(a[1] - b[1]) <= eps &&
    Math.abs(a[2] - b[2]) <= eps
  )
}
