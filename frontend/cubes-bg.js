/**
 * Anamnesis — GlowingCubesBackground v6 (Three.js + UnrealBloomPass)
 * ====================================================================
 * High-emissive 3D meshes rendered via Three.js with hardware UnrealBloomPass.
 * Features:
 * - ACESFilmicToneMapping
 * - StandardMaterials (high emissive white + cyan metallic base)
 * - PointLights anchored inside cubes illuminating dark space
 * - Additive sprite halos
 */

import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

(function () {
  'use strict';

  // Make sure previous custom canvas is removed if it exists
  const oldCanvas = document.getElementById('cubes-bg-canvas');
  if (oldCanvas) oldCanvas.remove();

  /* ── 1. Init Renderer & Scene ───────────────────────────────────── */
  const renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  renderer.domElement.id = 'cubes-bg-canvas';
  Object.assign(renderer.domElement.style, {
    position: 'fixed', top: '0', left: '0',
    width: '100vw', height: '100vh',
    zIndex: '-1', pointerEvents: 'none',
    overflow: 'hidden'
  });
  // Add !important to CSS to ensure overriding. We can do this by setting cssText directly, or just standard properties.
  renderer.domElement.style.setProperty('position', 'fixed', 'important');
  renderer.domElement.style.setProperty('top', '0', 'important');
  renderer.domElement.style.setProperty('left', '0', 'important');
  renderer.domElement.style.setProperty('width', '100vw', 'important');
  renderer.domElement.style.setProperty('height', '100vh', 'important');
  renderer.domElement.style.setProperty('pointer-events', 'none', 'important');
  renderer.domElement.style.setProperty('z-index', '-1', 'important');
  renderer.domElement.style.setProperty('overflow', 'hidden', 'important');

  document.body.insertBefore(renderer.domElement, document.body.firstChild);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#030509');

  const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 2000);
  camera.position.z = 400;

  const raycaster = new THREE.Raycaster();
  const mouseVec = new THREE.Vector2(-999, -999);
  const mouseWorld = new THREE.Vector3();
  const planeZ0 = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);

  /* ── 2. Post-Processing (Unreal Bloom) ──────────────────────────── */
  const renderScene = new RenderPass(scene, camera);
  const bloomPass = new UnrealBloomPass(
    new THREE.Vector2(window.innerWidth, window.innerHeight),
    0.45,  // strength
    0.5,  // radius
    0.2   // threshold
  );

  const composer = new EffectComposer(renderer);
  composer.addPass(renderScene);
  composer.addPass(bloomPass);

  /* ── 3. Texture Generation for Halo ─────────────────────────────── */
  function createHaloTexture() {
    const size = 256;
    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext('2d');
    
    const grad = ctx.createRadialGradient(size/2, size/2, 0, size/2, size/2, size/2);
    grad.addColorStop(0, 'rgba(255,255,255,1.0)');
    grad.addColorStop(0.2, 'rgba(0, 240, 255, 0.8)');
    grad.addColorStop(1, 'rgba(0, 240, 255, 0.0)');
    
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, size, size);
    
    const texture = new THREE.CanvasTexture(canvas);
    return texture;
  }
  const haloTex = createHaloTexture();

  /* ── 4. Cube Materials & Geometry ───────────────────────────────── */
  const cubeGeom = new THREE.BoxGeometry(1, 1, 1);
  const cubeMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color('#0B0F19'),
    emissive: new THREE.Color('#00F0FF'),
    emissiveIntensity: 0.4,
    roughness: 0.2,
    metalness: 0.8,
    transparent: true,
    opacity: 0.08
  });

  const haloMat = new THREE.SpriteMaterial({
    map: haloTex,
    color: 0xffffff,
    blending: THREE.AdditiveBlending,
    transparent: true,
    depthWrite: false
  });

  /* ── 5. Lifecycle Management ────────────────────────────────────── */
  const N_CUBES = 20;
  const LIFE_MIN = 2.0;
  const LIFE_MAX = 4.0;
  const BIRTH_F = 0.15;
  const DEATH_F = 0.15;

  class CubeEntity {
    constructor(ageOffset = 0) {
      this.group = new THREE.Group();

      // Mesh & Edges
      this.mesh = new THREE.Mesh(cubeGeom, cubeMat.clone());
      this.group.add(this.mesh);
      
      const edges = new THREE.EdgesGeometry(cubeGeom);
      this.edgesMat = new THREE.LineBasicMaterial({ color: 0x00F0FF, transparent: true, opacity: 0.4 });
      this.line = new THREE.LineSegments(edges, this.edgesMat);
      this.mesh.add(this.line);

      // Point Light
      this.light = new THREE.PointLight('#00F0FF', 0, 10);
      // this.group.add(this.light); // Removed per user request

      // Halo Sprite
      this.sprite = new THREE.Sprite(haloMat.clone());
      // this.group.add(this.sprite); // Removed per user request

      scene.add(this.group);
      this.reset(ageOffset);
    }

    reset(ageOffset = 0) {
      this.vx = 0;
      this.vy = 0;
      this.wx = (Math.random() - 0.5) * 800;
      this.wy = (Math.random() - 0.5) * 450;
      this.wz = (Math.random() - 0.5) * 200 - 100;
      this.group.position.set(this.wx, this.wy, this.wz);

      this.sz = 8 + Math.random() * 25;
      
      this.drx = (Math.random() - 0.5) * 0.02;
      this.dry = (Math.random() - 0.5) * 0.025;
      this.drz = (Math.random() - 0.5) * 0.01;

      this.fp = Math.random() * Math.PI * 2;
      this.fa = 5 + Math.random() * 15;
      this.fs = 0.5 + Math.random() * 0.8;

      this.lf = LIFE_MIN + Math.random() * (LIFE_MAX - LIFE_MIN);
      this.age = -Math.abs(ageOffset);
    }

    update(dt) {
      this.age += dt;
      if (this.age > this.lf) {
        this.reset(0);
      }

      if (this.age < 0) {
        this.group.visible = false;
        return;
      }
      this.group.visible = true;

      // Rotation
      this.mesh.rotation.x += this.drx;
      this.mesh.rotation.y += this.dry;
      this.mesh.rotation.z += this.drz;

      // Physics (Spring to origin & Float)
      const floatY = Math.sin(this.age * this.fs + this.fp) * this.fa;
      
      const springX = (this.wx - this.group.position.x) * 0.05;
      const springY = (this.wy + floatY - this.group.position.y) * 0.05;
      this.vx += springX;
      this.vy += springY;

      // Mouse Cursor Repulsion Force (Boosted 5x)
      const dx = this.group.position.x - mouseWorld.x;
      const dy = this.group.position.y - mouseWorld.y;
      const dist = Math.sqrt(dx*dx + dy*dy);
      
      const repelRadius = 200; // Interaction radius (reduced for subtle feel)
      if (dist < repelRadius && dist > 0.1) {
        const force = (repelRadius - dist) / repelRadius;
        this.vx += (dx / dist) * force * 1.2;
        this.vy += (dy / dist) * force * 1.2;
      }

      // Smooth Spring Damping (increased for smoother return)
      this.vx *= 0.92;
      this.vy *= 0.92;

      this.group.position.x += this.vx;
      this.group.position.y += this.vy;

      // Lifecycle calc
      const t = this.age / this.lf;
      let scale = 0, alpha = 0, lightIntensity = 0;

      if (t < BIRTH_F) {
        // Spawn
        const p = t / BIRTH_F;
        // easeOutBack equivalent roughly
        const c1 = 1.70158; const c3 = c1 + 1;
        scale = 1 + c3 * Math.pow(p - 1, 3) + c1 * Math.pow(p - 1, 2);
        scale = Math.max(0, scale);
        
        alpha = p;
        lightIntensity = p * 0.7; // soft pulse up to 0.7
      } else if (t < 1 - DEATH_F) {
        // Peak
        scale = 1.0;
        alpha = 1.0;
        lightIntensity = 0.5 + 0.2 * Math.sin(this.age * 3.0); // soft pulse
      } else {
        // Dissolve
        const p = (t - (1 - DEATH_F)) / DEATH_F;
        const easeIn = p * p * p;
        scale = 1.0 + easeIn * 0.2;
        alpha = 1.0 - easeIn;
        lightIntensity = (1.0 - p) * 0.7;
      }

      this.mesh.scale.set(this.sz * scale, this.sz * scale, this.sz * scale);
      
      // Update materials
      this.mesh.material.transparent = true;
      this.mesh.material.opacity = alpha * 0.20; // Reduced opacity for cleaner wireframe focus
      this.mesh.material.emissiveIntensity = 0.60 * alpha;
      this.edgesMat.opacity = alpha * 0.40;
      
      // Rotate emissive color for variety
      if (this.fp > Math.PI) {
        this.mesh.material.emissive.setHex(0x8B5CF6);
      } else {
        this.mesh.material.emissive.setHex(0x00F0FF);
      }
      
      // Halo is 2.5x the size of the cube
      const haloSz = this.sz * scale * 2.5;
      this.sprite.scale.set(haloSz, haloSz, 1);
      this.sprite.material.opacity = 0;
      this.sprite.visible = false;

      // Light
      this.light.intensity = 0;
    }
  }

  const cubes = [];
  for (let i = 0; i < N_CUBES; i++) {
    cubes.push(new CubeEntity(Math.random() * LIFE_MAX));
  }

  /* ── 6. Mouse Parallax & Raycasting ─────────────────────────────── */
  let mx = 0, my = 0;
  window.addEventListener('mousemove', e => {
    mx = (e.clientX / window.innerWidth - 0.5) * 2;
    my = (e.clientY / window.innerHeight - 0.5) * 2;
    mouseVec.set(mx, -my);
  });

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    composer.setSize(window.innerWidth, window.innerHeight);
  });

  /* ── 7. Render Loop ─────────────────────────────────────────────── */
  const clock = new THREE.Clock();
  let camTargetX = 0;
  let camTargetY = 0;

  function animate() {
    requestAnimationFrame(animate);
    const dt = clock.getDelta();

    // Smooth camera parallax
    camTargetX += (mx * 30 - camTargetX) * 0.05;
    camTargetY += (-my * 30 - camTargetY) * 0.05;
    camera.position.x = camTargetX;
    camera.position.y = camTargetY;
    camera.lookAt(scene.position);

    // Update mouse world position for repulsion
    raycaster.setFromCamera(mouseVec, camera);
    raycaster.ray.intersectPlane(planeZ0, mouseWorld);

    for (const c of cubes) {
      c.update(dt);
    }

    composer.render();
  }

  animate();

})();
