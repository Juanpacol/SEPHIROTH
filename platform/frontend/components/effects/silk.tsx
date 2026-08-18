"use client";

/** Animated silk-like shader background (WebGL, via three.js/@react-three/fiber).
 * Vendored from reactbits.dev's "Silk" component — vertex/fragment shaders and
 * uniform wiring are unchanged; only the props are typed and the default color
 * matches what the landing page passes in.
 *
 * Purely decorative: `pointer-events-none` on the wrapping `<Canvas>` container
 * (set by the caller) keeps it from ever intercepting clicks on the hero content
 * painted on top of it. */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { forwardRef, useRef, useMemo, useLayoutEffect, useEffect } from "react";
import { Color, Mesh, ShaderMaterial } from "three";

const hexToNormalizedRGB = (hex: string): [number, number, number] => {
  const clean = hex.replace("#", "");
  return [
    parseInt(clean.slice(0, 2), 16) / 255,
    parseInt(clean.slice(2, 4), 16) / 255,
    parseInt(clean.slice(4, 6), 16) / 255,
  ];
};

const vertexShader = `
varying vec2 vUv;
varying vec3 vPosition;

void main() {
  vPosition = position;
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const fragmentShader = `
varying vec2 vUv;
varying vec3 vPosition;

uniform float uTime;
uniform vec3  uColor;
uniform float uSpeed;
uniform float uScale;
uniform float uRotation;
uniform float uNoiseIntensity;

const float e = 2.71828182845904523536;

float noise(vec2 texCoord) {
  float G = e;
  vec2  r = (G * sin(G * texCoord));
  return fract(r.x * r.y * (1.0 + texCoord.x));
}

vec2 rotateUvs(vec2 uv, float angle) {
  float c = cos(angle);
  float s = sin(angle);
  mat2  rot = mat2(c, -s, s, c);
  return rot * uv;
}

void main() {
  float rnd        = noise(gl_FragCoord.xy);
  vec2  uv         = rotateUvs(vUv * uScale, uRotation);
  vec2  tex        = uv * uScale;
  float tOffset    = uSpeed * uTime;

  tex.y += 0.03 * sin(8.0 * tex.x - tOffset);

  float pattern = 0.6 +
                  0.4 * sin(5.0 * (tex.x + tex.y +
                                   cos(3.0 * tex.x + 5.0 * tex.y) +
                                   0.02 * tOffset) +
                           sin(20.0 * (tex.x + tex.y - 0.1 * tOffset)));

  vec4 col = vec4(uColor, 1.0) * vec4(pattern) - rnd / 15.0 * uNoiseIntensity;
  col.a = 1.0;
  gl_FragColor = col;
}
`;

interface SilkUniforms {
  [uniform: string]: { value: number | Color };
  uSpeed: { value: number };
  uScale: { value: number };
  uNoiseIntensity: { value: number };
  uColor: { value: Color };
  uRotation: { value: number };
  uTime: { value: number };
}

const SilkPlane = forwardRef<Mesh, { uniforms: SilkUniforms }>(function SilkPlane({ uniforms }, ref) {
  const { viewport } = useThree();

  useLayoutEffect(() => {
    const mesh = (ref as React.MutableRefObject<Mesh | null>).current;
    if (mesh) mesh.scale.set(viewport.width, viewport.height, 1);
  }, [ref, viewport]);

  useFrame((_, delta) => {
    const mesh = (ref as React.MutableRefObject<Mesh | null>).current;
    const material = mesh?.material as ShaderMaterial | undefined;
    if (material) material.uniforms.uTime.value += 0.1 * delta;
  });

  return (
    <mesh ref={ref}>
      <planeGeometry args={[1, 1, 1, 1]} />
      <shaderMaterial uniforms={uniforms} vertexShader={vertexShader} fragmentShader={fragmentShader} />
    </mesh>
  );
});

export interface SilkProps {
  speed?: number;
  scale?: number;
  color?: string;
  noiseIntensity?: number;
  rotation?: number;
}

export default function Silk({ speed = 5, scale = 1, color = "#646464", noiseIntensity = 1.5, rotation = 0 }: SilkProps) {
  const meshRef = useRef<Mesh>(null);

  const uniforms = useMemo<SilkUniforms>(
    () => ({
      uSpeed: { value: speed },
      uScale: { value: scale },
      uNoiseIntensity: { value: noiseIntensity },
      uColor: { value: new Color(...hexToNormalizedRGB(color)) },
      uRotation: { value: rotation },
      uTime: { value: 0 },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  useEffect(() => {
    uniforms.uSpeed.value = speed;
    uniforms.uScale.value = scale;
    uniforms.uNoiseIntensity.value = noiseIntensity;
    uniforms.uColor.value.setRGB(...hexToNormalizedRGB(color));
    uniforms.uRotation.value = rotation;
  }, [speed, scale, noiseIntensity, color, rotation, uniforms]);

  return (
    <Canvas dpr={[1, 2]} frameloop="always" gl={{ antialias: true, alpha: true }}>
      <SilkPlane ref={meshRef} uniforms={uniforms} />
    </Canvas>
  );
}
