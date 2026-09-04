import * as THREE from "three";
import { parseOsb6Preview } from "../shared/osb6-preview.js";

const RENDER_WIDTH = 480;
const RENDER_HEIGHT = 640;
const MAX_CACHED_FIGHTERS = 32;
// Engine light rig for injected fighters: ftport.c sOsbLights =
// gdSPDefLights1(145,145,145 ambient, 255,255,255 diffuse, dir 45,95,70).
const ENGINE_AMBIENT = 145 / 255;
const ENGINE_KEY_DIR = new THREE.Vector3(45, 95, 70);
// scvsintro.c / sc1pintro.c fighter cameras use fovy 30.
const ENGINE_FOVY = 30;
const fighterCache = new Map();
let renderQueue = Promise.resolve();
let renderer = null;

function bundleUrl(character) {
  // Production entries carry the immutable object URL; local dev falls back
  // to the engine's relative name.
  if (character?.bundleUrl) return character.bundleUrl;
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

  // Reproduce the engine's fixed-function light rig for injected fighters
  // (ftport.c sOsbLights): grey ambient + one white directional key from
  // front-top, Gouraud per vertex, shade clamped to 1.0 BEFORE it multiplies
  // the texel exactly like the RSP does. A three.js Lambert material with an
  // emissive fill was flattening the mesh into a paper cutout.
  const material = new THREE.ShaderMaterial({
    uniforms: {
      map: { value: texture },
      ambient: { value: ENGINE_AMBIENT },
      lightDir: { value: ENGINE_KEY_DIR.clone() },
    },
    vertexShader: `
      uniform float ambient;
      uniform vec3 lightDir;
      varying vec2 vUv;
      varying float vShade;
      void main() {
        vUv = uv;
        // The engine's key is "front-top" relative to the in-game camera
        // (fighters face +-X, camera on +Z), so apply it in view space.
        vec3 n = normalize(normalMatrix * normal);
        float ndotl = max(dot(n, normalize(lightDir)), 0.0);
        vShade = min(ambient + ndotl, 1.0);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform sampler2D map;
      varying vec2 vUv;
      varying float vShade;
      void main() {
        vec4 texel = texture2D(map, vUv);
        if (texel.a < 0.1) discard;
        gl_FragColor = vec4(texel.rgb * vShade, 1.0);
        #include <colorspace_fragment>
      }
    `,
    side: THREE.DoubleSide,
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

  // Perspective like the game's pre-battle / VS-card cameras (fovy 30), not
  // orthographic: the depth cues are half of what makes the mesh read as 3D.
  const aspect = RENDER_WIDTH / RENDER_HEIGHT;
  const viewHeight = Math.max(size.y, size.x / aspect) * 1.08;
  const halfFov = THREE.MathUtils.degToRad(ENGINE_FOVY / 2);
  const distance = (viewHeight / 2) / Math.tan(halfFov) + size.z / 2;
  const camera = new THREE.PerspectiveCamera(ENGINE_FOVY, aspect, 10, distance * 4);
  camera.position.set(0, 0, distance);
  camera.lookAt(0, 0, 0);

  const scene = new THREE.Scene();
  scene.add(mesh);
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
