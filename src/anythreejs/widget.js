/**
 * anythreejs - Renderer widget
 *
 * Three.js rendering using anywidget
 */

import * as THREE from "https://esm.sh/three@0.182.0";
import { OrbitControls } from "https://esm.sh/three@0.182.0/addons/controls/OrbitControls.js";
import { TrackballControls } from "https://esm.sh/three@0.182.0/addons/controls/TrackballControls.js";

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
 * Create a Three.js geometry from serialized data
 */
function createGeometry(data) {
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
          let array = attr.array;
          if (Array.isArray(array)) {
            array = new Float32Array(array);
          }
          const itemSize = attr.itemSize || 3;
          geometry.setAttribute(
            name,
            new THREE.BufferAttribute(array, itemSize, attr.normalized)
          );
        }
      }

      if (data.index) {
        let indexArray = data.index;
        if (Array.isArray(indexArray)) {
          indexArray = new Uint32Array(indexArray);
        }
        geometry.setIndex(new THREE.BufferAttribute(indexArray, 1));
      }

      // Compute normals if not provided
      if (!data.attributes?.normal && data.attributes?.position) {
        geometry.computeVertexNormals();
      }

      return geometry;
    }

    case "EdgesGeometry": {
      const sourceGeometry = data.geometry ? createGeometry(data.geometry) : null;
      if (sourceGeometry) {
        return new THREE.EdgesGeometry(sourceGeometry, data.thresholdAngle ?? 1);
      }
      return new THREE.BufferGeometry();
    }

    default:
      console.warn(`Unknown geometry type: ${data.type}`);
      return new THREE.BoxGeometry(1, 1, 1);
  }
}

/**
 * Create a Three.js material from serialized data
 */
function createMaterial(data) {
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
    case "MeshBasicMaterial":
      return new THREE.MeshBasicMaterial({
        ...baseProps,
        wireframe: data.wireframe ?? false,
        vertexColors: parseVertexColors(data.vertexColors),
      });

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
function createObject(data) {
  if (!data) return null;

  let obj;

  switch (data.type) {
    case "Mesh": {
      const geometry = createGeometry(data.geometry);
      const material = createMaterial(data.material);
      obj = new THREE.Mesh(geometry, material);
      break;
    }

    case "Points": {
      const geometry = createGeometry(data.geometry) || new THREE.BufferGeometry();
      const material = createMaterial(data.material);
      obj = new THREE.Points(geometry, material);
      break;
    }

    case "Line": {
      const geometry = createGeometry(data.geometry) || new THREE.BufferGeometry();
      const material = createMaterial(data.material);
      obj = new THREE.Line(geometry, material);
      break;
    }

    case "LineSegments": {
      const geometry = createGeometry(data.geometry) || new THREE.BufferGeometry();
      const material = createMaterial(data.material);
      obj = new THREE.LineSegments(geometry, material);
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
          const child = createObject(childData);
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
      const child = createObject(childData);
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
      const halfWidth = ((data.right ?? 1) - (data.left ?? -1)) / 2;
      const halfHeight = ((data.top ?? 1) - (data.bottom ?? -1)) / 2;
      camera = new THREE.OrthographicCamera(
        -halfWidth * aspect,
        halfWidth * aspect,
        halfHeight,
        -halfHeight,
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
function buildScene(sceneData) {
  const scene = new THREE.Scene();

  if (sceneData.background) {
    scene.background = new THREE.Color(sceneData.background);
  }

  if (sceneData.children) {
    for (const childData of sceneData.children) {
      const child = createObject(childData);
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
  // Create container
  const container = document.createElement("div");
  container.style.width = "100%";
  container.style.height = "100%";
  container.style.position = "relative";
  el.appendChild(container);

  // Get initial dimensions
  let width = model.get("width");
  let height = model.get("height");

  // Create renderer
  const renderer = new THREE.WebGLRenderer({
    antialias: model.get("antialias"),
    alpha: model.get("alpha"),
  });
  renderer.setSize(width, height);
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  // Color space settings for compatibility with old pythreejs
  // Use LinearSRGBColorSpace to match old pythreejs behavior
  // where vertex colors were displayed without gamma correction
  renderer.outputColorSpace = THREE.LinearSRGBColorSpace;

  container.appendChild(renderer.domElement);

  // State
  let scene = null;
  let camera = null;
  let controls = null;
  let animationId = null;

  // Raycaster for picking
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();

  /**
   * Update only the scene, preserving camera position and controls
   */
  function updateScene() {
    const sceneData = model.get("_scene_data");

    // Save current camera state
    let savedCameraPosition = null;
    let savedCameraRotation = null;
    let savedControlsTarget = null;

    if (camera) {
      savedCameraPosition = camera.position.clone();
      savedCameraRotation = camera.rotation.clone();
    }
    if (controls && controls.target) {
      savedControlsTarget = controls.target.clone();
    }

    // Rebuild scene
    if (sceneData && Object.keys(sceneData).length > 0) {
      scene = buildScene(sceneData);
    } else {
      scene = new THREE.Scene();
      scene.background = new THREE.Color("#000000");
    }

    // Add camera back to scene
    if (camera) {
      scene.add(camera);

      // Restore camera state
      if (savedCameraPosition) {
        camera.position.copy(savedCameraPosition);
      }
      if (savedCameraRotation) {
        camera.rotation.copy(savedCameraRotation);
      }
    }

    // Restore controls target
    if (controls && savedControlsTarget) {
      controls.target.copy(savedControlsTarget);
    }
  }

  /**
   * Build/rebuild scene, camera, and controls from model data (full rebuild)
   */
  function rebuild() {
    const sceneData = model.get("_scene_data");
    const cameraData = model.get("_camera_data");
    const controlsData = model.get("_controls_data");

    const aspect = width / height;

    // Build scene
    if (sceneData && Object.keys(sceneData).length > 0) {
      scene = buildScene(sceneData);
    } else {
      scene = new THREE.Scene();
      scene.background = new THREE.Color("#000000");
    }

    // Build camera
    camera = createCamera(cameraData, aspect);

    // Add camera to scene (pythreejs does this)
    scene.add(camera);

    // Setup controls
    if (controls) {
      controls.dispose();
      controls = null;
    }

    if (controlsData && controlsData.length > 0) {
      const ctrlData = controlsData[0]; // Use first control

      if (ctrlData.type === "OrbitControls") {
        controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = ctrlData.enableDamping ?? true;
        controls.dampingFactor = ctrlData.dampingFactor ?? 0.05;
        controls.enableZoom = ctrlData.enableZoom ?? true;
        controls.enableRotate = ctrlData.enableRotate ?? true;
        controls.enablePan = ctrlData.enablePan ?? true;
        controls.autoRotate = ctrlData.autoRotate ?? false;
        controls.autoRotateSpeed = ctrlData.autoRotateSpeed ?? 2.0;

        if (ctrlData.target) {
          controls.target.set(...ctrlData.target);
        }
      } else if (ctrlData.type === "TrackballControls") {
        controls = new TrackballControls(camera, renderer.domElement);
        if (ctrlData.target) {
          controls.target.set(...ctrlData.target);
        }
      }
    }
  }

  /**
   * Animation loop
   */
  function animate() {
    animationId = requestAnimationFrame(animate);

    if (controls) {
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
      } else if (camera.isOrthographicCamera) {
        const aspect = width / height;
        const frustumHeight = camera.top - camera.bottom;
        camera.left = (-frustumHeight * aspect) / 2;
        camera.right = (frustumHeight * aspect) / 2;
        camera.updateProjectionMatrix();
      }
    }
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
   * Handle click events
   */
  function onClick(event) {
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
    if (!model.get("enable_picking")) return;

    const hitInfo = performRaycast(event);
    if (hitInfo) {
      hitInfo.doubleClick = true;
    }

    model.set("_click_info", hitInfo || {});
    model.save_changes();
  }

  /**
   * Handle hover/mousemove events (throttled)
   */
  let hoverTimeout = null;
  function onMouseMove(event) {
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
    }, 50); // 50ms throttle
  }

  // Initialize
  rebuild();
  animate();

  // Add event listeners for picking
  renderer.domElement.addEventListener("click", onClick);
  renderer.domElement.addEventListener("dblclick", onDblClick);
  renderer.domElement.addEventListener("mousemove", onMouseMove);

  // Watch for model changes
  // Scene updates preserve camera position
  model.on("change:_scene_data", updateScene);
  // Camera and controls updates require full rebuild
  model.on("change:_camera_data", rebuild);
  model.on("change:_controls_data", rebuild);
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
    renderer.domElement.removeEventListener("click", onClick);
    renderer.domElement.removeEventListener("dblclick", onDblClick);
    renderer.domElement.removeEventListener("mousemove", onMouseMove);
    if (controls) {
      controls.dispose();
    }
    renderer.dispose();
    container.remove();
  };
}

export default { render };

