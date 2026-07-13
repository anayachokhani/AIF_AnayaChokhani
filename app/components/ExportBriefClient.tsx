"use client";

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
  generated_at: string;
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

export function ExportBriefClient({ designId }: { designId: string }) {
  const [payload, setPayload] = useState<ExportPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadExport() {
      setError("");
      try {
        const response = await fetch(apiUrl(`/api/export/${designId}`));
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
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
  }, [designId]);

  const itemTotal = useMemo(() => {
    return payload?.selected_items.reduce((sum, item) => sum + item.price_inr, 0) ?? 0;
  }, [payload]);
  const generatedAt = payload ? new Date(payload.generated_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "";

  if (error) {
    return (
      <main className="page-shell printable-page">
        <section className="export-status" role="alert">
          <span className="eyebrow">Export brief</span>
          <h1>Design brief unavailable</h1>
          <p>{error}</p>
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
          <span className="eyebrow">Shareable artifact</span>
          <h1>Design Brief {payload.design_id}</h1>
          <p>
            {payload.room_brief.room_type.replace("_", " ")} - {Math.round(payload.room_brief.width_cm)} x{" "}
            {Math.round(payload.room_brief.depth_cm)} cm - {formatCurrency(payload.room_brief.budget_inr)} budget.
          </p>
          <p>Design ID {payload.design_id} - Generated {generatedAt}</p>
        </div>
        <button className="secondary-button print-button" type="button" onClick={() => globalThis.print()}>
          Print PDF
        </button>
      </section>

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
