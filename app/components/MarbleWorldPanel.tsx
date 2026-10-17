"use client";

import { useEffect, useState } from "react";

type WorldJob = {
  status: "not_started" | "generating" | "ready" | "failed";
  image_hash: string;
  operation_id?: string;
  world_url?: string | null;
  splat_url?: string | null;
  metric_scale_factor?: number;
  ground_plane_offset?: number;
  message?: string;
};

type Props = { designId: string; imageDataUrl: string; displayName: string; apiBase: string };

async function readResponse(response: Response): Promise<WorldJob> {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail?.message ?? "Could not reach the 3D world service.");
  return payload;
}

export function MarbleWorldPanel({ designId, imageDataUrl, displayName, apiBase }: Props) {
  const [job, setJob] = useState<WorldJob | null>(null);
  const [imageHash, setImageHash] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [viewerVersion, setViewerVersion] = useState(0);
  const endpoint = `${apiBase}/api/design/${encodeURIComponent(designId)}/worlds`;

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function check() {
      try {
        const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(imageDataUrl));
        const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
        if (!active) return;
        setImageHash(hash);
        const result = await readResponse(await fetch(`${endpoint}/${hash}`, {
          credentials: "include", signal: controller.signal,
        }));
        if (!active) return;
        setError("");
        setJob(result);
        if (result.status === "generating") timer = setTimeout(check, 5000);
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not check your 3D world.");
      }
    }
    void check();
    return () => { active = false; controller.abort(); if (timer) clearTimeout(timer); };
  }, [endpoint, imageDataUrl, refresh]);

  async function generate() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await readResponse(await fetch(endpoint, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image_data_url: imageDataUrl, display_name: displayName.slice(0, 64) || "Interior design world" }),
      }));
      setJob(result);
      setRefresh((value) => value + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create your 3D world.");
    } finally {
      setBusy(false);
    }
  }

  const generating = busy || job?.status === "generating";
  const viewerParams = job?.splat_url ? encodeURIComponent(JSON.stringify({
    url: job.splat_url, scale: job.metric_scale_factor ?? 1, offset: job.ground_plane_offset ?? 0,
  })) : "";

  return (
    <section className="marble-world-panel" aria-label="Explorable 3D interior">
      <div className="concept-heading">
        <div><span className="eyebrow">Step inside your design</span><h3>Explore in 3D</h3></div>
        <span className={`status ${job?.status === "ready" ? "hard" : "soft"}`}>
          {generating ? "Creating world" : job?.status === "ready" ? "World ready" : "3D world"}
        </span>
      </div>
      <p>Create an explorable world from this exact design version. Walk around and see your room from new angles.</p>
      <p className="marble-world-note">AI reconstructs unseen areas, so this is a visual preview rather than a measured floor plan.</p>
      {error ? <p role="alert">{error}</p> : null}
      {job?.status === "failed" ? <p role="alert">{job.message}</p> : null}
      <div className="studio-action-row">
        {(!job || job.status === "not_started" || job.status === "failed") ? (
          <button type="button" className="primary-button" disabled={busy || !imageHash || !job} onClick={generate}>
            {busy ? "Starting world..." : job?.status === "failed" ? "Retry 3D world" : "Create 3D world"}
          </button>
        ) : null}
        {error ? <button type="button" className="secondary-button" onClick={() => { setViewerVersion((value) => value + 1); setRefresh((value) => value + 1); }}>Check again</button> : null}
        {job?.world_url ? <a className="secondary-button" href={job.world_url} target="_blank" rel="noopener noreferrer">Open in Marble</a> : null}
        {job?.status === "ready" ? <button type="button" className="secondary-button" onClick={() => { setViewerVersion((value) => value + 1); setRefresh((value) => value + 1); }}>Reload 3D view</button> : null}
      </div>
      {generating ? <p role="status">Marble is reconstructing your room. This may take several minutes. You can return to this saved design while it finishes.</p> : null}
      {job?.status === "ready" && viewerParams ? (
        <>
          <iframe key={viewerVersion} className="marble-world-viewer" src={`/world-viewer.html#${viewerParams}`} title="Explore your generated interior in 3D" allow="fullscreen" allowFullScreen sandbox="allow-scripts allow-same-origin allow-pointer-lock" />
          <p className="marble-world-note">Drag to look around. Use W, A, S, D to move; Q and E to move down and up. Click the viewer first to use the keyboard.</p>
        </>
      ) : null}
      {job?.status === "ready" && !viewerParams ? <p>The world is ready, but its 3D assets are not available here yet. Reload or open it in Marble.</p> : null}
    </section>
  );
}

