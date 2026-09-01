import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import {
  clearControllerTutorialCompletion,
  readControllerTutorialCompletion,
  saveControllerTutorialCompletion,
  shouldRequireControllerTutorial,
} from './control-tutorial.js?v=20260901-reset1';
import {
  completeControlsRoadblock,
  controlsRoadblockRequired,
} from './controls-roadblock.js';

const APP_BRIDGE = window.openSmashReactBridge;
const ROM_SHA256 = '15592e79d3c5295cef4371d4992f0bd25bec2102fc29644c93e682f7ea99ef3d';
const ROM_SIZE = 16 * 1024 * 1024;
const ROM_STORAGE_KEY = 'opensmash.rom-verified.v1';
const RANDOM_FIGHTER_COUNT = 12;
const RANDOM_STAGE_COUNT = 9;
const CARTRIDGE_FRONT_YAW = Math.PI * 1.5 - 0.18;
const CARTRIDGE_IDLE_SPIN_SPEED = 0.22;
const CARTRIDGE_DRAG_THRESHOLD = 6;
const CARTRIDGE_FACE_TURN_SPRING = 125;
const CARTRIDGE_FACE_TURN_DAMPING = 20.5;
const CARTRIDGE_FACE_TURN_LAUNCH_SPEED = 4;
const FLOW_FADE_MS = 520;
const FLOW_POSITION_SPRING = 56;
const FLOW_POSITION_DAMPING = 11.5;
const FLOW_ROTATION_SPRING = 64;
const FLOW_ROTATION_DAMPING = 12;
const FLOW_SCALE_SPRING = 70;
const FLOW_SCALE_DAMPING = 13;
const CONTROLLER_PRESS_SPRING = 92;
const CONTROLLER_PRESS_DAMPING = 14.5;
const CONTROLLER_DROP_SPRING = 118;
const CONTROLLER_DROP_DAMPING = 18;
const CONTROLLER_FLIP_SPRING = 30;
const CONTROLLER_FLIP_DAMPING = 8.7;
const CONTROLLER_Z_REVEAL_MS = 1150;
const CONTROLLER_ENTRANCE_HANDOFF_MS = 180;
const CONSOLE_DOCK_MS = 3710;
const CONSOLE_APPROACH_MS = 1220;
const CONSOLE_IDLE_MS = 720;
const CONSOLE_WINDUP_MS = 480;
const CONSOLE_SUSPENSE_MS = 100;
const CONSOLE_SLAM_MS = 330;
const CONSOLE_RETREAT_START_MS = 2910;
const CONSOLE_CARTRIDGE_FIT_SCALE = 0.44;
const CONSOLE_CARTRIDGE_READY_CLEARANCE = 0.34;
const CONSOLE_DOCK_FRONT_YAW = Math.PI * 1.5;
const CONSOLE_DOCK_FRONT_PITCH = 0.18;
const REQUIRED_CONTROL_KEYS = Object.freeze(['w', 'a', 's', 'd', 'j', 'k', 'l', 'i', 'o']);
const CONTROLLER_KEY_TORQUE = Object.freeze({
  w: Object.freeze([0.035, 0, 0]),
  a: Object.freeze([0.038, 0, 0.025]),
  s: Object.freeze([0.055, 0, 0]),
  d: Object.freeze([0.038, 0, -0.025]),
  j: Object.freeze([0.02, 0, -0.068]),
  k: Object.freeze([0.03, 0, -0.08]),
  l: Object.freeze([0.06, 0, 0]),
  i: Object.freeze([0.02, 0, 0.078]),
  o: Object.freeze([0.02, 0, -0.078]),
});

const grid = document.getElementById('replica-grid');
const videoFrame = document.querySelector('.intro-video-frame');
const introVideo = document.getElementById('intro-video');
const gameFrame = document.getElementById('intro-game-frame');
const resetRomButton = document.getElementById('rom-reset-button');
const overlay = document.getElementById('launch-flow-overlay');
const flowCanvas = document.getElementById('launch-flow-canvas');
const flowTitle = document.getElementById('launch-flow-title');
const flowCopy = document.getElementById('launch-flow-copy');
const fileInput = document.getElementById('rom-file-input');
const uploadButton = document.getElementById('rom-upload-button');
const cancelButton = document.getElementById('launch-cancel-button');
const formError = document.getElementById('rom-form-error');
const controllerStep = document.getElementById('launch-flow-controller-step');
const controlsMenuButton = document.getElementById('controls-menu-button');
const controlsCloseButton = document.getElementById('controls-close-button');
const controlPrompt = document.getElementById('launch-control-prompt');
const controlKeycaps = [...document.querySelectorAll('[data-control-key]')];
const controllerCallouts = document.getElementById('controller-callouts');
const controllerCalloutLines = document.getElementById('controller-callout-lines');

let pendingFighter = null;
let validationBusy = false;
let previousFocus = null;
let flowSequence = 0;
let flowTimer = 0;
let controllerTutorialCompletedThisSession = false;
let controlCheckComplete = false;
let controlExitPending = false;
let controlsPreviewMode = false;
let createUploadMode = false;
const completedControlKeys = new Set();
const heldControlKeys = new Set();

function randomInt(max) {
  return Math.floor(Math.random() * max);
}

function hasVerifiedRom() {
  if (APP_BRIDGE?.isAuthorized) return APP_BRIDGE.isAuthorized();
  try {
    return localStorage.getItem(ROM_STORAGE_KEY) === ROM_SHA256;
  } catch {
    return false;
  }
}

function rememberVerifiedRom() {
  if (APP_BRIDGE) {
    syncRomResetButton();
    return;
  }
  try { localStorage.setItem(ROM_STORAGE_KEY, ROM_SHA256); }
  catch { /* The current launch still works if storage is unavailable. */ }
  syncRomResetButton();
}

function usesMobileControls() {
  return document.body.classList.contains('uses-mobile-controls');
}

function hasCompletedControllerTutorial() {
  if (controllerTutorialCompletedThisSession) return true;
  try { return readControllerTutorialCompletion(localStorage); }
  catch { return false; }
}

function rememberCompletedControllerTutorial() {
  controllerTutorialCompletedThisSession = true;
  try { saveControllerTutorialCompletion(localStorage); }
  catch { /* Completion still applies to this launch if storage is unavailable. */ }
}

function resetControllerTutorial() {
  controllerTutorialCompletedThisSession = false;
  try { clearControllerTutorialCompletion(localStorage); }
  catch { /* The in-memory reset still applies to this tab. */ }
}

function requiresControllerTutorial() {
  return controlsRoadblockRequired() || shouldRequireControllerTutorial({
    completed: hasCompletedControllerTutorial(),
    mobileControls: usesMobileControls(),
  });
}

function forgetVerifiedRom() {
  if (APP_BRIDGE) return;
  try { localStorage.removeItem(ROM_STORAGE_KEY); }
  catch { /* Reset the current session even if storage is unavailable. */ }
}

function syncRomResetButton() {
  if (resetRomButton) resetRomButton.hidden = !hasVerifiedRom();
}

function fighterFromSelection(detail) {
  const fkind = Number(detail?.fkind);
  if (!Number.isInteger(fkind) || fkind < 0 || fkind >= RANDOM_FIGHTER_COUNT) return null;
  return Object.freeze({
    displayName: detail.displayName || detail.label || 'this fighter',
    slug: detail.slug || null,
    actionType: 'character',
    fkind,
    bundle: detail.bundle || null,
    selectionName: detail.name || detail.slug || null,
  });
}

function engineUrl(fighter) {
  const url = new URL('./engine/', location.href);
  const params = url.searchParams;
  params.set('cb', String(Date.now()));
  if (fighter.bundle) {
    params.set('inject', `bundles/${fighter.bundle}`);
    params.set('fkind', String(fighter.fkind));
    params.set('player', '0');
  }
  params.set('SSB64_BOOT_BATTLE', [
    fighter.fkind,
    randomInt(RANDOM_FIGHTER_COUNT),
    randomInt(RANDOM_STAGE_COUNT),
    1,
    randomInt(RANDOM_FIGHTER_COUNT),
    randomInt(RANDOM_FIGHTER_COUNT),
  ].join(','));
  return url.href;
}

function scrollToPageTop() {
  const behavior = matchMedia('(prefers-reduced-motion: reduce)').matches
    ? 'auto'
    : 'smooth';
  window.scrollTo({ top: 0, left: 0, behavior });
}

function keepPageScrollableFromGame() {
  const gameWindow = gameFrame?.contentWindow;
  if (!gameWindow) return;

  gameWindow.addEventListener('wheel', event => {
    // The Emscripten canvas also handles wheel events. Intercept them before
    // they reach the game so its WASM handler cannot consume the gesture or
    // make scrolling the parent page fall behind the pointer/trackpad input.
    event.preventDefault();
    event.stopImmediatePropagation();
    const deltaScale = event.deltaMode === WheelEvent.DOM_DELTA_LINE
      ? 16
      : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
        ? window.innerHeight
        : 1;
    window.scrollBy({
      left: event.deltaX * deltaScale,
      top: event.deltaY * deltaScale,
      // `auto` inherits the page's `scroll-behavior: smooth`, which restarts
      // the animation for every trackpad tick and makes most of the gesture
      // appear to be swallowed. Wheel input needs to move the page immediately;
      // the browser-provided deltas already contain the gesture's momentum.
      behavior: 'instant',
    });
  }, { capture: true, passive: false });
}

function launch(fighter) {
  if (!gameFrame || !videoFrame) return;
  pendingFighter = null;
  introVideo?.pause();
  gameFrame.title = `${fighter.displayName} — Super Weights Bros`;
  const source = APP_BRIDGE?.launch
    ? APP_BRIDGE.launch({ type: fighter.actionType || 'character', slug: fighter.slug })
    : engineUrl(fighter);
  if (!source || source === 'about:blank') {
    window.characterGrid?.select(null);
    return;
  }
  gameFrame.src = source;
  videoFrame.classList.add('is-game-running');
  window.characterGrid?.select(fighter.selectionName || fighter.slug || null);
  scrollToPageTop();
}

function closeGame() {
  window.characterGrid?.select(null);
  if (!gameFrame || !videoFrame) return;
  APP_BRIDGE?.closeGame?.();
  gameFrame.src = 'about:blank';
  gameFrame.title = 'Super Weights Bros game';
  videoFrame.classList.remove('is-game-running');
  if (introVideo) {
    introVideo.currentTime = 0;
    introVideo.play().catch(() => {});
  }
}

function resetRom() {
  forgetVerifiedRom();
  APP_BRIDGE?.clearVerification?.();
  pendingFighter = null;
  closeLaunchFlow(true);
  closeGame();
  syncRomResetButton();
}

function bytesToHex(bytes) {
  return [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

// Full-screen 3D launch flow -------------------------------------------------

let renderer = null;
let scene = null;
let camera = null;
let activeModel = null;
let activeModelKind = 'none';
let requestedModelKind = 'none';
let visualPhase = 'idle';
let visualStartedAt = 0;
let modelRestedAt = 0;
let animationFrame = 0;
let lastFlowFrameAt = 0;
const entranceVelocity = new THREE.Vector3();
const entranceAngularVelocity = new THREE.Vector3();
const flowMotionTargetPosition = new THREE.Vector3();
const flowMotionTargetRotation = new THREE.Vector3();
const flowMotionTargetAngularVelocity = new THREE.Vector3();
const flowMotionStartPosition = new THREE.Vector3();
let entranceScale = 1;
let entranceScaleVelocity = 0;
let flowMotionTargetScale = 1;
let flowMotionCompletion = null;
let cartridgePromise = null;
let consolePromise = null;
let controllerPromise = null;
let flowRenderTarget = null;
let flowPostScene = null;
let flowPostCamera = null;
let flowPostMaterial = null;

let cartridgeHovered = false;
let cartridgePressed = false;
let cartridgeDragging = false;
let cartridgeDragPointerId = null;
let cartridgeDragDistance = 0;
let cartridgePointerStartX = 0;
let cartridgePointerStartY = 0;
let cartridgeLastPointerTime = 0;
let cartridgePhysicsReady = false;
let cartridgeYaw = CARTRIDGE_FRONT_YAW;
let cartridgeYawVelocity = CARTRIDGE_IDLE_SPIN_SPEED;
let cartridgeFaceTurnActive = false;
let cartridgeFaceTurnTarget = CARTRIDGE_FRONT_YAW;
let cartridgeHoverAmount = 0;
let cartridgePressAmount = 0;
const cartridgePhysicsPosition = new THREE.Vector3();
const cartridgeVelocity = new THREE.Vector3();
const cartridgeDragTarget = new THREE.Vector3();
const cartridgeDragOffset = new THREE.Vector3();
const cartridgePointerWorld = new THREE.Vector3();
const cartridgePreviousPointerWorld = new THREE.Vector3();
const cartridgePointerVelocity = new THREE.Vector3();
const cartridgePointerDelta = new THREE.Vector3();
const cartridgeSpringTarget = new THREE.Vector3();
const cartridgeTilt = { x: 0, z: 0, vx: 0, vz: 0 };
const cartridgeRaycaster = new THREE.Raycaster();
const cartridgePointerNdc = new THREE.Vector2();
const controllerTilt = new THREE.Vector3();
const controllerTiltVelocity = new THREE.Vector3();
const controllerTiltTarget = new THREE.Vector3();
const controllerBaseEuler = new THREE.Euler(0, 0, 0, 'XYZ');
const controllerPressEuler = new THREE.Euler(0, 0, 0, 'XYZ');
const controllerBaseQuaternion = new THREE.Quaternion();
const controllerPressQuaternion = new THREE.Quaternion();
let controllerDrop = 0;
let controllerDropVelocity = 0;
let controllerFlip = 0;
let controllerFlipVelocity = 0;
let controllerZRevealUntil = 0;
let controllerEntranceHandoffStartedAt = 0;
let controllerEntranceHandoffScale = 1;
const controllerEntranceHandoffPosition = new THREE.Vector3();
const controllerEntranceHandoffQuaternion = new THREE.Quaternion();
const controllerIdlePosition = new THREE.Vector3();
const controllerIdleQuaternion = new THREE.Quaternion();
let consoleDockAssembly = null;
let consoleDockModel = null;
const consoleDockCartridgeStartPosition = new THREE.Vector3();
const consoleDockCartridgeReadyPosition = new THREE.Vector3();
const consoleDockCartridgeTargetPosition = new THREE.Vector3();
const consoleDockCartridgeWindupPosition = new THREE.Vector3();
const consoleDockCartridgeInsertionVector = new THREE.Vector3();
const consoleDockCartridgeStartQuaternion = new THREE.Quaternion();
const consoleDockCartridgeTargetQuaternion = new THREE.Quaternion();
const consoleDockCartridgeWindupQuaternion = new THREE.Quaternion();
const consoleDockConsoleStartPosition = new THREE.Vector3();
const consoleDockConsoleTargetPosition = new THREE.Vector3();
const consoleDockConsoleStartQuaternion = new THREE.Quaternion();
const consoleDockConsoleTargetQuaternion = new THREE.Quaternion();
const consoleDockAnchorOffset = new THREE.Vector3();
const consoleDockAssemblyOriginPosition = new THREE.Vector3();
const consoleDockAssemblyOriginQuaternion = new THREE.Quaternion();
const consoleDockAssemblyTargetPosition = new THREE.Vector3(0, 1.4, -1.8);
const consoleDockAssemblyTargetQuaternion = new THREE.Quaternion();
let consoleDockCartridgeStartScale = 1;
let consoleDockCartridgeTargetScale = 1;
let consoleDockConsoleScale = 1;

const gltfLoader = new GLTFLoader();
const textureLoader = new THREE.TextureLoader();
const FLOW_SHADER_DEFAULTS = Object.freeze({
  pixelSize: 2,
  colorSteps: 12,
  posterize: 0.5,
  dither: 1,
  outlineWidth: 1,
  outlineStrength: 0.7,
  outlineColor: '#383838',
  gamma: 2.5,
});

function loadFlowShaderSettings() {
  let stored = {};
  try {
    stored = JSON.parse(localStorage.getItem('opensmash.shader-tuning.v3') || '{}');
  } catch { /* Match the cursor shader defaults when storage is unavailable. */ }
  const settings = { ...FLOW_SHADER_DEFAULTS };
  for (const key of ['pixelSize', 'colorSteps', 'posterize', 'dither',
                     'outlineWidth', 'outlineStrength', 'gamma']) {
    if (Number.isFinite(Number(stored[key]))) settings[key] = Number(stored[key]);
  }
  if (/^#[0-9a-f]{6}$/i.test(stored.outlineColor || '')) {
    settings.outlineColor = stored.outlineColor;
  }
  return settings;
}

function shaderColor(hex) {
  const value = Number.parseInt(hex.slice(1), 16);
  return new THREE.Vector3(
    ((value >> 16) & 255) / 255,
    ((value >> 8) & 255) / 255,
    (value & 255) / 255
  );
}

const flowShaderSettings = loadFlowShaderSettings();
const controllerAnchorScreen = new THREE.Vector3();
const controllerLabelScreen = new THREE.Vector3();
const controllerZAnchorPoint = [0, 0];
const controllerZLabelPoint = [0, 0];
const controllerCalloutLayout = Object.freeze({
  stick: Object.freeze({ anchor: [0.50, 0.55], label: [0.50, 0.34] }),
  a: Object.freeze({ anchor: [0.67, 0.32], label: [0.72, 0.17] }),
  b: Object.freeze({ anchor: [0.75, 0.40], label: [0.88, 0.36] }),
  z: Object.freeze({
    anchor: [0.50, 0.72],
    label: [0.50, 0.94],
    backAnchor: [0.50, 0.33],
    backLabel: [0.50, 0.94],
  }),
  'left-bumper': Object.freeze({ anchor: [0.18, 0.17], label: [-0.04, 0.08] }),
  'right-bumper': Object.freeze({ anchor: [0.83, 0.17], label: [1.04, 0.08] }),
});

function createFlowPostProcess() {
  flowRenderTarget = new THREE.WebGLRenderTarget(4, 4, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    generateMipmaps: false,
  });
  flowPostScene = new THREE.Scene();
  flowPostCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  flowPostMaterial = new THREE.ShaderMaterial({
    transparent: true,
    uniforms: {
      tex: { value: flowRenderTarget.texture },
      res: { value: new THREE.Vector2(4, 4) },
      colorSteps: { value: flowShaderSettings.colorSteps },
      posterize: { value: flowShaderSettings.posterize },
      dither: { value: flowShaderSettings.dither },
      outlineWidth: { value: flowShaderSettings.outlineWidth },
      outlineStrength: { value: flowShaderSettings.outlineStrength },
      outlineColor: { value: shaderColor(flowShaderSettings.outlineColor) },
      gamma: { value: flowShaderSettings.gamma },
    },
    vertexShader: `varying vec2 vUv;
      void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
    fragmentShader: `
      uniform sampler2D tex; uniform vec2 res; varying vec2 vUv;
      uniform float colorSteps, posterize, dither, outlineWidth, outlineStrength, gamma;
      uniform vec3 outlineColor;
      float bayer4(vec2 p) {
        int x = int(mod(p.x, 4.0)), y = int(mod(p.y, 4.0));
        int m[16]; m[0]=0; m[1]=8; m[2]=2; m[3]=10; m[4]=12; m[5]=4; m[6]=14; m[7]=6;
        m[8]=3; m[9]=11; m[10]=1; m[11]=9; m[12]=15; m[13]=7; m[14]=13; m[15]=5;
        return (float(m[y*4+x]) + 0.5) / 16.0;
      }
      bool solidAt(vec2 t) {
        float threshold = mix(0.5, bayer4(t), dither);
        return texture2D(tex, (t + 0.5) / res).a >= threshold;
      }
      void main() {
        vec2 texel = floor(vUv * res);
        if (!solidAt(texel)) discard;
        vec4 c = texture2D(tex, (texel + 0.5) / res);
        vec3 col = pow(clamp(c.rgb, 0.0, 1.0), vec3(1.0 / gamma));
        vec3 stepped = floor(col * colorSteps + 0.5) / colorSteps;
        col = mix(col, stepped, posterize);
        bool edge = false;
        if (outlineWidth >= 0.5) {
          edge = !solidAt(texel + vec2(1.0, 0.0)) || !solidAt(texel - vec2(1.0, 0.0))
              || !solidAt(texel + vec2(0.0, 1.0)) || !solidAt(texel - vec2(0.0, 1.0));
        }
        if (outlineWidth >= 1.5) {
          edge = edge || !solidAt(texel + vec2(2.0, 0.0)) || !solidAt(texel - vec2(2.0, 0.0))
              || !solidAt(texel + vec2(0.0, 2.0)) || !solidAt(texel - vec2(0.0, 2.0));
        }
        if (outlineWidth >= 2.5) {
          edge = edge || !solidAt(texel + vec2(3.0, 0.0)) || !solidAt(texel - vec2(3.0, 0.0))
              || !solidAt(texel + vec2(0.0, 3.0)) || !solidAt(texel - vec2(0.0, 3.0));
        }
        if (edge) col = mix(col, min(col, outlineColor), outlineStrength);
        gl_FragColor = vec4(col, 1.0);
      }`,
  });
  flowPostScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), flowPostMaterial));
}

function prepareCartridge(gltf, labelTexture) {
  const model = gltf.scene;
  const bounds = new THREE.Box3().setFromObject(model);
  const center = bounds.getCenter(new THREE.Vector3());
  const size = bounds.getSize(new THREE.Vector3());
  model.position.sub(center);
  model.traverse(child => {
    if (!child.isMesh) return;
    child.frustumCulled = false;
    child.material = new THREE.MeshStandardMaterial({
      color: 0xb8b5ba,
      emissive: 0x121116,
      emissiveIntensity: 0.16,
      roughness: 0.84,
      metalness: 0,
    });
  });

  labelTexture.colorSpace = THREE.SRGBColorSpace;
  const labelArtwork = new THREE.Mesh(
    new THREE.PlaneGeometry(0.48046875, 0.587890625),
    new THREE.MeshBasicMaterial({
      map: labelTexture,
      transparent: true,
      alphaTest: 0.02,
      depthWrite: false,
      side: THREE.DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: -4,
      polygonOffsetUnits: -4,
    })
  );
  labelArtwork.position.set(0.0876, 0.015625, 0.0087890625);
  labelArtwork.rotation.y = Math.PI * 0.5;
  labelArtwork.renderOrder = 1;
  model.add(labelArtwork);

  const wrapper = new THREE.Group();
  wrapper.add(model);
  wrapper.scale.setScalar(0.8 / Math.max(size.x, size.y, size.z));
  wrapper.userData.homeY = 0.68;
  wrapper.userData.homeScale = wrapper.scale.x;
  wrapper.userData.baseHomeScale = wrapper.scale.x;
  wrapper.updateMatrixWorld(true);
  wrapper.userData.baseDiameter = new THREE.Box3().setFromObject(wrapper)
    .getBoundingSphere(new THREE.Sphere()).radius * 2;
  return wrapper;
}

function prepareController(gltf) {
  const model = gltf.scene;
  const bounds = new THREE.Box3().setFromObject(model);
  const center = bounds.getCenter(new THREE.Vector3());
  const size = bounds.getSize(new THREE.Vector3());
  model.position.sub(center);
  model.traverse(child => {
    if (!child.isMesh) return;
    child.frustumCulled = false;
    const materials = Array.isArray(child.material) ? child.material : [child.material];
    materials.forEach(material => {
      if (material?.map) material.map.colorSpace = THREE.SRGBColorSpace;
      if (material) {
        material.roughness = Math.max(material.roughness ?? 0.5, 0.45);
        material.needsUpdate = true;
      }
    });
  });

  const wrapper = new THREE.Group();
  wrapper.add(model);
  model.updateMatrixWorld(true);
  const localBounds = new THREE.Box3().setFromObject(model);
  const localSize = localBounds.getSize(new THREE.Vector3());
  wrapper.userData.calloutBounds = {
    min: localBounds.min.clone(),
    max: localBounds.max.clone(),
    frontY: localBounds.max.y + localSize.y * 0.025,
    backY: localBounds.min.y - localSize.y * 0.025,
  };
  wrapper.scale.setScalar(2.05 / Math.max(size.x, size.y, size.z));
  wrapper.rotation.set(1.32, 0.06, 0);
  wrapper.userData.homeY = -0.05;
  wrapper.userData.homeScale = wrapper.scale.x;
  wrapper.userData.baseHomeScale = wrapper.scale.x;
  wrapper.updateMatrixWorld(true);
  wrapper.userData.baseDiameter = new THREE.Box3().setFromObject(wrapper)
    .getBoundingSphere(new THREE.Sphere()).radius * 2;
  return wrapper;
}

function prepareConsole(gltf) {
  const model = gltf.scene;
  const bounds = new THREE.Box3().setFromObject(model);
  const center = bounds.getCenter(new THREE.Vector3());
  model.position.sub(center);
  model.traverse(child => {
    if (!child.isMesh) return;
    child.frustumCulled = false;
    const materials = Array.isArray(child.material) ? child.material : [child.material];
    materials.forEach(material => {
      if (material?.map) material.map.colorSpace = THREE.SRGBColorSpace;
      if (material) {
        material.roughness = Math.max(material.roughness ?? 0.5, 0.52);
        material.needsUpdate = true;
      }
    });
  });

  model.updateMatrixWorld(true);
  const snapAnchor = model.getObjectByName('CartridgeSnapAnchor');
  const mouthAnchor = model.getObjectByName('CartridgeMouthAnchor');
  const wrapper = new THREE.Group();
  wrapper.add(model);
  wrapper.userData.snapAnchor = snapAnchor
    ? snapAnchor.getWorldPosition(new THREE.Vector3())
    : new THREE.Vector3(-0.146, 0.177, 0);
  wrapper.userData.mouthAnchor = mouthAnchor
    ? mouthAnchor.getWorldPosition(new THREE.Vector3())
    : new THREE.Vector3(-0.146, 0.264, 0);
  return wrapper;
}

function fitFlowModelToViewport(model, kind) {
  if (!camera || !model) return;
  const viewHeight = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5)) *
    Math.abs(camera.position.z);
  const viewWidth = viewHeight * camera.aspect;
  const widthAllowance = kind === 'controller' ? 0.84 : 0.9;
  const heightAllowance = kind === 'controller' ? 0.68 : 0.82;
  const diameter = Math.max(0.001, model.userData.baseDiameter || 1);
  const fit = Math.min(
    1,
    viewWidth * widthAllowance / diameter,
    viewHeight * heightAllowance / diameter
  );
  model.userData.homeScale = model.userData.baseHomeScale * fit;
}

function preloadFlowModels() {
  cartridgePromise ||= Promise.all([
    gltfLoader.loadAsync('./assets/n64-cartridge-tripo.glb'),
    textureLoader.loadAsync('./assets/cartridge-label-art.png'),
  ]).then(([gltf, texture]) => prepareCartridge(gltf, texture));
  consolePromise ||= gltfLoader
    .loadAsync('./assets/hybrid-four-port-console-fitted.glb')
    .then(prepareConsole);
  controllerPromise ||= gltfLoader
    .loadAsync('./assets/nintendo-64-controller.glb')
    .then(prepareController);
}

function ensureFlowRenderer() {
  if (renderer || !flowCanvas) return;
  renderer = new THREE.WebGLRenderer({
    canvas: flowCanvas,
    alpha: true,
    antialias: false,
    powerPreference: 'high-performance',
  });
  renderer.setClearColor(0x000000, 0);
  renderer.localClippingEnabled = false;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  createFlowPostProcess();

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
  camera.position.set(0, 0, 8);
  scene.add(new THREE.HemisphereLight(0xfff6e9, 0x16111c, 2.6));
  const key = new THREE.DirectionalLight(0xffecd1, 4.4);
  key.position.set(-3.5, 4.5, 6);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x6f8dff, 2.2);
  rim.position.set(4, 0.4, -2);
  scene.add(rim);
  const face = new THREE.PointLight(0xff5c34, 6, 16, 2);
  face.position.set(-3.5, -2, 5);
  scene.add(face);
  resizeFlowRenderer();
  preloadFlowModels();
}

function resizeFlowRenderer() {
  if (!renderer || !camera) return;
  const width = Math.max(1, window.innerWidth);
  const height = Math.max(1, window.innerHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  if (activeModel && activeModelKind !== 'none') {
    fitFlowModelToViewport(activeModel, activeModelKind);
  }
  const targetWidth = Math.max(4, Math.round(width / flowShaderSettings.pixelSize));
  const targetHeight = Math.max(4, Math.round(height / flowShaderSettings.pixelSize));
  flowRenderTarget?.setSize(targetWidth, targetHeight);
  flowPostMaterial?.uniforms.res.value.set(targetWidth, targetHeight);
}

function projectControllerCalloutPoint(point, target, backAmount = 0) {
  const bounds = activeModel?.userData.calloutBounds;
  if (!bounds || !camera) return null;
  target.set(
    THREE.MathUtils.lerp(bounds.min.x, bounds.max.x, point[0]),
    THREE.MathUtils.lerp(bounds.frontY, bounds.backY, backAmount),
    THREE.MathUtils.lerp(bounds.min.z, bounds.max.z, point[1])
  );
  activeModel.localToWorld(target);
  target.project(camera);
  target.x = (target.x * 0.5 + 0.5) * window.innerWidth;
  target.y = (-target.y * 0.5 + 0.5) * window.innerHeight;
  return target;
}

function updateControllerCallouts() {
  if (!controllerCallouts || !controllerCalloutLines || !activeModel ||
      activeModelKind !== 'controller' || overlay?.dataset.step !== 'controller') return;

  activeModel.updateMatrixWorld(true);
  camera.updateMatrixWorld(true);
  const width = window.innerWidth;
  const height = window.innerHeight;
  const rawZReveal = THREE.MathUtils.clamp(Math.abs(controllerFlip) / Math.PI, 0, 1);
  const zRevealAmount = rawZReveal * rawZReveal * (3 - 2 * rawZReveal);
  controllerCallouts.classList.toggle('is-z-reveal', zRevealAmount > 0.34);
  controllerCalloutLines.setAttribute('viewBox', `0 0 ${width} ${height}`);

  for (const [control, layout] of Object.entries(controllerCalloutLayout)) {
    let anchorPoint = layout.anchor;
    let labelPoint = layout.label;
    let backAmount = 0;
    if (control === 'z' && layout.backAnchor && layout.backLabel) {
      backAmount = zRevealAmount;
      controllerZAnchorPoint[0] = THREE.MathUtils.lerp(
        layout.anchor[0], layout.backAnchor[0], backAmount
      );
      controllerZAnchorPoint[1] = THREE.MathUtils.lerp(
        layout.anchor[1], layout.backAnchor[1], backAmount
      );
      controllerZLabelPoint[0] = THREE.MathUtils.lerp(
        layout.label[0], layout.backLabel[0], backAmount
      );
      controllerZLabelPoint[1] = THREE.MathUtils.lerp(
        layout.label[1], layout.backLabel[1], backAmount
      );
      anchorPoint = controllerZAnchorPoint;
      labelPoint = controllerZLabelPoint;
    }
    const anchor = projectControllerCalloutPoint(
      anchorPoint, controllerAnchorScreen, backAmount
    );
    const label = projectControllerCalloutPoint(
      labelPoint, controllerLabelScreen, backAmount
    );
    if (!anchor || !label) continue;
    const anchorX = anchor.x;
    const anchorY = anchor.y;
    const labelX = THREE.MathUtils.clamp(
      label.x, 48, width - 48
    );
    const labelY = THREE.MathUtils.clamp(
      label.y, 42, height - 42
    );
    const callout = controllerCallouts.querySelector(`[data-control-callout="${control}"]`);
    const lineGroup = controllerCalloutLines.querySelector(`[data-control-line="${control}"]`);
    const line = lineGroup?.querySelector('line');
    const dot = lineGroup?.querySelector('circle');
    if (callout) {
      callout.style.left = `${labelX}px`;
      callout.style.top = `${labelY}px`;
    }
    if (line) {
      line.setAttribute('x1', String(anchorX));
      line.setAttribute('y1', String(anchorY));
      line.setAttribute('x2', String(labelX));
      line.setAttribute('y2', String(labelY));
    }
    if (dot) {
      dot.setAttribute('cx', String(anchorX));
      dot.setAttribute('cy', String(anchorY));
    }
  }
}

function resetControllerPhysics() {
  heldControlKeys.clear();
  controllerCallouts?.classList.remove('is-z-reveal');
  controllerTilt.set(0, 0, 0);
  controllerTiltVelocity.set(0, 0, 0);
  controllerTiltTarget.set(0, 0, 0);
  controllerDrop = 0;
  controllerDropVelocity = 0;
  controllerFlip = 0;
  controllerFlipVelocity = 0;
  controllerZRevealUntil = 0;
  controllerEntranceHandoffStartedAt = 0;
}

function pressControllerControl(key, repeated) {
  if (repeated || heldControlKeys.has(key)) return;
  heldControlKeys.add(key);
  const torque = CONTROLLER_KEY_TORQUE[key];
  if (!torque || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  controllerTiltVelocity.x += torque[0] * 3.4;
  controllerTiltVelocity.y += torque[1] * 3.4;
  controllerTiltVelocity.z += torque[2] * 3.4;
  controllerDropVelocity -= 0.085;
  if (key === 'l') {
    controllerZRevealUntil = performance.now() + CONTROLLER_Z_REVEAL_MS;
    controllerFlipVelocity = Math.max(controllerFlipVelocity, 1.25);
  }
}

function updateControllerPhysics(now, dt, homeY, homeScale, reducedMotion) {
  const idleTime = now / 1000;
  controllerTiltTarget.set(0, 0, 0);
  if (!reducedMotion) {
    for (const key of heldControlKeys) {
      const torque = CONTROLLER_KEY_TORQUE[key];
      if (!torque) continue;
      controllerTiltTarget.x += torque[0];
      controllerTiltTarget.y += torque[1];
      controllerTiltTarget.z += torque[2];
    }
    controllerTiltTarget.x = THREE.MathUtils.clamp(controllerTiltTarget.x, -0.09, 0.09);
    controllerTiltTarget.y = THREE.MathUtils.clamp(controllerTiltTarget.y, -0.09, 0.09);
    controllerTiltTarget.z = THREE.MathUtils.clamp(controllerTiltTarget.z, -0.11, 0.11);
  }

  for (const axis of ['x', 'y', 'z']) {
    controllerTiltVelocity[axis] += (
      (controllerTiltTarget[axis] - controllerTilt[axis]) * CONTROLLER_PRESS_SPRING -
      controllerTiltVelocity[axis] * CONTROLLER_PRESS_DAMPING
    ) * dt;
    controllerTilt[axis] += controllerTiltVelocity[axis] * dt;
  }

  const dropTarget = reducedMotion || heldControlKeys.size === 0 ? 0 : -0.026;
  controllerDropVelocity += (
    (dropTarget - controllerDrop) * CONTROLLER_DROP_SPRING -
    controllerDropVelocity * CONTROLLER_DROP_DAMPING
  ) * dt;
  controllerDrop += controllerDropVelocity * dt;

  const flipTarget = !reducedMotion &&
      (heldControlKeys.has('l') || now < controllerZRevealUntil)
    ? Math.PI
    : 0;
  controllerFlipVelocity += (
    (flipTarget - controllerFlip) * CONTROLLER_FLIP_SPRING -
    controllerFlipVelocity * CONTROLLER_FLIP_DAMPING
  ) * dt;
  controllerFlip += controllerFlipVelocity * dt;

  activeModel.position.set(
    0,
    homeY + Math.sin(idleTime * 1.75) * 0.045 + controllerDrop,
    0
  );
  activeModel.scale.setScalar(homeScale);
  controllerBaseEuler.set(
    1.32 + Math.sin(idleTime * 1.1) * 0.018 + controllerTilt.x,
    0.06 + Math.sin(idleTime * 0.75) * 0.025,
    0
  );
  controllerPressEuler.set(0, controllerTilt.y + controllerFlip, controllerTilt.z);
  controllerBaseQuaternion.setFromEuler(controllerBaseEuler);
  controllerPressQuaternion.setFromEuler(controllerPressEuler);
  activeModel.quaternion.copy(controllerPressQuaternion).multiply(controllerBaseQuaternion);

  if (controllerEntranceHandoffStartedAt) {
    const handoffProgress = THREE.MathUtils.clamp(
      (now - controllerEntranceHandoffStartedAt) / CONTROLLER_ENTRANCE_HANDOFF_MS,
      0,
      1
    );
    const handoffBlend = THREE.MathUtils.smootherstep(handoffProgress, 0, 1);
    controllerIdlePosition.copy(activeModel.position);
    controllerIdleQuaternion.copy(activeModel.quaternion);
    activeModel.position.lerpVectors(
      controllerEntranceHandoffPosition,
      controllerIdlePosition,
      handoffBlend
    );
    activeModel.quaternion.copy(controllerEntranceHandoffQuaternion)
      .slerp(controllerIdleQuaternion, handoffBlend);
    activeModel.scale.setScalar(THREE.MathUtils.lerp(
      controllerEntranceHandoffScale,
      homeScale,
      handoffBlend
    ));
    if (handoffProgress >= 1) controllerEntranceHandoffStartedAt = 0;
  }

  if (controlExitPending && now >= controllerZRevealUntil &&
      Math.abs(controllerFlip) < 0.025 && Math.abs(controllerFlipVelocity) < 0.12) {
    controlExitPending = false;
    clearTimeout(flowTimer);
    flowTimer = window.setTimeout(continueToGame, 140);
  }
}

function configureEntrancePhysics(model, kind) {
  const homeScale = model.userData.homeScale;
  model.position.set(0, -5.3, 0);
  flowMotionStartPosition.copy(model.position);
  flowMotionTargetPosition.set(0, model.userData.homeY, 0);
  entranceVelocity.set(0, 0, 0);
  entranceAngularVelocity.set(0, 0, 0);
  entranceScale = homeScale * 0.76;
  entranceScaleVelocity = 0;
  flowMotionTargetScale = homeScale;
  flowMotionCompletion = null;
  model.scale.setScalar(entranceScale);
  if (kind === 'cartridge') {
    model.rotation.set(0.18, CARTRIDGE_FRONT_YAW - Math.PI * 4, -0.16);
    flowMotionTargetRotation.set(-0.08, CARTRIDGE_FRONT_YAW, 0);
    flowMotionTargetAngularVelocity.set(0, CARTRIDGE_IDLE_SPIN_SPEED, 0);
  } else {
    model.rotation.set(0.92, -0.32, 0.12);
    flowMotionTargetRotation.set(1.32, 0.06, 0);
    flowMotionTargetAngularVelocity.set(0, 0, 0);
  }
}

function finishPhysicsEntrance(now, homeY, homeScale, snapToRest = false) {
  if (activeModelKind === 'cartridge' || snapToRest) {
    activeModel.position.set(0, homeY, 0);
    activeModel.scale.setScalar(homeScale);
  }
  if (activeModelKind === 'cartridge') {
    activeModel.rotation.x = -0.08;
    activeModel.rotation.z = 0;
    cartridgePhysicsPosition.copy(activeModel.position);
    cartridgeDragTarget.copy(activeModel.position);
    cartridgeVelocity.copy(entranceVelocity);
    cartridgeYaw = activeModel.rotation.y;
    cartridgeYawVelocity = entranceAngularVelocity.y;
    cartridgePhysicsReady = true;
  } else if (snapToRest) {
    activeModel.rotation.set(1.32, 0.06, 0);
    controllerEntranceHandoffStartedAt = 0;
  } else {
    controllerEntranceHandoffPosition.copy(activeModel.position);
    controllerEntranceHandoffQuaternion.copy(activeModel.quaternion);
    controllerEntranceHandoffScale = activeModel.scale.x;
    controllerEntranceHandoffStartedAt = now;
  }
  visualPhase = 'idle';
  visualStartedAt = now;
  modelRestedAt = 0;
}

function stepFlowMotionPhysics(dt) {
  let remainingDt = dt;
  while (remainingDt > 0) {
    const stepDt = Math.min(remainingDt, 1 / 120);
    entranceVelocity.x += (
      (flowMotionTargetPosition.x - activeModel.position.x) * FLOW_POSITION_SPRING -
      entranceVelocity.x * FLOW_POSITION_DAMPING
    ) * stepDt;
    entranceVelocity.y += (
      (flowMotionTargetPosition.y - activeModel.position.y) * FLOW_POSITION_SPRING -
      entranceVelocity.y * FLOW_POSITION_DAMPING
    ) * stepDt;
    entranceVelocity.z += (
      (flowMotionTargetPosition.z - activeModel.position.z) * FLOW_POSITION_SPRING -
      entranceVelocity.z * FLOW_POSITION_DAMPING
    ) * stepDt;
    activeModel.position.addScaledVector(entranceVelocity, stepDt);

    flowMotionTargetRotation.addScaledVector(flowMotionTargetAngularVelocity, stepDt);
    entranceAngularVelocity.x += (
      (flowMotionTargetRotation.x - activeModel.rotation.x) * FLOW_ROTATION_SPRING -
      (entranceAngularVelocity.x - flowMotionTargetAngularVelocity.x) *
        FLOW_ROTATION_DAMPING
    ) * stepDt;
    entranceAngularVelocity.y += (
      (flowMotionTargetRotation.y - activeModel.rotation.y) * FLOW_ROTATION_SPRING -
      (entranceAngularVelocity.y - flowMotionTargetAngularVelocity.y) *
        FLOW_ROTATION_DAMPING
    ) * stepDt;
    entranceAngularVelocity.z += (
      (flowMotionTargetRotation.z - activeModel.rotation.z) * FLOW_ROTATION_SPRING -
      (entranceAngularVelocity.z - flowMotionTargetAngularVelocity.z) *
        FLOW_ROTATION_DAMPING
    ) * stepDt;
    activeModel.rotation.x += entranceAngularVelocity.x * stepDt;
    activeModel.rotation.y += entranceAngularVelocity.y * stepDt;
    activeModel.rotation.z += entranceAngularVelocity.z * stepDt;

    entranceScaleVelocity += (
      (flowMotionTargetScale - entranceScale) * FLOW_SCALE_SPRING -
      entranceScaleVelocity * FLOW_SCALE_DAMPING
    ) * stepDt;
    entranceScale += entranceScaleVelocity * stepDt;
    activeModel.scale.setScalar(entranceScale);
    remainingDt -= stepDt;
  }

  const positionSettled = activeModel.position.distanceToSquared(flowMotionTargetPosition) <
      0.00015 &&
    entranceVelocity.lengthSq() < 0.0064;
  const rotationSettled = Math.abs(activeModel.rotation.x - flowMotionTargetRotation.x) < 0.008 &&
    Math.abs(activeModel.rotation.y - flowMotionTargetRotation.y) < 0.008 &&
    Math.abs(activeModel.rotation.z - flowMotionTargetRotation.z) < 0.008 &&
    Math.abs(entranceAngularVelocity.x - flowMotionTargetAngularVelocity.x) < 0.06 &&
    Math.abs(entranceAngularVelocity.y - flowMotionTargetAngularVelocity.y) < 0.06 &&
    Math.abs(entranceAngularVelocity.z - flowMotionTargetAngularVelocity.z) < 0.06;
  const scaleSettled = Math.abs(entranceScale - flowMotionTargetScale) <
      flowMotionTargetScale * 0.0025 &&
    Math.abs(entranceScaleVelocity) < flowMotionTargetScale * 0.02;
  return positionSettled && rotationSettled && scaleSettled;
}

function updatePhysicsEntrance(now, dt, homeY, homeScale, reducedMotion) {
  if (reducedMotion) {
    finishPhysicsEntrance(now, homeY, homeScale, true);
  } else if (stepFlowMotionPhysics(dt)) {
    finishPhysicsEntrance(now, homeY, homeScale);
  }
}

function screenToFlowWorld(clientX, clientY, target, z = 0) {
  if (!camera) return target.set(0, 0, z);
  const viewHeight = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5)) *
    Math.abs(camera.position.z - z);
  return target.set(
    ((clientX / window.innerWidth) * 2 - 1) * viewHeight * camera.aspect * 0.5,
    (1 - (clientY / window.innerHeight) * 2) * viewHeight * 0.5,
    z
  );
}

function flowWorldBounds(z = 0) {
  const halfHeight = Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5)) *
    Math.abs(camera.position.z - z);
  return { halfWidth: halfHeight * camera.aspect, halfHeight };
}

function clampCartridgeTarget(target) {
  const { halfWidth, halfHeight } = flowWorldBounds(target.z);
  const radius = 0.5;
  target.x = THREE.MathUtils.clamp(target.x, -halfWidth + radius, halfWidth - radius);
  target.y = THREE.MathUtils.clamp(target.y, -halfHeight + radius, halfHeight - radius);
  return target;
}

function pointerHitsCartridge(clientX, clientY) {
  if (!camera || !activeModel || activeModelKind !== 'cartridge' || !activeModel.visible) {
    return false;
  }
  cartridgePointerNdc.set(
    (clientX / window.innerWidth) * 2 - 1,
    -(clientY / window.innerHeight) * 2 + 1
  );
  activeModel.updateMatrixWorld(true);
  camera.updateMatrixWorld(true);
  cartridgeRaycaster.setFromCamera(cartridgePointerNdc, camera);
  return cartridgeRaycaster.intersectObject(activeModel, true).length > 0;
}

function setCartridgeHovered(value) {
  cartridgeHovered = value;
  overlay?.classList.toggle('is-cartridge-hovered', value);
}

function resetCartridgeInteraction() {
  cartridgePressed = false;
  cartridgeDragging = false;
  cartridgeDragPointerId = null;
  cartridgeDragDistance = 0;
  cartridgeLastPointerTime = 0;
  cartridgePhysicsReady = false;
  cartridgeYaw = CARTRIDGE_FRONT_YAW;
  cartridgeYawVelocity = CARTRIDGE_IDLE_SPIN_SPEED;
  cartridgeFaceTurnActive = false;
  cartridgeFaceTurnTarget = CARTRIDGE_FRONT_YAW;
  cartridgeHoverAmount = 0;
  cartridgePressAmount = 0;
  cartridgePhysicsPosition.set(0, 0, 0);
  cartridgeVelocity.set(0, 0, 0);
  cartridgeDragTarget.set(0, 0, 0);
  cartridgePointerVelocity.set(0, 0, 0);
  cartridgeTilt.x = 0;
  cartridgeTilt.z = 0;
  cartridgeTilt.vx = 0;
  cartridgeTilt.vz = 0;
  setCartridgeHovered(false);
  overlay?.classList.remove('is-cartridge-dragging');
}

function startCartridgeFaceTurn() {
  let frontDelta = Math.atan2(
    Math.sin(CARTRIDGE_FRONT_YAW - cartridgeYaw),
    Math.cos(CARTRIDGE_FRONT_YAW - cartridgeYaw)
  );
  while (frontDelta <= Math.PI) frontDelta += Math.PI * 2;
  cartridgeFaceTurnTarget = cartridgeYaw + frontDelta;
  cartridgeFaceTurnActive = true;
  cartridgeYawVelocity = Math.max(
    Math.abs(cartridgeYawVelocity), CARTRIDGE_FACE_TURN_LAUNCH_SPEED
  );
}

function resolveCartridgeViewportBounce() {
  const { halfWidth, halfHeight } = flowWorldBounds(cartridgePhysicsPosition.z);
  const radius = 0.5;
  const left = -halfWidth + radius;
  const right = halfWidth - radius;
  const bottom = -halfHeight + radius;
  const top = halfHeight - radius;

  if (cartridgePhysicsPosition.x < left || cartridgePhysicsPosition.x > right) {
    const side = cartridgePhysicsPosition.x < left ? left : right;
    const movingOutward = cartridgePhysicsPosition.x < left
      ? cartridgeVelocity.x < 0
      : cartridgeVelocity.x > 0;
    cartridgePhysicsPosition.x = side;
    if (movingOutward) cartridgeVelocity.x *= -0.56;
    cartridgeVelocity.y *= 0.86;
  }
  if (cartridgePhysicsPosition.y < bottom || cartridgePhysicsPosition.y > top) {
    const side = cartridgePhysicsPosition.y < bottom ? bottom : top;
    const movingOutward = cartridgePhysicsPosition.y < bottom
      ? cartridgeVelocity.y < 0
      : cartridgeVelocity.y > 0;
    cartridgePhysicsPosition.y = side;
    if (movingOutward) cartridgeVelocity.y *= -0.56;
    cartridgeVelocity.x *= 0.86;
  }
}

function updateCartridgePhysics(now, dt, homeY, homeScale) {
  if (!cartridgePhysicsReady) {
    cartridgePhysicsPosition.set(activeModel.position.x, activeModel.position.y, 0);
    cartridgeDragTarget.copy(cartridgePhysicsPosition);
    cartridgeVelocity.set(0, 0, 0);
    cartridgePhysicsReady = true;
  }

  const idleTime = now / 1000;
  if (cartridgeDragging) cartridgeSpringTarget.copy(cartridgeDragTarget);
  else cartridgeSpringTarget.set(0, homeY + Math.sin(idleTime * 1.7) * 0.045, 0);
  const speed = cartridgeVelocity.length();
  const spring = cartridgeDragging ? 105 : 54;
  const linearDrag = cartridgeDragging ? 15 : 6.5;
  const airDrag = linearDrag + speed * 0.3;
  cartridgeVelocity.x += (
    (cartridgeSpringTarget.x - cartridgePhysicsPosition.x) * spring -
    cartridgeVelocity.x * airDrag
  ) * dt;
  cartridgeVelocity.y += (
    (cartridgeSpringTarget.y - cartridgePhysicsPosition.y) * spring -
    cartridgeVelocity.y * airDrag
  ) * dt;
  cartridgeVelocity.z += (
    (cartridgeSpringTarget.z - cartridgePhysicsPosition.z) * spring -
    cartridgeVelocity.z * airDrag
  ) * dt;
  cartridgePhysicsPosition.addScaledVector(cartridgeVelocity, dt);
  resolveCartridgeViewportBounce();
  activeModel.position.copy(cartridgePhysicsPosition);

  const hovering = cartridgeHovered || cartridgeDragging;
  cartridgeHoverAmount += ((hovering ? 1 : 0) - cartridgeHoverAmount) *
    Math.min(1, dt * 9);
  cartridgePressAmount += ((cartridgePressed ? 1 : 0) - cartridgePressAmount) *
    Math.min(1, dt * 14);

  if (cartridgeFaceTurnActive) {
    const error = cartridgeFaceTurnTarget - cartridgeYaw;
    cartridgeYawVelocity += (
      error * CARTRIDGE_FACE_TURN_SPRING -
      cartridgeYawVelocity * CARTRIDGE_FACE_TURN_DAMPING
    ) * dt;
    cartridgeYaw += cartridgeYawVelocity * dt;
    if (Math.abs(error) < 0.002 && Math.abs(cartridgeYawVelocity) < 0.025) {
      cartridgeYaw = cartridgeFaceTurnTarget;
      cartridgeYawVelocity = 0;
      cartridgeFaceTurnActive = false;
    }
  } else {
    if (hovering) {
      const error = Math.atan2(
        Math.sin(CARTRIDGE_FRONT_YAW - cartridgeYaw),
        Math.cos(CARTRIDGE_FRONT_YAW - cartridgeYaw)
      );
      cartridgeYawVelocity += (error * 46 - cartridgeYawVelocity * 9.2) * dt;
    } else {
      cartridgeYawVelocity += (CARTRIDGE_IDLE_SPIN_SPEED - cartridgeYawVelocity) *
        Math.min(1, dt * 2.8);
    }
    cartridgeYaw += cartridgeYawVelocity * dt;
  }
  if (Math.abs(cartridgeYaw) > Math.PI * 200) {
    cartridgeYaw = CARTRIDGE_FRONT_YAW + Math.atan2(
      Math.sin(cartridgeYaw - CARTRIDGE_FRONT_YAW),
      Math.cos(cartridgeYaw - CARTRIDGE_FRONT_YAW)
    );
  }

  const tiltTargetX = THREE.MathUtils.clamp(cartridgeVelocity.y * 0.085, -0.2, 0.2);
  const tiltTargetZ = THREE.MathUtils.clamp(-cartridgeVelocity.x * 0.11, -0.34, 0.34);
  cartridgeTilt.vx += ((tiltTargetX - cartridgeTilt.x) * 62 -
    cartridgeTilt.vx * 8.2) * dt;
  cartridgeTilt.vz += ((tiltTargetZ - cartridgeTilt.z) * 62 -
    cartridgeTilt.vz * 8.2) * dt;
  cartridgeTilt.x += cartridgeTilt.vx * dt;
  cartridgeTilt.z += cartridgeTilt.vz * dt;

  activeModel.rotation.set(
    -0.08 + cartridgeTilt.x - cartridgePressAmount * 0.1 +
      Math.sin(idleTime * 1.1) * 0.02,
    cartridgeYaw,
    cartridgeTilt.z + Math.sin(idleTime * 1.35) * 0.02
  );
  activeModel.scale.setScalar(homeScale * (
    1 + cartridgeHoverAmount * 0.055 - cartridgePressAmount * 0.035
  ));
}

function updateCartridgeDrag(event, trackVelocity = true) {
  screenToFlowWorld(event.clientX, event.clientY, cartridgePointerWorld);
  const now = event.timeStamp || performance.now();
  if (trackVelocity && cartridgeLastPointerTime) {
    const sampleDt = Math.max((now - cartridgeLastPointerTime) / 1000, 1 / 240);
    const blend = Math.min(1, sampleDt * 18);
    cartridgePointerVelocity.lerp(
      cartridgePointerDelta.copy(cartridgePointerWorld)
        .sub(cartridgePreviousPointerWorld)
        .divideScalar(sampleDt),
      blend
    );
  }
  cartridgePreviousPointerWorld.copy(cartridgePointerWorld);
  cartridgeLastPointerTime = now;
  cartridgeDragTarget.copy(cartridgePointerWorld).add(cartridgeDragOffset);
  cartridgeDragTarget.z = 0;
  clampCartridgeTarget(cartridgeDragTarget);
}

function beginCartridgeDrag(event) {
  cartridgeDragging = true;
  cartridgeLastPointerTime = 0;
  cartridgePointerVelocity.set(0, 0, 0);
  screenToFlowWorld(event.clientX, event.clientY, cartridgePointerWorld);
  cartridgeDragOffset.copy(cartridgePhysicsPosition).sub(cartridgePointerWorld);
  cartridgeDragOffset.z = 0;
  cartridgePreviousPointerWorld.copy(cartridgePointerWorld);
  updateCartridgeDrag(event, false);
  overlay?.classList.add('is-cartridge-dragging');
}

function finishCartridgePointer(event, cancelled = false) {
  if (event.pointerId !== cartridgeDragPointerId) return;
  if (cartridgeDragging && !cancelled) {
    updateCartridgeDrag(event);
    cartridgeVelocity.addScaledVector(cartridgePointerVelocity, 0.24);
    startCartridgeFaceTurn();
  } else if (!cancelled && cartridgePressed) {
    startCartridgeFaceTurn();
  }
  cartridgePressed = false;
  cartridgeDragging = false;
  cartridgeDragPointerId = null;
  overlay?.classList.remove('is-cartridge-dragging');
  if (overlay?.hasPointerCapture(event.pointerId)) {
    overlay.releasePointerCapture(event.pointerId);
  }
}

function easeOutCubic(value) {
  return 1 - Math.pow(1 - THREE.MathUtils.clamp(value, 0, 1), 3);
}

function easeInOutCubic(value) {
  const amount = THREE.MathUtils.clamp(value, 0, 1);
  return amount < 0.5
    ? 4 * amount * amount * amount
    : 1 - Math.pow(-2 * amount + 2, 3) / 2;
}

function springArrivalProgress(value) {
  const amount = THREE.MathUtils.clamp(value, 0, 1);
  const riseEnd = 0.8;
  if (amount < riseEnd) {
    return easeInOutCubic(amount / riseEnd) * 1.04;
  }
  const settle = (amount - riseEnd) / (1 - riseEnd);
  return 1 + Math.cos(settle * Math.PI * 2) * 0.04 *
    Math.pow(1 - settle, 2);
}

function clearConsoleDockTransition() {
  if (!consoleDockAssembly) return;
  if (consoleDockModel) consoleDockModel.visible = false;
  scene?.remove(consoleDockAssembly);
  consoleDockAssembly = null;
  consoleDockModel = null;
}

function finishConsoleDockTransition() {
  const completion = flowMotionCompletion;
  flowMotionCompletion = null;
  clearConsoleDockTransition();
  activeModel = null;
  activeModelKind = 'none';
  visualPhase = 'departed';
  completion?.();
}

async function beginConsoleDockTransition(completion) {
  if (!activeModel || activeModelKind !== 'cartridge') {
    completion?.();
    return;
  }
  requestedModelKind = 'console-dock';

  let consoleModel;
  try {
    consoleModel = await consolePromise;
  } catch (error) {
    console.error('Could not load the console model; using the standard transition.', error);
    beginModelExit(completion);
    return;
  }
  if (requestedModelKind !== 'console-dock' || !scene || overlay?.hidden) return;

  cartridgePressed = false;
  cartridgeDragging = false;
  cartridgeDragPointerId = null;
  setCartridgeHovered(false);
  overlay?.classList.remove('is-cartridge-dragging');

  consoleDockAssembly = new THREE.Group();
  consoleDockAssembly.name = 'ConsoleDockAssembly';
  scene.add(consoleDockAssembly);
  consoleDockAssembly.attach(activeModel);
  consoleDockModel = consoleModel;
  consoleDockAssembly.add(consoleDockModel);
  consoleDockModel.visible = true;

  consoleDockAssembly.position.set(0, 0, 0);
  consoleDockAssembly.quaternion.identity();
  consoleDockAssembly.scale.setScalar(1);
  consoleDockCartridgeStartPosition.copy(activeModel.position);
  consoleDockCartridgeStartQuaternion.copy(activeModel.quaternion);
  consoleDockCartridgeStartScale = activeModel.scale.x;
  consoleDockCartridgeTargetPosition.set(0, activeModel.userData.homeY - 0.18, 0);
  consoleDockCartridgeTargetQuaternion.setFromEuler(
    new THREE.Euler(CONSOLE_DOCK_FRONT_PITCH, CONSOLE_DOCK_FRONT_YAW, 0)
  );
  consoleDockCartridgeTargetScale = activeModel.userData.homeScale;
  consoleDockConsoleScale = consoleDockCartridgeTargetScale /
    CONSOLE_CARTRIDGE_FIT_SCALE;

  consoleDockAnchorOffset.copy(consoleDockModel.userData.snapAnchor)
    .multiplyScalar(consoleDockConsoleScale)
    .applyQuaternion(consoleDockCartridgeTargetQuaternion);
  consoleDockConsoleTargetPosition.copy(consoleDockCartridgeTargetPosition)
    .sub(consoleDockAnchorOffset);
  consoleDockAnchorOffset.copy(consoleDockModel.userData.mouthAnchor)
    .multiplyScalar(consoleDockConsoleScale)
    .applyQuaternion(consoleDockCartridgeTargetQuaternion);
  consoleDockCartridgeReadyPosition.copy(consoleDockConsoleTargetPosition)
    .add(consoleDockAnchorOffset);
  consoleDockCartridgeReadyPosition.y += CONSOLE_CARTRIDGE_READY_CLEARANCE;
  consoleDockCartridgeInsertionVector.copy(consoleDockCartridgeTargetPosition)
    .sub(consoleDockCartridgeReadyPosition);
  consoleDockCartridgeWindupPosition.copy(consoleDockCartridgeReadyPosition)
    .add(new THREE.Vector3(0.46, 0.52, 0.08));
  consoleDockCartridgeWindupQuaternion.copy(consoleDockCartridgeTargetQuaternion)
    .multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.1, 0, -0.32)));
  consoleDockConsoleStartPosition.copy(consoleDockConsoleTargetPosition)
    .add(new THREE.Vector3(0.12, -5.2, -0.22));
  consoleDockConsoleTargetQuaternion.copy(consoleDockCartridgeTargetQuaternion);
  consoleDockConsoleStartQuaternion.copy(consoleDockConsoleTargetQuaternion)
    .multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.58, 0.08, -0.06)));
  consoleDockModel.position.copy(consoleDockConsoleStartPosition);
  consoleDockModel.quaternion.copy(consoleDockConsoleStartQuaternion);
  consoleDockModel.scale.setScalar(consoleDockConsoleScale);

  flowMotionCompletion = completion;
  visualPhase = 'console-dock';
  visualStartedAt = performance.now();
  lastFlowFrameAt = 0;
  startFlowAnimation();
}

function updateConsoleDockTransition(now, reducedMotion) {
  if (!consoleDockAssembly || !consoleDockModel || !activeModel) return 1;
  const elapsed = reducedMotion ? CONSOLE_DOCK_MS : Math.max(0, now - visualStartedAt);
  const approach = springArrivalProgress(elapsed / CONSOLE_APPROACH_MS);
  consoleDockModel.position.lerpVectors(
    consoleDockConsoleStartPosition,
    consoleDockConsoleTargetPosition,
    approach
  );
  consoleDockModel.quaternion.slerpQuaternions(
    consoleDockConsoleStartQuaternion,
    consoleDockConsoleTargetQuaternion,
    approach
  );

  const windupStartedAt = CONSOLE_APPROACH_MS + CONSOLE_IDLE_MS;
  const suspenseStartedAt = windupStartedAt + CONSOLE_WINDUP_MS;
  const slamStartedAt = suspenseStartedAt + CONSOLE_SUSPENSE_MS;
  const slam = THREE.MathUtils.clamp((elapsed - slamStartedAt) / CONSOLE_SLAM_MS, 0, 1);
  const impactPoint = 0.68;

  if (elapsed < CONSOLE_APPROACH_MS) {
    const cartridgeAlign = easeOutCubic(elapsed / CONSOLE_APPROACH_MS);
    activeModel.position.lerpVectors(
      consoleDockCartridgeStartPosition,
      consoleDockCartridgeReadyPosition,
      cartridgeAlign
    );
    activeModel.quaternion.slerpQuaternions(
      consoleDockCartridgeStartQuaternion,
      consoleDockCartridgeTargetQuaternion,
      cartridgeAlign
    );
    activeModel.scale.setScalar(THREE.MathUtils.lerp(
      consoleDockCartridgeStartScale,
      consoleDockCartridgeTargetScale,
      cartridgeAlign
    ));
  } else if (elapsed < windupStartedAt) {
    const idleTime = (elapsed - CONSOLE_APPROACH_MS) / 1000;
    const idleBob = Math.sin(idleTime * Math.PI * 1.5) * 0.025;
    activeModel.position.copy(consoleDockCartridgeReadyPosition);
    activeModel.position.y += idleBob;
    activeModel.quaternion.copy(consoleDockCartridgeTargetQuaternion);
    activeModel.scale.setScalar(consoleDockCartridgeTargetScale);
    consoleDockModel.position.y += idleBob * 0.35;
  } else if (elapsed < suspenseStartedAt) {
    const windup = easeInOutCubic(
      (elapsed - windupStartedAt) / CONSOLE_WINDUP_MS
    );
    activeModel.position.lerpVectors(
      consoleDockCartridgeReadyPosition,
      consoleDockCartridgeWindupPosition,
      windup
    );
    activeModel.position.y += Math.sin(windup * Math.PI) * 0.16;
    activeModel.quaternion.slerpQuaternions(
      consoleDockCartridgeTargetQuaternion,
      consoleDockCartridgeWindupQuaternion,
      windup
    );
    activeModel.scale.setScalar(consoleDockCartridgeTargetScale * (
      1 + Math.sin(windup * Math.PI) * 0.055
    ));
  } else if (elapsed < slamStartedAt) {
    const suspense = (elapsed - suspenseStartedAt) / CONSOLE_SUSPENSE_MS;
    activeModel.position.copy(consoleDockCartridgeWindupPosition);
    activeModel.position.y += Math.sin(suspense * Math.PI) * 0.018;
    activeModel.quaternion.copy(consoleDockCartridgeWindupQuaternion);
    activeModel.scale.setScalar(consoleDockCartridgeTargetScale * 1.02);
  } else if (slam < impactPoint) {
    const acceleration = Math.pow(slam / impactPoint, 3);
    activeModel.position.lerpVectors(
      consoleDockCartridgeWindupPosition,
      consoleDockCartridgeTargetPosition,
      acceleration
    );
    activeModel.quaternion.slerpQuaternions(
      consoleDockCartridgeWindupQuaternion,
      consoleDockCartridgeTargetQuaternion,
      acceleration
    );
    activeModel.scale.setScalar(consoleDockCartridgeTargetScale * (
      1.02 - acceleration * 0.06
    ));
  } else {
    const settle = (slam - impactPoint) / (1 - impactPoint);
    const rebound = Math.sin(settle * Math.PI * 2.2) *
      Math.exp(-settle * 4.5) * 0.22;
    activeModel.position.copy(consoleDockCartridgeTargetPosition)
      .addScaledVector(consoleDockCartridgeInsertionVector, rebound);
    activeModel.quaternion.copy(consoleDockCartridgeTargetQuaternion);
    activeModel.scale.setScalar(consoleDockCartridgeTargetScale * (
      1 + Math.sin(settle * Math.PI * 2) * Math.exp(-settle * 4) * 0.04
    ));
  }
  if (slam >= 1) {
    activeModel.position.copy(consoleDockCartridgeTargetPosition);
    activeModel.quaternion.copy(consoleDockCartridgeTargetQuaternion);
    activeModel.scale.setScalar(consoleDockCartridgeTargetScale);
  }

  const retreat = easeInOutCubic(
    (elapsed - CONSOLE_RETREAT_START_MS) /
      (CONSOLE_DOCK_MS - CONSOLE_RETREAT_START_MS)
  );
  consoleDockAssembly.position.lerpVectors(
    consoleDockAssemblyOriginPosition,
    consoleDockAssemblyTargetPosition,
    retreat
  );
  consoleDockAssembly.quaternion.slerpQuaternions(
    consoleDockAssemblyOriginQuaternion,
    consoleDockAssemblyTargetQuaternion,
    retreat
  );
  consoleDockAssembly.scale.setScalar(THREE.MathUtils.lerp(1, 0.54, retreat));

  const impactAt = slamStartedAt + CONSOLE_SLAM_MS * impactPoint;
  const shakeElapsed = elapsed - impactAt;
  if (shakeElapsed >= 0 && shakeElapsed < 360) {
    const shakeEnvelope = Math.exp(-shakeElapsed / 105) * (1 - shakeElapsed / 360);
    consoleDockAssembly.position.x += Math.sin(shakeElapsed * 0.12) *
      0.055 * shakeEnvelope;
    consoleDockAssembly.position.y += Math.sin(shakeElapsed * 0.17 + 0.9) *
      0.035 * shakeEnvelope;
    consoleDockAssembly.rotateZ(
      Math.sin(shakeElapsed * 0.14 + 0.4) * 0.018 * shakeEnvelope
    );
  }

  if (elapsed >= CONSOLE_DOCK_MS) finishConsoleDockTransition();
  return 1 - retreat;
}

function beginPhysicalDeparture(direction, completion) {
  if (!activeModel) return;
  const controllerDeparture = activeModelKind === 'controller';
  const controllerExit = direction > 0 && controllerDeparture;
  const departureDirection = controllerExit ? -1 : direction;
  cartridgePressed = false;
  cartridgeDragging = false;
  cartridgeDragPointerId = null;
  setCartridgeHovered(false);
  overlay?.classList.remove('is-cartridge-dragging');
  flowMotionStartPosition.copy(activeModel.position);
  flowMotionTargetPosition.set(0, departureDirection * 5.3, 0);
  entranceVelocity.set(0, departureDirection * 1.2, 0);
  if (activeModelKind === 'cartridge') {
    entranceVelocity.add(cartridgeVelocity);
  }
  entranceAngularVelocity.set(0, controllerDeparture ? 0 : direction * 2.2, 0);
  flowMotionTargetAngularVelocity.set(0, 0, 0);
  entranceScale = activeModel.scale.x;
  entranceScaleVelocity = 0;
  flowMotionTargetScale = controllerDeparture
    ? activeModel.scale.x
    : activeModel.userData.homeScale * 0.76;
  if (controllerDeparture) {
    flowMotionTargetRotation.copy(activeModel.rotation);
  } else if (direction < 0) {
    flowMotionTargetRotation.set(0.18, activeModel.rotation.y - Math.PI * 4, -0.16);
  } else if (activeModelKind === 'cartridge') {
    flowMotionTargetRotation.set(-0.18, activeModel.rotation.y + Math.PI * 2, 0.12);
  } else {
    flowMotionTargetRotation.set(1.58, 0.06, 0);
  }
  flowMotionCompletion = completion;
  visualPhase = direction < 0 ? 'reverse' : 'exit';
  visualStartedAt = performance.now();
  startFlowAnimation();
}

function finishPhysicalDeparture() {
  activeModel.position.copy(flowMotionTargetPosition);
  activeModel.rotation.set(
    flowMotionTargetRotation.x,
    flowMotionTargetRotation.y,
    flowMotionTargetRotation.z
  );
  activeModel.scale.setScalar(flowMotionTargetScale);
  activeModel.visible = false;
  visualPhase = 'departed';
  const completion = flowMotionCompletion;
  flowMotionCompletion = null;
  completion?.();
}

function updatePhysicalDeparture(dt, reducedMotion) {
  const controllerExit = activeModelKind === 'controller' && visualPhase === 'exit';
  const totalDistance = Math.max(
    0.001,
    flowMotionStartPosition.distanceTo(flowMotionTargetPosition)
  );
  const settled = reducedMotion || stepFlowMotionPhysics(dt);
  const progress = 1 - THREE.MathUtils.clamp(
    activeModel.position.distanceTo(flowMotionTargetPosition) / totalDistance,
    0,
    1
  );
  if (settled || progress >= 0.94) finishPhysicalDeparture();
  if (controllerExit) return 1;
  return 1 - THREE.MathUtils.clamp((progress - 0.68) / 0.26, 0, 1);
}

function beginModelReverse(completion) {
  beginPhysicalDeparture(-1, completion);
}

async function showFlowModel(kind, phase = 'enter') {
  ensureFlowRenderer();
  requestedModelKind = kind;
  overlay?.classList.remove('is-model-settled');
  const model = await (kind === 'cartridge' ? cartridgePromise : controllerPromise);
  if (requestedModelKind !== kind || !scene) return;
  if (activeModel) scene.remove(activeModel);
  activeModel = model;
  activeModelKind = kind;
  modelRestedAt = 0;
  fitFlowModelToViewport(activeModel, kind);
  activeModel.visible = true;
  if (kind === 'cartridge') resetCartridgeInteraction();
  else resetControllerPhysics();
  configureEntrancePhysics(activeModel, kind);
  if (flowCanvas) flowCanvas.style.opacity = '1';
  scene.add(activeModel);
  visualPhase = phase;
  visualStartedAt = performance.now();
  lastFlowFrameAt = 0;
  startFlowAnimation();
}

function startFlowAnimation() {
  if (!animationFrame) animationFrame = requestAnimationFrame(renderFlow);
}

function stopFlowAnimation() {
  if (animationFrame) cancelAnimationFrame(animationFrame);
  animationFrame = 0;
  lastFlowFrameAt = 0;
}

function renderFlow(now) {
  animationFrame = 0;
  if (!renderer || !scene || !camera || overlay?.hidden) return;
  const dt = lastFlowFrameAt
    ? Math.min(1 / 20, Math.max(1 / 240, (now - lastFlowFrameAt) / 1000))
    : 1 / 60;
  lastFlowFrameAt = now;

  if (activeModel) {
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const elapsed = Math.max(0, now - visualStartedAt);
    const homeY = activeModel.userData.homeY;
    const homeScale = activeModel.userData.homeScale;
    let opacity = 1;

    if (visualPhase === 'enter') {
      updatePhysicsEntrance(now, dt, homeY, homeScale, reducedMotion);
    } else if (visualPhase === 'console-dock') {
      opacity = updateConsoleDockTransition(now, reducedMotion);
    } else if (visualPhase === 'exit' || visualPhase === 'reverse') {
      opacity = updatePhysicalDeparture(dt, reducedMotion);
    } else if (visualPhase === 'idle') {
      const idleTime = elapsed / 1000;
      if (activeModelKind === 'cartridge') {
        updateCartridgePhysics(now, dt, homeY, homeScale);
      } else {
        updateControllerPhysics(now, dt, homeY, homeScale, reducedMotion);
      }
      if (!overlay?.classList.contains('is-model-settled')) {
        const cartridgeAtRest = activeModelKind !== 'cartridge' || (
          !cartridgeDragging && !cartridgePressed &&
          Math.abs(cartridgePhysicsPosition.x) < 0.05 &&
          Math.abs(cartridgePhysicsPosition.y - homeY) < 0.1 &&
          cartridgeVelocity.lengthSq() < 0.09
        );
        if (cartridgeAtRest) {
          if (!modelRestedAt) modelRestedAt = now;
          const settleDelay = reducedMotion ? 0 : 140;
          if (now - modelRestedAt >= settleDelay) {
            overlay?.classList.add('is-model-settled');
          }
        } else {
          modelRestedAt = 0;
        }
      }
    }
    flowCanvas.style.opacity = String(opacity);
  }

  updateControllerCallouts();

  renderer.setRenderTarget(flowRenderTarget);
  renderer.setClearColor(0x000000, 0);
  renderer.clear();
  renderer.render(scene, camera);
  renderer.setRenderTarget(null);
  renderer.render(flowPostScene, flowPostCamera);
  startFlowAnimation();
}

function beginModelExit(completion) {
  beginPhysicalDeparture(1, completion);
}

function resetRomPrompt() {
  validationBusy = false;
  if (fileInput) {
    fileInput.disabled = false;
    fileInput.value = '';
  }
  if (uploadButton) {
    uploadButton.disabled = false;
    uploadButton.textContent = 'Upload ROM';
  }
  if (cancelButton) cancelButton.disabled = false;
  if (formError) {
    formError.hidden = true;
    formError.textContent = '';
  }
}

function resetControlCheck() {
  controlCheckComplete = false;
  controlExitPending = false;
  completedControlKeys.clear();
  resetControllerPhysics();
  controlKeycaps.forEach(keycap => keycap.classList.remove('is-complete', 'is-pressed'));
  controlPrompt?.classList.remove('is-complete');
  if (controlPrompt) {
    controlPrompt.textContent = controlsPreviewMode
      ? 'Press the mapped keys to try the controls'
      : 'Press each key on your keyboard to continue';
  }
}

function registerControlKey(event) {
  if (!overlay || overlay.hidden || overlay.dataset.step !== 'controller' ||
      controlCheckComplete) return false;
  const key = event.key.toLowerCase();
  if (!REQUIRED_CONTROL_KEYS.includes(key)) return false;
  event.preventDefault();
  pressControllerControl(key, event.repeat);
  completedControlKeys.add(key);
  const keycap = controlKeycaps.find(item => item.dataset.controlKey === key);
  keycap?.classList.add('is-complete', 'is-pressed');
  if (completedControlKeys.size === REQUIRED_CONTROL_KEYS.length) {
    if (controlsPreviewMode) {
      controlPrompt?.classList.add('is-complete');
      if (controlPrompt) {
        controlPrompt.textContent = 'All controls tested — keep pressing keys or close';
      }
      return true;
    }
    controlCheckComplete = true;
    rememberCompletedControllerTutorial();
    controlPrompt?.classList.add('is-complete');
    clearTimeout(flowTimer);
    const flipInProgress = controllerZRevealUntil > performance.now() ||
      Math.abs(controllerFlip) >= 0.025 || Math.abs(controllerFlipVelocity) >= 0.12;
    if (flipInProgress) controlExitPending = true;
    else flowTimer = window.setTimeout(continueToGame, 360);
  }
  return true;
}

function showControlsPreview() {
  if (!overlay || !overlay.hidden) return;
  flowSequence += 1;
  clearTimeout(flowTimer);
  pendingFighter = null;
  previousFocus = document.activeElement;
  controlsPreviewMode = true;
  resetRomPrompt();
  resetControlCheck();
  overlay.dataset.mode = 'controls-preview';
  overlay.dataset.step = 'controller';
  modelRestedAt = 0;
  overlay.classList.remove('is-leaving', 'is-model-settled');
  overlay.hidden = false;
  document.body.classList.add('is-launch-flow-open');
  ensureFlowRenderer();
  showFlowModel('controller');
  requestAnimationFrame(() => {
    overlay.classList.add('is-visible');
    flowTimer = window.setTimeout(() => controllerStep?.focus(), 1150);
  });
}

function showRequiredControls(fighter) {
  if (!overlay || !overlay.hidden) return;
  flowSequence += 1;
  clearTimeout(flowTimer);
  pendingFighter = fighter;
  previousFocus = document.activeElement;
  controlsPreviewMode = false;
  resetRomPrompt();
  resetControlCheck();
  overlay.dataset.mode = 'launch';
  overlay.dataset.step = 'controller';
  modelRestedAt = 0;
  overlay.classList.remove('is-leaving', 'is-model-settled');
  overlay.hidden = false;
  document.body.classList.add('is-launch-flow-open');
  ensureFlowRenderer();
  showFlowModel('controller');
  requestAnimationFrame(() => {
    overlay.classList.add('is-visible');
    flowTimer = window.setTimeout(() => controllerStep?.focus(), 1150);
  });
}

function showLaunchFlow(fighter, { create = false } = {}) {
  if (!overlay || !overlay.hidden) return;
  flowSequence += 1;
  clearTimeout(flowTimer);
  pendingFighter = fighter;
  previousFocus = document.activeElement;
  controlsPreviewMode = false;
  createUploadMode = create;
  resetRomPrompt();
  resetControlCheck();
  if (flowTitle) flowTitle.textContent = create ? 'Create a fighter' : 'Play Smash the Weights';
  if (flowCopy) {
    flowCopy.textContent = create
      ? 'To create a fighter upload your legally obtained Super Smash Bros 64 ROM. ' +
        'It is normalized and hashed locally and never uploaded.'
      : 'To play Smash the Weights upload your legally obtained Super Smash Bros 64 ROM. ' +
        'It is normalized and hashed locally and never uploaded.';
  }
  overlay.dataset.mode = create ? 'create' : 'launch';
  overlay.dataset.step = 'upload';
  modelRestedAt = 0;
  overlay.classList.remove('is-leaving', 'is-model-settled');
  overlay.hidden = false;
  document.body.classList.add('is-launch-flow-open');
  ensureFlowRenderer();
  showFlowModel('cartridge');
  requestAnimationFrame(() => {
    overlay.classList.add('is-visible');
    flowTimer = window.setTimeout(() => uploadButton?.focus(), 1250);
  });
}

function finishClosingFlow(sequence, restoreFocus) {
  if (!overlay || sequence !== flowSequence) return;
  flowMotionCompletion = null;
  clearConsoleDockTransition();
  overlay.hidden = true;
  modelRestedAt = 0;
  overlay.classList.remove('is-visible', 'is-leaving', 'is-model-settled');
  overlay.dataset.mode = 'launch';
  overlay.dataset.step = 'upload';
  document.body.classList.remove('is-launch-flow-open');
  requestedModelKind = 'none';
  if (activeModel) activeModel.visible = false;
  stopFlowAnimation();
  resetCartridgeInteraction();
  resetRomPrompt();
  controlsPreviewMode = false;
  createUploadMode = false;
  resetControlCheck();
  if (restoreFocus && previousFocus instanceof HTMLElement) previousFocus.focus();
  previousFocus = null;
}

function closeLaunchFlow(immediate = false) {
  if (!overlay || overlay.hidden) return;
  flowSequence += 1;
  const sequence = flowSequence;
  clearTimeout(flowTimer);
  pendingFighter = null;
  overlay.dataset.step = 'closing';
  if (immediate) {
    finishClosingFlow(sequence, false);
    return;
  }
  if (!activeModel || !activeModel.visible) {
    overlay.classList.add('is-leaving');
    flowTimer = window.setTimeout(
      () => finishClosingFlow(sequence, true), FLOW_FADE_MS
    );
    return;
  }
  beginModelReverse(() => {
    if (sequence !== flowSequence || overlay.hidden) return;
    overlay.classList.add('is-leaving');
    flowTimer = window.setTimeout(
      () => finishClosingFlow(sequence, true), FLOW_FADE_MS
    );
  });
}

function cancelLaunchFlow() {
  if (createUploadMode && APP_BRIDGE?.cancelCreateRom) {
    createUploadMode = false;
    closeLaunchFlow();
    APP_BRIDGE.cancelCreateRom();
    return;
  }
  closeLaunchFlow();
}

function transitionToController() {
  if (!overlay || overlay.hidden) return;
  const sequence = flowSequence;
  controlsPreviewMode = false;
  overlay.dataset.mode = 'launch';
  resetControlCheck();
  modelRestedAt = 0;
  overlay.classList.remove('is-model-settled');
  overlay.dataset.step = 'transition';
  beginConsoleDockTransition(() => {
    if (sequence !== flowSequence || overlay.hidden) return;
    overlay.dataset.step = 'controller';
    showFlowModel('controller');
    flowTimer = window.setTimeout(() => controllerStep?.focus(), 1150);
  });
}

async function validateRom(file) {
  if (!file || !pendingFighter || validationBusy) return;
  validationBusy = true;
  if (formError) {
    formError.hidden = true;
    formError.textContent = '';
  }
  if (fileInput) fileInput.disabled = true;
  if (cancelButton) cancelButton.disabled = true;
  if (uploadButton) {
    uploadButton.disabled = true;
    uploadButton.textContent = 'Validating locally…';
  }

  try {
    const bridgeValidator = createUploadMode
      ? APP_BRIDGE?.validateCreateRom
      : APP_BRIDGE?.validateRom;
    if (bridgeValidator) {
      await bridgeValidator(file, status => {
        if (!uploadButton) return;
        uploadButton.textContent = ({
          reading: 'Reading locally…',
          extracting: 'Extracting locally…',
          hashing: 'Normalizing & hashing…',
          validating: 'Checking ROM…',
        })[status] || 'Validating locally…';
      });
    } else {
      const buffer = await file.arrayBuffer();
      const digest = await crypto.subtle.digest('SHA-256', buffer);
      const hash = bytesToHex(new Uint8Array(digest));
      if (file.size !== ROM_SIZE || hash !== ROM_SHA256) {
        throw new Error('That file is not the supported Super Smash Bros. 64 ROM.');
      }
    }
    rememberVerifiedRom();
    if (createUploadMode) {
      APP_BRIDGE?.completeCreateRom?.();
      createUploadMode = false;
      closeLaunchFlow();
    } else if (!requiresControllerTutorial()) {
      const fighter = pendingFighter;
      launch(fighter);
      closeLaunchFlow(true);
    } else {
      transitionToController();
    }
  } catch (error) {
    validationBusy = false;
    if (fileInput) {
      fileInput.disabled = false;
      fileInput.value = '';
    }
    if (uploadButton) {
      uploadButton.disabled = false;
      uploadButton.textContent = 'Upload ROM';
    }
    if (cancelButton) cancelButton.disabled = false;
    if (formError) {
      formError.hidden = false;
      formError.textContent = error?.message || 'Could not validate that file.';
    }
    uploadButton?.focus();
  }
}

function continueToGame() {
  if (!overlay || !pendingFighter || overlay.dataset.step !== 'controller') return;
  const fighter = pendingFighter;
  flowSequence += 1;
  const sequence = flowSequence;
  clearTimeout(flowTimer);
  overlay.dataset.step = 'closing';
  completeControlsRoadblock();
  launch(fighter);
  beginModelExit(() => {
    if (sequence !== flowSequence || overlay.hidden) return;
    overlay.classList.add('is-leaving');
    flowTimer = window.setTimeout(
      () => finishClosingFlow(sequence, false), FLOW_FADE_MS
    );
  });
}

function requestLaunch(fighter) {
  if (!hasVerifiedRom()) {
    showLaunchFlow(fighter);
  } else if (requiresControllerTutorial()) {
    showRequiredControls(fighter);
  } else {
    launch(fighter);
  }
}

uploadButton?.addEventListener('click', () => {
  if (!validationBusy) fileInput?.click();
});
fileInput?.addEventListener('change', () => validateRom(fileInput.files?.[0]));
cancelButton?.addEventListener('click', () => {
  if (!validationBusy) cancelLaunchFlow();
});
controlsMenuButton?.addEventListener('click', () => {
  if (!usesMobileControls()) showControlsPreview();
});
controlsCloseButton?.addEventListener('click', () => closeLaunchFlow());

overlay?.addEventListener('pointerdown', event => {
  if (overlay.dataset.step !== 'upload' || visualPhase !== 'idle' || validationBusy) return;
  if (event.target instanceof Element && event.target.closest('button, input')) return;
  if (!pointerHitsCartridge(event.clientX, event.clientY)) return;
  cartridgePressed = true;
  cartridgeDragPointerId = event.pointerId;
  cartridgeDragDistance = 0;
  cartridgePointerStartX = event.clientX;
  cartridgePointerStartY = event.clientY;
  screenToFlowWorld(event.clientX, event.clientY, cartridgePointerWorld);
  cartridgePreviousPointerWorld.copy(cartridgePointerWorld);
  setCartridgeHovered(true);
  overlay.setPointerCapture(event.pointerId);
  event.preventDefault();
});

overlay?.addEventListener('pointermove', event => {
  if (event.pointerId === cartridgeDragPointerId) {
    cartridgeDragDistance = Math.max(
      cartridgeDragDistance,
      Math.hypot(
        event.clientX - cartridgePointerStartX,
        event.clientY - cartridgePointerStartY
      )
    );
    if (!cartridgeDragging && cartridgeDragDistance >= CARTRIDGE_DRAG_THRESHOLD) {
      beginCartridgeDrag(event);
    }
    if (cartridgeDragging) updateCartridgeDrag(event);
    return;
  }
  if (overlay.dataset.step === 'upload' && visualPhase === 'idle' && !validationBusy) {
    setCartridgeHovered(pointerHitsCartridge(event.clientX, event.clientY));
  }
});

overlay?.addEventListener('pointerup', event => {
  finishCartridgePointer(event);
  if (overlay.dataset.step === 'upload' && visualPhase === 'idle') {
    setCartridgeHovered(pointerHitsCartridge(event.clientX, event.clientY));
  }
});
overlay?.addEventListener('pointercancel', event => finishCartridgePointer(event, true));
overlay?.addEventListener('pointerleave', () => {
  if (!cartridgeDragging) setCartridgeHovered(false);
});
window.addEventListener('pointerup', event => finishCartridgePointer(event));

grid?.addEventListener('characterselect', event => {
  const fighter = fighterFromSelection(event.detail);
  if (fighter) {
    APP_BRIDGE?.announceCharacter?.(fighter.slug);
    requestLaunch(fighter);
  }
});

resetRomButton?.addEventListener('click', resetRom);
window.addEventListener('resize', resizeFlowRenderer);
window.addEventListener('keydown', event => {
  if (registerControlKey(event)) return;
  const dismissibleUpload = overlay?.dataset.step === 'upload' && !validationBusy;
  const dismissibleControls = controlsPreviewMode && overlay?.dataset.step === 'controller';
  if (event.key === 'Escape' && overlay && !overlay.hidden &&
      (dismissibleUpload || dismissibleControls)) {
    cancelLaunchFlow();
  }
});
window.addEventListener('keyup', event => {
  const key = event.key.toLowerCase();
  heldControlKeys.delete(key);
  controlKeycaps.find(item => item.dataset.controlKey === key)
    ?.classList.remove('is-pressed');
});
gameFrame?.addEventListener('load', () => {
  if (!videoFrame?.classList.contains('is-game-running')) return;
  keepPageScrollableFromGame();
  gameFrame.contentWindow?.focus();
});

window.gameLauncher = Object.freeze({
  get running() { return Boolean(videoFrame?.classList.contains('is-game-running')); },
  get verified() { return hasVerifiedRom(); },
  get mobileControls() { return usesMobileControls(); },
  get controlsCompleted() { return hasCompletedControllerTutorial(); },
  showControls: showControlsPreview,
  requestCreate() {
    showLaunchFlow({
      displayName: 'the fighter lab',
      slug: null,
      actionType: 'create',
      fkind: 0,
      bundle: null,
    }, { create: true });
  },
  requestCharacter(slug) {
    const character = APP_BRIDGE?.characters?.find(candidate => candidate.slug === slug);
    if (!character) return;
    requestLaunch({
      displayName: character.name,
      slug: character.slug,
      actionType: 'character',
      fkind: Number(character.fkind),
      bundle: character.bundle || null,
      selectionName: character.slug,
    });
  },
  request(actionType = 'select') {
    requestLaunch({
      displayName: actionType === 'start' ? 'the full game' : 'character select',
      slug: null,
      actionType,
      fkind: 0,
      bundle: null,
    });
  },
  close: closeGame,
  reset: resetRom,
  resetControls: resetControllerTutorial,
  sync: syncRomResetButton,
});

preloadFlowModels();
syncRomResetButton();
