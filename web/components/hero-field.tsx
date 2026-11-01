"use client";
// The hero's moving field: ShaderGradient (MIT, by ruucm; docs/third-party.md) on three.js, with Prompt
// Bond's two fields recoloured. Light: warm paper, soft grey-blue and a pale teal. Dark: ink navy with a
// muted teal glow. "3d" lighting needs no environment map, so nothing loads from ShaderGradient's site.
import { useThree } from "@react-three/fiber";
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
    brightness: 1.2,
    cDistance: 1.5,
    cPolarAngle: 120,
    cameraZoom: 1,
    color1: "#FAF8F3",
    color2: "#D6E0EC",
    color3: "#BDEBE1",
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
    color1: "#13283C",
    color2: "#176560",
    color3: "#0F1B2D",
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

/** Frames only while the hero moves; paused, it paints once on demand. */
function FramePolicy({ moving, mode }: { moving: boolean; mode: string }) {
  const setFrameloop = useThree((state) => state.setFrameloop);
  const invalidate = useThree((state) => state.invalidate);
  useEffect(() => {
    setFrameloop(moving ? "always" : "demand");
    invalidate();
  }, [moving, mode, setFrameloop, invalidate]);
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
      <ShaderGradient {...FIELDS[mode]} animate="on" />
      <FramePolicy moving={moving} mode={mode} />
    </ShaderGradientCanvas>
  );
}
