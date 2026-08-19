"""
Renderer widget - the main anywidget that displays Three.js scenes.

Sync protocol
-------------
The renderer keeps JavaScript in sync through three channels:

1. ``_scene_state`` (synced trait, Python -> JS): a *normalized* snapshot of
   the full object graph — ``{uuid: spec}`` plus root uuids. Specs reference
   other objects by uuid and carry array data as binary buffers (memoryviews,
   extracted by the widget protocol). Written at construction and on explicit
   full resyncs (``render()``, scene/camera/controls replacement); JS rebuilds
   its registry from it, preserving the interactive camera pose.

2. Delta ops (custom messages, Python -> JS): every property change, child
   add/remove, or attribute-array update is sent as a small op
   (``create`` / ``update`` / ``buffer`` / ``child_add`` / ``child_remove`` /
   ``remove``) targeting a uuid. Binary payloads travel as message buffers.
   Each message carries an increasing ``epoch``.

3. ``_camera_state`` (synced trait, JS -> Python): throttled interactive
   camera/controls pose. Tagged with the last epoch JS applied so stale
   updates (raced with a Python-side camera set) are dropped. Applied to the
   Python camera with echo suppression, so observers fire but no ops are
   emitted back to the originating renderer.
"""

import pathlib
from typing import Any, Optional

import numpy as np
import anywidget
import traitlets

from .core import Scene
from .core.base import ThreeJSBase
from .core.buffer import BufferAttribute, _infer_dtype, binary_wrapper
from .core.geometry import _serialize_attribute


def _extract_buffers(node, buffers: list):
    """Replace memoryviews in a JSON-ish payload with ``{"__buffer__": i}``
    placeholders, collecting them into ``buffers`` for binary transport."""
    if isinstance(node, memoryview):
        buffers.append(node)
        return {"__buffer__": len(buffers) - 1}
    if isinstance(node, dict):
        return {key: _extract_buffers(value, buffers) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_extract_buffers(value, buffers) for value in node]
    return node


def _json_safe(value):
    """Coerce a property value into a JSON/buffer-transportable form.

    Arrays keep their own dtype (narrowed to a WebGL-representable width) —
    forcing float32 here once corrupted uint8 DataTexture image updates."""
    if isinstance(value, np.ndarray):
        return binary_wrapper(value, dtype=_infer_dtype(value))
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


class Renderer(anywidget.AnyWidget):
    """
    WebGL renderer widget that displays a Three.js scene.

    This is the main widget for displaying 3D content in Jupyter notebooks.

    Example:
        from anythreejs import Renderer, Scene, PerspectiveCamera, OrbitControls
        from anythreejs import Mesh, BoxGeometry, MeshStandardMaterial

        scene = Scene(background="#1a1a2e")
        scene.add(Mesh(BoxGeometry(1, 1, 1), MeshStandardMaterial(color="#ff6600")))

        camera = PerspectiveCamera(position=(0, 0, 5))
        controls = OrbitControls(controlling=camera)

        renderer = Renderer(camera=camera, scene=scene, controls=[controls])
        renderer  # Display in notebook
    """

    # The shipped widget is a self-contained esbuild bundle (three.js
    # included) — no CDN or network access at runtime. Source lives in
    # js/widget.js; rebuild with `npm run build`.
    _esm = pathlib.Path(__file__).parent / "static" / "widget.js"
    _css = pathlib.Path(__file__).parent / "widget.css"

    # Normalized snapshot of the scene graph (Python -> JS, on full resync)
    _scene_state = traitlets.Dict({}).tag(sync=True)

    # Interactive camera pose (JS -> Python, throttled)
    _camera_state = traitlets.Dict({}).tag(sync=True)

    width = traitlets.CInt(600).tag(sync=True)
    height = traitlets.CInt(400).tag(sync=True)

    antialias = traitlets.Bool(True).tag(sync=True)
    alpha = traitlets.Bool(False).tag(sync=True)

    # Click/hover events - synced from JavaScript
    _click_info = traitlets.Dict({}).tag(sync=True)
    _hover_info = traitlets.Dict({}).tag(sync=True)

    # Picker events - synced from JavaScript
    _picker_event = traitlets.Dict({}).tag(sync=True)

    # Raycast on click (cheap, per-event). Hover raycasting is opt-in
    # because it costs a scene traversal at up to 20Hz while the mouse moves.
    enable_picking = traitlets.Bool(True).tag(sync=True)
    enable_hover = traitlets.Bool(False).tag(sync=True)

    def __init__(
        self,
        camera=None,
        scene=None,
        controls=None,
        width: int = 600,
        height: int = 400,
        antialias: bool = True,
        alpha: bool = False,
        **kwargs,
    ):
        # Protocol state must exist before traitlets fire any handlers.
        self._scene: Optional[Scene] = None
        self._camera = None
        self._controls: list = []
        self._objects: dict[str, ThreeJSBase] = {}
        self._known: set[str] = set()
        self._refs: dict[str, int] = {}
        self._epoch = 0
        self._camera_epoch = 0
        self._batch_depth = 0
        self._pending_ops: list[dict] = []
        # (uuid, prop) pairs currently being applied FROM JS: exactly these
        # are suppressed from re-emission. A blanket flag here once
        # swallowed scene mutations made by user observers reacting to
        # picker/camera events — permanently desyncing Python and JS.
        self._remote_props: set = set()
        self._snapshot_dirty = False
        self._resync_seq = 0

        super().__init__(
            width=int(width),
            height=int(height),
            antialias=antialias,
            alpha=alpha,
            **kwargs,
        )

        self._scene = scene
        self._camera = camera
        self._controls = list(controls) if controls else []

        for obj in self._iter_roots():
            obj._attach_renderer(self)
        self._refresh_snapshot()

        self.observe(self._on_camera_state, names=["_camera_state"])
        self.observe(self._on_picker_event, names=["_picker_event"])

    # ------------------------------------------------------------------
    # Roots and registry
    # ------------------------------------------------------------------

    def _iter_roots(self):
        if self._scene is not None:
            yield self._scene
        if self._camera is not None:
            yield self._camera
        yield from self._controls

    def _register_object(self, obj: ThreeJSBase):
        self._objects[obj.uuid] = obj

    def _unregister_object(self, obj: ThreeJSBase):
        self._objects.pop(obj.uuid, None)

    @property
    def scene(self) -> Optional[Scene]:
        return self._scene

    @scene.setter
    def scene(self, value: Scene):
        self._scene = value
        if value is not None:
            value._attach_renderer(self)
        self._full_resync()

    @property
    def camera(self):
        return self._camera

    @camera.setter
    def camera(self, value):
        old = self._camera
        if value is old:
            return
        self._camera = value
        # Incremental: a camera swap is an O(1) change — a full resync here
        # would re-ship every scene buffer and rebuild the JS world.
        self._begin_batch()
        try:
            if value is not None:
                self._acquire(value)
            self._queue({"op": "set_camera", "camera": value.uuid if value else None})
            if old is not None:
                self._release(old)
        finally:
            self._end_batch()

    @property
    def controls(self) -> list:
        # A copy: in-place mutation would bypass attachment and resync.
        # Assign a new list instead.
        return list(self._controls)

    @controls.setter
    def controls(self, value: list):
        new_controls = list(value) if value else []
        old_controls = self._controls
        if new_controls == old_controls:
            return
        self._controls = new_controls
        # Incremental: matplotgl reassigns the controls list on every
        # zoom/pan toolbar toggle — a full resync here shipped the whole
        # scene (12MB+ at matplotgl scale) for a ~500-byte change.
        self._begin_batch()
        try:
            for ctrl in new_controls:
                if ctrl not in old_controls:
                    self._acquire(ctrl)
            self._queue(
                {"op": "set_controls", "controls": [c.uuid for c in new_controls]}
            )
            for ctrl in old_controls:
                if ctrl not in new_controls:
                    self._release(ctrl)
        finally:
            self._end_batch()

    # ------------------------------------------------------------------
    # Snapshot (full state)
    # ------------------------------------------------------------------

    def _build_snapshot(self) -> dict[str, Any]:
        """Serialize the whole graph into a normalized snapshot dict."""
        specs: dict[str, Any] = {}

        def walk(obj: ThreeJSBase):
            if obj.uuid in specs:
                return
            specs[obj.uuid] = True  # placeholder guards against cycles
            for dep in obj._owned_objects():
                walk(dep)
            specs[obj.uuid] = obj.to_dict(flat=True)

        for root in self._iter_roots():
            walk(root)

        return {
            "version": 2,
            "epoch": self._epoch,
            # Bumped on explicit resyncs so the trait never compares equal
            # to a quietly injected get_state() snapshot (traitlets would
            # otherwise treat render() as a silent no-op).
            "resync": self._resync_seq,
            "objects": specs,
            "scene": self._scene.uuid if self._scene else None,
            "camera": self._camera.uuid if self._camera else None,
            "controls": [ctrl.uuid for ctrl in self._controls],
        }

    def _refresh_snapshot(self):
        """Write a fresh snapshot into the ``_scene_state`` trait (synced to
        JS, which rebuilds its world) and reset the known-uuid set."""
        self._resync_seq += 1
        self._snapshot_dirty = False
        for root in self._iter_roots():
            root._attach_renderer(self)
        state = self._build_snapshot()

        # Detach objects that are no longer part of this renderer's graph.
        for uid in set(self._known) - set(state["objects"]):
            obj = self._objects.get(uid)
            if obj is not None:
                obj._detach_renderer(self)

        self._known = set(state["objects"])
        self._rebuild_refs()
        self._scene_state = state

    def get_state(self, key=None, drop_defaults=False):
        """Refresh a stale snapshot before state is read for embedding or
        export (delta ops advance the scene without rewriting the trait).
        The value is injected quietly — no sync message — so the live JS
        world, already up to date via ops, is not rebuilt."""
        wants_scene = (
            key is None
            or key == "_scene_state"
            or (not isinstance(key, str) and "_scene_state" in key)
        )
        if self._snapshot_dirty and wants_scene:
            self._snapshot_dirty = False
            self._trait_values["_scene_state"] = self._build_snapshot()
        return super().get_state(key=key, drop_defaults=drop_defaults)

    def _full_resync(self):
        self._pending_ops = []
        self._refresh_snapshot()

    # Backwards-compatible alias (objects used to call this on any change).
    def _request_render(self):
        self._full_resync()

    def close(self):
        """Detach from the object graph before closing the widget, so
        reused objects stop holding (and emitting through) this renderer."""
        for obj in list(self._objects.values()):
            obj._renderers.discard(self)
        self._objects.clear()
        self._known.clear()
        self._refs.clear()
        self._pending_ops = []
        super().close()

    def render(self, scene=None, camera=None):
        """Force a full resync. For compatibility - rendering is automatic."""
        if scene is not None:
            self._scene = scene
            scene._attach_renderer(self)
        if camera is not None:
            self._camera = camera
            camera._attach_renderer(self)
        self._full_resync()

    # ------------------------------------------------------------------
    # Delta ops
    # ------------------------------------------------------------------

    def _begin_batch(self):
        self._batch_depth += 1

    def _end_batch(self):
        self._batch_depth -= 1
        if self._batch_depth <= 0:
            self._batch_depth = 0
            self._flush()

    def _queue(self, op: dict):
        self._pending_ops.append(op)
        if self._batch_depth == 0:
            self._flush()

    def _flush(self):
        if not self._pending_ops:
            return
        ops, self._pending_ops = self._pending_ops, []
        self._epoch += 1

        camera_uuid = self._camera.uuid if self._camera else None
        control_uuids = {ctrl.uuid for ctrl in self._controls}
        for op in ops:
            uid = op.get("uuid")
            if (
                uid == camera_uuid
                or uid in control_uuids
                or op.get("op") in ("set_camera", "set_controls")
            ):
                self._camera_epoch = self._epoch
                break

        buffers: list = []
        payload = _extract_buffers(
            {"kind": "ops", "epoch": self._epoch, "ops": ops}, buffers
        )
        self._snapshot_dirty = True
        self.send(payload, buffers=buffers or None)

    def _ensure_created(self, obj: ThreeJSBase):
        """Emit create ops for ``obj`` and everything it references that JS
        does not know yet, dependencies first."""
        if obj.uuid in self._known:
            return
        obj._attach_renderer(self)
        self._known.add(obj.uuid)
        for dep in obj._owned_objects():
            self._acquire(dep)
        self._queue({"op": "create", "uuid": obj.uuid, "spec": obj.to_dict(flat=True)})

    # Lifecycle is tracked with per-edge reference counts instead of
    # reachability walks: an "edge" is a root slot (scene/camera/each
    # control), a parent->child link, or an owned reference (geometry,
    # material, map, EdgesGeometry source). Removal therefore costs
    # O(released subtree), not O(scene) — a full-graph walk per artist
    # removal once made plopp-style teardown loops quadratic. The scene
    # graph is a DAG (verified by construction: owned refs never point
    # back), which refcounting handles exactly.

    def _acquire(self, obj: ThreeJSBase):
        """Record one owner edge to ``obj``, creating it JS-side if new."""
        self._ensure_created(obj)
        self._refs[obj.uuid] = self._refs.get(obj.uuid, 0) + 1

    def _release(self, obj: ThreeJSBase):
        """Drop one owner edge; when the last edge goes, emit a remove op
        (JS disposes), detach, and cascade to owned references."""
        uuid = obj.uuid
        if uuid not in self._known:
            self._refs.pop(uuid, None)
            return
        count = self._refs.get(uuid, 0) - 1
        if count > 0:
            self._refs[uuid] = count
            return
        self._refs.pop(uuid, None)
        self._known.discard(uuid)
        self._queue({"op": "remove", "uuid": uuid})
        obj._detach_renderer(self)
        for dep in obj._owned_objects():
            self._release(dep)

    def _rebuild_refs(self):
        """Recompute all edge counts from the live graph (full-resync path)."""
        refs: dict[str, int] = {}
        visited: set[str] = set()

        def walk(obj: ThreeJSBase):
            if obj.uuid in visited:
                return
            visited.add(obj.uuid)
            for dep in obj._owned_objects():
                refs[dep.uuid] = refs.get(dep.uuid, 0) + 1
                walk(dep)

        for root in self._iter_roots():
            refs[root.uuid] = refs.get(root.uuid, 0) + 1
            walk(root)
        self._refs = refs

    # ------------------------------------------------------------------
    # Object event hooks (called from ThreeJSBase)
    # ------------------------------------------------------------------

    def _on_children_added(self, parent: ThreeJSBase, children: list):
        if parent.uuid not in self._known:
            return
        self._begin_batch()
        try:
            for child in children:
                self._acquire(child)
                self._queue(
                    {"op": "child_add", "uuid": parent.uuid, "child": child.uuid}
                )
        finally:
            self._end_batch()

    def _on_children_removed(self, parent: ThreeJSBase, children: list):
        if parent.uuid not in self._known:
            return
        self._begin_batch()
        try:
            for child in children:
                self._queue(
                    {"op": "child_remove", "uuid": parent.uuid, "child": child.uuid}
                )
                self._release(child)
        finally:
            self._end_batch()

    def _on_object_change(self, obj: ThreeJSBase, name: str, old, new):
        if (obj.uuid, name) in self._remote_props:
            return  # echo of a value JS just told us about
        if obj.uuid not in self._known:
            return
        if name == "children":
            return  # structural changes handled via _on_children_added/removed

        if name == "attribute_data":
            # In-place update of a named BufferGeometry attribute.
            attr = obj.attributes.get(new)
            if attr is not None:
                self._queue(
                    {
                        "op": "buffer",
                        "uuid": obj.uuid,
                        "attribute": new,
                        "value": attr.to_dict(flat=True),
                    }
                )
            return

        if name == "index_data":
            if obj.index is not None:
                self._queue(
                    {
                        "op": "buffer",
                        "uuid": obj.uuid,
                        "attribute": "__index__",
                        "value": obj.index.to_dict(flat=True),
                    }
                )
            return

        if name == "attributes":
            self._queue(
                {
                    "op": "update",
                    "uuid": obj.uuid,
                    "props": {
                        "attributes": {
                            key: _serialize_attribute(attr, flat=True)
                            for key, attr in obj.attributes.items()
                        }
                    },
                }
            )
            return

        if name == "index":
            props = {"index": new.to_dict(flat=True) if new is not None else None}
            self._queue({"op": "update", "uuid": obj.uuid, "props": props})
            return

        if isinstance(new, ThreeJSBase) or (
            new is None and isinstance(old, ThreeJSBase)
        ):
            # Reference assignment (geometry=, material=, map=, ...),
            # including clearing it: the old resource loses an owner edge
            # so it is detached and disposed when unshared.
            self._begin_batch()
            try:
                if new is not None:
                    self._acquire(new)
                self._queue(
                    {
                        "op": "update",
                        "uuid": obj.uuid,
                        "props": {name: new.uuid if new is not None else None},
                    }
                )
                if isinstance(old, ThreeJSBase):
                    self._release(old)
            finally:
                self._end_batch()
            return

        if isinstance(new, BufferAttribute):
            self._queue(
                {
                    "op": "update",
                    "uuid": obj.uuid,
                    "props": {name: new.to_dict(flat=True)},
                }
            )
            return

        if name == "rotation" and isinstance(new, (list, tuple)) and len(new) == 4:
            props = {"rotation": list(new[:3]), "rotationOrder": new[3]}
            self._queue({"op": "update", "uuid": obj.uuid, "props": props})
            return

        self._queue(
            {"op": "update", "uuid": obj.uuid, "props": {name: _json_safe(new)}}
        )

    # ------------------------------------------------------------------
    # JS -> Python state
    # ------------------------------------------------------------------

    def _on_camera_state(self, change):
        """Apply interactive camera pose from JS to the Python-side camera,
        firing observers without echoing ops back."""
        data = change.get("new") or {}
        if not data:
            return
        if data.get("epoch", 0) < self._camera_epoch:
            return  # stale: raced with a Python-originated camera update

        camera = self._camera
        pairs = set()
        if camera is not None:
            pairs.update(
                (camera.uuid, prop) for prop in ("position", "rotation", "zoom")
            )
        pairs.update(
            (ctrl.uuid, "target")
            for ctrl in self._controls
            if ctrl._type in ("OrbitControls", "TrackballControls")
        )
        self._remote_props = pairs
        try:
            if camera is not None:
                with camera.hold_trait_notifications():
                    if "position" in data:
                        camera.position = data["position"]
                    if "rotation" in data:
                        camera.rotation = data["rotation"]
                    if "zoom" in data and hasattr(camera, "zoom"):
                        camera.zoom = data["zoom"]
            if "target" in data:
                for ctrl in self._controls:
                    if ctrl._type in ("OrbitControls", "TrackballControls"):
                        ctrl.target = data["target"]
        finally:
            self._remote_props = set()

    def _on_picker_event(self, change):
        """Handle picker events from JavaScript."""
        event_data = change.get("new", {})
        if not event_data:
            return

        picker_uuid = event_data.get("picker_uuid")
        if not picker_uuid:
            return

        for ctrl in self._controls:
            if ctrl._type == "Picker" and ctrl.uuid == picker_uuid:
                self._remote_props = {
                    (ctrl.uuid, prop)
                    for prop in (
                        "point",
                        "distance",
                        "faceIndex",
                        "modifiers",
                        "object",
                    )
                }
                try:
                    with ctrl.hold_trait_notifications():
                        if "point" in event_data:
                            point = event_data["point"]
                            ctrl.point = tuple(point) if point else None
                        if "distance" in event_data:
                            ctrl.distance = event_data["distance"]
                        if "faceIndex" in event_data:
                            ctrl.faceIndex = event_data["faceIndex"]
                        if "modifiers" in event_data:
                            ctrl.modifiers = event_data.get("modifiers", [])
                        if "object_uuid" in event_data:
                            ctrl.object = self._objects.get(event_data["object_uuid"])
                finally:
                    self._remote_props = set()
                break
