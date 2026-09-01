import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import logoModelUrl from './assets/smash-the-weights-logo.glb?url';

const stage = document.getElementById('hero-logo-stage');
const canvas = document.getElementById('hero-logo-canvas');

if (stage && canvas) {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
    powerPreference: 'high-performance',
  });
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.18;

  // Match the hand cursor's low-resolution N64-style post-process. The hand
  // owns the live tuning object once its module has loaded; these defaults
  // cover the title's first frame and keep it usable as a standalone scene.
  const RETRO_SHADER_DEFAULTS = Object.freeze({
    enabled: true,
    pixelSize: 2,
    colorSteps: 12,
    posterize: 0.5,
    dither: 1,
    outlineWidth: 1,
    outlineStrength: 0.7,
    outlineColor: '#383838',
    gamma: 2.5,
  });
  const SHADER_STORAGE_KEY = 'opensmash.shader-tuning.v3';

  function loadRetroShaderSettings() {
    let stored = {};
    try { stored = JSON.parse(localStorage.getItem(SHADER_STORAGE_KEY) || '{}'); }
    catch (_) { /* Use the hand shader defaults if storage is unavailable. */ }
    const settings = { ...RETRO_SHADER_DEFAULTS };
    for (const key of ['pixelSize', 'colorSteps', 'posterize', 'dither',
                       'outlineWidth', 'outlineStrength', 'gamma']) {
      if (Number.isFinite(Number(stored[key]))) settings[key] = Number(stored[key]);
    }
    if (typeof stored.enabled === 'boolean') settings.enabled = stored.enabled;
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
      (value & 255) / 255,
    );
  }

  const fallbackShaderSettings = loadRetroShaderSettings();
  const logoTarget = new THREE.WebGLRenderTarget(4, 4, {
    minFilter: THREE.NearestFilter,
    magFilter: THREE.NearestFilter,
    generateMipmaps: false,
  });
  const postScene = new THREE.Scene();
  const postCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const postMaterial = new THREE.ShaderMaterial({
    transparent: true,
    uniforms: {
      tex: { value: logoTarget.texture },
      res: { value: new THREE.Vector2(4, 4) },
      colorSteps: { value: fallbackShaderSettings.colorSteps },
      posterize: { value: fallbackShaderSettings.posterize },
      dither: { value: fallbackShaderSettings.dither },
      outlineWidth: { value: fallbackShaderSettings.outlineWidth },
      outlineStrength: { value: fallbackShaderSettings.outlineStrength },
      outlineColor: { value: shaderColor(fallbackShaderSettings.outlineColor) },
      gamma: { value: fallbackShaderSettings.gamma },
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
  postScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), postMaterial));

  function currentShaderSettings() {
    return window.__shaderSettings || fallbackShaderSettings;
  }

  function syncPostMaterial(settings) {
    postMaterial.uniforms.colorSteps.value = settings.colorSteps;
    postMaterial.uniforms.posterize.value = settings.posterize;
    postMaterial.uniforms.dither.value = settings.dither;
    postMaterial.uniforms.outlineWidth.value = settings.outlineWidth;
    postMaterial.uniforms.outlineStrength.value = settings.outlineStrength;
    postMaterial.uniforms.outlineColor.value.copy(shaderColor(settings.outlineColor));
    postMaterial.uniforms.gamma.value = settings.gamma;
  }

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-5.45, 5.45, 2, -2, 0.1, 40);
  camera.position.set(0, 0, 12);
  camera.lookAt(0, 0, 0);

  scene.add(new THREE.HemisphereLight(0xfff6df, 0x28130d, 2.1));
  const keyLight = new THREE.DirectionalLight(0xfff0cc, 3.2);
  keyLight.position.set(-3.5, 5, 8);
  scene.add(keyLight);
  const rimLight = new THREE.DirectionalLight(0xff3218, 2.0);
  rimLight.position.set(5, -2, -3);
  scene.add(rimLight);
  // The hand cursor carries a white point light through the hardware scene.
  // Mirror it here because the logo is rendered in a separate WebGL scene.
  const cursorLight = new THREE.PointLight(0xffffff, 0, 0, 2);
  cursorLight.position.set(0, 0, 2.7);
  scene.add(cursorLight);

  const logoRoot = new THREE.Group();
  // The corner viewport is intentionally the same compact size as the static
  // overlay it replaces. Zoom the model within that viewport so the live GLB
  // occupies the full badge instead of retaining the old full-width stage's
  // large transparent margins.
  const LOGO_SCALE = (1 / 3) * 1.68 * 1.88;
  // Apply the final scale before the asynchronously loaded model is attached,
  // so there is no one-paint flash at the Group's default scale of 1.
  logoRoot.scale.setScalar(LOGO_SCALE);
  const faceCameraRotationX = Math.PI / 2;
  scene.add(logoRoot);
  let logoModel = null;
  let stageVisible = true;
  let previousFrameTime = 0;
  let pointerAvailable = false;
  let pointerClientX = window.innerWidth * 0.5;
  let pointerClientY = window.innerHeight * 0.5;
  let pointerX = 0;
  let pointerY = 0;
  let pointerProximity = 0;
  let logoPressed = false;
  let pressedPointerId = null;
  let pressAmount = 0;
  let halfViewWidth = 5.45;
  let halfViewHeight = 2;
  const cursorLightTarget = new THREE.Vector3(0, 0, 2.7);

  function smoothstep(edge0, edge1, value) {
    const amount = THREE.MathUtils.clamp((value - edge0) / (edge1 - edge0), 0, 1);
    return amount * amount * (3 - 2 * amount);
  }

  function rememberPointer(event) {
    if (event.pointerType === 'touch') return;
    pointerAvailable = true;
    pointerClientX = event.clientX;
    pointerClientY = event.clientY;
  }

  window.addEventListener('pointermove', rememberPointer, { passive: true });
  window.addEventListener('pointerdown', rememberPointer, { passive: true });
  document.addEventListener('pointerout', event => {
    if (!event.relatedTarget) pointerAvailable = false;
  });

  function pointerIsOverLogo(event) {
    const fallback = stage.querySelector('.hero-logo-fallback');
    const bounds = fallback?.getBoundingClientRect() || stage.getBoundingClientRect();
    return event.clientX >= bounds.left && event.clientX <= bounds.right &&
      event.clientY >= bounds.top && event.clientY <= bounds.bottom;
  }

  stage.addEventListener('pointerdown', event => {
    if ((event.pointerType === 'mouse' && event.button !== 0) ||
        !pointerIsOverLogo(event)) return;
    logoPressed = true;
    pressedPointerId = event.pointerId;
    // Ensure even a very quick click produces at least one visible press frame.
    pressAmount = Math.max(pressAmount, 0.12);
  }, { passive: true });

  function releaseLogo(event) {
    if (pressedPointerId !== null && event.pointerId !== pressedPointerId) return;
    logoPressed = false;
    pressedPointerId = null;
  }

  window.addEventListener('pointerup', releaseLogo, { passive: true });
  window.addEventListener('pointercancel', releaseLogo, { passive: true });
  window.addEventListener('blur', () => {
    logoPressed = false;
    pressedPointerId = null;
  });

  function resizeLogoRenderer() {
    const width = Math.max(1, stage.clientWidth);
    const height = Math.max(1, stage.clientHeight);
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    const outputWidth = Math.round(width * pixelRatio);
    const outputHeight = Math.round(height * pixelRatio);
    if (canvas.width !== outputWidth || canvas.height !== outputHeight) {
      renderer.setPixelRatio(pixelRatio);
      renderer.setSize(width, height, false);
    }

    const pixelSize = Math.max(1, currentShaderSettings().pixelSize);
    const lowWidth = Math.max(4, Math.round(width / pixelSize));
    const lowHeight = Math.max(4, Math.round(height / pixelSize));
    if (logoTarget.width !== lowWidth || logoTarget.height !== lowHeight) {
      logoTarget.setSize(lowWidth, lowHeight);
      postMaterial.uniforms.res.value.set(lowWidth, lowHeight);
    }

    halfViewWidth = 5.45;
    halfViewHeight = halfViewWidth / (width / height);
    camera.left = -halfViewWidth;
    camera.right = halfViewWidth;
    camera.top = halfViewHeight;
    camera.bottom = -halfViewHeight;
    camera.updateProjectionMatrix();
  }

  new GLTFLoader().load(
    logoModelUrl,
    gltf => {
      logoModel = gltf.scene;
      const bounds = new THREE.Box3().setFromObject(logoModel);
      const center = bounds.getCenter(new THREE.Vector3());
      logoModel.position.sub(center);
      logoModel.traverse(object => {
        if (!object.isMesh) return;
        object.frustumCulled = false;
        const materials = Array.isArray(object.material)
          ? object.material
          : [object.material];
        for (const material of materials) {
          if (!material) continue;
          material.side = THREE.DoubleSide;
          if (material.map) {
            material.map.colorSpace = THREE.SRGBColorSpace;
            material.map.anisotropy = renderer.capabilities.getMaxAnisotropy();
          }
        }
      });
      logoRoot.add(logoModel);
    },
    undefined,
    error => {
      stage.dataset.modelState = 'fallback';
      console.error('Could not load the Smash the Weights logo GLB', error);
    },
  );

  const observer = new IntersectionObserver(entries => {
    stageVisible = entries.some(entry => entry.isIntersecting);
  }, { rootMargin: '120px' });
  observer.observe(stage);

  function renderLogo(now) {
    requestAnimationFrame(renderLogo);
    if (!stageVisible) return;
    resizeLogoRenderer();
    const seconds = now * 0.001;
    const dt = previousFrameTime
      ? Math.min(0.05, (now - previousFrameTime) * 0.001)
      : 1 / 60;
    previousFrameTime = now;

    const bounds = stage.getBoundingClientRect();
    const centerX = bounds.left + bounds.width * 0.5;
    const centerY = bounds.top + bounds.height * 0.5;
    const distanceX = pointerClientX < bounds.left
      ? bounds.left - pointerClientX
      : Math.max(0, pointerClientX - bounds.right);
    const distanceY = pointerClientY < bounds.top
      ? bounds.top - pointerClientY
      : Math.max(0, pointerClientY - bounds.bottom);
    const pointerDistance = Math.hypot(distanceX, distanceY);
    const proximityGoal = pointerAvailable
      ? 1 - smoothstep(24, 260, pointerDistance)
      : 0;
    const proximitySpeed = proximityGoal > pointerProximity ? 10 : 5;
    pointerProximity += (proximityGoal - pointerProximity) *
      (1 - Math.exp(-dt * proximitySpeed));

    const pointerXGoal = THREE.MathUtils.clamp(
      (pointerClientX - centerX) / Math.max(1, bounds.width * 0.5), -1.2, 1.2
    );
    const pointerYGoal = THREE.MathUtils.clamp(
      (pointerClientY - centerY) / Math.max(1, bounds.height * 0.5), -1.2, 1.2
    );
    const pointerFollow = 1 - Math.exp(-dt * 9);
    pointerX += (pointerXGoal - pointerX) * pointerFollow;
    pointerY += (pointerYGoal - pointerY) * pointerFollow;
    pressAmount += ((logoPressed ? 1 : 0) - pressAmount) *
      (1 - Math.exp(-dt * (logoPressed ? 22 : 11)));

    cursorLightTarget.set(
      pointerX * halfViewWidth,
      -pointerY * halfViewHeight,
      2.7
    );
    cursorLight.position.lerp(cursorLightTarget, 1 - Math.exp(-dt * 14));
    cursorLight.intensity = 18 * pointerProximity;

    // Blender's glTF Y-up conversion exports the sign face in the XZ plane.
    // Turn it toward this stage's +Z camera instead of showing it edge-on.
    let pitch = faceCameraRotationX;
    let yaw = 0;
    let roll = 0;
    let bob = 0;
    let pulse = 1;
    if (!reducedMotion.matches) {
      pitch += Math.sin(seconds * 0.78) * 0.018 - pointerY * 0.075 * pointerProximity;
      yaw += Math.sin(seconds * 0.57 + 1.1) * 0.035 +
        pointerX * 0.11 * pointerProximity;
      roll = Math.sin(seconds * 0.43 + 0.5) * 0.014;
      bob = Math.sin(seconds * 1.1) * 0.045 + Math.sin(seconds * 0.51) * 0.018;
      pulse = 1 + Math.sin(seconds * 0.8) * 0.006;
    }
    // The model was translated by its full 3D bounds center when loaded, so
    // this press rotation pivots around the exact horizontal/vertical center
    // of the lettering rather than an edge or its original Blender origin.
    pitch -= pressAmount * 0.13;
    logoRoot.rotation.set(pitch, yaw, roll);
    logoRoot.position.set(0, bob, -pressAmount * 0.16);
    logoRoot.scale.setScalar(LOGO_SCALE * pulse);

    const shaderSettings = currentShaderSettings();
    if (!shaderSettings.enabled || location.hash.includes('raw')) {
      renderer.setRenderTarget(null);
      renderer.render(scene, camera);
    } else {
      syncPostMaterial(shaderSettings);
      renderer.setRenderTarget(logoTarget);
      renderer.setClearColor(0x000000, 0);
      renderer.clear();
      renderer.render(scene, camera);
      renderer.setRenderTarget(null);
      renderer.render(postScene, postCamera);
    }

    // Keep the fallback above the canvas until a correctly sized model frame
    // has actually been drawn. This makes loading a cross-fade, not a snap.
    if (logoModel && !stage.classList.contains('is-ready')) {
      stage.classList.add('is-ready');
    }
  }

  requestAnimationFrame(renderLogo);
}
