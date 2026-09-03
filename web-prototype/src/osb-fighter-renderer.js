import * as THREE from "three";
import { parseOsb6Preview } from "../shared/osb6-preview.js";

const RENDER_WIDTH = 480;
const RENDER_HEIGHT = 640;
const MAX_CACHED_FIGHTERS = 32;
const fighterCache = new Map();
let renderQueue = Promise.resolve();
let renderer = null;

function bundleUrl(character) {
  const bundle = character?.bundle;
  if (!bundle) throw new Error(`No in-game bundle for ${character?.name || "fighter"}`);
  if (/^(?:https?:)?\//.test(bundle)) return bundle;
  return `/engine/bundles/${encodeURIComponent(bundle)}`;
}

function queued(task) {
  const result = renderQueue.then(task, task);
  renderQueue = result.catch(() => {});
  return result;
}

function getRenderer() {
  if (renderer) return renderer;
  const canvas = document.createElement("canvas");
  canvas.width = RENDER_WIDTH;
  canvas.height = RENDER_HEIGHT;
  renderer = new THREE.WebGLRenderer({
    alpha: true,
    antialias: true,
    canvas,
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(1);
  renderer.setSize(RENDER_WIDTH, RENDER_HEIGHT, false);
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  return renderer;
}

async function snapshotCanvas(canvas) {
  if (typeof createImageBitmap === "function") return createImageBitmap(canvas);
  const copy = document.createElement("canvas");
  copy.width = canvas.width;
  copy.height = canvas.height;
  copy.getContext("2d").drawImage(canvas, 0, 0);
  return copy;
}

async function renderParsedFighter(parsed) {
  const activeRenderer = getRenderer();
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(parsed.positions, 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(parsed.normals, 3));
  geometry.setAttribute("uv", new THREE.BufferAttribute(parsed.uvs, 2));
  geometry.setIndex(new THREE.BufferAttribute(parsed.indices, 1));
  geometry.computeBoundingSphere();

  const texture = new THREE.DataTexture(
    parsed.rgba,
    parsed.textureWidth,
    parsed.textureHeight,
    THREE.RGBAFormat,
    THREE.UnsignedByteType,
  );
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;

  // Keep the character-screen brightness while retaining the N64 mesh's
  // normal-based facial and clothing contours. Strong ambient fill prevents
  // the muddy unlit sides produced by the original low-fill light rig.
  const material = new THREE.MeshLambertMaterial({
    alphaTest: .1,
    emissive: 0xffffff,
    emissiveIntensity: .86,
    emissiveMap: texture,
    map: texture,
    side: THREE.DoubleSide,
    transparent: true,
  });
  const mesh = new THREE.Mesh(geometry, material);
  // Generated fighters face along +X in their authored in-game bind pose.
  mesh.rotation.y = -Math.PI / 2;
  mesh.updateMatrixWorld(true);

  const box = new THREE.Box3().setFromObject(mesh);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  mesh.position.x -= center.x;
  mesh.position.y -= center.y;
  mesh.position.z -= center.z;
  mesh.updateMatrixWorld(true);

  const aspect = RENDER_WIDTH / RENDER_HEIGHT;
  const viewHeight = Math.max(size.y, size.x / aspect) * 1.08;
  const viewWidth = viewHeight * aspect;
  const camera = new THREE.OrthographicCamera(
    -viewWidth / 2,
    viewWidth / 2,
    viewHeight / 2,
    -viewHeight / 2,
    .1,
    5000,
  );
  camera.position.set(0, 0, 1500);
  camera.lookAt(0, 0, 0);

  const scene = new THREE.Scene();
  scene.add(mesh);
  // The texture supplies 86% unshaded color, while the light rig contributes
  // the final 4–14%. This keeps roughly 10% shadow without muddying the roster.
  scene.add(new THREE.AmbientLight(0xffffff, .04));
  const keyLight = new THREE.DirectionalLight(0xfff4e5, .12);
  keyLight.position.set(-2, 4, 8);
  scene.add(keyLight);
  const fillLight = new THREE.DirectionalLight(0xc8e6ff, .02);
  fillLight.position.set(4, 1, 6);
  scene.add(fillLight);
  activeRenderer.clear();
  activeRenderer.render(scene, camera);
  const snapshot = await snapshotCanvas(activeRenderer.domElement);

  geometry.dispose();
  material.dispose();
  texture.dispose();
  return snapshot;
}

export function renderInGameFighter(character) {
  const url = bundleUrl(character);
  const key = `${url}#${character.fkind ?? 0}`;
  if (fighterCache.has(key)) {
    const cached = fighterCache.get(key);
    fighterCache.delete(key);
    fighterCache.set(key, cached);
    return cached;
  }

  const parsed = fetch(url)
    .then((response) => {
      if (!response.ok) throw new Error(`Could not load ${character.name}'s in-game model`);
      return response.arrayBuffer();
    })
    .then((bytes) => parseOsb6Preview(bytes, character.fkind ?? 0));
  const result = parsed.then((fighter) => queued(() => renderParsedFighter(fighter)));
  fighterCache.set(key, result);
  result.then(() => {
    // Reinsert resolved entries so Map order doubles as a tiny LRU. A long
    // editing session can shuffle indefinitely without retaining every
    // 480×640 bitmap it has ever previewed.
    fighterCache.delete(key);
    fighterCache.set(key, result);
    while (fighterCache.size > MAX_CACHED_FIGHTERS) {
      const oldestKey = fighterCache.keys().next().value;
      const oldest = fighterCache.get(oldestKey);
      fighterCache.delete(oldestKey);
      oldest?.then((image) => image?.close?.()).catch(() => {});
    }
  }).catch(() => {
    if (fighterCache.get(key) === result) fighterCache.delete(key);
  });
  return result;
}
