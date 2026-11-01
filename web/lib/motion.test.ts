// The moving hero's WebGL rule under `node --test`: a software renderer keeps the still.
import assert from "node:assert/strict";
import { test } from "node:test";

import { softwareRenderer } from "./motion.ts";

test("software renderers keep the still: SwiftShader, llvmpipe, softpipe and Windows' basic driver", () => {
  for (const name of [
    "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
    "Google SwiftShader",
    "llvmpipe (LLVM 15.0.7, 256 bits)",
    "softpipe",
    "ANGLE (Microsoft, Microsoft Basic Render Driver (0x0000008C) Direct3D11 vs_5_0 ps_5_0, D3D11)",
  ]) {
    assert.equal(softwareRenderer(name), true, name);
  }
});

test("a graphics card's renderer moves", () => {
  for (const name of [
    "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 (0x00002484) Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Apple M2",
    "Mali-G78",
  ]) {
    assert.equal(softwareRenderer(name), false, name);
  }
});
