#!/usr/bin/env node
// Render a scene plan to mp4: serve dist/, open it in a headless browser (Edge/Chrome/Chromium),
// render frame by frame on the scene's own clock, pipe PNG frames into ffmpeg.
// Usage: node render.mjs --scene scene.json --out clip.mp4
//        node render.mjs --scene scene.json --stills 0.5,4,8 --out-dir previews/   (PNG frames at those seconds)
//        node render.mjs --catalog                                                (what this build supports)
//        add --pack anim-pack.glb to use a humanoid animation pack from any path
// Progress goes to stdout as JSON lines: {"event":"info"|"progress"|"done", ...}
import { spawn } from "node:child_process";
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const here = dirname(fileURLToPath(import.meta.url));
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const emit = (o) => process.stdout.write(JSON.stringify(o) + "\n");
const scenePath = arg("scene"), out = arg("out"), stills = arg("stills"), outDir = arg("out-dir"), packFile = arg("pack");
const catalogOnly = process.argv.includes("--catalog");
const dist = arg("dist", join(here, "dist"));
if (!catalogOnly && (!scenePath || !(out || (stills && outDir)))) {
  console.error("usage: node render.mjs --scene scene.json --out clip.mp4 | --stills 1,4 --out-dir dir | --catalog"); process.exit(2);
}
if (!existsSync(join(dist, "index.html"))) { console.error(`renderer not built: run "npm run build" in ${here}`); process.exit(3); }
const scene = catalogOnly ? {} : JSON.parse(readFileSync(scenePath, "utf8"));

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".glb": "model/gltf-binary",
  ".woff2": "font/woff2", ".woff": "font/woff", ".json": "application/json", ".png": "image/png" };
const server = createServer((req, res) => {
  const rel = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^([/\\])+/, "");
  // --pack serves an animation pack from anywhere as models/anim-pack.glb
  const f = packFile && rel.replace(/\\/g, "/") === "models/anim-pack.glb" ? packFile : join(dist, rel || "index.html");
  if ((f !== packFile && !f.startsWith(dist)) || !existsSync(f) || statSync(f).isDirectory()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "content-type": MIME[extname(f)] ?? "application/octet-stream" });
  createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const url = `http://127.0.0.1:${server.address().port}/index.html`;

// Windows: Microsoft Edge is always installed; elsewhere use Playwright's Chromium or VSS_BROWSER_PATH
const executablePath = process.env.VSS_BROWSER_PATH || undefined;
const channel = executablePath ? undefined : (process.env.VSS_BROWSER_CHANNEL || (process.platform === "win32" ? "msedge" : undefined));
const browser = await chromium.launch({ headless: true, channel, executablePath,
  // force_high_performance_gpu: on laptops with two GPUs (Intel + NVIDIA/AMD) use the discrete one, not the
  // power-saving one Windows hands to apps by default
  args: ["--ignore-gpu-blocklist", "--enable-gpu-rasterization", "--enable-unsafe-swiftshader", "--disable-background-timer-throttling",
    "--force_high_performance_gpu"] });
const t0 = Date.now();
let ff;
try {
  const page = await browser.newPage({ viewport: { width: scene.width ?? 720, height: scene.height ?? 1280 } });
  page.on("pageerror", (e) => emit({ event: "page-error", message: String(e) }));
  await page.goto(url);
  await page.waitForFunction(() => window.vss?.ready, null, { timeout: 60000 });
  if (catalogOnly) {
    emit({ event: "catalog", live: await page.evaluate(() => window.vss.catalog()), file: await page.evaluate(() => window.vss.fileCatalog) });
    process.exitCode = 0;
    throw null;
  }
  const info = await page.evaluate((s) => window.vss.load(s), scene);
  emit({ event: "info", ...info });
  if (stills) {
    mkdirSync(outDir, { recursive: true });
    for (const sec of stills.split(",").map(Number)) {
      const data = await page.evaluate((k) => window.vss.frame(k), Math.min(info.frames - 1, Math.round(sec * info.fps)));
      const f = join(outDir, `still-${sec.toFixed(2)}.png`);
      writeFileSync(f, Buffer.from(data.slice(data.indexOf(",") + 1), "base64"));
      emit({ event: "still", t: sec, file: f });
    }
    emit({ event: "done", seconds: (Date.now() - t0) / 1000 });
    throw null;
  }
  ff = spawn(process.env.FFMPEG_PATH || "ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe",
    "-framerate", String(info.fps), "-c:v", "png", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
    "-preset", "medium", "-crf", String(scene.crf ?? 16), "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"] });
  const done = new Promise((res, rej) => ff.on("close", (c) => (c === 0 ? res() : rej(new Error(`ffmpeg exited ${c}`)))));
  // quality report: near-black frames that no fade/iris/wipe explains, blown-out frames, exposure guard use
  const qa = { frames: 0, black: [], blown: [], guarded: 0, minGuard: 1, meanLuma: 0 };
  for (let i = 0; i < info.frames; i++) {
    const { data, stats } = await page.evaluate((k) => window.vss.frameWithStats(k), i);
    if (!data?.startsWith("data:image/png")) throw new Error(`frame ${i} came back empty`);
    const buf = Buffer.from(data.slice(data.indexOf(",") + 1), "base64");
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
    qa.frames++; qa.meanLuma += stats.mean;
    const transition = stats.fade > 0.3 || stats.iris >= 0 || stats.wipe >= 0;
    if (stats.mean < (scene.qa?.black_luma ?? 10) && !transition) qa.black.push(i);
    if (stats.clipped > (scene.qa?.blown_share ?? 0.25)) qa.blown.push(i);
    if (stats.guard < 0.999) { qa.guarded++; qa.minGuard = Math.min(qa.minGuard, stats.guard); }
    if (i % 12 === 0 || i === info.frames - 1) emit({ event: "progress", frame: i + 1, frames: info.frames, seconds: (Date.now() - t0) / 1000 });
  }
  ff.stdin.end();
  await done;
  const runs = (xs) => xs.reduce((acc, x) => { const r = acc[acc.length - 1]; if (r && x === r[1] + 1) r[1] = x; else acc.push([x, x]); return acc; }, [])
    .map(([a, b]) => [+(a / info.fps).toFixed(2), +((b + 1) / info.fps).toFixed(2)]);
  emit({ event: "qa", frames: qa.frames, expected: info.frames, fps: info.fps, mean_luma: +(qa.meanLuma / Math.max(1, qa.frames)).toFixed(1),
    black: runs(qa.black), blown: runs(qa.blown), guarded_frames: qa.guarded, min_exposure_scale: +qa.minGuard.toFixed(3) });
  emit({ event: "done", out, seconds: (Date.now() - t0) / 1000 });
} catch (e) {
  if (e === null) { /* --catalog / --stills finished early */ } else {
  emit({ event: "error", message: String(e?.message ?? e) });
  process.exitCode = 1;
  ff?.kill();
  }
} finally {
  await browser.close();
  server.close();
}
