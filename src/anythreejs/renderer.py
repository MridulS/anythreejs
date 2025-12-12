"""
Renderer widget - the main anywidget that displays Three.js scenes.
"""

import pathlib
from typing import Optional, Dict
import numpy as np

import anywidget
import traitlets

from .core import Scene


class BufferManager:
    """Manages binary buffers for efficient data transfer to JavaScript."""

    def __init__(self):
        self._buffers: Dict[str, memoryview] = {}
        self._next_id = 0

    def register_buffer(self, array: np.ndarray) -> str:
        """
        Register a numpy array as a binary buffer and return its ID.

        Args:
            array: NumPy array to register

        Returns:
            Buffer ID string that can be used to reference this buffer
        """
        buffer_id = f"buf_{self._next_id}"
        self._next_id += 1

        # Ensure array is contiguous for efficient transfer
        if not array.flags.c_contiguous:
            array = np.ascontiguousarray(array)

        # Create memoryview for zero-copy transfer
        self._buffers[buffer_id] = memoryview(array)
        return buffer_id

    def get_buffers_dict(self) -> Dict[str, memoryview]:
        """Get all registered buffers."""
        return self._buffers

    def clear(self):
        """Clear all registered buffers."""
        self._buffers.clear()
        self._next_id = 0


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

    _esm = pathlib.Path(__file__).parent / "widget.js"
    _css = pathlib.Path(__file__).parent / "widget.css"

    # Synced traits
    _scene_data = traitlets.Dict({}).tag(sync=True)
    _camera_data = traitlets.Dict({}).tag(sync=True)
    _controls_data = traitlets.List([]).tag(sync=True)
    _buffers_changed = traitlets.Int(0).tag(
        sync=True
    )  # Counter to trigger buffer updates

    width = traitlets.CInt(600).tag(sync=True)
    height = traitlets.CInt(400).tag(sync=True)

    antialias = traitlets.Bool(True).tag(sync=True)
    alpha = traitlets.Bool(False).tag(sync=True)

    # Click/interaction events - synced from JavaScript
    _click_info = traitlets.Dict({}).tag(sync=True)
    _hover_info = traitlets.Dict({}).tag(sync=True)

    # Picker events - synced from JavaScript
    _picker_event = traitlets.Dict({}).tag(sync=True)

    # Enable/disable picking
    enable_picking = traitlets.Bool(True).tag(sync=True)

    @traitlets.validate("width")
    def _validate_width(self, proposal):
        return int(proposal["value"])

    @traitlets.validate("height")
    def _validate_height(self, proposal):
        return int(proposal["value"])

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
        # Initialize buffer manager before super().__init__()
        # because trait synchronization may call get_state()
        self._buffer_manager = BufferManager()

        super().__init__(
            width=int(width),
            height=int(height),
            antialias=antialias,
            alpha=alpha,
            **kwargs,
        )

        self._scene = scene
        self._camera = camera
        self._controls = controls or []

        if scene:
            scene._set_renderer(self)
            self._scene_data = scene.to_dict(buffer_manager=None)

        if camera:
            camera._set_renderer(self)
            self._camera_data = camera.to_dict()

        for ctrl in self._controls:
            ctrl._set_renderer(self)
        self._update_controls_data()

        # Observe picker events from JavaScript
        self.observe(self._on_picker_event, names=["_picker_event"])

    def _on_picker_event(self, change):
        """Handle picker events from JavaScript."""
        event_data = change.get("new", {})
        if not event_data:
            return

        picker_uuid = event_data.get("picker_uuid")
        if not picker_uuid:
            return

        # Find the picker with matching UUID
        for ctrl in self._controls:
            if (
                hasattr(ctrl, "_type")
                and ctrl._type == "Picker"
                and ctrl.uuid == picker_uuid
            ):
                # Update picker properties
                if "point" in event_data:
                    point = event_data["point"]
                    ctrl.point = tuple(point) if point else None
                if "distance" in event_data:
                    ctrl.distance = event_data["distance"]
                if "faceIndex" in event_data:
                    ctrl.faceIndex = event_data["faceIndex"]
                if "modifiers" in event_data:
                    ctrl.modifiers = event_data.get("modifiers", [])
                break

    @property
    def scene(self) -> Optional[Scene]:
        return self._scene

    @scene.setter
    def scene(self, value: Scene):
        if self._scene:
            self._scene._set_renderer(None)
        self._scene = value
        if value:
            value._set_renderer(self)
            self._scene_data = value.to_dict(buffer_manager=None)

    @property
    def camera(self):
        return self._camera

    @camera.setter
    def camera(self, value):
        if self._camera:
            self._camera._set_renderer(None)
        self._camera = value
        if value:
            value._set_renderer(self)
            self._camera_data = value.to_dict()

    @property
    def controls(self) -> list:
        return self._controls

    @controls.setter
    def controls(self, value: list):
        for ctrl in self._controls:
            ctrl._set_renderer(None)
        self._controls = value or []
        for ctrl in self._controls:
            ctrl._set_renderer(self)
        self._update_controls_data()

    def _update_controls_data(self):
        self._controls_data = [ctrl.to_dict() for ctrl in self._controls]

    def _request_render(self):
        """Called by objects when they change to trigger re-render."""
        # Binary buffers disabled - anywidget doesn't transfer them correctly
        # Using JSON-only serialization for now
        if self._scene:
            self._scene_data = self._scene.to_dict(buffer_manager=None)
        if self._camera:
            self._camera_data = self._camera.to_dict()
        self._update_controls_data()

    def get_state(self, key=None, drop_defaults=False):
        """
        Override to include binary buffers in the state.

        This allows efficient transfer of large numpy arrays as binary data
        instead of JSON serialization.
        """
        state = super().get_state(key=key, drop_defaults=drop_defaults)

        # Add binary buffers if any exist
        buffers = self._buffer_manager.get_buffers_dict()
        if buffers:
            state["buffers"] = {k: {"data": v} for k, v in buffers.items()}

        return state

    def render(self, scene=None, camera=None):
        """Render the scene. For compatibility - rendering is automatic."""
        if scene:
            self.scene = scene
        if camera:
            self.camera = camera
        self._request_render()
