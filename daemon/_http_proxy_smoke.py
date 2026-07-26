import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "td"))
import proxy_mesh as pm

BASE = "http://127.0.0.1:9983"


def post_json(path, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def put_glb(oid, glb):
    boundary = "----fdtest"
    chunks = []

    def field(name, value):
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(str(value).encode())
        chunks.append(b"\r\n")

    field("fingerprint", "fp1")
    field("verts", 3)
    field("tris", 1)
    chunks.append(f"--{boundary}\r\n".encode())
    chunks.append(
        b'Content-Disposition: form-data; name="file"; filename="p.glb"\r\n'
        b"Content-Type: model/gltf-binary\r\n\r\n"
    )
    chunks.append(glb)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    body = b"".join(chunks)
    req = urllib.request.Request(
        BASE + f"/api/objects/{oid}/proxy",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="PUT",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


post_json(
    "/api/objects/register",
    {
        "id": "testmesh",
        "name": "t",
        "proxy_mode": "mesh",
        "bounds": {"min": [-1, -0.5, -0.25], "max": [1, 0.5, 0.25]},
    },
)
post_json("/api/objects/register", {"id": "testmask", "name": "m", "proxy_mode": "mask"})
glb = pm.write_glb([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])
try:
    put_glb("testmask", glb)
    print("mask_put_should_fail")
except urllib.error.HTTPError as e:
    print("mask_reject_ok", e.code)

meta = put_glb("testmesh", glb)
print("mesh_put", meta.get("proxy"))
raw = urllib.request.urlopen(BASE + "/api/objects/testmesh/proxy.glb").read()
print("get", raw[:4], len(raw))

body = json.dumps({"bounds": {"min": [0, 0, 0], "max": [2, 1, 0.5]}, "_quiet": True}).encode()
req = urllib.request.Request(
    BASE + "/api/objects/testmesh",
    data=body,
    headers={"Content-Type": "application/json"},
    method="PATCH",
)
with urllib.request.urlopen(req) as r:
    o = json.loads(r.read().decode())
print("quiet_bounds", o["bounds"])
print("ok")
