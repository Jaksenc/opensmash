import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import logoModelUrl from "../visual/assets/smash-the-weights-logo.glb?url";

export const OG_LOGO_RENDER_WIDTH = 900;
export const OG_LOGO_RENDER_HEIGHT = 300;

let logoPromise = null;

async function snapshotCanvas(canvas) {
  if (typeof createImageBitmap === "function") return createImageBitmap(canvas);
  const copy = document.createElement("canvas");
  copy.width = canvas.width;
  copy.height = canvas.height;
  copy.getContext("2d").drawImage(canvas, 0, 0);
  return copy;
}

async function renderLogoModel() {
  const canvas = document.createElement("canvas");
  canvas.width = OG_LOGO_RENDER_WIDTH;
  canvas.height = OG_LOGO_RENDER_HEIGHT;
  const renderer = new THREE.WebGLRenderer({
    alpha: true,
    antialias: true,
    canvas,
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(1);
  renderer.setSize(OG_LOGO_RENDER_WIDTH, OG_LOGO_RENDER_HEIGHT, false);
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const gltf = await new GLTFLoader().loadAsync(logoModelUrl);
  const model = gltf.scene;
  const modelBounds = new THREE.Box3().setFromObject(model);
  model.position.sub(modelBounds.getCenter(new THREE.Vector3()));
  model.traverse((object) => {
    if (!object.isMesh) return;
    object.frustumCulled = false;
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of materials) {
      if (!material) continue;
      material.side = THREE.DoubleSide;
      if (material.map) {
        material.map.colorSpace = THREE.SRGBColorSpace;
        material.map.anisotropy = renderer.capabilities.getMaxAnisotropy();
      }
    }
  });

  const root = new THREE.Group();
  // Blender exports the sign face in the XZ plane, matching the live homepage
  // logo. Turn that face toward this renderer's +Z camera.
  root.rotation.x = Math.PI / 2;
  root.add(model);
  root.updateMatrixWorld(true);

  const bounds = new THREE.Box3().setFromObject(root);
  root.position.sub(bounds.getCenter(new THREE.Vector3()));
  root.updateMatrixWorld(true);
  const size = new THREE.Box3().setFromObject(root).getSize(new THREE.Vector3());
  const aspect = OG_LOGO_RENDER_WIDTH / OG_LOGO_RENDER_HEIGHT;
  const viewWidth = Math.max(size.x, size.y * aspect) * 1.06;
  const viewHeight = viewWidth / aspect;
  const camera = new THREE.OrthographicCamera(
    -viewWidth / 2,
    viewWidth / 2,
    viewHeight / 2,
    -viewHeight / 2,
    .1,
    1000,
  );
  camera.position.set(0, 0, Math.max(20, size.z * 5));
  camera.lookAt(0, 0, 0);

  const scene = new THREE.Scene();
  scene.add(root);
  scene.add(new THREE.HemisphereLight(0xfff6df, 0x28130d, 2.1));
  const keyLight = new THREE.DirectionalLight(0xfff0cc, 3.2);
  keyLight.position.set(-3.5, 5, 8);
  scene.add(keyLight);
  const rimLight = new THREE.DirectionalLight(0xff3218, 2);
  rimLight.position.set(5, -2, -3);
  scene.add(rimLight);

  renderer.render(scene, camera);
  const snapshot = await snapshotCanvas(canvas);
  renderer.dispose();
  renderer.forceContextLoss();
  return snapshot;
}

export function renderGameLogo() {
  if (!logoPromise) {
    logoPromise = renderLogoModel().catch((error) => {
      logoPromise = null;
      throw error;
    });
  }
  return logoPromise;
}
