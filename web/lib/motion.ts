// When the landing's moving hero may run: never on a software WebGL renderer, which draws on the CPU and
// would starve the page (CI runners, PCs without graphics acceleration); they keep the still.
const SOFTWARE = /swiftshader|llvmpipe|softpipe|software|basic render/i;

/** True for a renderer name (WEBGL_debug_renderer_info's) that draws without a graphics card. */
export const softwareRenderer = (name: string) => SOFTWARE.test(name);
