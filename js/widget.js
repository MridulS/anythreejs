/**
 * anythreejs - Renderer widget
 *
 * Three.js rendering using anywidget.
 *
 * Architecture:
 * - One `World` per widget model (created in `initialize`): holds the
 *   uuid -> spec map and uuid -> three.js object registry, and applies
 *   the normalized `_scene_state` snapshot plus incremental delta ops
 *   arriving as custom messages (create/update/buffer/child_add/
 *   child_remove/remove). Removal disposes GPU resources.
 * - One `View` per display (created in `render`): its own WebGLRenderer,
 *   controls instance and event listeners, all rendering the shared
 *   World scene/camera. Interactive camera pose is synced back to Python
 *   through the `_camera_state` trait, throttled and tagged with the last
 *   applied epoch so Python can drop stale updates.
 */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TrackballControls } from "three/addons/controls/TrackballControls.js";
import { Line2 } from "three/addons/lines/Line2.js";
import { LineGeometry } from "three/addons/lines/LineGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";

// Debug logging flag - set to true to enable debug logs
const DEBUG = false;
const debug = (...args) => DEBUG && console.log("[anythreejs]", ...args);

// Performance constants
const PICKER_THROTTLE_MS = 16; // ~60fps for picker mousemove events
const HOVER_THROTTLE_MS = 50; // 50ms throttle for hover detection
const CAMERA_SYNC_THROTTLE_MS = 50; // camera pose sync-back to Python

// ---------------------------------------------------------------------------
// Constant maps
// ---------------------------------------------------------------------------

const SIDE_MAP = {
  FrontSide: THREE.FrontSide,
  BackSide: THREE.BackSide,
  DoubleSide: THREE.DoubleSide,
  front: THREE.FrontSide,
  back: THREE.BackSide,
  double: THREE.DoubleSide,
};

const FORMAT_MAP = {
  RGBFormat: THREE.RGBFormat,
  RGBAFormat: THREE.RGBAFormat,
  RedFormat: THREE.RedFormat,
  RGFormat: THREE.RGFormat,
  AlphaFormat: THREE.AlphaFormat,
};

const TYPE_MAP = {
  UnsignedByteType: THREE.UnsignedByteType,
  ByteType: THREE.ByteType,
  ShortType: THREE.ShortType,
  UnsignedShortType: THREE.UnsignedShortType,
  IntType: THREE.IntType,
  UnsignedIntType: THREE.UnsignedIntType,
  FloatType: THREE.FloatType,
  HalfFloatType: THREE.HalfFloatType,
};

const WRAP_MAP = {
  ClampToEdgeWrapping: THREE.ClampToEdgeWrapping,
  RepeatWrapping: THREE.RepeatWrapping,
  MirroredRepeatWrapping: THREE.MirroredRepeatWrapping,
};

const FILTER_MAP = {
  NearestFilter: THREE.NearestFilter,
  LinearFilter: THREE.LinearFilter,
  NearestMipmapNearestFilter: THREE.NearestMipmapNearestFilter,
  NearestMipmapLinearFilter: THREE.NearestMipmapLinearFilter,
  LinearMipmapNearestFilter: THREE.LinearMipmapNearestFilter,
  LinearMipmapLinearFilter: THREE.LinearMipmapLinearFilter,
};

const GEOMETRY_TYPES = new Set([
  "BoxGeometry",
  "SphereGeometry",
  "PlaneGeometry",
  "CylinderGeometry",
  "CircleGeometry",
  "TorusGeometry",
  "EdgesGeometry",
  "LineGeometry",
  "BufferGeometry",
]);

const MATERIAL_TYPES = new Set([
  "Material",
  "MeshBasicMaterial",
  "MeshStandardMaterial",
  "MeshPhongMaterial",
  "MeshLambertMaterial",
  "PointsMaterial",
  "LineBasicMaterial",
  "LineDashedMaterial",
  "SpriteMaterial",
  "LineMaterial",
  "ShaderMaterial",
]);

const TEXTURE_TYPES = new Set(["DataTexture", "TextTexture"]);

const HELPER_TYPES = new Set(["AxesHelper", "GridHelper"]);

const CONTROL_TYPES = new Set(["OrbitControls", "TrackballControls", "Picker"]);

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

/**
 * Build a THREE.Color from a CSS-ish string. Unlike THREE.Color, this
 * accepts 8-digit (#rrggbbaa) and 4-digit (#rgba) hex by dropping alpha —
 * matplotlib's to_hex(keep_alpha=True) produces these.
 */
function colorOf(value, fallback = "#ffffff") {
  let v = value ?? fallback;
  if (typeof v === "string" && v.startsWith("#")) {
    if (v.length === 9) v = v.slice(0, 7);
    else if (v.length === 5) v = v.slice(0, 4);
  }
  return new THREE.Color(v);
}

/**
 * Convert vertexColors value to boolean.
 * Old pythreejs used 'VertexColors' string, new Three.js uses boolean.
 */
function parseVertexColors(value) {
  return value === "VertexColors" || value === true;
}

function typedArrayFor(dtype) {
  if (!dtype) return Float32Array;
  const d = dtype.toLowerCase();
  if (d.includes("float32")) return Float32Array;
  if (d.includes("float64")) return Float64Array;
  if (d.includes("uint32")) return Uint32Array;
  if (d.includes("int32")) return Int32Array;
  if (d.includes("uint16")) return Uint16Array;
  if (d.includes("int16")) return Int16Array;
  if (d.includes("uint8")) return Uint8Array;
  if (d.includes("int8")) return Int8Array;
  return Float32Array;
}

// Matches numpy dtype names ("float32", "uint8", ...) — NOT three.js type
// names ("UnsignedByteType"). DataTexture specs carry a three.js `dtype`
// AND a `data` key, which once made the whole spec look like a wrapper.
const NUMPY_DTYPE = /^(?:float|u?int)(?:8|16|32|64)$/;

function isBufferWrapper(node) {
  return (
    node !== null &&
    typeof node === "object" &&
    !Array.isArray(node) &&
    !ArrayBuffer.isView(node) &&
    typeof node.dtype === "string" &&
    NUMPY_DTYPE.test(node.dtype) &&
    "data" in node &&
    !("type" in node)
  );
}

/**
 * Turn a `{dtype, data}` wrapper into a TypedArray. `data` may be a
 * DataView (snapshot path: the widget protocol reinserts binary buffers
 * in place), a `{__buffer__: i}` placeholder (delta ops path, resolved
 * against the message buffers), or a plain array (JSON fallback).
 * The bytes are copied so the result is aligned and owns its memory.
 */
function toTypedArray(wrapper, buffers, alias = false) {
  const Ctor = typedArrayFor(wrapper.dtype);
  let d = wrapper.data;
  if (d && typeof d === "object" && !ArrayBuffer.isView(d) && "__buffer__" in d) {
    d = buffers?.[d.__buffer__];
  }
  if (d instanceof DataView) {
    // Aliasing view when aligned: avoids a full copy on the hot buffer-op
    // path (the message buffer is ours to keep alive).
    if (alias && d.byteOffset % Ctor.BYTES_PER_ELEMENT === 0) {
      return new Ctor(d.buffer, d.byteOffset, d.byteLength / Ctor.BYTES_PER_ELEMENT);
    }
    return new Ctor(d.buffer.slice(d.byteOffset, d.byteOffset + d.byteLength));
  }
  if (d instanceof ArrayBuffer) {
    return alias ? new Ctor(d) : new Ctor(d.slice(0));
  }
  if (ArrayBuffer.isView(d)) {
    if (alias && d instanceof Ctor) return d;
    return new Ctor(d.buffer.slice(d.byteOffset, d.byteOffset + d.byteLength));
  }
  if (Array.isArray(d)) {
    return Ctor.from(d);
  }
  console.warn("anythreejs: unresolvable binary payload", wrapper);
  return new Ctor(0);
}

/** Recursively resolve `{dtype, data}` wrappers inside a spec/props tree. */
function resolveBuffers(node, buffers) {
  if (node === null || typeof node !== "object") return node;
  if (ArrayBuffer.isView(node) || node instanceof ArrayBuffer) return node;
  if (isBufferWrapper(node)) {
    return { ...node, data: toTypedArray(node, buffers) };
  }
  if (Array.isArray(node)) return node.map((v) => resolveBuffers(v, buffers));
  const out = {};
  for (const [key, value] of Object.entries(node)) {
    out[key] = resolveBuffers(value, buffers);
  }
  return out;
}

/** Get the TypedArray for an attribute entry (wrapper or legacy forms). */
function attributeArray(entry) {
  if (!entry) return null;
  if (ArrayBuffer.isView(entry)) return entry;
  if (Array.isArray(entry)) return Uint32Array.from(entry); // bare index list
  if (ArrayBuffer.isView(entry.data)) return entry.data;
  if (Array.isArray(entry.data)) return typedArrayFor(entry.dtype).from(entry.data);
  if (Array.isArray(entry.array)) return typedArrayFor(entry.dtype).from(entry.array);
  return null;
}

/** Apply position, rotation, scale from a spec to an object. */
function applyTransform(obj, spec) {
  if (spec.position) obj.position.set(...spec.position);
  if (spec.rotation) {
    obj.rotation.set(
      spec.rotation[0],
      spec.rotation[1],
      spec.rotation[2],
      spec.rotationOrder ?? "XYZ"
    );
  }
  if (spec.scale) obj.scale.set(...spec.scale);
  // Quaternion takes precedence over Euler rotation when both are set
  // (pythreejs surface: McStasScript orients components via quaternions).
  if (spec.quaternion) obj.quaternion.set(...spec.quaternion);
}

// ---------------------------------------------------------------------------
// Builders: serialized spec -> three.js object
// ---------------------------------------------------------------------------

function buildGeometry(spec, world) {
  switch (spec.type) {
    case "BoxGeometry":
      return new THREE.BoxGeometry(
        spec.width,
        spec.height,
        spec.depth,
        spec.widthSegments,
        spec.heightSegments,
        spec.depthSegments
      );

    case "SphereGeometry":
      return new THREE.SphereGeometry(
        spec.radius,
        spec.widthSegments,
        spec.heightSegments,
        spec.phiStart,
        spec.phiLength,
        spec.thetaStart,
        spec.thetaLength
      );

    case "PlaneGeometry":
      return new THREE.PlaneGeometry(
        spec.width,
        spec.height,
        spec.widthSegments,
        spec.heightSegments
      );

    case "CylinderGeometry":
      return new THREE.CylinderGeometry(
        spec.radiusTop,
        spec.radiusBottom,
        spec.height,
        spec.radialSegments,
        spec.heightSegments,
        spec.openEnded,
        spec.thetaStart,
        spec.thetaLength
      );

    case "CircleGeometry":
      return new THREE.CircleGeometry(
        spec.radius,
        spec.segments,
        spec.thetaStart,
        spec.thetaLength
      );

    case "TorusGeometry":
      return new THREE.TorusGeometry(
        spec.radius,
        spec.tube,
        spec.radialSegments,
        spec.tubularSegments,
        spec.arc
      );

    case "BufferGeometry": {
      const geometry = new THREE.BufferGeometry();
      for (const [name, entry] of Object.entries(spec.attributes ?? {})) {
        const array = attributeArray(entry);
        if (array) {
          geometry.setAttribute(
            name,
            new THREE.BufferAttribute(
              array,
              entry.itemSize ?? 3,
              entry.normalized ?? false
            )
          );
        } else {
          debug("no array data for attribute", name);
        }
      }
      if (spec.index != null) {
        const index = attributeArray(spec.index);
        if (index) geometry.setIndex(new THREE.BufferAttribute(index, 1));
      }
      // Normals are computed by Mesh consumers (markMeshGeometry) —
      // Points/Line clouds never read them, and computing them per
      // position update cost ~80ms/tick at 1M points.
      return geometry;
    }

    case "EdgesGeometry": {
      const source = spec.geometry ? world.ensure(spec.geometry) : null;
      if (source && source.isBufferGeometry) {
        return new THREE.EdgesGeometry(source, spec.thresholdAngle ?? 1);
      }
      return new THREE.BufferGeometry();
    }

    case "LineGeometry": {
      const geometry = new LineGeometry();
      const positions = attributeArray(spec.positions) ?? flattenNested(spec.positions);
      if (positions) geometry.setPositions(positions);
      const colors = attributeArray(spec.colors) ?? flattenNested(spec.colors);
      if (colors) geometry.setColors(colors);
      return geometry;
    }

    default:
      console.warn(`anythreejs: unknown geometry type: ${spec.type}`);
      return null;
  }
}

/** Legacy JSON path: positions may be a flat list or list of [x,y,z]. */
function flattenNested(value) {
  if (!Array.isArray(value)) return null;
  return Array.isArray(value[0]) ? value.flat() : value;
}

function buildTexture(spec) {
  switch (spec.type) {
    case "DataTexture": {
      let format = FORMAT_MAP[spec.format] ?? THREE.RGBAFormat;
      let array = attributeArray(spec.data);
      if (!array && Array.isArray(spec.data)) {
        // Legacy JSON list: pick array kind from the declared three.js type
        const declared = TYPE_MAP[spec.dtype] ?? THREE.UnsignedByteType;
        array =
          declared === THREE.FloatType || declared === THREE.HalfFloatType
            ? Float32Array.from(spec.data)
            : Uint8Array.from(spec.data);
      }
      if (!array) {
        console.warn("anythreejs: DataTexture without data");
        return null;
      }

      // The three.js texel type follows the actual array kind.
      let dtype;
      if (array instanceof Float32Array || array instanceof Float64Array) {
        if (array instanceof Float64Array) array = Float32Array.from(array);
        dtype = THREE.FloatType;
      } else if (array instanceof Uint16Array) {
        dtype = THREE.UnsignedShortType;
      } else if (array instanceof Uint8Array) {
        dtype = THREE.UnsignedByteType;
      } else {
        array = Uint8Array.from(array);
        dtype = THREE.UnsignedByteType;
      }

      let width = spec.width;
      let height = spec.height;
      if (!width || !height) {
        const channels =
          format === THREE.RGBAFormat ? 4 : format === THREE.RGBFormat ? 3 : 1;
        const pixels = array.length / channels;
        width = height = Math.round(Math.sqrt(pixels));
        debug("DataTexture: inferred dimensions", width, height);
      }

      // RGBFormat was removed from three.js - expand RGB to RGBA.
      if (format === THREE.RGBFormat || spec.format === "RGBFormat") {
        const pixels = array.length / 3;
        const rgba =
          dtype === THREE.FloatType
            ? new Float32Array(pixels * 4)
            : new Uint8Array(pixels * 4);
        const alpha = dtype === THREE.FloatType ? 1.0 : 255;
        for (let i = 0; i < pixels; i++) {
          rgba[i * 4] = array[i * 3];
          rgba[i * 4 + 1] = array[i * 3 + 1];
          rgba[i * 4 + 2] = array[i * 3 + 2];
          rgba[i * 4 + 3] = alpha;
        }
        array = rgba;
        format = THREE.RGBAFormat;
      }

      const texture = new THREE.DataTexture(array, width, height, format, dtype);
      texture.wrapS = WRAP_MAP[spec.wrapS] ?? THREE.ClampToEdgeWrapping;
      texture.wrapT = WRAP_MAP[spec.wrapT] ?? THREE.ClampToEdgeWrapping;
      texture.magFilter = FILTER_MAP[spec.magFilter] ?? THREE.LinearFilter;
      texture.minFilter = FILTER_MAP[spec.minFilter] ?? THREE.LinearFilter;
      texture.colorSpace =
        dtype === THREE.UnsignedByteType
          ? THREE.SRGBColorSpace
          : THREE.LinearSRGBColorSpace;
      // Data comes in numpy row order; don't flip.
      texture.flipY = false;
      texture.needsUpdate = true;
      return texture;
    }

    case "TextTexture": {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      const text = spec.string || "";
      const fontSize = spec.size || 100;
      const fontFace = spec.fontFace || "Arial";

      ctx.font = `${fontSize}px ${fontFace}`;
      const metrics = ctx.measureText(text);

      const width = spec.squareTexture
        ? Math.max(metrics.width, fontSize)
        : metrics.width || fontSize;
      const height = spec.squareTexture ? width : fontSize * 1.2;

      canvas.width = width;
      canvas.height = height;

      ctx.font = `${fontSize}px ${fontFace}`;
      ctx.fillStyle = spec.color || "black";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(text, width / 2, height / 2);

      const texture = new THREE.CanvasTexture(canvas);
      texture.needsUpdate = true;
      return texture;
    }

    default:
      console.warn(`anythreejs: unknown texture type: ${spec.type}`);
      return null;
  }
}

function buildMaterial(spec, world) {
  const side = SIDE_MAP[spec.side] ?? THREE.FrontSide;
  const map = spec.map ? world.ensure(spec.map) : null;

  const baseProps = {
    color: colorOf(spec.color),
    opacity: spec.opacity ?? 1,
    transparent: spec.transparent ?? false,
    visible: spec.visible ?? true,
    side: side,
    depthTest: spec.depthTest ?? true,
    depthWrite: spec.depthWrite ?? true,
  };

  switch (spec.type) {
    case "MeshBasicMaterial": {
      const mat = new THREE.MeshBasicMaterial({
        ...baseProps,
        wireframe: spec.wireframe ?? false,
        vertexColors: parseVertexColors(spec.vertexColors),
      });
      if (map) {
        mat.map = map;
        mat.needsUpdate = true;
      }
      return mat;
    }

    case "MeshStandardMaterial": {
      const mat = new THREE.MeshStandardMaterial({
        ...baseProps,
        roughness: spec.roughness ?? 0.5,
        metalness: spec.metalness ?? 0.5,
        wireframe: spec.wireframe ?? false,
        flatShading: spec.flatShading ?? false,
        vertexColors: parseVertexColors(spec.vertexColors),
        emissive: colorOf(spec.emissive, "#000000"),
        emissiveIntensity: spec.emissiveIntensity ?? 1.0,
      });
      if (map) {
        mat.map = map;
        mat.needsUpdate = true;
      }
      return mat;
    }

    case "MeshPhongMaterial": {
      const mat = new THREE.MeshPhongMaterial({
        ...baseProps,
        shininess: spec.shininess ?? 30,
        specular: colorOf(spec.specular, "#111111"),
        wireframe: spec.wireframe ?? false,
        flatShading: spec.flatShading ?? false,
        vertexColors: parseVertexColors(spec.vertexColors),
      });
      if (map) {
        mat.map = map;
        mat.needsUpdate = true;
      }
      return mat;
    }

    case "MeshLambertMaterial": {
      const mat = new THREE.MeshLambertMaterial({
        ...baseProps,
        wireframe: spec.wireframe ?? false,
        vertexColors: parseVertexColors(spec.vertexColors),
      });
      if (map) {
        mat.map = map;
        mat.needsUpdate = true;
      }
      return mat;
    }

    case "PointsMaterial":
      return new THREE.PointsMaterial({
        ...baseProps,
        size: spec.size ?? 1,
        sizeAttenuation: spec.sizeAttenuation ?? true,
        vertexColors: parseVertexColors(spec.vertexColors),
      });

    case "LineBasicMaterial":
      return new THREE.LineBasicMaterial({
        ...baseProps,
        linewidth: spec.linewidth ?? 1,
        vertexColors: parseVertexColors(spec.vertexColors),
      });

    case "LineDashedMaterial":
      return new THREE.LineDashedMaterial({
        ...baseProps,
        linewidth: spec.linewidth ?? 1,
        dashSize: spec.dashSize ?? 3,
        gapSize: spec.gapSize ?? 1,
        vertexColors: parseVertexColors(spec.vertexColors),
      });

    case "SpriteMaterial": {
      const props = {
        transparent: spec.transparent ?? !!map,
        opacity: spec.opacity ?? 1,
      };
      if (map) props.map = map;
      else props.color = colorOf(spec.color);
      return new THREE.SpriteMaterial(props);
    }

    case "ShaderMaterial": {
      const params = {
        transparent: spec.transparent ?? false,
        opacity: spec.opacity ?? 1,
        visible: spec.visible ?? true,
        side: side,
        depthTest: spec.depthTest ?? true,
        depthWrite: spec.depthWrite ?? true,
      };
      if (spec.vertexShader) params.vertexShader = spec.vertexShader;
      if (spec.fragmentShader) params.fragmentShader = spec.fragmentShader;
      if (spec.uniforms) params.uniforms = structuredClone(spec.uniforms);
      return new THREE.ShaderMaterial(params);
    }

    case "LineMaterial": {
      const mat = new LineMaterial({
        color: colorOf(spec.color).getHex(),
        linewidth: spec.linewidth ?? 1,
        vertexColors: parseVertexColors(spec.vertexColors),
        opacity: spec.opacity ?? 1,
        transparent: spec.transparent ?? false,
        dashed: spec.dashed ?? false,
        dashScale: spec.dashScale ?? 1,
        dashSize: spec.dashSize ?? 1,
        gapSize: spec.gapSize ?? 1,
      });
      if (Array.isArray(spec.resolution)) {
        mat.resolution.set(spec.resolution[0], spec.resolution[1]);
      } else {
        mat.resolution.set(window.innerWidth, window.innerHeight);
      }
      return mat;
    }

    default:
      console.warn(`anythreejs: unknown material type: ${spec.type}`);
      return new THREE.MeshBasicMaterial(baseProps);
  }
}

function buildCamera(spec) {
  let camera;
  switch (spec.type) {
    case "PerspectiveCamera":
      camera = new THREE.PerspectiveCamera(
        spec.fov ?? 50,
        spec.aspect ?? 1,
        spec.near ?? 0.1,
        spec.far ?? 2000
      );
      break;

    case "OrthographicCamera":
      camera = new THREE.OrthographicCamera(
        spec.left ?? -1,
        spec.right ?? 1,
        spec.top ?? 1,
        spec.bottom ?? -1,
        spec.near ?? 0.1,
        spec.far ?? 2000
      );
      camera.zoom = spec.zoom ?? 1;
      camera.updateProjectionMatrix();
      break;

    default:
      console.warn(`anythreejs: unknown camera type: ${spec.type}`);
      camera = new THREE.PerspectiveCamera(50, 1, 0.1, 2000);
  }
  return camera;
}

/** Build a scene-graph node (mesh, light, helper, camera, group, ...). */
function buildSceneNode(spec, world) {
  let obj = null;

  switch (spec.type) {
    case "Scene":
      obj = new THREE.Scene();
      obj.background = spec.background ? colorOf(spec.background) : null;
      break;

    case "Mesh": {
      const geometry = spec.geometry ? world.ensure(spec.geometry) : undefined;
      const material = spec.material ? world.ensure(spec.material) : undefined;
      obj = new THREE.Mesh(geometry ?? undefined, material ?? undefined);
      if (spec.geometry) world.markMeshGeometry(spec.geometry, geometry);
      break;
    }

    case "Points": {
      const geometry = world.ensure(spec.geometry) ?? new THREE.BufferGeometry();
      const material = spec.material ? world.ensure(spec.material) : undefined;
      obj = new THREE.Points(geometry, material ?? undefined);
      break;
    }

    case "Line": {
      const geometry = world.ensure(spec.geometry) ?? new THREE.BufferGeometry();
      const material = spec.material ? world.ensure(spec.material) : undefined;
      obj = new THREE.Line(geometry, material ?? undefined);
      break;
    }

    case "LineSegments": {
      const geometry = world.ensure(spec.geometry) ?? new THREE.BufferGeometry();
      const material = spec.material ? world.ensure(spec.material) : undefined;
      obj = new THREE.LineSegments(geometry, material ?? undefined);
      break;
    }

    case "Line2": {
      const geometry = world.ensure(spec.geometry) ?? new LineGeometry();
      const material =
        world.ensure(spec.material) ?? new LineMaterial({ color: 0xffffff });
      obj = new Line2(geometry, material);
      obj.computeLineDistances();
      break;
    }

    case "Sprite": {
      const material = spec.material ? world.ensure(spec.material) : null;
      obj = new THREE.Sprite(material ?? new THREE.SpriteMaterial());
      break;
    }

    case "Group":
      obj = new THREE.Group();
      break;

    case "AmbientLight":
      obj = new THREE.AmbientLight(colorOf(spec.color), spec.intensity ?? 1);
      break;

    case "DirectionalLight":
      obj = new THREE.DirectionalLight(colorOf(spec.color), spec.intensity ?? 1);
      obj.castShadow = spec.castShadow ?? false;
      if (spec.target) {
        obj.target.position.set(...spec.target);
        // The target is not in the scene graph, so its matrixWorld (which
        // three.js derives the light direction from) must be updated by
        // hand or the target is silently ignored.
        obj.target.updateMatrixWorld(true);
      }
      break;

    case "PointLight":
      obj = new THREE.PointLight(
        colorOf(spec.color),
        spec.intensity ?? 1,
        spec.distance ?? 0,
        spec.decay ?? 2
      );
      obj.castShadow = spec.castShadow ?? false;
      break;

    case "HemisphereLight":
      obj = new THREE.HemisphereLight(
        colorOf(spec.skyColor),
        colorOf(spec.groundColor, "#444444"),
        spec.intensity ?? 1
      );
      break;

    case "SpotLight":
      obj = new THREE.SpotLight(
        colorOf(spec.color),
        spec.intensity ?? 1,
        spec.distance ?? 0,
        spec.angle ?? Math.PI / 6,
        spec.penumbra ?? 0,
        spec.decay ?? 2
      );
      obj.castShadow = spec.castShadow ?? false;
      if (spec.target) {
        obj.target.position.set(...spec.target);
        obj.target.updateMatrixWorld(true); // see DirectionalLight
      }
      break;

    case "GridHelper":
      obj = new THREE.GridHelper(
        spec.size ?? 10,
        spec.divisions ?? 10,
        colorOf(spec.colorCenterLine, "#444444"),
        colorOf(spec.colorGrid, "#888888")
      );
      break;

    case "AxesHelper":
      obj = new THREE.AxesHelper(spec.size ?? 1);
      break;

    case "PerspectiveCamera":
    case "OrthographicCamera":
      obj = buildCamera(spec);
      break;

    default:
      console.warn(`anythreejs: unknown object type: ${spec.type}`);
      return null;
  }

  applyTransform(obj, spec);
  if (spec.lookAt && obj.isCamera) obj.lookAt(new THREE.Vector3(...spec.lookAt));
  obj.name = spec.name || "";
  obj.visible = spec.visible !== false;
  obj.userData.uuid = spec.uuid;

  for (const childUuid of spec.children ?? []) {
    const child = world.ensure(childUuid);
    if (child) obj.add(child);
  }

  return obj;
}

// ---------------------------------------------------------------------------
// World: shared registry + reconciler (one per widget model)
// ---------------------------------------------------------------------------

class World {
  constructor(model) {
    this.model = model;
    this.specs = new Map(); // uuid -> spec (buffers resolved)
    this.objects = new Map(); // uuid -> three.js object
    this.controlSpecs = []; // OrbitControls / TrackballControls specs
    this.pickers = []; // Picker descriptors
    this.views = new Set();
    this.scene = null;
    this.camera = null;
    this.sceneUuid = null;
    this.cameraUuid = null;
    this.controlsTarget = new THREE.Vector3();
    this.hasControlsTarget = false;
    this.latchUuid = null; // controls uuid the target latch belongs to
    this.lastEpoch = 0;
    this.edgesCount = 0; // EdgesGeometry specs alive (fast-skip when 0)
    this.edgeRebuilds = 0; // observability for coalescing tests
    this._dirtyEdgeSources = null;

    this._onCustomMsg = (msg, buffers) => {
      if (msg && msg.kind === "ops") this.applyOps(msg, buffers ?? []);
    };
    this._onSnapshot = () => this.applySnapshot(true);
    model.on("msg:custom", this._onCustomMsg);
    model.on("change:_scene_state", this._onSnapshot);

    this.applySnapshot(false);
  }

  // -- construction -------------------------------------------------------

  ensure(uuid) {
    if (!uuid) return null;
    if (this.objects.has(uuid)) return this.objects.get(uuid);
    const spec = this.specs.get(uuid);
    if (!spec) {
      console.warn("anythreejs: reference to unknown object", uuid);
      return null;
    }
    if (CONTROL_TYPES.has(spec.type)) return null; // no three.js counterpart
    let obj = null;
    try {
      if (GEOMETRY_TYPES.has(spec.type)) obj = buildGeometry(spec, this);
      else if (MATERIAL_TYPES.has(spec.type)) obj = buildMaterial(spec, this);
      else if (TEXTURE_TYPES.has(spec.type)) obj = buildTexture(spec);
      else obj = buildSceneNode(spec, this);
    } catch (error) {
      console.error("anythreejs: failed to build", spec.type, uuid, error);
    }
    if (obj) this.objects.set(uuid, obj);
    return obj;
  }

  registerControl(spec) {
    if (spec.type === "Picker") {
      this.pickers.push({
        uuid: spec.uuid,
        event: spec.event || "click",
        controlling: spec.controlling ?? null,
        all: spec.all ?? false,
        lineThreshold: spec.lineThreshold ?? null,
        pointThreshold: spec.pointThreshold ?? null,
      });
    } else {
      this.controlSpecs.push(spec);
    }
  }

  applySnapshot(preservePose) {
    const state = this.model.get("_scene_state") ?? {};

    // Preserve the interactive pose only when the snapshot still uses the
    // SAME camera — a replaced camera must adopt its own (Python-set) pose.
    const sameCamera =
      this.cameraUuid !== null && (state.camera ?? null) === this.cameraUuid;
    const previousControlsUuid = this.controlSpecs[0]?.uuid ?? null;

    let pose = null;
    if (preservePose && sameCamera && this.camera) {
      pose = {
        position: this.camera.position.clone(),
        rotation: this.camera.rotation.clone(),
        zoom: this.camera.zoom,
        target: this.controlsTarget.clone(),
        hasTarget: this.hasControlsTarget,
      };
    }

    this.disposeAll();

    for (const [uuid, spec] of Object.entries(state.objects ?? {})) {
      this.specs.set(uuid, resolveBuffers(spec, []));
    }
    this.edgesCount = 0;
    for (const spec of this.specs.values()) {
      if (spec.type === "EdgesGeometry") this.edgesCount += 1;
    }
    this.sceneUuid = state.scene ?? null;
    this.cameraUuid = state.camera ?? null;
    this.lastEpoch = state.epoch ?? 0;

    for (const uuid of state.controls ?? []) {
      const spec = this.specs.get(uuid);
      if (spec) this.registerControl(spec);
    }

    this.scene = this.sceneUuid ? this.ensure(this.sceneUuid) : null;
    if (!this.scene) {
      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color("#000000");
    }
    this.camera = this.cameraUuid ? this.ensure(this.cameraUuid) : null;
    if (!this.camera) {
      this.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 2000);
      this.camera.position.set(0, 0, 5);
    }
    // pythreejs adds the camera to the scene (lights parented to the camera
    // etc. keep working).
    if (this.camera.parent === null) this.scene.add(this.camera);

    // Replaced controls must adopt their own spec target: the interactive
    // target latch only carries across a resync when the controls object
    // (and camera) survived it.
    const sameControls =
      previousControlsUuid !== null &&
      (this.controlSpecs[0]?.uuid ?? null) === previousControlsUuid;

    if (pose) {
      this.camera.position.copy(pose.position);
      this.camera.rotation.copy(pose.rotation);
      this.camera.zoom = pose.zoom;
      this.camera.updateProjectionMatrix?.();
      if (sameControls) {
        this.controlsTarget.copy(pose.target);
        this.hasControlsTarget = pose.hasTarget;
      }
    }
    if (!sameCamera || !sameControls) {
      this.hasControlsTarget = false;
    }

    this.refreshLineResolutions();
    for (const view of this.views) view.onWorldRebuilt();
    debug("snapshot applied:", this.specs.size, "objects");
  }

  // -- delta ops ----------------------------------------------------------

  applyOps(msg, buffers) {
    this.lastEpoch = msg.epoch ?? this.lastEpoch;
    // Coalesce derived-edge rebuilds: N position ops on one source in a
    // message trigger one re-extraction, not N.
    this._dirtyEdgeSources = new Set();
    for (const op of msg.ops ?? []) {
      try {
        this.applyOp(op, buffers);
      } catch (error) {
        console.error("anythreejs: op failed", op, error);
      }
    }
    const dirty = this._dirtyEdgeSources;
    this._dirtyEdgeSources = null;
    for (const uuid of dirty) {
      this.edgeRebuilds += 1;
      this.rebuildDependents(uuid, new Set([uuid]));
    }
  }

  applyOp(op, buffers) {
    switch (op.op) {
      case "create": {
        const spec = resolveBuffers(op.spec, buffers);
        this.specs.set(op.uuid, spec);
        if (spec.type === "EdgesGeometry") this.edgesCount += 1;
        if (CONTROL_TYPES.has(spec.type)) {
          this.registerControl(spec);
          for (const view of this.views) view.onWorldRebuilt();
        } else {
          this.ensure(op.uuid);
        }
        break;
      }

      case "update": {
        const props = resolveBuffers(op.props ?? {}, buffers);
        this.updateObject(op.uuid, props);
        break;
      }

      case "buffer": {
        // Resolved here (not via resolveBuffers) so the hot path can use
        // an aliasing view over the message buffer instead of a copy.
        let value = op.value ?? {};
        if (isBufferWrapper(value)) {
          value = { ...value, data: toTypedArray(value, buffers, true) };
        } else {
          value = resolveBuffers(value, buffers);
        }
        this.applyBufferOp(op.uuid, op.attribute, value);
        break;
      }

      case "set_controls": {
        this.controlSpecs = [];
        this.pickers = [];
        for (const uuid of op.controls ?? []) {
          const spec = this.specs.get(uuid);
          if (spec) this.registerControl(spec);
        }
        for (const view of this.views) view.onWorldRebuilt();
        break;
      }

      case "set_camera": {
        this.cameraUuid = op.camera ?? null;
        let camera = this.cameraUuid ? this.ensure(this.cameraUuid) : null;
        if (!camera) {
          camera = new THREE.PerspectiveCamera(50, 1, 0.1, 2000);
          camera.position.set(0, 0, 5);
        }
        this.camera = camera;
        if (this.camera.parent === null && this.scene) {
          this.scene.add(this.camera);
        }
        this.hasControlsTarget = false; // new camera: spec target wins
        for (const view of this.views) view.onWorldRebuilt();
        break;
      }

      case "child_add": {
        const parent = this.ensure(op.uuid);
        const child = this.ensure(op.child);
        if (parent && child) parent.add(child);
        break;
      }

      case "child_remove": {
        const parent = this.objects.get(op.uuid);
        const child = this.objects.get(op.child);
        if (parent && child) parent.remove(child);
        break;
      }

      case "remove":
        this.removeObject(op.uuid);
        break;

      default:
        console.warn("anythreejs: unknown op", op.op);
    }
  }

  updateObject(uuid, props) {
    const spec = this.specs.get(uuid);
    if (!spec) return;
    Object.assign(spec, props);

    if (CONTROL_TYPES.has(spec.type)) {
      this.updateControls(uuid, props);
      return;
    }

    const obj = this.objects.get(uuid);
    if (!obj) return; // not built yet; merged spec is used at build time

    if (GEOMETRY_TYPES.has(spec.type) || TEXTURE_TYPES.has(spec.type)) {
      if (
        spec.type === "LineGeometry" &&
        this.updateLineGeometryInPlace(obj, spec, props)
      ) {
        return;
      }
      this.rebuildResource(uuid);
      return;
    }
    if (MATERIAL_TYPES.has(spec.type)) {
      this.applyMaterialProps(obj, spec, props);
      return;
    }
    if (HELPER_TYPES.has(spec.type)) {
      this.rebuildSceneNode(uuid);
      return;
    }
    this.applyNodeProps(obj, spec, props);
  }

  applyMaterialProps(mat, spec, props) {
    for (const [key, value] of Object.entries(props)) {
      switch (key) {
        case "color":
          if (mat.color) mat.color.copy(colorOf(value));
          break;
        case "emissive":
          if (mat.emissive) mat.emissive.copy(colorOf(value, "#000000"));
          break;
        case "specular":
          if (mat.specular) mat.specular.copy(colorOf(value, "#111111"));
          break;
        case "side":
          mat.side = SIDE_MAP[value] ?? mat.side;
          break;
        case "vertexColors":
          mat.vertexColors = parseVertexColors(value);
          break;
        case "map":
          mat.map = value ? this.ensure(value) : null;
          break;
        case "uniforms":
          if (mat.isShaderMaterial && value) {
            mat.uniforms = structuredClone(value);
          }
          break;
        case "resolution":
          if (mat.resolution && Array.isArray(value)) {
            mat.resolution.set(value[0], value[1]);
          }
          break;
        default:
          if (key in mat) mat[key] = value;
      }
    }
    mat.needsUpdate = true;
  }

  applyNodeProps(obj, spec, props) {
    for (const [key, value] of Object.entries(props)) {
      switch (key) {
        case "position":
          obj.position.set(...value);
          break;
        case "rotation":
          obj.rotation.set(
            value[0],
            value[1],
            value[2],
            spec.rotationOrder ?? obj.rotation.order
          );
          break;
        case "rotationOrder":
          obj.rotation.order = value;
          break;
        case "quaternion":
          if (Array.isArray(value)) obj.quaternion.set(...value);
          break;
        case "scale":
          obj.scale.set(...value);
          break;
        case "visible":
          obj.visible = value;
          break;
        case "name":
          obj.name = value;
          break;
        case "background":
          if (obj.isScene) obj.background = value ? colorOf(value) : null;
          break;
        case "geometry": {
          // null clears to an empty geometry (matching how buildSceneNode
          // treats a mesh serialized without one).
          const geometry = value
            ? this.ensure(value)
            : new THREE.BufferGeometry();
          if (geometry) {
            obj.geometry = geometry;
            if (obj.isLine2) obj.computeLineDistances();
            if (obj.isMesh && value) this.markMeshGeometry(value, geometry);
          }
          break;
        }
        case "material": {
          const material = value
            ? this.ensure(value)
            : new THREE.MeshBasicMaterial();
          if (material) obj.material = material;
          break;
        }
        case "color":
          if (obj.color) obj.color.copy(colorOf(value));
          break;
        case "skyColor":
          if (obj.isHemisphereLight) obj.color.copy(colorOf(value));
          break;
        case "groundColor":
          if (obj.isHemisphereLight) obj.groundColor.copy(colorOf(value, "#444444"));
          break;
        case "target":
          if (obj.target?.position && Array.isArray(value)) {
            obj.target.position.set(...value);
            obj.target.updateMatrixWorld(true); // detached target: see build
          }
          break;
        case "lookAt":
          if (obj.isCamera && Array.isArray(value)) {
            obj.lookAt(new THREE.Vector3(...value));
          }
          break;
        case "fov":
        case "aspect":
        case "near":
        case "far":
        case "zoom":
        case "left":
        case "right":
        case "top":
        case "bottom":
          obj[key] = value;
          obj.updateProjectionMatrix?.();
          break;
        default:
          if (key in obj) obj[key] = value;
      }
    }
  }

  applyBufferOp(uuid, attribute, value) {
    const spec = this.specs.get(uuid);
    if (!spec) return;

    // Merge into the spec FIRST — unconditionally — so a later
    // rebuildResource regenerates from current data even if the geometry
    // isn't built yet or was serialized without an attributes dict.
    if (attribute === "__index__") {
      spec.index = value;
    } else {
      if (!spec.attributes) spec.attributes = {};
      spec.attributes[attribute] = value;
    }

    const geometry = this.objects.get(uuid);
    if (!geometry || !geometry.isBufferGeometry) return;
    const array = attributeArray(value);
    if (!array) return;

    if (attribute === "__index__") {
      geometry.setIndex(new THREE.BufferAttribute(array, 1));
      return;
    }

    const existing = geometry.getAttribute(attribute);
    if (
      existing &&
      existing.array.length === array.length &&
      existing.array.constructor === array.constructor
    ) {
      existing.array.set(array);
      existing.needsUpdate = true;
    } else {
      geometry.setAttribute(
        attribute,
        new THREE.BufferAttribute(
          array,
          value.itemSize ?? existing?.itemSize ?? 3,
          value.normalized ?? false
        )
      );
    }
    if (attribute === "position") {
      // Lazy invalidation: three recomputes bounds on demand (render/
      // raycast) — eager recomputation cost ~116ms/tick at 1M points.
      geometry.boundingBox = null;
      geometry.boundingSphere = null;
      // Normals only where a Mesh actually consumes them (see
      // markMeshGeometry) — never for point clouds/lines.
      if (spec.__needsNormals) geometry.computeVertexNormals();
    }
    if (attribute === "position" || attribute === "__index__") {
      this.markEdgeSourceDirty(uuid);
    }
  }

  /** Flag a BufferGeometry as feeding a lit Mesh: it needs computed
   * normals at build time and after every position update. */
  markMeshGeometry(uuid, geometry) {
    const spec = this.specs.get(uuid);
    if (!spec || spec.type !== "BufferGeometry") return;
    if (spec.attributes?.normal) return;
    spec.__needsNormals = true;
    if (
      geometry?.isBufferGeometry &&
      geometry.attributes.position &&
      !geometry.attributes.normal
    ) {
      geometry.computeVertexNormals();
    }
  }

  /** Queue (or run) the derived-edges rebuild for a changed source. */
  markEdgeSourceDirty(uuid) {
    if (this.edgesCount === 0) return;
    if (this._dirtyEdgeSources) {
      this._dirtyEdgeSources.add(uuid);
    } else {
      this.edgeRebuilds += 1;
      this.rebuildDependents(uuid, new Set([uuid]));
    }
  }

  /** In-place fast path for LineGeometry position/color updates with an
   * unchanged point count: writes into the existing instanced buffers,
   * avoiding geometry rebuild + full-registry swap scan + GPU realloc
   * (matplotgl updates every fat line per pan tick — the rebuild path
   * made that O(lines^2)). Returns false to fall back to a rebuild. */
  updateLineGeometryInPlace(geometry, spec, props) {
    if (!geometry || !geometry.isLineSegmentsGeometry) return false;
    for (const key of Object.keys(props)) {
      if (key !== "positions" && key !== "colors") return false;
    }

    if (props.positions !== undefined) {
      const positions = attributeArray(props.positions);
      if (!positions) return false;
      const start = geometry.attributes.instanceStart;
      const segments = positions.length / 3 - 1;
      if (!start || segments < 1 || start.data.array.length !== segments * 6) {
        return false;
      }
      const buffer = start.data.array;
      for (let i = 0; i < segments; i++) {
        const src = i * 3;
        const dst = i * 6;
        for (let c = 0; c < 6; c++) buffer[dst + c] = positions[src + c];
      }
      start.data.needsUpdate = true;

      const distances = geometry.attributes.instanceDistanceStart;
      if (distances && distances.data.array.length === segments * 2) {
        const dist = distances.data.array;
        let cumulative = 0;
        for (let i = 0; i < segments; i++) {
          dist[2 * i] = cumulative;
          const src = i * 3;
          const dx = positions[src + 3] - positions[src];
          const dy = positions[src + 4] - positions[src + 1];
          const dz = positions[src + 5] - positions[src + 2];
          cumulative += Math.sqrt(dx * dx + dy * dy + dz * dz);
          dist[2 * i + 1] = cumulative;
        }
        distances.data.needsUpdate = true;
      }
      geometry.boundingBox = null;
      geometry.boundingSphere = null;
    }

    if (props.colors !== undefined) {
      const colors = attributeArray(props.colors);
      const colorStart = geometry.attributes.instanceColorStart;
      const segments = colors ? colors.length / 3 - 1 : 0;
      if (
        !colors ||
        !colorStart ||
        colorStart.data.array.length !== segments * 6
      ) {
        return false;
      }
      const buffer = colorStart.data.array;
      for (let i = 0; i < segments; i++) {
        const src = i * 3;
        const dst = i * 6;
        for (let c = 0; c < 6; c++) buffer[dst + c] = colors[src + c];
      }
      colorStart.data.needsUpdate = true;
    }
    return true;
  }

  /** Rebuild EdgesGeometry entries derived from a changed source
   * geometry (edges depend on positions/index, so color-only updates
   * never reach here). */
  rebuildDependents(uuid, seen) {
    for (const [id, spec] of this.specs) {
      if (
        spec.type === "EdgesGeometry" &&
        spec.geometry === uuid &&
        !seen.has(id)
      ) {
        this.rebuildResource(id, seen);
      }
    }
  }

  /** Rebuild a geometry/material/texture in place: build a fresh object
   * from the (already merged) spec and swap it on everything that
   * references the old one, then dispose the old one. Derived
   * EdgesGeometry entries rebuild along with their source (`seen` guards
   * against pathological cycles). */
  rebuildResource(uuid, seen = new Set()) {
    seen.add(uuid);
    const old = this.objects.get(uuid);
    this.objects.delete(uuid);
    const fresh = this.ensure(uuid);
    this.rebuildDependents(uuid, seen);
    if (!old || !fresh) return;
    for (const [, node] of this.objects) {
      if (node.isObject3D) {
        if (node.geometry === old) {
          node.geometry = fresh;
          if (node.isLine2) node.computeLineDistances();
        }
        if (node.material === old) node.material = fresh;
        if (node.material && node.material.map === old) {
          node.material.map = fresh;
          node.material.needsUpdate = true;
        }
      } else if (node.isMaterial && node.map === old) {
        node.map = fresh;
        node.needsUpdate = true;
      }
    }
    old.dispose?.();
    this.refreshLineResolutions();
  }

  /** Rebuild a scene-graph node whose constructor params changed
   * (helpers: AxesHelper size, GridHelper divisions...). */
  rebuildSceneNode(uuid) {
    const old = this.objects.get(uuid);
    const parent = old?.parent ?? null;
    this.objects.delete(uuid);
    const fresh = this.ensure(uuid);
    if (old && fresh && parent) {
      parent.add(fresh);
      parent.remove(old);
    }
    old?.dispose?.();
  }

  updateControls(uuid, props) {
    const picker = this.pickers.find((p) => p.uuid === uuid);
    if (picker) {
      if ("event" in props) picker.event = props.event;
      if ("controlling" in props) picker.controlling = props.controlling;
      if ("all" in props) picker.all = props.all;
      if ("lineThreshold" in props) picker.lineThreshold = props.lineThreshold;
      if ("pointThreshold" in props) picker.pointThreshold = props.pointThreshold;
      return;
    }
    if ("target" in props && Array.isArray(props.target)) {
      this.controlsTarget.set(...props.target);
      this.hasControlsTarget = true;
    }
    for (const view of this.views) view.applyControlsProps(uuid, props);
  }

  removeObject(uuid) {
    const obj = this.objects.get(uuid);
    if (this.specs.get(uuid)?.type === "EdgesGeometry") this.edgesCount -= 1;
    this.objects.delete(uuid);
    this.specs.delete(uuid);
    this.controlSpecs = this.controlSpecs.filter((s) => s.uuid !== uuid);
    this.pickers = this.pickers.filter((p) => p.uuid !== uuid);
    if (obj) {
      if (obj.isObject3D) obj.removeFromParent();
      obj.dispose?.();
    }
  }

  refreshLineResolutions() {
    for (const view of this.views) view.applyLineResolution();
  }

  disposeAll() {
    for (const [, obj] of this.objects) {
      obj.dispose?.();
    }
    this.objects.clear();
    this.specs.clear();
    this.controlSpecs = [];
    this.pickers = [];
    this.scene = null;
    this.camera = null;
  }

  dispose() {
    this.model.off("msg:custom", this._onCustomMsg);
    this.model.off("change:_scene_state", this._onSnapshot);
    this.disposeAll();
  }
}

// ---------------------------------------------------------------------------
// View: one per display of the widget
// ---------------------------------------------------------------------------

class View {
  constructor(world, model, el) {
    this.world = world;
    this.model = model;

    this.container = document.createElement("div");
    this.container.classList.add("anythreejs-container");
    this.container.style.width = "100%";
    this.container.style.height = "100%";
    this.container.style.position = "relative";
    el.appendChild(this.container);

    this.width = model.get("width");
    this.height = model.get("height");

    this.renderer = new THREE.WebGLRenderer({
      antialias: model.get("antialias"),
      alpha: model.get("alpha"),
    });
    this.renderer.setSize(this.width, this.height);
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // sRGB output so matplotlib-style colors display correctly.
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.container.appendChild(this.renderer.domElement);

    this.controls = null;
    this.controlsUuid = null;
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
    this.hoverTimeout = null;
    this.pickerMoveTimeout = null;
    this.cameraSyncTimeout = null;

    this._onResize = () => this.resize();
    model.on("change:width", this._onResize);
    model.on("change:height", this._onResize);

    this._onClick = (e) => this.onClick(e);
    this._onDblClick = (e) => this.onDblClick(e);
    this._onMouseDown = (e) => this.handlePickerEvent(e, "mousedown");
    this._onMouseUp = (e) => this.handlePickerEvent(e, "mouseup");
    this._onMouseMove = (e) => this.onMouseMove(e);
    const dom = this.renderer.domElement;
    dom.addEventListener("click", this._onClick);
    dom.addEventListener("dblclick", this._onDblClick);
    dom.addEventListener("mousedown", this._onMouseDown);
    dom.addEventListener("mouseup", this._onMouseUp);
    dom.addEventListener("mousemove", this._onMouseMove);

    this.buildControls();
    this.applyLineResolution();

    this._animate = () => this.animate();
    this.animationId = requestAnimationFrame(this._animate);

    world.views.add(this);
  }

  onWorldRebuilt() {
    this.buildControls();
  }

  // -- controls -----------------------------------------------------------

  buildControls() {
    if (this.controls) {
      this.controls.dispose();
      this.controls = null;
      this.controlsUuid = null;
    }
    const camera = this.world.camera;
    const spec = this.world.controlSpecs[0];
    if (!camera || !spec) return;

    if (spec.type === "OrbitControls") {
      const controls = new OrbitControls(camera, this.renderer.domElement);
      controls.enableDamping = spec.enableDamping ?? true;
      controls.dampingFactor = spec.dampingFactor ?? 0.05;
      controls.enableZoom = spec.enableZoom ?? true;
      // 2D orthographic views default to pan/zoom without rotation.
      controls.enableRotate = camera.isOrthographicCamera
        ? spec.enableRotate ?? false
        : spec.enableRotate ?? true;
      controls.enablePan = spec.enablePan ?? true;
      controls.autoRotate = spec.autoRotate ?? false;
      controls.autoRotateSpeed = spec.autoRotateSpeed ?? 2.0;
      controls.screenSpacePanning = spec.screenSpacePanning ?? true;
      this.controls = controls;
    } else if (spec.type === "TrackballControls") {
      this.controls = new TrackballControls(camera, this.renderer.domElement);
    }
    if (!this.controls) return;
    this.controlsUuid = spec.uuid;

    // A different controls object owns the latch now: its spec target
    // must win over any previous interactive target.
    if (spec.uuid !== this.world.latchUuid) {
      this.world.hasControlsTarget = false;
      this.world.latchUuid = spec.uuid;
    }

    if (this.world.hasControlsTarget) {
      this.controls.target.copy(this.world.controlsTarget);
    } else {
      if (Array.isArray(spec.target)) this.controls.target.set(...spec.target);
      this.world.controlsTarget.copy(this.controls.target);
      this.world.hasControlsTarget = true;
    }

    this.controls.addEventListener("change", () => {
      this.world.controlsTarget.copy(this.controls.target);
      this.scheduleCameraSync();
    });
    this.controls.addEventListener("end", () => this.syncCameraNow());
  }

  applyControlsProps(uuid, props) {
    if (!this.controls || uuid !== this.controlsUuid) return;
    if ("target" in props && Array.isArray(props.target)) {
      this.controls.target.set(...props.target);
    }
    for (const key of [
      "enableDamping",
      "dampingFactor",
      "enableZoom",
      "enableRotate",
      "enablePan",
      "autoRotate",
      "autoRotateSpeed",
      "screenSpacePanning",
    ]) {
      if (key in props) this.controls[key] = props[key];
    }
  }

  // -- camera pose sync-back ---------------------------------------------

  scheduleCameraSync() {
    if (this.cameraSyncTimeout) return;
    this.cameraSyncTimeout = setTimeout(() => {
      this.cameraSyncTimeout = null;
      this.syncCameraNow();
    }, CAMERA_SYNC_THROTTLE_MS);
  }

  syncCameraNow() {
    const camera = this.world.camera;
    if (!camera) return;
    const state = {
      position: camera.position.toArray(),
      rotation: [camera.rotation.x, camera.rotation.y, camera.rotation.z],
      zoom: camera.zoom,
      epoch: this.world.lastEpoch,
    };
    if (this.controls?.target) state.target = this.controls.target.toArray();
    this.model.set("_camera_state", state);
    this.model.save_changes();
  }

  // -- frame loop / sizing ------------------------------------------------

  animate() {
    this.animationId = requestAnimationFrame(this._animate);
    const { scene, camera } = this.world;
    if (this.controls) {
      // Follow target changes made through other views.
      if (
        this.world.hasControlsTarget &&
        !this.controls.target.equals(this.world.controlsTarget)
      ) {
        this.controls.target.copy(this.world.controlsTarget);
      }
      this.controls.update();
    }
    if (scene && camera) this.renderer.render(scene, camera);
  }

  resize() {
    this.width = this.model.get("width");
    this.height = this.model.get("height");
    this.renderer.setSize(this.width, this.height);
    const camera = this.world.camera;
    if (camera && camera.isPerspectiveCamera) {
      camera.aspect = this.width / this.height;
      camera.updateProjectionMatrix();
    }
    // OrthographicCamera bounds are managed by the Python side.
    this.applyLineResolution();
  }

  applyLineResolution() {
    const scene = this.world.scene;
    if (!scene) return;
    scene.traverse((obj) => {
      if (obj.material && obj.material.isLineMaterial) {
        obj.material.resolution.set(this.width, this.height);
      }
    });
  }

  // -- picking ------------------------------------------------------------

  getMousePosition(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  }

  pickableObjects() {
    const objects = [];
    this.world.scene?.traverse((obj) => {
      if (obj.isMesh || obj.isPoints || obj.isLine || obj.isSprite) {
        objects.push(obj);
      }
    });
    return objects;
  }

  performRaycast(event) {
    const { scene, camera } = this.world;
    if (!scene || !camera) return null;
    this.getMousePosition(event);
    this.raycaster.setFromCamera(this.mouse, camera);
    this.raycaster.params.Line.threshold = 1;
    this.raycaster.params.Points.threshold = 1;
    const intersects = this.raycaster.intersectObjects(this.pickableObjects(), false);
    if (intersects.length === 0) return null;
    const hit = intersects[0];
    return {
      name: hit.object.name || "",
      uuid: hit.object.userData.uuid || hit.object.uuid,
      type: hit.object.type,
      point: hit.point ? [hit.point.x, hit.point.y, hit.point.z] : null,
      distance: hit.distance,
      faceIndex: hit.faceIndex ?? null,
      index: hit.index ?? null, // for points
      instanceId: hit.instanceId ?? null,
    };
  }

  performPickerRaycast(event, picker) {
    const { scene, camera } = this.world;
    if (!scene || !camera) return null;
    this.getMousePosition(event);
    this.raycaster.setFromCamera(this.mouse, camera);
    // Per-picker raycast tolerances (pythreejs Picker surface).
    this.raycaster.params.Line.threshold = picker.lineThreshold ?? 1;
    this.raycaster.params.Points.threshold = picker.pointThreshold ?? 1;

    let pickable = [];
    if (picker.controlling) {
      scene.traverse((obj) => {
        const objUuid = obj.userData.uuid || obj.uuid;
        if (objUuid === picker.controlling) pickable.push(obj);
      });
    } else {
      pickable = this.pickableObjects();
    }
    if (pickable.length === 0) {
      return { picker_uuid: picker.uuid, point: null };
    }

    const intersects = this.raycaster.intersectObjects(pickable, true);
    if (intersects.length === 0) {
      return { picker_uuid: picker.uuid, point: null };
    }
    const hit = intersects[0];
    return {
      picker_uuid: picker.uuid,
      point: hit.point ? [hit.point.x, hit.point.y, hit.point.z] : null,
      distance: hit.distance,
      faceIndex: hit.faceIndex ?? null,
      object_uuid: hit.object.userData.uuid || hit.object.uuid,
      modifiers: getModifiers(event),
    };
  }

  handlePickerEvent(event, eventType) {
    for (const picker of this.world.pickers) {
      if (picker.event === eventType) {
        const result = this.performPickerRaycast(event, picker);
        if (result) {
          this.model.set("_picker_event", result);
          this.model.save_changes();
        }
      }
    }
  }

  onClick(event) {
    this.handlePickerEvent(event, "click");
    if (!this.model.get("enable_picking")) return;
    const hitInfo = this.performRaycast(event);
    this.model.set("_click_info", hitInfo || {});
    this.model.save_changes();
  }

  onDblClick(event) {
    this.handlePickerEvent(event, "dblclick");
    if (!this.model.get("enable_picking")) return;
    const hitInfo = this.performRaycast(event);
    if (hitInfo) hitInfo.doubleClick = true;
    this.model.set("_click_info", hitInfo || {});
    this.model.save_changes();
  }

  onMouseMove(event) {
    if (!this.pickerMoveTimeout && this.world.pickers.length > 0) {
      this.pickerMoveTimeout = setTimeout(() => {
        this.pickerMoveTimeout = null;
        this.handlePickerEvent(event, "mousemove");
      }, PICKER_THROTTLE_MS);
    }

    // Hover raycasting is opt-in: it traverses the scene on every throttled
    // mousemove, which is expensive for large point clouds.
    if (!this.model.get("enable_picking") || !this.model.get("enable_hover")) {
      return;
    }
    if (this.hoverTimeout) return;
    this.hoverTimeout = setTimeout(() => {
      this.hoverTimeout = null;
      const hitInfo = this.performRaycast(event);
      const current = this.model.get("_hover_info") || {};
      const newUuid = hitInfo ? hitInfo.uuid : null;
      const oldUuid = current.uuid || null;
      if (newUuid !== oldUuid) {
        this.model.set("_hover_info", hitInfo || {});
        this.model.save_changes();
      }
    }, HOVER_THROTTLE_MS);
  }

  // -- teardown -----------------------------------------------------------

  dispose() {
    if (this.animationId) cancelAnimationFrame(this.animationId);
    if (this.hoverTimeout) clearTimeout(this.hoverTimeout);
    if (this.pickerMoveTimeout) clearTimeout(this.pickerMoveTimeout);
    if (this.cameraSyncTimeout) clearTimeout(this.cameraSyncTimeout);
    const dom = this.renderer.domElement;
    dom.removeEventListener("click", this._onClick);
    dom.removeEventListener("dblclick", this._onDblClick);
    dom.removeEventListener("mousedown", this._onMouseDown);
    dom.removeEventListener("mouseup", this._onMouseUp);
    dom.removeEventListener("mousemove", this._onMouseMove);
    this.model.off("change:width", this._onResize);
    this.model.off("change:height", this._onResize);
    this.controls?.dispose();
    this.renderer.dispose();
    this.container.remove();
    this.world.views.delete(this);
  }
}

function getModifiers(event) {
  const mods = [];
  if (event.shiftKey) mods.push("shift");
  if (event.ctrlKey) mods.push("ctrl");
  if (event.altKey) mods.push("alt");
  if (event.metaKey) mods.push("meta");
  return mods;
}

// ---------------------------------------------------------------------------
// anywidget entry points
// ---------------------------------------------------------------------------

export default {
  initialize({ model }) {
    const world = new World(model);
    model._anythreejsWorld = world;
    return () => {
      world.dispose();
      delete model._anythreejsWorld;
    };
  },

  render({ model, el }) {
    let world = model._anythreejsWorld;
    if (!world) {
      // Environments that skip initialize (older anywidget) still work.
      world = new World(model);
      model._anythreejsWorld = world;
    }
    const view = new View(world, model, el);
    return () => view.dispose();
  },
};
