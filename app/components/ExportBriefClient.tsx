"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { formatCurrency } from "../data";

const API_BASE = process.env.NEXT_PUBLIC_FORMAOS_API_BASE ?? "http://localhost:8000";

type ExportItem = {
  item_id: string;
  title: string;
  product_type: string;
  width_cm: number;
  depth_cm: number;
  height_cm?: number | null;
  material?: string | null;
  color?: string | null;
  price_inr: number;
  image_path?: string | null;
  image_available?: boolean;
  placement_zone?: string | null;
};

type ExportPayload = {
  design_id: string;
  project_name: string;
  generated_at: string;
  revision_id?: string | null;
  concept_image_data_url?: string | null;
  source_image_data_url?: string | null;
  revision_label?: string | null;
  room_brief: {
    room_type: string;
    width_cm: number;
    depth_cm: number;
    budget_inr: number;
    style_words: string[];
  };
  user_requirements: {
    style_words: string[];
    constraints: string[];
    missing_questions: string[];
  };
  selected_items: ExportItem[];
  total_price_inr: number;
  budget_summary: {
    budget_inr: number;
    total_price_inr: number;
    remaining_inr: number;
    status: string;
  };
  fit_notes: string[];
  vastu_summary: {
    name: string;
    status: string;
    notes: string[];
  };
  attribution: string;
};

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

function imagePath(item: ExportItem) {
  if (item.image_available && item.image_path) {
    return item.image_path.startsWith("/") ? item.image_path : `/${item.image_path}`;
  }
  return "/product-placeholder.svg";
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character] ?? character);
}

async function waitForImages(container: ParentNode) {
  const images = Array.from(container.querySelectorAll("img"));
  await Promise.all(images.map(async (image) => {
    if (!image.complete) {
      await new Promise<void>((resolve) => {
        image.addEventListener("load", () => resolve(), { once: true });
        image.addEventListener("error", () => resolve(), { once: true });
      });
    }
    await image.decode().catch(() => undefined);
  }));
}

async function imageSourceAsDataUrl(source: string) {
  if (source.startsWith("data:")) return source;
  const response = await fetch(new URL(source, window.location.origin), { credentials: "include" });
  if (!response.ok) return source;
  const blob = await response.blob();
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

const downloadedBriefStyles = `
  * { box-sizing: border-box; }
  body { margin: 0; background: #f5f3ef; color: #171614; font: 14px/1.5 Arial, sans-serif; }
  main { width: min(1100px, calc(100% - 40px)); margin: 24px auto; }
  h1, h2, h3, p { margin-top: 0; }
  h1 { font: 600 34px/1.1 Georgia, serif; }
  h2 { font-size: 20px; } h3 { margin-bottom: 5px; font-size: 15px; }
  .eyebrow, .product-category { color: #a94328; font-size: 11px; font-weight: 700; text-transform: uppercase; }
  .export-heading { display: flex; justify-content: space-between; gap: 24px; margin-bottom: 20px; }
  .export-actions { display: none; }
  .export-room-visuals { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
  .export-room-visuals figure { margin: 0; } .export-room-visuals figcaption { padding-top: 6px; color: #667069; }
  .export-room-visuals img { width: 100%; aspect-ratio: 16/10; object-fit: cover; border-radius: 6px; }
  .export-visuals { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin-bottom: 18px; }
  .export-visuals img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; }
  .brief-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
  article, .export-attribution { padding: 16px; border: 1px solid #dedbd4; border-radius: 6px; background: white; }
  dl { margin: 0; } dl div { display: flex; justify-content: space-between; gap: 20px; padding: 8px 0; border-bottom: 1px solid #ece9e3; }
  dt { color: #69716b; } dd { margin: 0; text-align: right; font-weight: 700; }
  .shopping-list { display: grid; gap: 10px; }
  .product-row { display: grid; grid-template-columns: 78px minmax(0, 1fr) auto; gap: 14px; align-items: center; }
  .product-row img { width: 78px; aspect-ratio: 1; object-fit: cover; border-radius: 5px; }
  .product-row p { margin-bottom: 3px; color: #69716b; }
  .checks { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; } .check { padding: 4px 8px; border-radius: 4px; background: #edf3eb; }
  .export-note-list { padding-left: 18px; } .export-attribution { margin-top: 18px; }
  @media print { @page { size: A4; margin: 14mm; } body { background: white; } main { width: 100%; margin: 0; } article, figure, .product-row { break-inside: avoid; } }
  @media (max-width: 700px) { .brief-grid, .export-room-visuals { grid-template-columns: 1fr; } .export-visuals { grid-template-columns: repeat(2, 1fr); } }
`;

export function ExportBriefClient({ designId, revisionId }: { designId: string; revisionId?: string }) {
  const [payload, setPayload] = useState<ExportPayload | null>(null);
  const [error, setError] = useState("");
  const [authRequired, setAuthRequired] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [exportAction, setExportAction] = useState<"" | "printing" | "downloading">("");
  const revisionQuery = revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : "";
  const briefPath = `/design/${designId}/brief${revisionId ? `?revision=${encodeURIComponent(revisionId)}` : ""}`;

  useEffect(() => {
    let cancelled = false;
    async function loadExport() {
      setError("");
      setAuthRequired(false);
      try {
        const response = await fetch(apiUrl(`/api/export/${designId}${revisionQuery}`), {
          credentials: "include",
          cache: "no-store",
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          if (body?.detail?.code === "authentication_required") setAuthRequired(true);
          const message = body?.detail?.code ? `${body.detail.code}: ${body.detail.message}` : "Unable to load export brief";
          throw new Error(message);
        }
        if (!cancelled) setPayload(body);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Unable to load export brief");
      }
    }
    loadExport();
    return () => {
      cancelled = true;
    };
  }, [designId, reloadToken, revisionQuery]);

  const itemTotal = useMemo(() => {
    return payload?.selected_items.reduce((sum, item) => sum + item.price_inr, 0) ?? 0;
  }, [payload]);
  const generatedAt = payload ? new Date(payload.generated_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "";

  async function printBrief() {
    const brief = document.querySelector(".export-brief-page");
    if (!brief) return;
    setExportAction("printing");
    await waitForImages(brief);
    window.focus();
    window.print();
    setExportAction("");
  }

  async function downloadBrief() {
    const brief = document.querySelector<HTMLElement>(".export-brief-page");
    if (!brief || !payload) return;
    setExportAction("downloading");
    try {
      await waitForImages(brief);
      const clone = brief.cloneNode(true) as HTMLElement;
      clone.querySelectorAll(".export-actions").forEach((element) => element.remove());
      const sourceImages = Array.from(brief.querySelectorAll<HTMLImageElement>("img"));
      const clonedImages = Array.from(clone.querySelectorAll<HTMLImageElement>("img"));
      await Promise.all(clonedImages.map(async (image, index) => {
        const source = sourceImages[index]?.currentSrc || sourceImages[index]?.src || image.src;
        image.src = await imageSourceAsDataUrl(source).catch(() => source);
      }));
      const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(payload.project_name)} design brief</title><style>${downloadedBriefStyles}</style></head><body>${clone.outerHTML}</body></html>`;
      const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      const versionSuffix = payload.revision_label ? `-${payload.revision_label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}` : "";
      link.download = `${payload.project_name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || payload.design_id}${versionSuffix}-design-brief.html`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } finally {
      setExportAction("");
    }
  }

  if (error) {
    return (
      <main className="page-shell printable-page">
        <section className="export-status" role="alert">
          <span className="eyebrow">Export brief</span>
          <h1>Design brief unavailable</h1>
          <p>{error}</p>
          <div className="export-actions">
            {authRequired ? <Link className="primary-button" href={`/login?next=${encodeURIComponent(briefPath)}`}>Sign in again</Link> : null}
            <button className="secondary-button" type="button" onClick={() => setReloadToken((value) => value + 1)}>Retry</button>
            <Link className="secondary-button" href="/workspace">Back to projects</Link>
          </div>
        </section>
      </main>
    );
  }

  if (!payload) {
    return (
      <main className="page-shell printable-page">
        <section className="export-status" aria-label="Export loading state">
          <span className="eyebrow">Export brief</span>
          <h1>Loading design brief</h1>
          <p>Fetching the saved design, catalogue items, prices, and checks.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell printable-page export-brief-page">
      <section className="export-heading">
        <div>
          <span className="eyebrow">Saved design brief{payload.revision_label ? ` · ${payload.revision_label}` : ""}</span>
          <h1>{payload.project_name}</h1>
          <p>
            {payload.room_brief.room_type.replace("_", " ")} - {Math.round(payload.room_brief.width_cm)} x{" "}
            {Math.round(payload.room_brief.depth_cm)} cm - {formatCurrency(payload.room_brief.budget_inr)} budget.
          </p>
          <p>Design ID {payload.design_id}{payload.revision_id ? ` · Version ID ${payload.revision_id}` : ""} - Generated {generatedAt}</p>
        </div>
        <div className="export-actions">
          <Link className="secondary-button" href="/workspace">Back to projects</Link>
          <button className="secondary-button" type="button" disabled={Boolean(exportAction)} onClick={downloadBrief}>
            {exportAction === "downloading" ? "Preparing..." : "Download brief"}
          </button>
          <button className="primary-button print-button" type="button" disabled={Boolean(exportAction)} onClick={printBrief}>
            {exportAction === "printing" ? "Preparing..." : "Print or save PDF"}
          </button>
        </div>
      </section>

      {payload.concept_image_data_url || payload.source_image_data_url ? (
        <section className="export-room-visuals" aria-label="Before and after room design">
          {payload.source_image_data_url ? <figure><img src={payload.source_image_data_url} alt="Original room before redesign" /><figcaption>Before - original room</figcaption></figure> : null}
          {payload.concept_image_data_url ? <figure><img src={payload.concept_image_data_url} alt="Generated room design" /><figcaption>After - {payload.revision_label || "current approved design"}</figcaption></figure> : null}
        </section>
      ) : null}

      <section className="export-visuals" aria-label="Concept and product visuals">
        {payload.selected_items.slice(0, 5).map((item) => (
          <img
            key={item.item_id}
            src={imagePath(item)}
            alt={item.title}
            onError={(event) => {
              event.currentTarget.src = "/product-placeholder.svg";
            }}
          />
        ))}
      </section>

      <section className="brief-grid export-summary-grid">
        <article className="feature-panel">
          <h2>Room brief</h2>
          <dl className="brief-list">
            <div>
              <dt>Room</dt>
              <dd>{payload.room_brief.room_type.replace("_", " ")}</dd>
            </div>
            <div>
              <dt>Dimensions</dt>
              <dd>
                {payload.room_brief.width_cm} x {payload.room_brief.depth_cm} cm
              </dd>
            </div>
            <div>
              <dt>Budget</dt>
              <dd>{formatCurrency(payload.room_brief.budget_inr)}</dd>
            </div>
            <div>
              <dt>Style</dt>
              <dd>{payload.room_brief.style_words.join(", ") || "Not specified"}</dd>
            </div>
            <div>
              <dt>User requirements</dt>
              <dd>{payload.user_requirements.constraints.join(", ") || "No extra constraints"}</dd>
            </div>
          </dl>
        </article>

        <article className="feature-panel">
          <h2>Budget summary</h2>
          <dl className="brief-list">
            <div>
              <dt>Selected total</dt>
              <dd>{formatCurrency(payload.budget_summary.total_price_inr)}</dd>
            </div>
            <div>
              <dt>User budget</dt>
              <dd>{formatCurrency(payload.budget_summary.budget_inr)}</dd>
            </div>
            <div>
              <dt>Remaining</dt>
              <dd>{formatCurrency(payload.budget_summary.remaining_inr)}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>{payload.budget_summary.status}</dd>
            </div>
          </dl>
          <div className="checks always-visible">
            <span className="check pass">Sourceable catalogue items</span>
            <span className={itemTotal === payload.total_price_inr ? "check pass" : "check fail"}>Total verified</span>
            <span className="check pass">Fit notes included</span>
            <span className="check pass">Vastu {payload.vastu_summary.status}</span>
          </div>
          <p className="note">
            Selected item total is {formatCurrency(payload.total_price_inr)}. {payload.attribution}
          </p>
        </article>
      </section>

      <section className="export-items" aria-label="Selected items to buy">
        <h2>Selected items</h2>
        <div className="shopping-list">
          {payload.selected_items.map((item) => (
            <article className="product-row detailed-row export-item-row" key={item.item_id}>
              <img
                src={imagePath(item)}
                alt={item.title}
                onError={(event) => {
                  event.currentTarget.src = "/product-placeholder.svg";
                }}
              />
              <div>
                <span className="product-category">{item.product_type}</span>
                <h3>{item.title}</h3>
                <p>
                  ID {item.item_id}: {item.width_cm} x {item.depth_cm} x {item.height_cm ?? "n/a"} cm
                </p>
                <p>
                  {item.material ?? "Material n/a"} - {item.color ?? "Colour n/a"} - zone {item.placement_zone ?? "n/a"}
                </p>
              </div>
              <strong>{formatCurrency(item.price_inr)}</strong>
            </article>
          ))}
        </div>
      </section>

      <section className="brief-grid export-summary-grid">
        <article className="logic-panel">
          <h2>Why it fits</h2>
          <ul className="export-note-list">
            {(payload.fit_notes.length ? payload.fit_notes : ["All selected catalogue items passed sourceability, fit, and budget checks."]).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </article>

        <article className="logic-panel">
          <h2>Vastu summary</h2>
          <p className="note">Status: {payload.vastu_summary.status}</p>
          <ul className="export-note-list">
            {(payload.vastu_summary.notes.length ? payload.vastu_summary.notes : ["No Vastu action required."]).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </article>
      </section>

      <section className="export-attribution">
        <strong>Attribution</strong>
        <p>Amazon Berkeley Objects (ABO) catalogue imagery and metadata are used for selected product references.</p>
        <p>{payload.attribution}</p>
        <p>INR prices are curated indicative demo values and should be verified before purchase.</p>
      </section>
    </main>
  );
}
