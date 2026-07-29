"""4designer analytic math — no Render Pick DAT, no GPU readback.

Ray/plane/disc hit-tests and hover math are plain-float Vec3 tuples (x, y, z)
so they can be unit-tested outside TD. Transform *writeback* (translate/
rotate under an arbitrary Object-COMP parent and any Rotate Order) instead
goes straight through TD's own `tdu.Matrix` + `ObjectCOMP.setTransform` —
verified live (docs.derivative.ca/Matrix_Class, /ObjectCOMP_Class):
`setTransform` round-trips exactly regardless of the target's `rord`, so
there is no hand-rolled euler/order table here — see `object_parent_world`
and `fourdesigner_ext.py`'s `_write_translate` / `_apply_rotation`.

Convention (verified against docs.derivative.ca): TD matrices are
column-major, right-handed, vector-on-the-right (`M * v`); translation is
column 3. Panel `u,v` are 0..1 left-to-right / bottom-to-top and only update
while a mouse button is held over the panel — exactly the click/drag moments
this module cares about.
"""

from __future__ import annotations

import math

Vec3 = tuple  # (x, y, z) floats — documented shape, not enforced at runtime


def v_sub(a, b):
	return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_add(a, b):
	return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_scale(a, s):
	return (a[0] * s, a[1] * s, a[2] * s)


def v_dot(a, b):
	return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a, b):
	return (
		a[1] * b[2] - a[2] * b[1],
		a[2] * b[0] - a[0] * b[2],
		a[0] * b[1] - a[1] * b[0],
	)


def v_length(a):
	return math.sqrt(v_dot(a, a))


def v_normalize(a, fallback=(0.0, 0.0, 1.0)):
	length = v_length(a)
	if length < 1e-9:
		return fallback
	return (a[0] / length, a[1] / length, a[2] / length)


def matrix_col(m, col):
	"""Column `col` (0..3) of a `tdu.Matrix`, as a plain Vec3 (drops row 3 / w)."""
	return (m[0, col], m[1, col], m[2, col])


def object_world_position(comp) -> "Vec3":
	"""World-space position of any 3D Object COMP — translation column of `worldTransform`."""
	return matrix_col(comp.worldTransform, 3)


def object_axis_world(comp, local_axis):
	"""World-space direction of a local axis vector under `comp`'s own rotation.

	Ignores translation and normalizes each basis column first, so the result
	is scale-independent — handle math should not stretch with a non-uniform
	object Scale.
	"""
	right = v_normalize(matrix_col(comp.worldTransform, 0))
	up = v_normalize(matrix_col(comp.worldTransform, 1))
	fwd = v_normalize(matrix_col(comp.worldTransform, 2))
	x, y, z = local_axis
	return v_normalize((
		right[0] * x + up[0] * y + fwd[0] * z,
		right[1] * x + up[1] * y + fwd[1] * z,
		right[2] * x + up[2] * y + fwd[2] * z,
	))


def object_world_pose_matrix(comp):
	"""`comp`'s world transform with Scale stripped -- pure rotation + translation.

	Used to place the (unparented) gizmo so its own local pars match `comp`'s
	*world* orientation, not `comp`'s local rx/ry/rz -- correct even when
	`comp` sits under a rotated Object-COMP parent. Basis columns are
	normalized (via `object_axis_world`) so a non-uniform Scale on `comp`
	never leaks into the gizmo's shape; `gizmo.setTransform(...)` round-trips
	exactly regardless of the gizmo's own (fixed, 'xyz') Rotate Order.
	"""
	right = object_axis_world(comp, (1.0, 0.0, 0.0))
	up = object_axis_world(comp, (0.0, 1.0, 0.0))
	fwd = object_axis_world(comp, (0.0, 0.0, 1.0))
	pos = object_world_position(comp)
	return tdu.Matrix(
		[right[0], right[1], right[2], 0.0],
		[up[0], up[1], up[2], 0.0],
		[fwd[0], fwd[1], fwd[2], 0.0],
		[pos[0], pos[1], pos[2], 1.0],
	)


# Back-compat aliases — cameraCOMP is just another Object COMP for this module.
camera_world_position = object_world_position


def camera_basis(cam):
	"""Right, up, forward axes of the camera in world space.

	TD camera forward is -Z in its own space, so world-space forward is the
	*negated* Z local axis.
	"""
	right = object_axis_world(cam, (1.0, 0.0, 0.0))
	up = object_axis_world(cam, (0.0, 1.0, 0.0))
	fwd = v_scale(object_axis_world(cam, (0.0, 0.0, 1.0)), -1.0)
	return right, up, fwd


def panel_uv_to_content(u, v, panel_w, panel_h, res_w, res_h):
	"""Remap panel-normalized `(u, v)` into content-normalized coords for
	`topfill=best` letterboxing.

	Panel u/v span the full Container; the Render TOP image is centered and
	uniformly scaled to fit. Returns content `(u_c, v_c)` that map 0..1 over
	the image (may fall outside when the click is in the letterbox bars).
	"""
	pw = max(float(panel_w), 1e-6)
	ph = max(float(panel_h), 1e-6)
	rw = max(float(res_w), 1e-6)
	rh = max(float(res_h), 1e-6)
	scale = min(pw / rw, ph / rh)
	content_w = rw * scale
	content_h = rh * scale
	ox = (pw - content_w) * 0.5
	oy = (ph - content_h) * 0.5
	u_c = (u * pw - ox) / content_w
	v_c = (v * ph - oy) / content_h
	return u_c, v_c


def unproject_ray(cam, u: float, v: float, res_w: float, res_h: float):
	"""World-space ray from a camera through content-normalized `(u, v)`.

	`u, v` are 0..1 over the *rendered image* (after any panel letterbox
	remap via `panel_uv_to_content`). Returns `(origin, direction)` as plain
	Vec3 tuples, `direction` normalized. No render/readback involved —
	`cameraCOMP.worldTransform` / `.projectionInverse()` are pure CPU matrix
	ops (docs.derivative.ca/CameraCOMP_Class).
	"""
	ndc_x = u * 2.0 - 1.0
	ndc_y = v * 2.0 - 1.0
	origin = camera_world_position(cam)
	# NDC z = 1 (far plane) is enough to define a direction once combined with origin;
	# tdu.Matrix.__mul__ on a tdu.Position auto-applies the perspective divide by w.
	inv_proj = cam.projectionInverse(res_w, res_h)
	cam_space_pt = inv_proj * tdu.Position(ndc_x, ndc_y, 1.0)
	world_pt = cam.worldTransform * cam_space_pt
	target = (world_pt.x, world_pt.y, world_pt.z)
	direction = v_normalize(v_sub(target, origin), fallback=camera_basis(cam)[2])
	return origin, direction


def ray_vs_aabb(origin, direction, bounds_min, bounds_max):
	"""Slab method. Returns nearest hit `t >= 0`, or `None`."""
	t_min, t_max = 0.0, float("inf")
	for axis in range(3):
		o, d = origin[axis], direction[axis]
		lo, hi = bounds_min[axis], bounds_max[axis]
		if abs(d) < 1e-12:
			if o < lo or o > hi:
				return None
			continue
		t1 = (lo - o) / d
		t2 = (hi - o) / d
		if t1 > t2:
			t1, t2 = t2, t1
		t_min = max(t_min, t1)
		t_max = min(t_max, t2)
		if t_min > t_max:
			return None
	return t_min if t_min < float("inf") else None


def closest_t_on_ray_to_line(ray_origin, ray_dir, line_point, line_dir):
	"""Parametric `t` along `line_point + t * line_dir` closest to `ray`.

	Standard closest-point-between-two-lines-in-3D solve. Used for the
	single-axis translate/scale handle: the handle IS the line, the mouse ray
	is the other line, and we only care where along the *handle* it lands.
	Returns `None` if the ray is (near) parallel to the line (degenerate view).
	"""
	d1 = v_normalize(line_dir)
	d2 = v_normalize(ray_dir)
	r = v_sub(ray_origin, line_point)
	a = v_dot(d1, d1)
	b = v_dot(d1, d2)
	c = v_dot(d2, d2)
	d = v_dot(d1, r)
	e = v_dot(d2, r)
	denom = a * c - b * b
	if abs(denom) < 1e-9:
		return None
	t_line = (b * e - c * d) / denom
	return t_line


def ray_line_distance(ray_origin, ray_dir, line_point, line_dir):
	"""Minimum distance between two skew 3D lines.

	Perpendicular gate for axis-handle hit-tests: `closest_t_on_ray_to_line`
	always returns *a* closest-approach parameter even when the mouse ray
	passes nowhere near the rod, so picking needs this distance too.
	"""
	d1 = v_normalize(ray_dir)
	d2 = v_normalize(line_dir)
	cross = v_cross(d1, d2)
	cross_len = v_length(cross)
	r = v_sub(line_point, ray_origin)
	if cross_len < 1e-9:
		perp = v_sub(r, v_scale(d1, v_dot(r, d1)))
		return v_length(perp)
	return abs(v_dot(r, cross)) / cross_len


def ray_vs_plane(ray_origin, ray_dir, plane_point, plane_normal):
	"""World-space hit point on an infinite plane, or `None` if parallel/behind."""
	n = v_normalize(plane_normal)
	denom = v_dot(n, ray_dir)
	if abs(denom) < 1e-9:
		return None
	t = v_dot(v_sub(plane_point, ray_origin), n) / denom
	if t < 0:
		return None
	return v_add(ray_origin, v_scale(ray_dir, t))


def ray_vs_disc(ray_origin, ray_dir, center, normal, radius, tolerance):
	"""Hit point on a thin ring (disc plane, radius +/- tolerance), or `None`.

	Used for rotate-ring hit-testing: intersect the ray with the ring's plane,
	then accept only if the hit lands within `tolerance` of `radius` from
	`center` (an actual annulus test, not a filled disc).
	"""
	hit = ray_vs_plane(ray_origin, ray_dir, center, normal)
	if hit is None:
		return None
	dist = v_length(v_sub(hit, center))
	if abs(dist - radius) > tolerance:
		return None
	return hit


def signed_angle_in_plane(v_prev, v_curr, normal):
	"""Signed angle (degrees) from `v_prev` to `v_curr`, both projected onto
	the plane defined by `normal`. Positive = right-hand rotation about
	`normal`. Used for the *incremental* rotate delta (never an absolute
	angle-from-mouse-position) fed into `tdu.Matrix.rotateOnAxis`.
	"""
	n = v_normalize(normal)

	def project(v):
		return v_sub(v, v_scale(n, v_dot(v, n)))

	a = v_normalize(project(v_prev))
	b = v_normalize(project(v_curr))
	cos_a = max(-1.0, min(1.0, v_dot(a, b)))
	angle = math.degrees(math.acos(cos_a))
	if v_dot(v_cross(a, b), n) < 0:
		angle = -angle
	return angle


def object_parent_world(obj):
	"""World transform of `obj`'s nearest Object-COMP parent, or identity.

	`obj.parent(1)` is the network parent, which for 3D purposes only counts
	if it's itself an Object COMP (has `worldTransform`) — TD's 3D parenting
	model (docs.derivative.ca/3D_Parenting). A plain Container/Base ancestor
	(or no parent at all) contributes nothing, so identity keeps
	world == local for root-level objects (verified live: `parent(1)` on a
	root Object COMP resolves to the panel's containerCOMP, which has no
	`worldTransform`).
	"""
	p = obj.parent(1)
	if p is not None and hasattr(p, "worldTransform"):
		return p.worldTransform
	return tdu.Matrix()


def gizmo_screen_scale(cam_world_pos, gizmo_world_pos, fov_y_deg, render_height, desired_px):
	"""Uniform gizmo scale so it reads as `desired_px` tall regardless of
	distance from the edit camera (same technique as Three.js
	`TransformControls` — Euclidean distance, not forward-axis distance).

	scale = dist * 2 * tan(fovY/2) * (desiredPixels / renderHeight)
	"""
	dist = v_length(v_sub(cam_world_pos, gizmo_world_pos))
	fov_y_rad = math.radians(fov_y_deg)
	return dist * 2.0 * math.tan(fov_y_rad * 0.5) * (desired_px / max(render_height, 1.0))
