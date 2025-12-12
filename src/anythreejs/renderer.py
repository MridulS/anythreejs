"""
Renderer widget - the main anywidget that displays Three.js scenes.
"""

import pathlib
from typing import Optional

import anywidget
import traitlets

from .core import Scene


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

    width = traitlets.Int(600).tag(sync=True)
    height = traitlets.Int(400).tag(sync=True)

    antialias = traitlets.Bool(True).tag(sync=True)
    alpha = traitlets.Bool(False).tag(sync=True)

    # Click/interaction events - synced from JavaScript
    _click_info = traitlets.Dict({}).tag(sync=True)
    _hover_info = traitlets.Dict({}).tag(sync=True)

    # Enable/disable picking
    enable_picking = traitlets.Bool(True).tag(sync=True)

    layout = traitlets.Any(None)

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
            self._scene_data = scene.to_dict()

        if camera:
            camera._set_renderer(self)
            self._camera_data = camera.to_dict()

        for ctrl in self._controls:
            ctrl._set_renderer(self)
        self._update_controls_data()

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
            self._scene_data = value.to_dict()

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
        if self._scene:
            self._scene_data = self._scene.to_dict()
        if self._camera:
            self._camera_data = self._camera.to_dict()
        self._update_controls_data()

    def render(self, scene=None, camera=None):
        """Render the scene. For compatibility - rendering is automatic."""
        if scene:
            self.scene = scene
        if camera:
            self.camera = camera
        self._request_render()
