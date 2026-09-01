import * as THREE from 'three';

const stage = document.getElementById('button-stage');
const canvas = document.getElementById('retro-button-canvas');
const buttons = [...document.querySelectorAll('[data-retro-label]')];
const postToggle = document.getElementById('post-toggle');
const pixelSizeControl = document.getElementById('pixel-size');
const eventStatus = document.getElementById('event-status');

function shaderColor(hex) {
  const value = Number.parseInt(String(hex || '#383838').slice(1), 16);
  return new THREE.Vector3(
    ((value >> 16) & 255) / 255,
    ((value >> 8) & 255) / 255,
    (value & 255) / 255,
  );
}

const renderer = new THREE.WebGLRenderer({
  canvas,
  alpha: true,
  antialias: false,
  powerPreference: 'high-performance',
});
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;

const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 1000);
camera.position.set(0, 0, 420);

scene.add(new THREE.HemisphereLight(0xfff5ce, 0x321207, 2.05));
const keyLight = new THREE.DirectionalLight(0xfff1bc, 3.65);
keyLight.position.set(-180, 210, 320);
scene.add(keyLight);
const warmRim = new THREE.DirectionalLight(0xff6b10, 1.75);
warmRim.position.set(240, -100, 100);
scene.add(warmRim);
const pointerLight = new THREE.PointLight(0xfff8df, 0, 420, 1.75);
pointerLight.position.set(0, 0, 150);
scene.add(pointerLight);

const renderTarget = new THREE.WebGLRenderTarget(4, 4, {
  minFilter: THREE.NearestFilter,
  magFilter: THREE.NearestFilter,
  generateMipmaps: false,
  depthBuffer: true,
});
const postScene = new THREE.Scene();
const postCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
const postMaterial = new THREE.ShaderMaterial({
  transparent: true,
  depthTest: false,
  depthWrite: false,
  uniforms: {
    tex: { value: renderTarget.texture },
    res: { value: new THREE.Vector2(4, 4) },
    colorSteps: { value: 12 },
    posterize: { value: 0.5 },
    dither: { value: 1 },
    outlineWidth: { value: 1 },
    outlineStrength: { value: 0.7 },
    outlineColor: { value: new THREE.Vector3(0x38 / 255, 0x38 / 255, 0x38 / 255) },
    gamma: { value: 2.5 },
  },
  vertexShader: `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = vec4(position.xy, 0.0, 1.0);
    }
  `,
  fragmentShader: `
    uniform sampler2D tex;
    uniform vec2 res;
    uniform float colorSteps, posterize, dither, outlineWidth, outlineStrength, gamma;
    uniform vec3 outlineColor;
    varying vec2 vUv;

    float bayer4(vec2 p) {
      int x = int(mod(p.x, 4.0)), y = int(mod(p.y, 4.0));
      int m[16];
      m[0]=0; m[1]=8; m[2]=2; m[3]=10;
      m[4]=12; m[5]=4; m[6]=14; m[7]=6;
      m[8]=3; m[9]=11; m[10]=1; m[11]=9;
      m[12]=15; m[13]=7; m[14]=13; m[15]=5;
      return (float(m[y*4+x]) + 0.5) / 16.0;
    }

    bool solidAt(vec2 texel) {
      float threshold = mix(0.5, bayer4(texel), dither);
      return texture2D(tex, (texel + 0.5) / res).a >= threshold;
    }

    void main() {
      vec2 texel = floor(vUv * res);
      if (!solidAt(texel)) discard;
      vec4 source = texture2D(tex, (texel + 0.5) / res);
      vec3 color = pow(clamp(source.rgb, 0.0, 1.0), vec3(1.0 / gamma));
      vec3 stepped = floor(color * colorSteps + 0.5) / colorSteps;
      color = mix(color, stepped, posterize);

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
      if (edge) color = mix(color, min(color, outlineColor), outlineStrength);
      gl_FragColor = vec4(color, 1.0);
    }
  `,
});
postScene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), postMaterial));

function roundedRectShape(width, height, radius) {
  const left = -width * 0.5;
  const right = width * 0.5;
  const bottom = -height * 0.5;
  const top = height * 0.5;
  const shape = new THREE.Shape();
  shape.moveTo(left + radius, bottom);
  shape.lineTo(right - radius, bottom);
  shape.quadraticCurveTo(right, bottom, right, bottom + radius);
  shape.lineTo(right, top - radius);
  shape.quadraticCurveTo(right, top, right - radius, top);
  shape.lineTo(left + radius, top);
  shape.quadraticCurveTo(left, top, left, top - radius);
  shape.lineTo(left, bottom + radius);
  shape.quadraticCurveTo(left, bottom, left + radius, bottom);
  return shape;
}

function capsuleShape(width, height) {
  const radius = height * 0.5;
  const leftCenter = -width * 0.5 + radius;
  const rightCenter = width * 0.5 - radius;
  const shape = new THREE.Shape();
  shape.moveTo(leftCenter, -radius);
  shape.lineTo(rightCenter, -radius);
  shape.absarc(rightCenter, 0, radius, -Math.PI * 0.5, Math.PI * 0.5, false);
  shape.lineTo(leftCenter, radius);
  shape.absarc(leftCenter, 0, radius, Math.PI * 0.5, Math.PI * 1.5, false);
  return shape;
}

function vertexGradient(geometry, stops) {
  const position = geometry.attributes.position;
  const colors = new Float32Array(position.count * 3);
  const color = new THREE.Color();
  const low = new THREE.Color(stops.low);
  const middle = new THREE.Color(stops.middle);
  const high = new THREE.Color(stops.high);
  geometry.computeBoundingBox();
  const minY = geometry.boundingBox.min.y;
  const height = Math.max(1, geometry.boundingBox.max.y - minY);
  for (let index = 0; index < position.count; index += 1) {
    const y = THREE.MathUtils.clamp((position.getY(index) - minY) / height, 0, 1);
    if (y < 0.52) color.lerpColors(low, middle, y / 0.52);
    else color.lerpColors(middle, high, (y - 0.52) / 0.48);
    colors[index * 3] = color.r;
    colors[index * 3 + 1] = color.g;
    colors[index * 3 + 2] = color.b;
  }
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
}

const shadowMaterial = new THREE.MeshStandardMaterial({
  color: 0x2c1403,
  roughness: 0.76,
  metalness: 0,
});
const sideMaterial = new THREE.MeshStandardMaterial({
  color: 0xa96700,
  emissive: 0x2b0d00,
  emissiveIntensity: 0.26,
  roughness: 0.35,
  metalness: 0.16,
});
const bevelMaterial = new THREE.MeshStandardMaterial({
  color: 0xf3b400,
  emissive: 0x4a1600,
  emissiveIntensity: 0.2,
  roughness: 0.3,
  metalness: 0.12,
});
const faceMaterial = new THREE.MeshStandardMaterial({
  vertexColors: true,
  emissive: 0x5d2100,
  emissiveIntensity: 0.16,
  roughness: 0.28,
  metalness: 0.11,
});
const highlightMaterial = new THREE.ShaderMaterial({
  transparent: true,
  depthWrite: false,
  depthTest: true,
  blending: THREE.AdditiveBlending,
  toneMapped: false,
  vertexShader: `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: `
    varying vec2 vUv;
    void main() {
      float featherX = smoothstep(0.0, 0.12, vUv.x)
        * smoothstep(0.0, 0.12, 1.0 - vUv.x);
      float centeredY = abs(vUv.y - 0.5) * 2.0;
      float featherY = 1.0 - smoothstep(0.0, 1.0, centeredY);
      featherY = pow(featherY, 1.65);
      float alpha = featherX * featherY * 0.48;
      gl_FragColor = vec4(1.0, 0.97, 0.62, alpha);
    }
  `,
});

function extrudedCapsule(width, height, depth, bevelSize, material) {
  const geometry = new THREE.ExtrudeGeometry(capsuleShape(width, height), {
    depth,
    steps: 1,
    bevelEnabled: true,
    bevelSegments: 2,
    bevelSize,
    bevelThickness: bevelSize * 0.72,
    curveSegments: 14,
  });
  geometry.translate(0, 0, -depth * 0.5);
  geometry.computeVertexNormals();
  return new THREE.Mesh(geometry, material);
}

function createLabelTexture(label) {
  const displayLabel = label.toUpperCase();
  const labelCanvas = document.createElement('canvas');
  labelCanvas.width = 1024;
  labelCanvas.height = 256;
  const context = labelCanvas.getContext('2d');
  context.clearRect(0, 0, labelCanvas.width, labelCanvas.height);
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.font = '500 192px "Kanit", sans-serif';
  context.lineJoin = 'round';

  const x = labelCanvas.width * 0.5 - 8;
  const y = labelCanvas.height * 0.49;
  context.strokeStyle = 'rgba(70, 42, 14, .97)';
  context.lineWidth = 17;
  context.strokeText(displayLabel, x + 6, y + 9);
  context.fillStyle = '#5b3b1b';
  context.fillText(displayLabel, x + 6, y + 9);

  context.strokeStyle = '#d9ae37';
  context.lineWidth = 7;
  context.strokeText(displayLabel, x, y);
  const gradient = context.createLinearGradient(0, 42, 0, 212);
  gradient.addColorStop(0, '#fffbd6');
  gradient.addColorStop(.46, '#fff2a8');
  gradient.addColorStop(1, '#e1b845');
  context.fillStyle = gradient;
  context.fillText(displayLabel, x, y);

  context.globalAlpha = .22;
  context.fillStyle = '#ffffff';
  context.fillText(displayLabel, x - 1, y - 2);
  context.globalAlpha = 1;

  const texture = new THREE.CanvasTexture(labelCanvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  return texture;
}

class RetroButtonVisual {
  constructor(element) {
    this.element = element;
    this.label = element.dataset.retroLabel;
    this.root = new THREE.Group();
    this.faceRoot = new THREE.Group();
    this.hovered = false;
    this.pressed = false;
    this.focused = false;
    this.pressAmount = 0;
    this.hoverAmount = 0;
    this.localPointerX = 0;
    this.localPointerY = 0;

    const shadow = extrudedCapsule(264, 49, 9, 5, shadowMaterial);
    shadow.position.set(0, -6.5, -8);
    this.root.add(shadow);

    const outer = extrudedCapsule(260, 48, 9, 5, [bevelMaterial, sideMaterial]);
    outer.position.z = 0;
    this.faceRoot.add(outer);

    const faceGeometry = new THREE.ShapeGeometry(capsuleShape(246, 37), 18);
    vertexGradient(faceGeometry, {
      low: 0xe49200,
      middle: 0xfff36b,
      high: 0xe9a500,
    });
    const face = new THREE.Mesh(faceGeometry, faceMaterial);
    face.position.set(0, 1, 9.3);
    this.faceRoot.add(face);

    const highlight = new THREE.Mesh(new THREE.PlaneGeometry(218, 14), highlightMaterial);
    highlight.position.set(-4, 7, 10.1);
    this.faceRoot.add(highlight);

    const labelTexture = createLabelTexture(this.label);
    const labelMaterial = new THREE.MeshBasicMaterial({
      map: labelTexture,
      transparent: true,
      alphaTest: 0.03,
      depthWrite: false,
      toneMapped: false,
    });
    const labelWidths = { About: 148, Controls: 184, Advanced: 198 };
    const labelWidth = labelWidths[this.label] || 184;
    const labelMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(labelWidth, 39),
      labelMaterial,
    );
    labelMesh.position.set(0, 0, 11.1);
    labelMesh.renderOrder = 3;
    this.faceRoot.add(labelMesh);

    this.root.add(this.faceRoot);
    scene.add(this.root);
    this.bindEvents();
  }

  bindEvents() {
    this.element.addEventListener('pointerenter', () => { this.hovered = true; });
    this.element.addEventListener('pointerleave', () => {
      this.hovered = false;
      this.pressed = false;
      this.localPointerX = 0;
      this.localPointerY = 0;
    });
    this.element.addEventListener('pointermove', event => {
      const rect = this.element.getBoundingClientRect();
      this.localPointerX = THREE.MathUtils.clamp(
        (event.clientX - rect.left) / rect.width * 2 - 1,
        -1,
        1,
      );
      this.localPointerY = THREE.MathUtils.clamp(
        (event.clientY - rect.top) / rect.height * 2 - 1,
        -1,
        1,
      );
    });
    this.element.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      this.pressed = true;
      this.element.setPointerCapture?.(event.pointerId);
    });
    this.element.addEventListener('pointerup', () => { this.pressed = false; });
    this.element.addEventListener('pointercancel', () => { this.pressed = false; });
    this.element.addEventListener('focus', () => { this.focused = true; });
    this.element.addEventListener('blur', () => {
      this.focused = false;
      this.pressed = false;
    });
    this.element.addEventListener('click', () => {
      if (!eventStatus) return;
      if (this.label === 'Advanced') {
        const expanded = this.element.getAttribute('aria-expanded') === 'true';
        this.element.setAttribute('aria-expanded', String(!expanded));
        eventStatus.value = `Advanced ${expanded ? 'closed' : 'opened'}`;
      } else {
        eventStatus.value = `${this.label} activated`;
      }
    });
  }

  syncRect(stageRect, stageWidth, stageHeight) {
    const rect = this.element.getBoundingClientRect();
    const x = rect.left - stageRect.left + rect.width * 0.5 - stageWidth * 0.5;
    const y = stageHeight * 0.5 - (rect.top - stageRect.top + rect.height * 0.5);
    const scale = Math.min(rect.width / 286, rect.height / 58);
    this.root.position.x = x;
    this.root.position.y = y;
    this.root.scale.setScalar(scale);
  }

  update(dt, time) {
    const hoverGoal = this.hovered || this.focused ? 1 : 0;
    const pressGoal = this.pressed ? 1 : 0;
    this.hoverAmount += (hoverGoal - this.hoverAmount) * (1 - Math.exp(-dt * 12));
    this.pressAmount += (pressGoal - this.pressAmount) * (1 - Math.exp(-dt * 23));

    const idle = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ? 0
      : Math.sin(time * 1.35 + (this.label === 'Advanced' ? 1.7 : 0)) * 0.55;
    this.faceRoot.position.y = idle + this.hoverAmount * 1.2 - this.pressAmount * 4.2;
    this.faceRoot.position.z = this.hoverAmount * 1.8 - this.pressAmount * 5.2;
    this.faceRoot.rotation.x = -this.localPointerY * 0.035 * this.hoverAmount + this.pressAmount * 0.025;
    this.faceRoot.rotation.y = this.localPointerX * 0.045 * this.hoverAmount;
    const scale = 1 + this.hoverAmount * 0.018 - this.pressAmount * 0.025;
    this.faceRoot.scale.setScalar(scale);
  }
}

const visuals = buttons.map(button => new RetroButtonVisual(button));
let lastTime = 0;
let stageWidth = 1;
let stageHeight = 1;
let pointerInside = false;
let pointerX = 0;
let pointerY = 0;

function resize() {
  stageWidth = Math.max(1, stage.clientWidth);
  stageHeight = Math.max(1, stage.clientHeight);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  renderer.setPixelRatio(dpr);
  renderer.setSize(stageWidth, stageHeight, false);

  camera.left = -stageWidth * 0.5;
  camera.right = stageWidth * 0.5;
  camera.top = stageHeight * 0.5;
  camera.bottom = -stageHeight * 0.5;
  camera.updateProjectionMatrix();

  const pixelSize = Number(
    pixelSizeControl?.value || window.__shaderSettings?.pixelSize || 2
  );
  const lowWidth = Math.max(4, Math.round(stageWidth / pixelSize));
  const lowHeight = Math.max(4, Math.round(stageHeight / pixelSize));
  renderTarget.setSize(lowWidth, lowHeight);
  postMaterial.uniforms.res.value.set(lowWidth, lowHeight);

  const stageRect = stage.getBoundingClientRect();
  for (const visual of visuals) {
    visual.syncRect(stageRect, stageWidth, stageHeight);
  }
}

stage.addEventListener('pointerenter', () => { pointerInside = true; });
stage.addEventListener('pointerleave', () => { pointerInside = false; });
stage.addEventListener('pointermove', event => {
  const rect = stage.getBoundingClientRect();
  pointerX = event.clientX - rect.left - rect.width * 0.5;
  pointerY = rect.height * 0.5 - (event.clientY - rect.top);
});

pixelSizeControl?.addEventListener('input', resize);
document.querySelector('[data-shader="pixelSize"]')?.addEventListener('input', resize);
new ResizeObserver(resize).observe(stage);
window.addEventListener('resize', resize);

function animate(now) {
  requestAnimationFrame(animate);
  const time = now * 0.001;
  const dt = lastTime ? Math.min(0.05, (now - lastTime) * 0.001) : 1 / 60;
  lastTime = now;

  const stageRect = stage.getBoundingClientRect();
  for (const visual of visuals) {
    visual.syncRect(stageRect, stageWidth, stageHeight);
    visual.update(dt, time);
  }

  pointerLight.position.x += (pointerX - pointerLight.position.x) * (1 - Math.exp(-dt * 14));
  pointerLight.position.y += (pointerY - pointerLight.position.y) * (1 - Math.exp(-dt * 14));
  const intensityGoal = pointerInside ? 15 : 0;
  pointerLight.intensity += (intensityGoal - pointerLight.intensity) * (1 - Math.exp(-dt * 8));

  const sharedSettings = window.__shaderSettings;
  if (sharedSettings) {
    postMaterial.uniforms.colorSteps.value = sharedSettings.colorSteps;
    postMaterial.uniforms.posterize.value = sharedSettings.posterize;
    postMaterial.uniforms.dither.value = sharedSettings.dither;
    postMaterial.uniforms.outlineWidth.value = sharedSettings.outlineWidth;
    postMaterial.uniforms.outlineStrength.value = sharedSettings.outlineStrength;
    postMaterial.uniforms.outlineColor.value.copy(shaderColor(sharedSettings.outlineColor));
    postMaterial.uniforms.gamma.value = sharedSettings.gamma;
  }

  const postEnabled = postToggle ? postToggle.checked : sharedSettings?.enabled !== false;
  if (!postEnabled) {
    renderer.setRenderTarget(null);
    renderer.clear();
    renderer.render(scene, camera);
    return;
  }

  renderer.setRenderTarget(renderTarget);
  renderer.setClearColor(0x000000, 0);
  renderer.clear();
  renderer.render(scene, camera);
  renderer.setRenderTarget(null);
  renderer.clear();
  renderer.render(postScene, postCamera);
}

document.fonts.ready.then(() => {
  resize();
  requestAnimationFrame(animate);
});
