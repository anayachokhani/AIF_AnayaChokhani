"use client";

import type { FormEvent } from "react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { formatCurrency } from "../data";
import { ZoneGrid, type ZoneGridItem } from "./ZoneGrid";

const directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "C"] as const;
const units = ["ft", "m", "cm"] as const;
const progressStates = ["planning", "designing", "grounding", "checking", "revising", "passed", "failed", "error"] as const;
const tabs = ["items", "vastu", "shopping"] as const;
const API_BASE = process.env.NEXT_PUBLIC_FORMAOS_API_BASE ?? "http://localhost:8000";
const apiErrorStates = [
  "invalid_brief",
  "no_catalogue_results",
  "retry_exhausted",
  "graph_failure",
  "missing_api_key",
  "general error",
] as const;

type Direction = (typeof directions)[number];
type Unit = (typeof units)[number];
type Tab = (typeof tabs)[number];
type ProgressState = (typeof progressStates)[number];

type CatalogueItem = {
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
  placement_zone?: Direction | null;
};

type GroundedSlot = {
  slot: {
    slot_id: string;
    category: string;
    placement_hint?: Direction | null;
  };
  placement_zone: Direction;
  selected_item?: CatalogueItem | null;
  alternatives: CatalogueItem[];
};

type VastuRuleResult = {
  rule_id: string;
  item_id: string;
  status: string;
  badge: string;
  note: string;
  rationale: string;
};

type VastuItemResult = {
  item_id: string;
  title: string;
  zone: Direction;
  badge: string;
  notes: string[];
  rule_results: VastuRuleResult[];
};

type BackendDesign = {
  design_id: string;
  status: "passed" | "failed";
  grounder_output: {
    grounded_slots: GroundedSlot[];
  };
  critic_verdict: {
    passed: boolean;
    total_price_inr: number;
    fit: { status: string; notes: string[] };
    budget: { status: string; notes: string[] };
    vastu: { status: string; notes: string[] };
    vastu_result?: {
      score: number;
      item_results: VastuItemResult[];
      notes: string[];
    } | null;
  };
};

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

function styleWords(value: string) {
  return value
    .toLowerCase()
    .split(/[, ]+/)
    .map((word) => word.trim())
    .filter(Boolean);
}

function constraintsFrom(value: string) {
  const normalized = value.toLowerCase();
  const constraints = [];
  if (normalized.includes("kid") || normalized.includes("child")) constraints.push("kid-friendly");
  if (normalized.includes("play")) constraints.push("play space");
  if (normalized.includes("storage")) constraints.push("extra storage");
  return constraints.length ? constraints : ["clear circulation"];
}

function cmValue(value: number, unit: Unit) {
  if (unit === "cm") return value;
  if (unit === "m") return value * 100;
  return value * 30.48;
}

function safeImagePath(item: CatalogueItem) {
  if (item.image_available && item.image_path) {
    return item.image_path.startsWith("/") ? item.image_path : `/${item.image_path}`;
  }
  return "/product-placeholder.svg";
}

function errorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return fallback;
  const detail = (payload as { detail?: { code?: string; message?: string } }).detail;
  const knownCode = apiErrorStates.find((code) => code === detail?.code);
  return knownCode ? `${knownCode}: ${detail?.message ?? fallback}` : fallback;
}

function selectedSlots(design: BackendDesign | null) {
  return design?.grounder_output.grounded_slots.filter((slot) => slot.selected_item) ?? [];
}

export function WorkspaceClient() {
  const [roomType, setRoomType] = useState("living_room");
  const [unit, setUnit] = useState<Unit>("ft");
  const [width, setWidth] = useState(10);
  const [depth, setDepth] = useState(12);
  const [budget, setBudget] = useState(180000);
  const [style, setStyle] = useState("warm modern kid-friendly storage");
  const [message, setMessage] = useState("Create a checked design.");
  const [revisionMessage, setRevisionMessage] = useState("Revise with the same constraints.");
  const [vastuEnabled, setVastuEnabled] = useState(true);
  const [mainDoor, setMainDoor] = useState<Direction>("N");
  const [compass, setCompass] = useState<Direction>("N");
  const [activeTab, setActiveTab] = useState<Tab>("items");
  const [sessionId, setSessionId] = useState("");
  const [design, setDesign] = useState<BackendDesign | null>(null);
  const [progress, setProgress] = useState<ProgressState>("planning");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const slots = selectedSlots(design);
  const visibleTotal = slots.reduce((sum, slot) => sum + (slot.selected_item?.price_inr ?? 0), 0);
  const backendTotal = design?.critic_verdict.total_price_inr ?? 0;
  const exactTotal = design ? visibleTotal === backendTotal : false;
  const budgetPercent = budget > 0 ? Math.min(100, Math.round(((design ? backendTotal : 0) / budget) * 100)) : 0;
  const budgetStatus = design?.critic_verdict.budget.status ?? "waiting";
  const widthCm = Math.round(cmValue(width, unit));
  const depthCm = Math.round(cmValue(depth, unit));
  const zoneItems: ZoneGridItem[] = slots.map((slot) => ({
    slot: slot.selected_item?.title ?? slot.slot.category,
    zone: slot.placement_zone,
  }));

  const ruleResults = useMemo(() => {
    return design?.critic_verdict.vastu_result?.item_results.flatMap((item) => item.rule_results) ?? [];
  }, [design]);

  const roomBrief = {
    room_type: roomType,
    width,
    depth,
    units: unit,
    budget_inr: budget,
    style_words: styleWords(style),
    constraints: constraintsFrom(style),
    vastu_enabled: vastuEnabled,
    main_door_direction: mainDoor,
    compass_direction: compass,
  };

  async function parseResponse(response: Response) {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorMessage(payload, "API request failed"));
    return payload;
  }

  async function runDesign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setDesign(null);
    setProgress("planning");
    try {
      const sessionResponse = await fetch(apiUrl("/api/session"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brief: roomBrief }),
      });
      const sessionPayload = await parseResponse(sessionResponse);
      setSessionId(sessionPayload.session_id);

      setProgress("designing");
      const chatResponse = await fetch(apiUrl("/api/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionPayload.session_id,
          message,
          max_retries: 2,
        }),
      });
      setProgress("grounding");
      const chatPayload = await parseResponse(chatResponse);
      setProgress("checking");
      setDesign(chatPayload.design);
      setProgress(chatPayload.design?.status === "failed" ? "failed" : "passed");
    } catch (caught) {
      setProgress("error");
      setError(caught instanceof Error ? caught.message : "general error");
    } finally {
      setLoading(false);
    }
  }

  async function reviseDesign() {
    if (!design) {
      setError("empty: generate a design before revision");
      return;
    }
    setLoading(true);
    setError("");
    setProgress("revising");
    try {
      const response = await fetch(apiUrl(`/api/design/${design.design_id}/revise`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          message: revisionMessage,
          max_retries: 2,
        }),
      });
      const payload = await parseResponse(response);
      setDesign(payload.design);
      setProgress(payload.design?.status === "failed" ? "failed" : "passed");
    } catch (caught) {
      setProgress("error");
      setError(caught instanceof Error ? caught.message : "general error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="workspace-shell" aria-label="FormaOS design workspace">
      <form className="workspace-chat-column" onSubmit={runDesign} aria-label="Room setup and chat">
        <div className="room-setup-bar">
          <label>
            Room
            <select className="select-input" value={roomType} onChange={(event) => setRoomType(event.target.value)}>
              <option value="living_room">Living room</option>
              <option value="bedroom">Bedroom</option>
              <option value="study">Study</option>
            </select>
          </label>
          <label>
            Width
            <input className="text-input" type="number" min="1" value={width} onChange={(event) => setWidth(Number(event.target.value))} />
          </label>
          <label>
            Depth
            <input className="text-input" type="number" min="1" value={depth} onChange={(event) => setDepth(Number(event.target.value))} />
          </label>
          <label>
            Units
            <select className="select-input" value={unit} onChange={(event) => setUnit(event.target.value as Unit)}>
              {units.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label>
            Budget
            <input className="text-input" type="number" min="1000" step="1000" value={budget} onChange={(event) => setBudget(Number(event.target.value))} />
          </label>
          <label>
            Main door
            <select className="select-input" value={mainDoor} onChange={(event) => setMainDoor(event.target.value as Direction)}>
              {directions.map((direction) => (
                <option key={direction} value={direction}>
                  {direction}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="workspace-wide-field">
          Style and constraints
          <input className="text-input" value={style} onChange={(event) => setStyle(event.target.value)} />
        </label>

        <div className="workspace-toggle-row">
          <label>
            <input type="checkbox" checked={vastuEnabled} onChange={(event) => setVastuEnabled(event.target.checked)} />
            Vastu
          </label>
          <label>
            Compass
            <select className="select-input" value={compass} onChange={(event) => setCompass(event.target.value as Direction)}>
              {directions.map((direction) => (
                <option key={direction} value={direction}>
                  {direction}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="chat-thread workspace-thread">
          <article className="message user-message">
            <span>User</span>
            <p>
              {width} by {depth} {unit} {roomType.replace("_", " ")}, {formatCurrency(budget)}, {style}.
            </p>
          </article>
          <article className="message system-message">
            <span>FormaOS</span>
            <p>
              {design
                ? `Backend design ${design.design_id}: ${slots.length} grounded items, ${formatCurrency(backendTotal)} total.`
                : "No backend design loaded yet."}
            </p>
          </article>
        </div>

        <div className="progress-rail" aria-label="Agent progress states">
          {progressStates.map((state) => (
            <span key={state} className={state === progress ? "progress-step complete" : "progress-step"}>
              {state}
            </span>
          ))}
        </div>

        <div className="chat-input-row">
          <input value={message} onChange={(event) => setMessage(event.target.value)} aria-label="Design request message" />
          <button className="primary-button" type="submit" disabled={loading}>
            Generate
          </button>
        </div>
        <div className="chat-input-row">
          <input value={revisionMessage} onChange={(event) => setRevisionMessage(event.target.value)} aria-label="Revision message" />
          <button className="secondary-button" type="button" onClick={reviseDesign} disabled={loading || !design}>
            Revise
          </button>
        </div>
        <p className="workspace-api-state">
          {loading ? "loading" : progress}
          {sessionId ? `: ${sessionId}` : ""}
        </p>
        {design ? (
          <Link className="secondary-button" href={`/design/${design.design_id}/brief`}>
            Open export brief
          </Link>
        ) : null}
        {error ? <p className="workspace-error" role="alert">{error}</p> : null}
      </form>

      <div className="workspace-design-column">
        <div className="workspace-toolbar">
          <div>
            <span className="eyebrow">Checked design</span>
            <h1>{roomType.replace("_", " ")}</h1>
          </div>
          <div className="workspace-facts" aria-label="Core plan facts">
            <span>{widthCm} x {depthCm} cm</span>
            <span>{design ? formatCurrency(backendTotal) : "No total"} total</span>
            <span>{budgetStatus} budget</span>
          </div>
        </div>

        {design ? (
          <div className="product-collage" aria-label="Product photo collage">
            {slots.map((slot) => (
              <img
                key={`collage-${slot.selected_item?.item_id}`}
                src={safeImagePath(slot.selected_item as CatalogueItem)}
                alt={slot.selected_item?.title ?? slot.slot.category}
                onError={(event) => {
                  event.currentTarget.src = "/product-placeholder.svg";
                }}
              />
            ))}
          </div>
        ) : (
          <div className="workspace-empty-state" aria-label="Empty design state">
            Submit a valid room brief to load backend-selected catalogue items.
          </div>
        )}

        <div className="workspace-tabs" role="tablist" aria-label="Design workspace tabs">
          {tabs.map((tab) => (
            <button
              key={tab}
              className={activeTab === tab ? "workspace-tab active" : "workspace-tab"}
              type="button"
              onClick={() => setActiveTab(tab)}
            >
              {tab === "shopping" ? "Shopping list" : tab}
            </button>
          ))}
        </div>

        {activeTab === "items" && (
          <div className="workspace-item-grid" aria-label="Grounded item cards">
            {slots.map((slot) => {
              const item = slot.selected_item as CatalogueItem;
              const vastuBadge = design.critic_verdict.vastu_result?.item_results.find((result) => result.item_id === item.item_id)?.badge;
              return (
                <article className="workspace-item-card" key={item.item_id}>
                  <img
                    src={safeImagePath(item)}
                    alt={item.title}
                    onError={(event) => {
                      event.currentTarget.src = "/product-placeholder.svg";
                    }}
                  />
                  <div>
                    <span className="product-category">{item.product_type}</span>
                    <h2>{item.title}</h2>
                    <p>
                      ID {item.item_id}: {item.width_cm} x {item.depth_cm} x {item.height_cm ?? "n/a"} cm - {item.material ?? "material n/a"} - {item.color ?? "colour n/a"}
                    </p>
                    <p>{design.critic_verdict.fit.notes.join(" ") || "Fit checked by backend."}</p>
                    <div className="item-meta-row">
                      <strong>{formatCurrency(item.price_inr)}</strong>
                      <span className="status hard">Zone {slot.placement_zone}</span>
                      {vastuEnabled ? <span className="status soft">Vastu {vastuBadge ?? design.critic_verdict.vastu.status}</span> : null}
                    </div>
                    <p className="alternatives">
                      Alternatives: {slot.alternatives.slice(0, 3).map((alternative) => `${alternative.item_id} ${alternative.title}`).join(", ")}
                    </p>
                  </div>
                </article>
              );
            })}
          </div>
        )}

        {activeTab === "vastu" && (
          <div className="workspace-vastu-panel">
            <ZoneGrid items={zoneItems} />
            <aside className="vastu-notes">
              <div className="score-card">
                <strong>{design?.critic_verdict.vastu_result?.score ?? 0}</strong>
                <p>{design?.critic_verdict.vastu.status ?? "waiting"} Vastu score.</p>
              </div>
              {ruleResults.slice(0, 4).map((rule) => (
                <article className="workspace-rule-card" key={`${rule.rule_id}-${rule.item_id}`}>
                  <strong>{rule.rule_id}: {rule.status}</strong>
                  <p>{rule.note}</p>
                  <p>{rule.rationale}</p>
                </article>
              ))}
              <article className="workspace-rule-card">
                <strong>Palette suggestions</strong>
                <p>{slots.map((slot) => slot.selected_item?.color).filter(Boolean).join(", ") || "Palette appears after backend selection."}</p>
              </article>
              <article className="workspace-rule-card">
                <strong>Actionable notes</strong>
                <p>{design?.critic_verdict.vastu_result?.notes.join(" ") || design?.critic_verdict.vastu.notes.join(" ") || "No Vastu action required."}</p>
              </article>
            </aside>
          </div>
        )}

        {activeTab === "shopping" && (
          <div className="workspace-shopping-panel" aria-label="Shopping list">
            <div className="budget-panel workspace-budget">
              <div>
                <span>Total</span>
                <strong>{formatCurrency(backendTotal)}</strong>
              </div>
              <div>
                <span>Budget</span>
                <strong>{formatCurrency(budget)}</strong>
              </div>
              <div className="budget-bar" aria-label="Budget bar status">
                <span style={{ width: `${budgetPercent}%` }} />
              </div>
              <p>
                {budgetStatus} budget. Displayed total {exactTotal ? "matches" : "does not match"} backend item sum.
              </p>
            </div>
            <div className="shopping-list">
              {slots.map((slot) => {
                const item = slot.selected_item as CatalogueItem;
                return (
                  <article className="product-row" key={`shopping-${item.item_id}`}>
                    <div>
                      <span className="product-category">{slot.slot.category}</span>
                      <h3>{item.title}</h3>
                      <p>{item.item_id}</p>
                    </div>
                    <strong>{formatCurrency(item.price_inr)}</strong>
                  </article>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
