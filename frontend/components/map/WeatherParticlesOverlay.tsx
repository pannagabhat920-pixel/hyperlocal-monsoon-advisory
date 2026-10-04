"use client";

import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { useMapStore } from "../../stores/mapStore";

export function WeatherParticlesOverlay() {
  const mountRef = useRef<HTMLDivElement>(null);
  const { selectedLayer } = useMapStore();

  useEffect(() => {
    if (!mountRef.current) return;

    const width = mountRef.current.clientWidth;
    const height = mountRef.current.clientHeight;

    // Scene & Camera
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    camera.position.z = 100;

    // Renderer
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    } catch {
      return;
    }
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mountRef.current.appendChild(renderer.domElement);

    // Weather Particles (Raindrops for onset/excess; heat haze particles for break)
    const particleCount = selectedLayer === "break" ? 400 : 1200;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const velocities = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 200;
      positions[i * 3 + 1] = Math.random() * 200 - 100;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 100;

      // Downward velocity for rain; upward drift for dry break spell
      velocities[i * 3 + 1] = selectedLayer === "break" ? 0.3 + Math.random() * 0.4 : -(1.5 + Math.random() * 2.5);
    }

    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));

    const material = new THREE.PointsMaterial({
      color: selectedLayer === "break" ? 0xf59e0b : selectedLayer === "excess" ? 0x38bdf8 : 0x0284c7,
      size: selectedLayer === "break" ? 2.5 : 1.8,
      transparent: true,
      opacity: 0.65,
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);

    // Animation Loop
    let animationFrameId: number;
    const animate = () => {
      const pos = geometry.attributes.position.array as Float32Array;

      for (let i = 0; i < particleCount; i++) {
        pos[i * 3 + 1] += velocities[i * 3 + 1];

        // Reset particles boundary
        if (selectedLayer === "break" && pos[i * 3 + 1] > 100) {
          pos[i * 3 + 1] = -100;
        } else if (selectedLayer !== "break" && pos[i * 3 + 1] < -100) {
          pos[i * 3 + 1] = 100;
        }
      }

      geometry.attributes.position.needsUpdate = true;
      renderer.render(scene, camera);
      animationFrameId = requestAnimationFrame(animate);
    };

    animate();

    const handleResize = () => {
      if (!mountRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };

    window.addEventListener("resize", handleResize);

    const currentMount = mountRef.current;

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
      if (currentMount && renderer.domElement) {
        currentMount.removeChild(renderer.domElement);
      }
      geometry.dispose();
      material.dispose();
      renderer.dispose();
    };
  }, [selectedLayer]);

  return (
    <div
      ref={mountRef}
      aria-hidden="true"
      className="absolute inset-0 pointer-events-none z-10 overflow-hidden"
    />
  );
}
