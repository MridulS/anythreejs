/**
 * Browser-side harness for widget.js.
 *
 * Provides a FakeModel implementing the slice of the anywidget model API
 * that widget.js uses (get/set/save_changes/on/off), plus helpers to boot
 * the widget from a Python-generated snapshot, feed it Python-captured op
 * messages, and inspect the resulting three.js world and rendered pixels.
 *
 * Binary payloads arrive from pytest as {"__b64__": "..."} markers and are
 * decoded to DataViews — exactly what the real widget manager delivers
 * after extracting binary buffers.
 */

function b64ToDataView(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new DataView(bytes.buffer);
}

function decode(node) {
  if (node === null || typeof node !== "object") return node;
  if (Array.isArray(node)) return node.map(decode);
  if (typeof node.__b64__ === "string") return b64ToDataView(node.__b64__);
  const out = {};
  for (const [key, value] of Object.entries(node)) out[key] = decode(value);
  return out;
}

class FakeModel {
  constructor(state) {
    this.state = state;
    this.listeners = new Map();
    this.saved = [];
    this.pending = {};
  }

  get(key) {
    return this.state[key];
  }

  set(key, value) {
    this.state[key] = value;
    this.pending[key] = value;
  }

  save_changes() {
    this.saved.push(JSON.parse(JSON.stringify(this.pending)));
    this.pending = {};
  }

  send(content) {
    (this.sentMessages ??= []).push(content);
  }

  on(event, callback) {
    if (!this.listeners.has(event)) this.listeners.set(event, []);
    this.listeners.get(event).push(callback);
  }

  off(event, callback) {
    const list = this.listeners.get(event) ?? [];
    const index = list.indexOf(callback);
    if (index >= 0) list.splice(index, 1);
  }

  emit(event, ...args) {
    for (const callback of [...(this.listeners.get(event) ?? [])]) {
      callback(...args);
    }
  }
}

const harness = {
  module: null,
  model: null,
  world: null,
  view: null,
  cleanups: [],

  async boot(payload) {
    // Tear down any previous widget instance on this page.
    while (this.cleanups.length) this.cleanups.pop()();

    const state = {
      width: 200,
      height: 150,
      antialias: false,
      alpha: false,
      enable_picking: true,
      enable_hover: false,
      _hover_info: {},
      _click_info: {},
      _picker_event: {},
      _camera_state: {},
      ...decode(payload.state ?? {}),
      _scene_state: decode(payload.scene_state ?? {}),
    };

    this.module = (await import("/widget.js")).default;
    this.model = new FakeModel(state);

    const initCleanup = this.module.initialize({ model: this.model });
    if (initCleanup) this.cleanups.push(initCleanup);

    const el = document.getElementById("root");
    el.innerHTML = "";
    const renderCleanup = this.module.render({ model: this.model, el });
    if (renderCleanup) this.cleanups.push(renderCleanup);

    this.world = this.model._anythreejsWorld;
    this.view = [...this.world.views][0];

    const t0 = performance.now();
    this.view.renderer.render(this.world.scene, this.world.camera);
    const firstRenderMs = performance.now() - t0;
    const summary = this.summary();
    summary.firstRenderMs = firstRenderMs;
    return summary;
  },

  applyMessages(messages) {
    for (const message of messages) {
      const buffers = (message.buffers ?? []).map(b64ToDataView);
      this.model.emit("msg:custom", message.content, buffers);
    }
    return this.summary();
  },

  /** Apply messages and force a frame, reporting JS-side timings. The
   * base64 decode (harness transport, not present in production) happens
   * BEFORE the timer — it once accounted for ~98% of applyMs at 1M pts. */
  applyMessagesTimed(messages) {
    const decoded = messages.map((message) => ({
      content: message.content,
      buffers: (message.buffers ?? []).map(b64ToDataView),
    }));
    const t0 = performance.now();
    for (const message of decoded) {
      this.model.emit("msg:custom", message.content, message.buffers);
    }
    const applyMs = performance.now() - t0;
    const t1 = performance.now();
    this.view.renderer.render(this.world.scene, this.world.camera);
    const renderMs = performance.now() - t1;
    return { applyMs, renderMs };
  },

  /** Count animation frames over a duration; the View's own loop renders
   * every frame, so this reports the effective frame rate under load. */
  measureFps(durationMs) {
    return new Promise((resolve) => {
      let frames = 0;
      const start = performance.now();
      const tick = () => {
        frames += 1;
        const elapsed = performance.now() - start;
        if (elapsed >= durationMs) {
          resolve({ frames, fps: (frames / elapsed) * 1000 });
        } else {
          requestAnimationFrame(tick);
        }
      };
      requestAnimationFrame(tick);
    });
  },

  setAutoRotate(enabled) {
    if (this.view.controls) {
      this.view.controls.autoRotate = enabled;
      this.view.controls.autoRotateSpeed = 20;
    }
  },

  /** Full-frame RGBA readback (rows flipped to top-down), base64-encoded.
   * Retries once on an all-black frame: see readPixel. */
  async screenshot() {
    let shot = this._screenshotOnce();
    let allBlack = true;
    for (let i = 0; i < shot.pixels.length; i += 64) {
      if (shot.pixels[i] || shot.pixels[i + 1] || shot.pixels[i + 2]) {
        allBlack = false;
        break;
      }
    }
    if (allBlack) {
      await new Promise((resolve) => requestAnimationFrame(resolve));
      shot = this._screenshotOnce();
    }
    let binary = "";
    for (let i = 0; i < shot.pixels.length; i += 8192) {
      binary += String.fromCharCode(...shot.pixels.subarray(i, i + 8192));
    }
    return { width: shot.width, height: shot.height, b64: btoa(binary) };
  },

  _screenshotOnce() {
    const renderer = this.view.renderer;
    renderer.render(this.world.scene, this.world.camera);
    renderer.render(this.world.scene, this.world.camera);
    const gl = renderer.getContext();
    const width = gl.drawingBufferWidth;
    const height = gl.drawingBufferHeight;
    const pixels = new Uint8Array(width * height * 4);
    gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);

    const flipped = new Uint8Array(width * height * 4);
    const rowBytes = width * 4;
    for (let y = 0; y < height; y++) {
      flipped.set(
        pixels.subarray(y * rowBytes, (y + 1) * rowBytes),
        (height - 1 - y) * rowBytes
      );
    }
    return { width, height, pixels: flipped };
  },

  setSceneState(payload) {
    this.model.state._scene_state = decode(payload);
    this.model.emit("change:_scene_state");
    return this.summary();
  },

  summary() {
    const world = this.world;
    const byType = {};
    for (const [, spec] of world.specs) {
      byType[spec.type] = (byType[spec.type] ?? 0) + 1;
    }
    let sceneNodes = 0;
    if (world.scene) world.scene.traverse(() => sceneNodes++);
    return {
      registry: world.objects.size,
      specs: world.specs.size,
      byType,
      sceneNodes,
      epoch: world.lastEpoch,
      camera: this.cameraPose(),
    };
  },

  cameraPose() {
    const camera = this.world.camera;
    if (!camera) return null;
    return {
      position: camera.position.toArray(),
      rotation: [camera.rotation.x, camera.rotation.y, camera.rotation.z],
      zoom: camera.zoom,
    };
  },

  /** Serializable inspection of one registry object by uuid. */
  object(uuid) {
    const obj = this.world.objects.get(uuid);
    if (!obj) return null;
    const out = { type: obj.type ?? obj.constructor.name };
    if (obj.isBufferGeometry) {
      out.attributes = {};
      for (const [name, attr] of Object.entries(obj.attributes)) {
        out.attributes[name] = {
          length: attr.array.length,
          itemSize: attr.itemSize,
          first: [...attr.array.slice(0, Math.min(6, attr.array.length))],
        };
      }
      out.index = obj.index ? obj.index.array.length : null;
      if (!obj.boundingSphere) obj.computeBoundingSphere();
      out.boundingSphereRadius = obj.boundingSphere.radius;
      if (obj.parameters) out.parameters = obj.parameters;
    }
    if (obj.isMaterial) {
      out.colorHex = obj.color ? obj.color.getHexString() : null;
      out.opacity = obj.opacity;
      out.transparent = obj.transparent;
      out.visible = obj.visible;
      out.depthTest = obj.depthTest;
      out.depthWrite = obj.depthWrite;
      out.hasMap = !!obj.map;
    }
    if (obj.isObject3D) {
      out.position = obj.position.toArray();
      out.quaternion = obj.quaternion.toArray();
      out.visible = obj.visible;
      out.children = obj.children.length;
    }
    return out;
  },

  /** Force a render and report live GPU resource counts. */
  renderInfo() {
    this.view.renderer.render(this.world.scene, this.world.camera);
    const memory = this.view.renderer.info.memory;
    return { geometries: memory.geometries, textures: memory.textures };
  },

  _readPixelOnce(fx, fy) {
    const renderer = this.view.renderer;
    renderer.render(this.world.scene, this.world.camera);
    renderer.render(this.world.scene, this.world.camera);
    const gl = renderer.getContext();
    const x = Math.floor(fx * (gl.drawingBufferWidth - 1));
    const y = Math.floor(fy * (gl.drawingBufferHeight - 1));
    const px = new Uint8Array(4);
    gl.readPixels(
      x,
      gl.drawingBufferHeight - 1 - y,
      1,
      1,
      gl.RGBA,
      gl.UNSIGNED_BYTE,
      px
    );
    return [...px];
  },

  /** Read one pixel at fractional canvas coordinates (0..1).
   * Cold-start SwiftShader has intermittently returned a stale black
   * frame on a session's FIRST read (4 sightings, never reproducible
   * after) — CI runners are always cold. A black read retries once after
   * an animation frame; genuinely black pixels just pay one rAF. */
  async readPixel(fx, fy) {
    let px = this._readPixelOnce(fx, fy);
    if (px[0] === 0 && px[1] === 0 && px[2] === 0) {
      await new Promise((resolve) => requestAnimationFrame(resolve));
      px = this._readPixelOnce(fx, fy);
    }
    return px;
  },

  savedStates() {
    return this.model.saved;
  },
};

window.harness = harness;
window.harnessReady = true;
