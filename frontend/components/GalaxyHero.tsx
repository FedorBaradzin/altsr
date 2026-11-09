"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

// Живая 3D-галактика токенов. Космос, GPU-частицы, параллакс по курсору.
// Фолбэки: prefers-reduced-motion (статично) и без WebGL (CSS-градиент).
export default function GalaxyHero() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch {
      return; // нет WebGL — остаётся CSS-фон из разметки
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    const scene = new THREE.Scene();
    const cam = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
    cam.position.set(0, 2.6, 8);

    const sizeTo = () => {
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      renderer.setSize(w, h, false);
      cam.aspect = w / Math.max(1, h);
      cam.updateProjectionMatrix();
    };

    // мягкий круглый спрайт
    const tc = document.createElement("canvas");
    tc.width = tc.height = 64;
    const tx = tc.getContext("2d")!;
    const g = tx.createRadialGradient(32, 32, 0, 32, 32, 32);
    g.addColorStop(0, "rgba(255,255,255,1)");
    g.addColorStop(0.25, "rgba(225,225,255,.9)");
    g.addColorStop(1, "rgba(255,255,255,0)");
    tx.fillStyle = g;
    tx.fillRect(0, 0, 64, 64);
    const sprite = new THREE.CanvasTexture(tc);

    const N = 5200;
    const pos = new Float32Array(N * 3);
    const col = new Float32Array(N * 3);
    const cV = new THREE.Color(0x8b5cf6);
    const cB = new THREE.Color(0x22d3ee);
    const cW = new THREE.Color(0xbfd2ff);
    const arms = 4;
    const radius = 7;
    for (let i = 0; i < N; i++) {
      const r = Math.pow(Math.random(), 0.6) * radius;
      const arm = ((i % arms) / arms) * Math.PI * 2;
      const spread = (Math.random() - 0.5) * (0.22 + r * 0.045);
      const a = arm + r * 0.55 + spread;
      pos[i * 3] = Math.cos(a) * r + (Math.random() - 0.5) * 0.3;
      pos[i * 3 + 1] = (Math.random() - 0.5) * (0.5 - r * 0.05);
      pos[i * 3 + 2] = Math.sin(a) * r + (Math.random() - 0.5) * 0.3;
      const mix = r / radius;
      const c = mix < 0.5 ? cW.clone().lerp(cV, mix * 2) : cV.clone().lerp(cB, (mix - 0.5) * 2);
      col[i * 3] = c.r;
      col[i * 3 + 1] = c.g;
      col[i * 3 + 2] = c.b;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    const mat = new THREE.PointsMaterial({
      size: 0.085, map: sprite, vertexColors: true, transparent: true,
      depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.95,
    });
    const galaxy = new THREE.Points(geo, mat);
    scene.add(galaxy);

    const coreGeo = new THREE.BufferGeometry();
    coreGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array([0, 0, 0]), 3));
    const core = new THREE.Points(coreGeo, new THREE.PointsMaterial({
      size: 2.6, map: sprite, color: 0xe9dfff, transparent: true,
      depthWrite: false, blending: THREE.AdditiveBlending, opacity: 0.85,
    }));
    scene.add(core);

    let mx = 0, my = 0, tx2 = 0, ty = 0, t = 0, raf = 0;
    const onMove = (e: MouseEvent) => {
      mx = e.clientX / window.innerWidth - 0.5;
      my = e.clientY / window.innerHeight - 0.5;
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("resize", sizeTo);
    sizeTo();

    const frame = () => {
      t += 0.0016;
      if (!reduce) {
        galaxy.rotation.y = t;
        tx2 += (mx - tx2) * 0.04;
        ty += (my - ty) * 0.04;
        cam.position.x = tx2 * 2.2;
        cam.position.y = 2.6 - ty * 1.4;
        cam.lookAt(0, 0, 0);
      }
      renderer.render(scene, cam);
      raf = requestAnimationFrame(frame);
    };
    frame();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("resize", sizeTo);
      geo.dispose();
      mat.dispose();
      sprite.dispose();
      renderer.dispose();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="absolute inset-0 h-full w-full"
      style={{ background: "radial-gradient(60% 50% at 70% 42%, rgba(139,92,246,.10), transparent 70%), radial-gradient(45% 40% at 20% 60%, rgba(34,211,238,.08), transparent 70%)" }}
    />
  );
}
