/**
 * anythreejs - Renderer widget
 *
 * Three.js rendering using anywidget
 */

import * as THREE from "https://esm.sh/three@0.182.0";
import { OrbitControls } from "https://esm.sh/three@0.182.0/addons/controls/OrbitControls.js";
import { TrackballControls } from "https://esm.sh/three@0.182.0/addons/controls/TrackballControls.js";
import { Line2 } from "https://esm.sh/three@0.182.0/addons/lines/Line2.js";
import { LineGeometry } from "https://esm.sh/three@0.182.0/addons/lines/LineGeometry.js";
import { LineMaterial } from "https://esm.sh/three@0.182.0/addons/lines/LineMaterial.js";

// Debug logging flag - set to true to enable debug logs
const DEBUG = false;
const debug = (...args) => DEBUG && console.log("[anythreejs]", ...args);

// Performance constants
const PICKER_THROTTLE_MS = 16; // ~60fps for picker mousemove events
const HOVER_THROTTLE_MS = 50;  // 50ms throttle for hover detection

/**
 * Global store for shared Three.js objects across multiple views of the same widget.
 * This is the key to pythreejs-like behavior - all views share the SAME Three.js
 * scene, camera, and controls objects, so moving the camera in one view instantly
 * moves it in all other views.
 */
const sharedObjects = new Map();

/**
 * Get or create shared Three.js objects for a model.
 * Returns { scene, camera, pickers, viewCount, needsRebuild, controlsTarget }
 * Note: controls are NOT shared - each view has its own controls instance
 * that attaches to its own DOM element, but they all control the shared camera.
 * The controlsTarget is shared so all controls orbit around the same point.
 */
function getSharedObjects(modelId) {
  if (!sharedObjects.has(modelId)) {
    sharedObjects.set(modelId, {
      scene: null,
      camera: null,
      pickers: [],
      viewCount: 0,
      needsRebuild: true,
      controlsTarget: null,  // Shared target for all controls instances
    });
  }
  return sharedObjects.get(modelId);
}

/**
 * Clean up shared objects when no more views exist
 */
function releaseSharedObjects(modelId) {
  const shared = sharedObjects.get(modelId);
  if (shared) {
    shared.viewCount--;
    debug("Release shared objects, viewCount:", shared.viewCount);
    if (shared.viewCount <= 0) {
      // Clean up shared Three.js objects
      // Note: controls are per-view and disposed there, not here
      sharedObjects.delete(modelId);
      debug("Deleted shared objects for model:", modelId);
    }
  }
}

/**
 * Map of side strings to Three.js constants
 */
const SIDE_MAP = {
  FrontSide: THREE.FrontSide,
  BackSide: THREE.BackSide,
  DoubleSide: THREE.DoubleSide,
  front: THREE.FrontSide,
  back: THREE.BackSide,
  double: THREE.DoubleSide,
};

/**
 * Convert vertexColors value to boolean
 * Old pythreejs used 'VertexColors' string, new Three.js uses boolean
 */
function parseVertexColors(value) {
  if (value === 'VertexColors' || value === true) {
    return true;
  }
  return false;
}

/**
 * Helper to convert dtype string to TypedArray constructor
 */
function getTypedArrayConstructor(dtype) {
  if (!dtype) return Float32Array;

  const dtypeLower = dtype.toLowerCase();
  if (dtypeLower.includes('float32')) return Float32Array;
  if (dtypeLower.includes('float64')) return Float64Array;
  if (dtypeLower.includes('int32')) return Int32Array;
  if (dtypeLower.includes('uint32')) return Uint32Array;
  if (dtypeLower.includes('int16')) return Int16Array;
  if (dtypeLower.includes('uint16')) return Uint16Array;
  if (dtypeLower.includes('int8')) return Int8Array;
  if (dtypeLower.includes('uint8')) return Uint8Array;

  return Float32Array;
}

/**
 * Create a Three.js geometry from serialized data
 */
function createGeometry(data, buffers = {}) {
  if (!data) return null;

  switch (data.type) {
    case "BoxGeometry":
      return new THREE.BoxGeometry(
        data.width,
        data.height,
        data.depth,
        data.widthSegments,
        data.heightSegments,
        data.depthSegments
      );

    case "SphereGeometry":
      return new THREE.SphereGeometry(
        data.radius,
        data.widthSegments,
        data.heightSegments,
        data.phiStart,
        data.phiLength,
        data.thetaStart,
        data.thetaLength
      );

    case "PlaneGeometry":
      return new THREE.PlaneGeometry(
        data.width,
        data.height,
        data.widthSegments,
        data.heightSegments
      );

    case "CylinderGeometry":
      return new THREE.CylinderGeometry(
        data.radiusTop,
        data.radiusBottom,
        data.height,
        data.radialSegments,
        data.heightSegments,
        data.openEnded,
        data.thetaStart,
        data.thetaLength
      );

    case "BufferGeometry": {
      const geometry = new THREE.BufferGeometry();

      if (data.attributes) {
        for (const [name, attr] of Object.entries(data.attributes)) {
          let array;

          debug(`Processing attribute ${name}:`, attr);
          debug(`  - Has bufferRef: ${!!attr.bufferRef}`);
          debug(`  - Has array: ${!!attr.array}`);
          debug(`  - Buffers available: ${Object.keys(buffers).length}`);

          // Check if using binary buffer transfer
          if (attr.bufferRef && buffers[attr.bufferRef]) {
            debug(`  - Using binary buffer: ${attr.bufferRef}`);
            const buffer = buffers[attr.bufferRef];
            const TypedArrayConstructor = getTypedArrayConstructor(attr.dtype);
            array = new TypedArrayConstructor(buffer);
            debug(`  - Created ${TypedArrayConstructor.name} with length ${array.length}`);
          } else if (attr.bufferRef && !buffers[attr.bufferRef]) {
            debug(`  - WARNING: bufferRef ${attr.bufferRef} not found in buffers!`);
            debug(`  - Available buffers: ${Object.keys(buffers).join(', ')}`);
            // Try fallback to JSON array if available
            if (attr.array) {
              debug(`  - Falling back to JSON array`);
              array = attr.array;
              if (Array.isArray(array)) {
                array = new Float32Array(array);
              }
            }
          } else if (attr.array) {
            // Using JSON array
            debug(`  - Using JSON array with length ${attr.array.length}`);
            array = attr.array;
            if (Array.isArray(array)) {
              array = new Float32Array(array);
            }
          }

          if (array) {
            const itemSize = attr.itemSize || 3;
            geometry.setAttribute(
              name,
              new THREE.BufferAttribute(array, itemSize, attr.normalized)
            );
            debug(`  - setAttribute ${name} successful`);
          } else {
            debug(`  - ERROR: No array data available for attribute ${name}`);
          }
        }
      }

      if (data.index) {
        let indexArray;

        // Check if using binary buffer transfer
        if (data.index.bufferRef && buffers[data.index.bufferRef]) {
          const buffer = buffers[data.index.bufferRef];
          const TypedArrayConstructor = getTypedArrayConstructor(data.index.dtype);
          indexArray = new TypedArrayConstructor(buffer);
        } else if (data.index.bufferRef && !buffers[data.index.bufferRef]) {
          debug(`WARNING: index bufferRef ${data.index.bufferRef} not found!`);
          // Try fallback
          if (Array.isArray(data.index)) {
            indexArray = new Uint32Array(data.index);
          }
        } else {
          // Fallback to JSON array
          indexArray = data.index;
          if (Array.isArray(indexArray)) {
            indexArray = new Uint32Array(indexArray);
          }
        }

        if (indexArray) {
          geometry.setIndex(new THREE.BufferAttribute(indexArray, 1));
        }
      }

      // Compute normals if not provided
      if (!data.attributes?.normal && data.attributes?.position) {
        geometry.computeVertexNormals();
      }

      return geometry;
    }

    case "EdgesGeometry": {
      const sourceGeometry = data.geometry ? createGeometry(data.geometry, buffers) : null;
      if (sourceGeometry) {
        return new THREE.EdgesGeometry(sourceGeometry, data.thresholdAngle ?? 1);
      }
      return new THREE.BufferGeometry();
    }

    case "LineGeometry": {
      const geometry = new LineGeometry();
      if (data.positions) {
        // Flatten if needed (could be array of [x,y,z] or flat array)
        let positions = data.positions;
        if (Array.isArray(positions[0])) {
          positions = positions.flat();
        }
        geometry.setPositions(positions);
      }
      if (data.colors) {
        let colors = data.colors;
        if (Array.isArray(colors[0])) {
          colors = colors.flat();
        }
        geometry.setColors(colors);
      }
      return geometry;
    }

    default:
      console.warn(`Unknown geometry type: ${data.type}`);
      return new THREE.BoxGeometry(1, 1, 1);
  }
}

/**
 * Map of format strings to Three.js constants
 */
const FORMAT_MAP = {
  "RGBFormat": THREE.RGBFormat,
  "RGBAFormat": THREE.RGBAFormat,
  "RedFormat": THREE.RedFormat,
  "RGFormat": THREE.RGFormat,
  "AlphaFormat": THREE.AlphaFormat,
};

/**
 * Map of type strings to Three.js constants
 */
const TYPE_MAP = {
  "UnsignedByteType": THREE.UnsignedByteType,
  "ByteType": THREE.ByteType,
  "ShortType": THREE.ShortType,
  "UnsignedShortType": THREE.UnsignedShortType,
  "IntType": THREE.IntType,
  "UnsignedIntType": THREE.UnsignedIntType,
  "FloatType": THREE.FloatType,
  "HalfFloatType": THREE.HalfFloatType,
};

/**
 * Map of wrapping strings to Three.js constants
 */
const WRAP_MAP = {
  "ClampToEdgeWrapping": THREE.ClampToEdgeWrapping,
  "RepeatWrapping": THREE.RepeatWrapping,
  "MirroredRepeatWrapping": THREE.MirroredRepeatWrapping,
};

/**
 * Map of filter strings to Three.js constants
 */
const FILTER_MAP = {
  "NearestFilter": THREE.NearestFilter,
  "LinearFilter": THREE.LinearFilter,
  "NearestMipmapNearestFilter": THREE.NearestMipmapNearestFilter,
  "NearestMipmapLinearFilter": THREE.NearestMipmapLinearFilter,
  "LinearMipmapNearestFilter": THREE.LinearMipmapNearestFilter,
  "LinearMipmapLinearFilter": THREE.LinearMipmapLinearFilter,
};

/**
 * Create a Three.js texture from serialized data
 */
function createTexture(data, buffers = {}) {
  if (!data) return null;

  debug("createTexture called with:", data.type, "format:", data.format, "dtype:", data.dtype);

  switch (data.type) {
    case "DataTexture": {
      // Get format and type
      let format = FORMAT_MAP[data.format] ?? THREE.RGBAFormat;
      const dtype = TYPE_MAP[data.dtype] ?? THREE.UnsignedByteType;

      debug("DataTexture: format=", format, "dtype=", dtype, "width=", data.width, "height=", data.height, "data length=", data.data?.length);

      // Convert data to appropriate typed array
      let array;
      let width = data.width;
      let height = data.height;

      // Check if using binary buffer transfer
      if (data.bufferRef && buffers[data.bufferRef]) {
        const buffer = buffers[data.bufferRef];
        const TypedArrayConstructor = getTypedArrayConstructor(data.dataType);
        array = new TypedArrayConstructor(buffer);
      } else if (data.data) {
        // Fallback to JSON array
        array = data.data;
        if (Array.isArray(array)) {
          // Determine array type based on dtype
          if (dtype === THREE.FloatType) {
            array = new Float32Array(array);
          } else if (dtype === THREE.HalfFloatType) {
            array = new Float32Array(array); // Three.js will convert
          } else if (dtype === THREE.UnsignedByteType) {
            array = new Uint8Array(array);
          } else {
            array = new Float32Array(array);
          }
        }
      }

      // Infer dimensions if not provided
      if (!width || !height) {
        // Assume square texture if dimensions not provided
        const channels = format === THREE.RGBAFormat ? 4 : (format === THREE.RGBFormat ? 3 : 1);
        const pixelCount = array.length / channels;
        width = height = Math.sqrt(pixelCount);
        debug("DataTexture: inferred dimensions:", width, "x", height);
      }

      // RGBFormat is deprecated in newer Three.js - convert RGB to RGBA
      if (format === THREE.RGBFormat || data.format === "RGBFormat") {
        debug("Converting RGB to RGBA format");
        const channels = 3;
        const pixelCount = array.length / channels;
        const rgbaArray = dtype === THREE.FloatType ? new Float32Array(pixelCount * 4) : new Uint8Array(pixelCount * 4);
        for (let i = 0; i < pixelCount; i++) {
          rgbaArray[i * 4 + 0] = array[i * 3 + 0]; // R
          rgbaArray[i * 4 + 1] = array[i * 3 + 1]; // G
          rgbaArray[i * 4 + 2] = array[i * 3 + 2]; // B
          rgbaArray[i * 4 + 3] = dtype === THREE.FloatType ? 1.0 : 255; // A
        }
        array = rgbaArray;
        format = THREE.RGBAFormat;
      }

      debug("Creating THREE.DataTexture with array length:", array.length, "width:", width, "height:", height, "format:", format);

      const texture = new THREE.DataTexture(array, width, height, format, dtype);
      texture.wrapS = WRAP_MAP[data.wrapS] ?? THREE.ClampToEdgeWrapping;
      texture.wrapT = WRAP_MAP[data.wrapT] ?? THREE.ClampToEdgeWrapping;
      texture.magFilter = FILTER_MAP[data.magFilter] ?? THREE.LinearFilter;
      texture.minFilter = FILTER_MAP[data.minFilter] ?? THREE.LinearFilter;

      // Set colorspace - use Linear for float textures, sRGB for byte textures
      if (dtype === THREE.UnsignedByteType) {
        texture.colorSpace = THREE.SRGBColorSpace;
      } else {
        texture.colorSpace = THREE.LinearSRGBColorSpace;
      }

      texture.needsUpdate = true;

      // Don't flip Y - the data comes in correct orientation from numpy
      texture.flipY = false;

      debug("DataTexture created successfully:", texture);

      return texture;
    }

    case "TextTexture": {
      // Create canvas-based text texture
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      const text = data.string || "";
      const fontSize = data.size || 100;
      const fontFace = data.fontFace || 'Arial';

      ctx.font = `${fontSize}px ${fontFace}`;
      const metrics = ctx.measureText(text);

      const width = metrics.width || fontSize;
      const height = fontSize * 1.2;

      canvas.width = width;
      canvas.height = height;

      ctx.font = `${fontSize}px ${fontFace}`;
      ctx.fillStyle = data.color || 'black';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, width / 2, height / 2);

      const texture = new THREE.CanvasTexture(canvas);
      texture.needsUpdate = true;
      return texture;
    }

    default:
      console.warn(`Unknown texture type: ${data.type}`);
      return null;
  }
}

/**
 * Create a Three.js material from serialized data
 */
function createMaterial(data, buffers = {}) {
  if (!data) return new THREE.MeshBasicMaterial();

  const side = SIDE_MAP[data.side] || THREE.FrontSide;

  const baseProps = {
    color: new THREE.Color(data.color || "#ffffff"),
    opacity: data.opacity ?? 1,
    transparent: data.transparent ?? false,
    visible: data.visible ?? true,
    side: side,
    depthTest: data.depthTest ?? true,
    depthWrite: data.depthWrite ?? true,
  };

  switch (data.type) {
    case "MeshBasicMaterial": {
      debug("Creating MeshBasicMaterial, has map:", !!data.map);
      const mat = new THREE.MeshBasicMaterial({
        ...baseProps,
        wireframe: data.wireframe ?? false,
        vertexColors: parseVertexColors(data.vertexColors),
      });
      // Handle texture map
      if (data.map) {
        debug("MeshBasicMaterial: creating texture from map");
        const texture = createTexture(data.map, buffers);
        if (texture) {
          mat.map = texture;
          mat.needsUpdate = true;
          debug("MeshBasicMaterial: map texture set successfully");
        } else {
          console.warn("MeshBasicMaterial: createTexture returned null");
        }
      }
      return mat;
    }

    case "MeshStandardMaterial":
      return new THREE.MeshStandardMaterial({
        ...baseProps,
        roughness: data.roughness ?? 0.5,
        metalness: data.metalness ?? 0.5,
        wireframe: data.wireframe ?? false,
        flatShading: data.flatShading ?? false,
        vertexColors: parseVertexColors(data.vertexColors),
        emissive: new THREE.Color(data.emissive || "#000000"),
        emissiveIntensity: data.emissiveIntensity ?? 1.0,
      });

    case "MeshPhongMaterial":
      return new THREE.MeshPhongMaterial({
        ...baseProps,
        shininess: data.shininess ?? 30,
        specular: new THREE.Color(data.specular || "#111111"),
        wireframe: data.wireframe ?? false,
        flatShading: data.flatShading ?? false,
        vertexColors: parseVertexColors(data.vertexColors),
      });

    case "MeshLambertMaterial":
      return new THREE.MeshLambertMaterial({
        ...baseProps,
        wireframe: data.wireframe ?? false,
        vertexColors: parseVertexColors(data.vertexColors),
      });

    case "PointsMaterial":
      return new THREE.PointsMaterial({
        color: new THREE.Color(data.color || "#ffffff"),
        size: data.size ?? 1,
        sizeAttenuation: data.sizeAttenuation ?? true,
        vertexColors: parseVertexColors(data.vertexColors),
        opacity: data.opacity ?? 1,
        transparent: data.transparent ?? false,
        depthTest: data.depthTest ?? true,
        depthWrite: data.depthWrite ?? true,
      });

    case "LineBasicMaterial":
      return new THREE.LineBasicMaterial({
        color: new THREE.Color(data.color || "#ffffff"),
        linewidth: data.linewidth ?? 1,
        vertexColors: parseVertexColors(data.vertexColors),
        opacity: data.opacity ?? 1,
        transparent: data.transparent ?? false,
      });

    case "LineDashedMaterial":
      return new THREE.LineDashedMaterial({
        color: new THREE.Color(data.color || "#ffffff"),
        linewidth: data.linewidth ?? 1,
        dashSize: data.dashSize ?? 3,
        gapSize: data.gapSize ?? 1,
        vertexColors: parseVertexColors(data.vertexColors),
        opacity: data.opacity ?? 1,
        transparent: data.transparent ?? false,
      });

    case "LineMaterial": {
      const mat = new LineMaterial({
        color: new THREE.Color(data.color || "#ffffff").getHex(),
        linewidth: data.linewidth ?? 1,
        vertexColors: parseVertexColors(data.vertexColors),
        opacity: data.opacity ?? 1,
        transparent: data.transparent ?? false,
        dashed: data.dashed ?? false,
        dashScale: data.dashScale ?? 1,
        dashSize: data.dashSize ?? 1,
        gapSize: data.gapSize ?? 1,
      });
      // LineMaterial needs resolution to be set
      mat.resolution.set(window.innerWidth, window.innerHeight);
      return mat;
    }

    default:
      console.warn(`Unknown material type: ${data.type}`);
      return new THREE.MeshBasicMaterial(baseProps);
  }
}

/**
 * Create a Three.js light from serialized data
 */
function createLight(data) {
  let light;

  switch (data.type) {
    case "AmbientLight":
      light = new THREE.AmbientLight(
        new THREE.Color(data.color || "#ffffff"),
        data.intensity ?? 1
      );
      break;

    case "DirectionalLight":
      light = new THREE.DirectionalLight(
        new THREE.Color(data.color || "#ffffff"),
        data.intensity ?? 1
      );
      light.castShadow = data.castShadow ?? false;
      if (data.target) {
        light.target.position.set(...data.target);
      }
      break;

    case "PointLight":
      light = new THREE.PointLight(
        new THREE.Color(data.color || "#ffffff"),
        data.intensity ?? 1,
        data.distance ?? 0,
        data.decay ?? 2
      );
      light.castShadow = data.castShadow ?? false;
      break;

    case "HemisphereLight":
      light = new THREE.HemisphereLight(
        new THREE.Color(data.skyColor || "#ffffff"),
        new THREE.Color(data.groundColor || "#444444"),
        data.intensity ?? 1
      );
      break;

    case "SpotLight":
      light = new THREE.SpotLight(
        new THREE.Color(data.color || "#ffffff"),
        data.intensity ?? 1,
        data.distance ?? 0,
        data.angle ?? Math.PI / 6,
        data.penumbra ?? 0,
        data.decay ?? 2
      );
      light.castShadow = data.castShadow ?? false;
      if (data.target) {
        light.target.position.set(...data.target);
      }
      break;

    default:
      console.warn(`Unknown light type: ${data.type}`);
      return null;
  }

  applyTransform(light, data);
  light.name = data.name || "";
  light.visible = data.visible !== false;
  light.userData.uuid = data.uuid;

  return light;
}

/**
 * Create a helper object
 */
function createHelper(data) {
  let helper;

  switch (data.type) {
    case "GridHelper":
      helper = new THREE.GridHelper(
        data.size ?? 10,
        data.divisions ?? 10,
        new THREE.Color(data.colorCenterLine || "#444444"),
        new THREE.Color(data.colorGrid || "#888888")
      );
      break;

    case "AxesHelper":
      helper = new THREE.AxesHelper(data.size ?? 1);
      break;

    default:
      console.warn(`Unknown helper type: ${data.type}`);
      return null;
  }

  applyTransform(helper, data);
  helper.name = data.name || "";
  helper.visible = data.visible !== false;
  helper.userData.uuid = data.uuid;

  return helper;
}

/**
 * Apply position, rotation, scale to an object
 */
function applyTransform(obj, data) {
  if (data.position) {
    obj.position.set(...data.position);
  }
  if (data.rotation) {
    obj.rotation.set(...data.rotation);
  }
  if (data.scale) {
    obj.scale.set(...data.scale);
  }
}

/**
 * Create a Three.js object from serialized data
 */
function createObject(data, buffers = {}) {
  if (!data) return null;

  let obj;

  switch (data.type) {
    case "Mesh": {
      const geometry = createGeometry(data.geometry, buffers);
      const material = createMaterial(data.material, buffers);
      obj = new THREE.Mesh(geometry, material);
      break;
    }

    case "Points": {
      const geometry = createGeometry(data.geometry, buffers) || new THREE.BufferGeometry();
      const material = createMaterial(data.material, buffers);
      obj = new THREE.Points(geometry, material);
      break;
    }

    case "Line": {
      const geometry = createGeometry(data.geometry, buffers) || new THREE.BufferGeometry();
      const material = createMaterial(data.material, buffers);
      obj = new THREE.Line(geometry, material);
      break;
    }

    case "LineSegments": {
      const geometry = createGeometry(data.geometry, buffers) || new THREE.BufferGeometry();
      const material = createMaterial(data.material, buffers);
      obj = new THREE.LineSegments(geometry, material);
      break;
    }

    case "Line2": {
      const geometry = createGeometry(data.geometry, buffers) || new LineGeometry();
      const material = createMaterial(data.material, buffers) || new LineMaterial({ color: 0xffffff });
      obj = new Line2(geometry, material);
      obj.computeLineDistances();
      break;
    }

    case "Sprite": {
      let material;
      if (data.material) {
        const matData = data.material;
        if (matData.map && matData.map.string) {
          // Create canvas-based text texture
          const canvas = document.createElement('canvas');
          const ctx = canvas.getContext('2d');
          const text = matData.map.string;
          const fontSize = matData.map.size || 100;
          const fontFace = matData.map.fontFace || 'Arial';

          ctx.font = `${fontSize}px ${fontFace}`;
          const metrics = ctx.measureText(text);

          // Make canvas square if requested
          const width = matData.map.squareTexture
            ? Math.max(metrics.width, fontSize)
            : metrics.width;
          const height = matData.map.squareTexture ? width : fontSize * 1.2;

          canvas.width = width;
          canvas.height = height;

          ctx.font = `${fontSize}px ${fontFace}`;
          ctx.fillStyle = matData.map.color || 'black';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(text, width / 2, height / 2);

          const texture = new THREE.CanvasTexture(canvas);
          material = new THREE.SpriteMaterial({
            map: texture,
            transparent: matData.transparent ?? true,
            opacity: matData.opacity ?? 1,
          });
        } else {
          material = new THREE.SpriteMaterial({
            color: new THREE.Color(matData.color || '#ffffff'),
            transparent: matData.transparent ?? false,
            opacity: matData.opacity ?? 1,
          });
        }
      } else {
        material = new THREE.SpriteMaterial();
      }
      obj = new THREE.Sprite(material);
      break;
    }

    case "Group": {
      obj = new THREE.Group();
      if (data.children) {
        for (const childData of data.children) {
          const child = createObject(childData, buffers);
          if (child) {
            obj.add(child);
          }
        }
      }
      break;
    }

    case "AmbientLight":
    case "DirectionalLight":
    case "PointLight":
    case "HemisphereLight":
    case "SpotLight":
      return createLight(data);

    case "GridHelper":
    case "AxesHelper":
      return createHelper(data);

    case "PerspectiveCamera":
    case "OrthographicCamera":
      // Cameras are usually handled separately, but if present as children
      // build via createCamera to avoid warnings.
      return createCamera(data, 1);

    default:
      console.warn(`Unknown object type: ${data.type}`);
      return null;
  }

  applyTransform(obj, data);
  obj.name = data.name || "";
  obj.visible = data.visible !== false;
  obj.userData.uuid = data.uuid;

  // Process children for non-Group objects too
  if (data.children && data.type !== "Group") {
    for (const childData of data.children) {
      const child = createObject(childData, buffers);
      if (child) {
        obj.add(child);
      }
    }
  }

  return obj;
}

/**
 * Create a camera from serialized data
 */
function createCamera(data, aspect) {
  if (!data) {
    return new THREE.PerspectiveCamera(50, aspect, 0.1, 2000);
  }

  let camera;

  switch (data.type) {
    case "PerspectiveCamera":
      camera = new THREE.PerspectiveCamera(
        data.fov ?? 50,
        data.aspect ?? aspect,
        data.near ?? 0.1,
        data.far ?? 2000
      );
      break;

    case "OrthographicCamera": {
      // Use the exact values provided from Python
      camera = new THREE.OrthographicCamera(
        data.left ?? -1,
        data.right ?? 1,
        data.top ?? 1,
        data.bottom ?? -1,
        data.near ?? 0.1,
        data.far ?? 2000
      );
      camera.zoom = data.zoom ?? 1;
      camera.updateProjectionMatrix();
      break;
    }

    default:
      console.warn(`Unknown camera type: ${data.type}`);
      camera = new THREE.PerspectiveCamera(50, aspect, 0.1, 2000);
  }

  applyTransform(camera, data);

  if (data.lookAt) {
    camera.lookAt(new THREE.Vector3(...data.lookAt));
  }

  return camera;
}

/**
 * Build scene from serialized data
 */
function buildScene(sceneData, buffers = {}) {
  const scene = new THREE.Scene();

  if (sceneData.background) {
    scene.background = new THREE.Color(sceneData.background);
  }

  if (sceneData.children) {
    for (const childData of sceneData.children) {
      const child = createObject(childData, buffers);
      if (child) {
        scene.add(child);
      }
    }
  }

  return scene;
}

/**
 * Main render function called by anywidget
 */
function render({ model, el }) {
  // Get the model ID for shared object lookup
  const modelId = model.model_id;
  const shared = getSharedObjects(modelId);
  shared.viewCount++;
  debug("New view for model:", modelId, "viewCount:", shared.viewCount);

  // Create container
  const container = document.createElement("div");
  container.style.width = "100%";
  container.style.height = "100%";
  container.style.position = "relative";
  el.appendChild(container);

  // Get initial dimensions
  let width = model.get("width");
  let height = model.get("height");

  // Create renderer (each view needs its own WebGL renderer)
  const renderer = new THREE.WebGLRenderer({
    antialias: model.get("antialias"),
    alpha: model.get("alpha"),
  });
  renderer.setSize(width, height);
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  // Color space settings for proper color rendering
  // Use SRGBColorSpace for correct gamma correction
  // This ensures matplotlib colors (which are in sRGB) display correctly
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  container.appendChild(renderer.domElement);

  // Local state for this view
  let controls = null;  // Each view has its own controls instance
  let animationId = null;
  let buffers = {}; // Binary buffers from Python

  // Reference to shared objects (will be populated by rebuild)
  let scene = shared.scene;
  let camera = shared.camera;
  let pickers = shared.pickers;

  /**
   * Extract binary buffers from widget state
   * In anywidget, buffers can be accessed through widget_manager
   */
  function updateBuffers() {
    try {
      // anywidget provides buffers through the widget manager's state
      if (model.widget_manager && model.widget_manager.get_state) {
        const state = model.widget_manager.get_state(model);
        if (state && state.buffers) {
          buffers = {};
          for (const [key, value] of Object.entries(state.buffers)) {
            // Extract the DataView from buffer data
            if (value && value.data) {
              buffers[key] = value.data.buffer;
            } else {
              buffers[key] = value;
            }
          }
          debug("Updated buffers:", Object.keys(buffers));
          return;
        }
      }

      // Fallback: buffers might be directly in model attributes
      // This is a simplified approach that may need adjustment
      debug("No buffers found in widget state");
      buffers = {};
    } catch (e) {
      debug("Error updating buffers:", e);
      buffers = {};
    }
  }

  // Update buffers initially
  updateBuffers();

  // Raycaster for picking
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();

  /**
   * Update resolution for all LineMaterial instances in the scene
   */
  function updateLineMaterialResolutions() {
    if (!scene) return;
    scene.traverse((obj) => {
      if (obj.material && obj.material.isLineMaterial) {
        obj.material.resolution.set(width, height);
      }
    });
  }

  /**
   * Update only the scene, preserving camera position and controls
   */
  function updateScene() {
    const sceneData = model.get("_scene_data");

    // Save current camera state from shared camera
    let savedCameraPosition = null;
    let savedCameraRotation = null;
    let savedControlsTarget = null;

    if (shared.camera) {
      savedCameraPosition = shared.camera.position.clone();
      savedCameraRotation = shared.camera.rotation.clone();
    }
    if (controls && controls.target) {
      savedControlsTarget = controls.target.clone();
    }

    // Rebuild scene (shared across all views)
    if (sceneData && Object.keys(sceneData).length > 0) {
      shared.scene = buildScene(sceneData, buffers);
    } else {
      shared.scene = new THREE.Scene();
      shared.scene.background = new THREE.Color("#000000");
    }
    scene = shared.scene;

    // Add camera back to scene
    if (shared.camera) {
      scene.add(shared.camera);

      // Restore camera state
      if (savedCameraPosition) {
        shared.camera.position.copy(savedCameraPosition);
      }
      if (savedCameraRotation) {
        shared.camera.rotation.copy(savedCameraRotation);
      }
    }

    // Restore controls target
    if (controls && savedControlsTarget) {
      controls.target.copy(savedControlsTarget);
    }

    // Update LineMaterial resolutions
    updateLineMaterialResolutions();
  }

  /**
   * Build/rebuild shared scene and camera from model data.
   * Scene and camera are shared across all views of the same widget.
   * Each view creates its own controls instance that controls the shared camera.
   */
  function rebuild() {
    const sceneData = model.get("_scene_data");
    const cameraData = model.get("_camera_data");
    const controlsData = model.get("_controls_data");

    const aspect = width / height;

    // Check if we need to build shared objects (first view or data changed)
    const isFirstView = shared.scene === null;

    if (isFirstView || shared.needsRebuild) {
      debug("Building shared scene and camera (first view or rebuild needed)");

      // Build scene (shared)
      if (sceneData && Object.keys(sceneData).length > 0) {
        shared.scene = buildScene(sceneData, buffers);
      } else {
        shared.scene = new THREE.Scene();
        shared.scene.background = new THREE.Color("#000000");
      }

      // Build camera (shared)
      shared.camera = createCamera(cameraData, aspect);

      // Add camera to scene (pythreejs does this)
      shared.scene.add(shared.camera);

      // Store pickers (shared)
      shared.pickers = [];
      if (controlsData && controlsData.length > 0) {
        for (const ctrlData of controlsData) {
          if (ctrlData.type === "Picker") {
            shared.pickers.push({
              uuid: ctrlData.uuid,
              event: ctrlData.event || "click",
              controlling: ctrlData.controlling,
              all: ctrlData.all ?? false,
            });
            debug("Registered picker:", ctrlData.uuid, "event:", ctrlData.event, "controlling:", ctrlData.controlling);
          }
        }
      }

      shared.needsRebuild = false;
    } else {
      debug("Reusing existing shared scene and camera");
    }

    // Update local references to shared objects
    scene = shared.scene;
    camera = shared.camera;
    pickers = shared.pickers;

    // Dispose of old controls for this view
    if (controls) {
      controls.dispose();
      controls = null;
    }

    // Create controls for THIS view (each view needs its own controls instance
    // because controls attach to a specific DOM element, but they all control
    // the SAME shared camera - this is how pythreejs achieves instant sync)
    if (controlsData && controlsData.length > 0) {
      for (const ctrlData of controlsData) {
        if (ctrlData.type === "OrbitControls") {
          // Create OrbitControls attached to this view's renderer, but controlling shared camera
          controls = new OrbitControls(camera, renderer.domElement);
          controls.enableDamping = ctrlData.enableDamping ?? true;
          controls.dampingFactor = ctrlData.dampingFactor ?? 0.05;
          controls.enableZoom = ctrlData.enableZoom ?? true;
          controls.enableRotate = ctrlData.enableRotate ?? true;
          controls.enablePan = ctrlData.enablePan ?? true;
          controls.autoRotate = ctrlData.autoRotate ?? false;
          controls.autoRotateSpeed = ctrlData.autoRotateSpeed ?? 2.0;

          // Enable screen space panning (important for 2D orthographic views)
          controls.screenSpacePanning = ctrlData.screenSpacePanning ?? true;

          // Default mouse buttons: LEFT=rotate, MIDDLE=dolly, RIGHT=pan
          // For orthographic 2D, disable rotation by default but keep pan on right-click
          if (camera.isOrthographicCamera) {
            controls.enableRotate = ctrlData.enableRotate ?? false;
          }

          debug("OrbitControls created for view, controlling shared camera");

          // Use shared target if it exists (from another view), otherwise initialize from data
          if (shared.controlsTarget) {
            controls.target.copy(shared.controlsTarget);
          } else if (ctrlData.target) {
            controls.target.set(...ctrlData.target);
            // Store as shared target
            shared.controlsTarget = controls.target.clone();
          } else {
            shared.controlsTarget = controls.target.clone();
          }

          // Sync target to shared state when user interacts
          controls.addEventListener("change", () => {
            if (shared.controlsTarget) {
              shared.controlsTarget.copy(controls.target);
            }
          });

        } else if (ctrlData.type === "TrackballControls") {
          controls = new TrackballControls(camera, renderer.domElement);

          // Use shared target if it exists
          if (shared.controlsTarget) {
            controls.target.copy(shared.controlsTarget);
          } else if (ctrlData.target) {
            controls.target.set(...ctrlData.target);
            shared.controlsTarget = controls.target.clone();
          } else {
            shared.controlsTarget = controls.target.clone();
          }

          // Sync target to shared state when user interacts
          controls.addEventListener("change", () => {
            if (shared.controlsTarget) {
              shared.controlsTarget.copy(controls.target);
            }
          });
        }
      }
    }

    // Debug: log all scene objects with their uuids
    if (scene && DEBUG) {
      debug("Scene objects:");
      scene.traverse((obj) => {
        if (obj.userData.uuid) {
          debug("  -", obj.type, "uuid:", obj.userData.uuid);
        }
      });
    }

    // Update LineMaterial resolutions after rebuild
    updateLineMaterialResolutions();
  }

  /**
   * Animation loop
   */
  function animate() {
    animationId = requestAnimationFrame(animate);

    if (controls) {
      // Sync target from shared state (in case another view changed it)
      if (shared.controlsTarget && controls.target) {
        // Only update if different to avoid resetting during interaction
        if (!controls.target.equals(shared.controlsTarget)) {
          controls.target.copy(shared.controlsTarget);
        }
      }
      controls.update();
    }

    if (scene && camera) {
      renderer.render(scene, camera);
    }
  }

  /**
   * Handle resize
   */
  function onResize() {
    width = model.get("width");
    height = model.get("height");

    renderer.setSize(width, height);

    if (camera) {
      if (camera.isPerspectiveCamera) {
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      }
      // Note: OrthographicCamera bounds are managed by the Python side
      // (e.g., matplotgl sets left/right/top/bottom directly)
      // so we don't auto-adjust them on resize
    }

    // Update LineMaterial resolutions
    updateLineMaterialResolutions();
  }

  /**
   * Get mouse position in normalized device coordinates
   */
  function getMousePosition(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  }

  /**
   * Perform raycasting and return hit info
   */
  function performRaycast(event) {
    if (!scene || !camera) return null;

    getMousePosition(event);
    raycaster.setFromCamera(mouse, camera);

    // Get all meshes/points that can be picked
    const pickableObjects = [];
    scene.traverse((obj) => {
      if (obj.isMesh || obj.isPoints || obj.isLine || obj.isLineSegments || obj.isSprite) {
        pickableObjects.push(obj);
      }
    });

    const intersects = raycaster.intersectObjects(pickableObjects, false);

    if (intersects.length > 0) {
      const hit = intersects[0];
      return {
        name: hit.object.name || "",
        uuid: hit.object.userData.uuid || hit.object.uuid,
        type: hit.object.type,
        point: hit.point ? [hit.point.x, hit.point.y, hit.point.z] : null,
        distance: hit.distance,
        faceIndex: hit.faceIndex ?? null,
        index: hit.index ?? null,  // For points
        instanceId: hit.instanceId ?? null,
      };
    }
    return null;
  }

  /**
   * Perform raycasting for a specific picker (against its controlling object)
   */
  function performPickerRaycast(event, picker) {
    if (!scene || !camera) return null;

    getMousePosition(event);
    raycaster.setFromCamera(mouse, camera);

    // Find objects to pick against
    let pickableObjects = [];

    if (picker.controlling) {
      // Pick against specific object(s)
      scene.traverse((obj) => {
        const objUuid = obj.userData.uuid || obj.uuid;
        if (objUuid === picker.controlling) {
          pickableObjects.push(obj);
        }
      });
    } else {
      // Pick against all meshes
      scene.traverse((obj) => {
        if (obj.isMesh || obj.isPoints || obj.isLine || obj.isLineSegments || obj.isSprite) {
          pickableObjects.push(obj);
        }
      });
    }

    if (pickableObjects.length === 0) {
      debug("Picker raycast: no pickable objects found for controlling:", picker.controlling);
      return { picker_uuid: picker.uuid, point: null };
    }

    const intersects = raycaster.intersectObjects(pickableObjects, true);

    if (intersects.length > 0) {
      debug("Picker raycast hit:", intersects[0].point);
    }

    if (intersects.length > 0) {
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
    return { picker_uuid: picker.uuid, point: null };
  }

  /**
   * Get keyboard modifiers from event
   */
  function getModifiers(event) {
    const mods = [];
    if (event.shiftKey) mods.push("shift");
    if (event.ctrlKey) mods.push("ctrl");
    if (event.altKey) mods.push("alt");
    if (event.metaKey) mods.push("meta");
    return mods;
  }

  /**
   * Handle picker events for a specific event type
   */
  function handlePickerEvent(event, eventType) {
    for (const picker of pickers) {
      if (picker.event === eventType) {
        const result = performPickerRaycast(event, picker);
        if (result) {
          model.set("_picker_event", result);
          model.save_changes();
        }
      }
    }
  }

  /**
   * Handle click events
   */
  function onClick(event) {
    // Handle pickers
    handlePickerEvent(event, "click");

    if (!model.get("enable_picking")) return;

    const hitInfo = performRaycast(event);

    // Always update _click_info (even if null/empty) to trigger observers
    model.set("_click_info", hitInfo || {});
    model.save_changes();
  }

  /**
   * Handle double-click events
   */
  function onDblClick(event) {
    // Handle pickers
    handlePickerEvent(event, "dblclick");

    if (!model.get("enable_picking")) return;

    const hitInfo = performRaycast(event);
    if (hitInfo) {
      hitInfo.doubleClick = true;
    }

    model.set("_click_info", hitInfo || {});
    model.save_changes();
  }

  /**
   * Handle mousedown events
   */
  function onMouseDown(event) {
    handlePickerEvent(event, "mousedown");
  }

  /**
   * Handle mouseup events
   */
  function onMouseUp(event) {
    handlePickerEvent(event, "mouseup");
  }

  /**
   * Handle hover/mousemove events (throttled)
   */
  let hoverTimeout = null;
  let pickerMoveTimeout = null;
  function onMouseMove(event) {
    // Handle mousemove pickers (throttled separately)
    if (!pickerMoveTimeout) {
      pickerMoveTimeout = setTimeout(() => {
        pickerMoveTimeout = null;
        handlePickerEvent(event, "mousemove");
      }, PICKER_THROTTLE_MS);
    }

    if (!model.get("enable_picking")) return;

    // Throttle hover events
    if (hoverTimeout) return;

    hoverTimeout = setTimeout(() => {
      hoverTimeout = null;

      const hitInfo = performRaycast(event);

      // Only update if changed (compare by uuid)
      const currentHover = model.get("_hover_info") || {};
      const newUuid = hitInfo ? hitInfo.uuid : null;
      const oldUuid = currentHover.uuid || null;

      if (newUuid !== oldUuid) {
        model.set("_hover_info", hitInfo || {});
        model.save_changes();
      }
    }, HOVER_THROTTLE_MS);
  }

  // Initialize - build/reuse shared scene and camera, create controls for this view
  rebuild();

  // Start animation loop
  animate();

  // Add event listeners for picking
  renderer.domElement.addEventListener("click", onClick);
  renderer.domElement.addEventListener("dblclick", onDblClick);
  renderer.domElement.addEventListener("mousedown", onMouseDown);
  renderer.domElement.addEventListener("mouseup", onMouseUp);
  renderer.domElement.addEventListener("mousemove", onMouseMove);

  // Watch for model changes
  // Scene updates preserve camera position
  model.on("change:_scene_data", () => {
    shared.needsRebuild = true;
    updateScene();
  });
  // Buffer updates require scene update
  model.on("change:_buffers_changed", () => {
    updateBuffers();
    shared.needsRebuild = true;
    updateScene();
  });
  // Camera and controls updates require full rebuild
  model.on("change:_camera_data", () => {
    shared.needsRebuild = true;
    rebuild();
  });
  model.on("change:_controls_data", () => {
    shared.needsRebuild = true;
    rebuild();
  });
  model.on("change:width", onResize);
  model.on("change:height", onResize);

  // Cleanup on widget removal
  return () => {
    if (animationId) {
      cancelAnimationFrame(animationId);
    }
    if (hoverTimeout) {
      clearTimeout(hoverTimeout);
    }
    if (pickerMoveTimeout) {
      clearTimeout(pickerMoveTimeout);
    }
    renderer.domElement.removeEventListener("click", onClick);
    renderer.domElement.removeEventListener("dblclick", onDblClick);
    renderer.domElement.removeEventListener("mousedown", onMouseDown);
    renderer.domElement.removeEventListener("mouseup", onMouseUp);
    renderer.domElement.removeEventListener("mousemove", onMouseMove);
    if (controls) {
      controls.dispose();
    }
    renderer.dispose();
    container.remove();

    // Release shared objects (will be deleted when viewCount reaches 0)
    releaseSharedObjects(modelId);
  };
}

export default { render };

