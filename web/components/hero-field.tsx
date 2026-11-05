"use client";
// The hero's moving field: ShaderGradient (MIT, by ruucm; docs/third-party.md) on three.js, with Prompt
// Bond's two fields recoloured in the site's neutral greys, off-white or charcoal with a soft glow. "3d"
// lighting needs no environment map, so nothing loads from ShaderGradient's site.
import { useFrame, useThree } from "@react-three/fiber";
import { ShaderGradient, ShaderGradientCanvas } from "@shadergradient/react";
import { useEffect } from "react";

const shared = {
  control: "props",
  cAzimuthAngle: 180,
  envPreset: "city",
  grain: "off",
  lightType: "3d",
  reflection: 0.1,
  positionX: 0,
  positionY: 0,
  positionZ: 0,
  range: "disabled",
  rangeStart: 0,
  rangeEnd: 40,
  shader: "defaults",
  type: "waterPlane",
  uAmplitude: 0,
  wireframe: false,
} as const;

// Prompt Bond's settings as it ships them (its source fields with its own overrides), in this palette.
export const FIELDS = {
  light: {
    ...shared,
    brightness: 1.29,
    cDistance: 1.5,
    cPolarAngle: 120,
    cameraZoom: 1,
    color1: "#F5F6F7",
    color2: "#EEF0F2",
    color3: "#F1F2F4",
    rotationX: 0,
    rotationY: 0,
    rotationZ: -90,
    uDensity: 1,
    uFrequency: 5.5,
    uSpeed: 0.1,
    uStrength: 1.2,
    uTime: 0.2,
  },
  dark: {
    ...shared,
    brightness: 0.8,
    cDistance: 2.4,
    cPolarAngle: 80,
    cameraZoom: 9.1,
    color1: "#171A1E",
    color2: "#191C21",
    color3: "#15171B",
    rotationX: 50,
    rotationY: 0,
    rotationZ: -60,
    uDensity: 1.5,
    uFrequency: 0,
    uSpeed: 0.1,
    uStrength: 1.1,
    uTime: 8,
  },
} as const;

type Timed = { material?: { userData?: { uTime?: { value: number } } } };

/** Frames only while the hero moves; paused, it paints once on demand. The field's time runs only while it moves, so
    it goes on from where it stopped: ShaderGradient's own clock runs on with no frame drawn, then jumps ahead. */
function FramePolicy({ moving, mode }: { moving: boolean; mode: string }) {
  const setFrameloop = useThree((state) => state.setFrameloop);
  const invalidate = useThree((state) => state.invalidate);
  const scene = useThree((state) => state.scene);
  useEffect(() => {
    setFrameloop(moving ? "always" : "demand");
    invalidate();
  }, [moving, mode, setFrameloop, invalidate]);
  useFrame((_, delta) => {
    const time = moving ? (scene.getObjectByName("shadergradient-mesh") as Timed | undefined)?.material?.userData?.uTime : undefined;
    if (time) time.value += Math.min(delta, 0.1); // the first frame after a stop counts as one
  });
  return null;
}

export default function Field({ mode, moving }: { mode: "light" | "dark"; moving: boolean }) {
  return (
    <ShaderGradientCanvas
      style={{ position: "absolute", inset: 0 }}
      pixelDensity={1}
      fov={45}
      pointerEvents="none"
      powerPreference="low-power"
      lazyLoad={false}
    >
      {/* From 0, as ShaderGradient's own clock started it; the settings' uTime only ever held a still field. */}
      <ShaderGradient {...FIELDS[mode]} uTime={0} animate="off" />
      <FramePolicy moving={moving} mode={mode} />
    </ShaderGradientCanvas>
  );
}
