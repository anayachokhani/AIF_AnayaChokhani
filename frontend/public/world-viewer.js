// World Labs SPZ assets rendered with Spark. No provider credentials reach this page.
const status = document.getElementById("status");
try {
  const parameters = JSON.parse(decodeURIComponent(location.hash.slice(1)));
  const asset = new URL(parameters.url);
  if (asset.protocol !== "https:") throw new Error("Invalid world asset URL.");
  const THREE = await import("three");
  const { SparkRenderer, SplatMesh, SplatLoader, SparkControls } = await import("@sparkjsdev/spark");
  const canvas = document.getElementById("world");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(65, 1, 0.01, 1000);
  const splatRenderer = new SparkRenderer({ renderer, view: { sort32: true } });
  scene.add(splatRenderer);
  const controls = new SparkControls({ canvas });
  const resize = () => {
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
  };
  addEventListener("resize", resize);
  resize();
  const packed = await new SplatLoader().loadAsync(asset.href, (progress) => {
    status.textContent = progress.total ? `Loading your room: ${Math.round(progress.loaded / progress.total * 100)}%` : "Loading your 3D room...";
  });
  const room = new SplatMesh({ packedSplats: packed });
  // Scale and ground alignment precede Marble's OpenCV-to-Three.js axis conversion.
  const scale = Number.isFinite(parameters.scale) && parameters.scale > 0 ? parameters.scale : 1;
  const offset = Number.isFinite(parameters.offset) ? parameters.offset : 0;
  room.scale.setScalar(scale);
  room.position.y = -offset;
  const frame = new THREE.Group();
  frame.rotation.x = Math.PI;
  frame.add(room);
  scene.add(frame);
  function reset() {
    camera.position.set(0, offset, 0);
    camera.quaternion.identity();
    canvas.focus();
  }
  reset();
  document.getElementById("reset").onclick = reset;
  document.getElementById("fullscreen").onclick = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch { status.hidden = false; status.textContent = "Fullscreen is unavailable in this browser. You can still explore below."; }
  };
  canvas.addEventListener("pointerdown", () => canvas.focus());
  status.hidden = true;
  renderer.setAnimationLoop(() => { controls.update(camera); renderer.render(scene, camera); });
  canvas.addEventListener("webglcontextlost", () => { status.hidden = false; status.textContent = "The 3D view lost its graphics connection. Reload the 3D view to continue."; });
  addEventListener("pagehide", () => {
    renderer.setAnimationLoop(null);
    room.dispose();
    renderer.dispose();
  }, { once: true });
} catch (error) {
  status.hidden = false;
  status.setAttribute("role", "alert");
  status.textContent = "The 3D view could not load. Reload the 3D view or use Open in Marble. " + (error instanceof Error ? error.message : "");
}
