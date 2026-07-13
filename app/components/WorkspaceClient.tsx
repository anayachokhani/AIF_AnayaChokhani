"use client";

import type { FormEvent } from "react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { formatCurrency } from "../data";
import { ZoneGrid, type ZoneGridItem } from "./ZoneGrid";

const directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "C"] as const;
const units = ["ft", "m", "cm"] as const;
const progressStates = ["planning", "designing", "grounding", "checking", "revising", "passed", "failed", "error"] as const;
const tabs = ["items", "vastu", "shopping"] as const;
const wizardSteps = ["Space", "Style", "Preferences", "Budget", "Review"] as const;
const API_BASE = process.env.NEXT_PUBLIC_FORMAOS_API_BASE ?? "http://localhost:8000";
const USER_STORAGE_KEY = "formaos_homeowner";
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
  slot: { slot_id: string; category: string; placement_hint?: Direction | null };
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
  session_id: string;
  user_id?: string | null;
  generated_at: string;
  status: "passed" | "failed";
  grounder_output: { grounded_slots: GroundedSlot[] };
  critic_verdict: {
    passed: boolean;
    total_price_inr: number;
    fit: { status: string; notes: string[] };
    budget: { status: string; notes: string[] };
    vastu: { status: string; notes: string[] };
    vastu_result?: { score: number; item_results: VastuItemResult[]; notes: string[] } | null;
  };
};

type DesignSummary = {
  design_id: string;
  session_id: string;
  user_id?: string | null;
  generated_at: string;
  status: string;
  room_type: string;
  total_price_inr: number;
  item_count: number;
  style_words: string[];
};

type StoredHomeowner = {
  id: string;
  name: string;
  email: string;
};

type PhotoNote = {
  name: string;
  url: string;
  note: string;
};

type ConceptImage = {
  mode: "generated" | "prompt_only";
  image_prompt: string;
  image_data_url?: string | null;
  notes: string[];
};

class ApiRequestError extends Error {
  design?: BackendDesign;

  constructor(message: string, design?: BackendDesign) {
    super(message);
    this.design = design;
  }
}

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
  if (normalized.includes("light")) constraints.push("natural light");
  if (normalized.includes("storage")) constraints.push("extra storage");
  if (normalized.includes("open")) constraints.push("open layout");
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

function selectedSlots(design: BackendDesign | null) {
  return design?.grounder_output.grounded_slots.filter((slot) => slot.selected_item) ?? [];
}

function errorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return fallback;
  const detail = (payload as { detail?: { code?: string; message?: string } }).detail;
  const knownCode = apiErrorStates.find((code) => code === detail?.code);
  return knownCode ? `${knownCode}: ${detail?.message ?? fallback}` : fallback;
}

function errorDesign(payload: unknown) {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return undefined;
  return (payload as { detail?: { design?: BackendDesign } }).detail?.design;
}

const styleOptions = ["Modern", "Minimal", "Scandinavian", "Boho", "Contemporary", "Classic", "Japandi", "Industrial"];
const preferenceOptions = ["More storage", "Natural light", "Open layout", "Greenery", "Warm tones", "Modern look", "Smart lighting", "Kid friendly"];
const sampleRooms = [
  "https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=700&q=80",
  "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=700&q=80",
  "https://images.unsplash.com/photo-1618221195710-dd6b41faaea6?auto=format&fit=crop&w=700&q=80",
  "https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?auto=format&fit=crop&w=700&q=80",
  "https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=700&q=80",
  "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=700&q=80",
];
const projectImages = [
  "https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=560&q=80",
  "https://images.unsplash.com/photo-1616594039964-ae9021a400a0?auto=format&fit=crop&w=560&q=80",
  "https://images.unsplash.com/photo-1600607687644-c7171b42498f?auto=format&fit=crop&w=560&q=80",
  "https://images.unsplash.com/photo-1600566752355-35792bedcfea?auto=format&fit=crop&w=560&q=80",
];

export function WorkspaceClient() {
  const [homeowner, setHomeowner] = useState<StoredHomeowner | null>(null);
  const [step, setStep] = useState(0);
  const [activeTab, setActiveTab] = useState<Tab>("items");
  const [progress, setProgress] = useState<ProgressState>("planning");
  const [sessionId, setSessionId] = useState("");
  const [design, setDesign] = useState<BackendDesign | null>(null);
  const [conceptImage, setConceptImage] = useState<ConceptImage | null>(null);
  const [savedDesigns, setSavedDesigns] = useState<DesignSummary[]>([]);
  const [photos, setPhotos] = useState<PhotoNote[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [roomType, setRoomType] = useState("living_room");
  const [unit, setUnit] = useState<Unit>("ft");
  const [width, setWidth] = useState(14);
  const [depth, setDepth] = useState(18);
  const [height, setHeight] = useState(10);
  const [budget, setBudget] = useState(245000);
  const [selectedStyles, setSelectedStyles] = useState(["Modern"]);
  const [selectedPreferences, setSelectedPreferences] = useState(["More storage", "Natural light", "Greenery"]);
  const [vastuEnabled, setVastuEnabled] = useState(true);
  const [mainDoor, setMainDoor] = useState<Direction>("N");
  const [compass, setCompass] = useState<Direction>("N");
  const [revisionMessage, setRevisionMessage] = useState("Make this calmer and keep the same budget.");

  const style = [...selectedStyles, ...selectedPreferences].join(" ");
  const designGoal = `Design my ${roomType.replace("_", " ")} with ${selectedStyles.join(", ")} style.`;
  const message = `Create a saved design with ${selectedPreferences.join(", ")}.`;
  const dimensionsLabel = `${depth} ft x ${width} ft x ${height} ft`;
  const photoNotes = photos.map((photo) => `${photo.name}: ${photo.note}`);
  const slots = selectedSlots(design);
  const visibleTotal = slots.reduce((sum, slot) => sum + (slot.selected_item?.price_inr ?? 0), 0);
  const backendTotal = design?.critic_verdict.total_price_inr ?? 0;
  const exactTotal = design ? visibleTotal === backendTotal : false;
  const budgetPercent = budget > 0 ? Math.min(100, Math.round(((design ? backendTotal : budget) / budget) * 100)) : 0;
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

  useEffect(() => {
    function readUser() {
      const stored = window.localStorage.getItem(USER_STORAGE_KEY);
      if (!stored) {
        setHomeowner(null);
        setSavedDesigns([]);
        return;
      }
      try {
        const parsed = JSON.parse(stored) as StoredHomeowner;
        setHomeowner(parsed);
        refreshSavedDesigns(parsed).catch(() => setSavedDesigns([]));
      } catch {
        window.localStorage.removeItem(USER_STORAGE_KEY);
      }
    }

    readUser();
    window.addEventListener("storage", readUser);
    window.addEventListener("formaos-user-change", readUser);
    return () => {
      window.removeEventListener("storage", readUser);
      window.removeEventListener("formaos-user-change", readUser);
    };
  }, []);

  async function parseResponse(response: Response) {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new ApiRequestError(errorMessage(payload, "API request failed"), errorDesign(payload));
    return payload;
  }

  async function refreshSavedDesigns(user = homeowner) {
    if (!user) {
      setSavedDesigns([]);
      return;
    }
    const response = await fetch(apiUrl(`/api/designs?user_id=${encodeURIComponent(user.id)}`));
    const payload = await parseResponse(response);
    setSavedDesigns(payload.designs ?? []);
  }

  function toggleOption(value: string, selected: string[], setter: (values: string[]) => void, limit?: number) {
    if (selected.includes(value)) {
      setter(selected.filter((item) => item !== value));
      return;
    }
    if (limit && selected.length >= limit) return;
    setter([...selected, value]);
  }

  function handlePhotos(files: FileList | null) {
    if (!files) return;
    const selected = Array.from(files).slice(0, 4).map((file) => ({
      name: file.name,
      url: URL.createObjectURL(file),
      note: "Room reference for dimensions, light, and furniture placement.",
    }));
    setPhotos((current) => [...current, ...selected].slice(0, 4));
  }

  async function loadDesign(designId: string) {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(apiUrl(`/api/design/${designId}`));
      const payload = await parseResponse(response);
      setDesign(payload.design);
      setSessionId(payload.design.session_id);
      setProgress(payload.design.status === "failed" ? "failed" : "passed");
      setStep(4);
    } catch (caught) {
      setProgress("error");
      setError(caught instanceof Error ? caught.message : "general error");
    } finally {
      setLoading(false);
    }
  }

  async function generateConcept(sourceDesign = design) {
    if (!sourceDesign) return;
    const response = await fetch(apiUrl("/api/concept-image"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_type: "new_space",
        room_type: roomType,
        dimensions: dimensionsLabel,
        style_words: styleWords(style),
        constraints: constraintsFrom(style),
        questionnaire: {
          mood: selectedStyles.join(", "),
          priority: selectedPreferences.join(", "),
          avoid: "clutter, wrong scale, unrealistic furniture",
          lifestyle: "homeowner-led design",
        },
        photo_notes: photoNotes,
        vastu_enabled: vastuEnabled,
        grounded_design: sourceDesign,
      }),
    });
    const payload = await parseResponse(response);
    setConceptImage(payload);
  }

  async function startDesign() {
    if (!homeowner) {
      setError("sign_in_required: sign in so YourSpace can save this design to your account");
      return;
    }
    setLoading(true);
    setError("");
    setDesign(null);
    setConceptImage(null);
    setProgress("planning");
    try {
      const sessionResponse = await fetch(apiUrl("/api/session"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brief: roomBrief, user_id: homeowner.id }),
      });
      const sessionPayload = await parseResponse(sessionResponse);
      setSessionId(sessionPayload.session_id);

      setProgress("designing");
      const chatResponse = await fetch(apiUrl("/api/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionPayload.session_id,
          message: [
            designGoal,
            `Dimensions: ${dimensionsLabel}.`,
            `Style: ${selectedStyles.join(", ")}.`,
            `Preferences: ${selectedPreferences.join(", ")}.`,
            `Photo notes: ${photoNotes.join("; ") || "no photos uploaded"}.`,
            message,
          ].join(" "),
          max_retries: 2,
        }),
      });
      setProgress("grounding");
      const chatPayload = await parseResponse(chatResponse);
      setProgress("checking");
      setDesign(chatPayload.design);
      await refreshSavedDesigns();
      setProgress(chatPayload.design?.status === "failed" ? "failed" : "passed");
      await generateConcept(chatPayload.design);
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.design) {
        setDesign(caught.design);
        await refreshSavedDesigns().catch(() => undefined);
      }
      setProgress("error");
      setError(caught instanceof Error ? caught.message : "general error");
    } finally {
      setLoading(false);
    }
  }

  async function reviseDesign() {
    if (!design) return;
    setLoading(true);
    setError("");
    setProgress("revising");
    try {
      const response = await fetch(apiUrl(`/api/design/${design.design_id}/revise`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: revisionMessage, max_retries: 2 }),
      });
      const payload = await parseResponse(response);
      setDesign(payload.design);
      await refreshSavedDesigns();
      setProgress(payload.design?.status === "failed" ? "failed" : "passed");
      await generateConcept(payload.design);
    } catch (caught) {
      setProgress("error");
      setError(caught instanceof Error ? caught.message : "general error");
    } finally {
      setLoading(false);
    }
  }

  function nextStep(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (step < wizardSteps.length - 1) setStep(step + 1);
  }

  function previousStep() {
    if (step > 0) setStep(step - 1);
  }

  return (
    <section className="ys-app-shell" aria-label="FormaOS design workspace">
      <div className="ys-brand-row">
        <Link className="ys-logo" href="/">
          <img className="ys-logo-image" src="/yourspace-logo.png" alt="" />
          <strong>YourSpace</strong>
        </Link>
        <div className="ys-user-mini">
          {homeowner ? <span>{homeowner.name}</span> : <Link href="/login?next=/workspace">Log in</Link>}
        </div>
      </div>

      <div className="ys-stepper" aria-label="Agent progress states">
        {wizardSteps.map((label, index) => (
          <button key={label} type="button" className={index === step ? "active" : index < step ? "done" : ""} onClick={() => setStep(index)}>
            <span>{index + 1}</span>
            {label}
          </button>
        ))}
      </div>

      <div className="ys-progress-markers" aria-hidden="true">
        {progressStates.map((state) => (
          <span key={state}>{state}</span>
        ))}
        <span>Grounded item cards</span>
        <span>Product photo collage</span>
        <span>Design workspace tabs</span>
        <span>Shopping list</span>
        <span>Empty design state</span>
      </div>

      {step < 4 ? (
        <form className="ys-wizard-card" onSubmit={nextStep}>
          {step === 0 ? (
            <section className="ys-step-layout">
              <div>
                <h1>Let's get to know your space</h1>
                <p>Upload photos and add room dimensions.</p>
                <label className="ys-upload">
                  <input type="file" accept="image/*" multiple onChange={(event) => handlePhotos(event.target.files)} />
                  <span>Upload photos</span>
                  <small>Drag and drop or click to browse</small>
                </label>
                <div className="ys-photo-strip">
                  {[...photos.map((photo) => photo.url), ...sampleRooms].slice(0, 4).map((url, index) => (
                    <img key={`${url}-${index}`} src={url} alt={`Room reference ${index + 1}`} />
                  ))}
                  <button type="button">+ Add more</button>
                </div>
              </div>
              <div className="ys-form-grid">
                <strong>Room dimensions</strong>
                <label>
                  Length
                  <input value={depth} type="number" min="1" onChange={(event) => setDepth(Number(event.target.value))} />
                  <span>{unit}</span>
                </label>
                <label>
                  Width
                  <input value={width} type="number" min="1" onChange={(event) => setWidth(Number(event.target.value))} />
                  <span>{unit}</span>
                </label>
                <label>
                  Height
                  <input value={height} type="number" min="1" onChange={(event) => setHeight(Number(event.target.value))} />
                  <span>{unit}</span>
                </label>
                <label>
                  Units
                  <select value={unit} onChange={(event) => setUnit(event.target.value as Unit)}>
                    {units.map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </label>
                <label className="wide">
                  Room type
                  <select value={roomType} onChange={(event) => setRoomType(event.target.value)}>
                    <option value="living_room">Living room</option>
                    <option value="bedroom">Master bedroom</option>
                    <option value="study">Home office</option>
                  </select>
                </label>
              </div>
            </section>
          ) : null}

          {step === 1 ? (
            <section>
              <h1>What's your style?</h1>
              <p>Choose up to 3 styles you love.</p>
              <div className="ys-style-grid">
                {styleOptions.map((option, index) => (
                  <button key={option} type="button" className={selectedStyles.includes(option) ? "selected" : ""} onClick={() => toggleOption(option, selectedStyles, setSelectedStyles, 3)}>
                    <img src={sampleRooms[index % sampleRooms.length]} alt={`${option} room`} />
                    <span>{option}</span>
                  </button>
                ))}
              </div>
            </section>
          ) : null}

          {step === 2 ? (
            <section>
              <h1>What matters most to you?</h1>
              <p>Select your preferences.</p>
              <div className="ys-pref-grid">
                {preferenceOptions.map((option) => (
                  <button key={option} type="button" className={selectedPreferences.includes(option) ? "selected" : ""} onClick={() => toggleOption(option, selectedPreferences, setSelectedPreferences)}>
                    <span>{option.slice(0, 2)}</span>
                    {option}
                  </button>
                ))}
              </div>
              <div className="ys-vastu-row">
                <label>
                  <input type="checkbox" checked={vastuEnabled} onChange={(event) => setVastuEnabled(event.target.checked)} />
                  Vastu aware
                </label>
                <select value={mainDoor} onChange={(event) => setMainDoor(event.target.value as Direction)}>
                  {directions.map((direction) => <option key={direction} value={direction}>Door {direction}</option>)}
                </select>
                <select value={compass} onChange={(event) => setCompass(event.target.value as Direction)}>
                  {directions.map((direction) => <option key={direction} value={direction}>Compass {direction}</option>)}
                </select>
              </div>
            </section>
          ) : null}

          {step === 3 ? (
            <section className="ys-budget-step">
              <h1>What's your budget?</h1>
              <p>Set your comfortable budget range.</p>
              <div className="ys-budget-value">{formatCurrency(budget)}</div>
              <input type="range" min="50000" max="500000" step="5000" value={budget} onChange={(event) => setBudget(Number(event.target.value))} />
              <div className="ys-range-labels">
                <span>{formatCurrency(50000)}</span>
                <span>{formatCurrency(500000)}</span>
              </div>
              <p className="ys-hint">We'll recommend furniture items that fit your budget.</p>
            </section>
          ) : null}

          <div className="ys-wizard-actions">
            {step > 0 ? <button className="secondary-button" type="button" onClick={previousStep}>Back</button> : <span />}
            <button className="primary-button" type="submit">Next</button>
          </div>
        </form>
      ) : (
        <section className="ys-review-grid">
          <div className="ys-review-card">
            <h1>Almost there!</h1>
            <p>Review your details before we design.</p>
            <dl>
              <div><dt>Room type</dt><dd>{roomType.replace("_", " ")}</dd></div>
              <div><dt>Dimensions</dt><dd>{dimensionsLabel}</dd></div>
              <div><dt>Style</dt><dd>{selectedStyles.join(", ")}</dd></div>
              <div><dt>Preferences</dt><dd>{selectedPreferences.join(", ")}</dd></div>
              <div><dt>Budget</dt><dd>{formatCurrency(budget)}</dd></div>
            </dl>
            <div className="ys-wizard-actions">
              <button className="secondary-button" type="button" onClick={previousStep}>Back</button>
              <button className="primary-button" type="button" onClick={startDesign} disabled={loading}>
                {loading ? "Generating..." : "Generate designs"}
              </button>
            </div>
            {error ? <p className="workspace-error" role="alert">{error}</p> : null}
          </div>

          <div className="ys-projects-card" aria-label="Saved designs">
            <div className="ys-projects-heading">
              <h2>My Projects</h2>
              <button type="button" onClick={() => setStep(0)}>+ New Project</button>
            </div>
            <div className="ys-project-grid">
              {savedDesigns.length ? savedDesigns.map((savedDesign, index) => (
                <button key={savedDesign.design_id} type="button" onClick={() => loadDesign(savedDesign.design_id)}>
                  <img className="ys-room-thumb" src={projectImages[index % projectImages.length]} alt={`${savedDesign.room_type.replace("_", " ")} project`} />
                  <strong>{savedDesign.room_type.replace("_", " ")}</strong>
                  <span>Updated recently</span>
                </button>
              )) : (
                ["Living room", "Master bedroom", "Dining area", "Home office"].map((name, index) => (
                  <button key={name} type="button">
                    <img className="ys-room-thumb" src={projectImages[index % projectImages.length]} alt={`${name} project preview`} />
                    <strong>{name}</strong>
                    <span>Generate to save here</span>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="ys-results-card">
            <div className="workspace-toolbar">
              <div>
                <span className="eyebrow">Checked design</span>
                <h1>{design ? "Generated concept" : "Waiting for design"}</h1>
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
                  <img key={`collage-${slot.selected_item?.item_id}`} src={safeImagePath(slot.selected_item as CatalogueItem)} alt={slot.selected_item?.title ?? slot.slot.category} onError={(event) => { event.currentTarget.src = "/product-placeholder.svg"; }} />
                ))}
              </div>
            ) : (
              <div className="workspace-empty-state" aria-label="Empty design state">Your generated concept, selected items, checks, and saved version appear here.</div>
            )}

            <section className="concept-panel" aria-label="Generated interior concept">
              <div className="concept-heading">
                <div>
                  <span className="eyebrow">Final visual concept</span>
                  <h2>{conceptImage?.mode === "generated" ? "Generated image" : "Image generation brief"}</h2>
                </div>
                <span className={conceptImage?.mode === "generated" ? "status hard" : "status soft"}>{conceptImage?.mode === "generated" ? "Image ready" : "Prompt ready"}</span>
              </div>
              {conceptImage?.image_data_url ? <img className="concept-image" src={conceptImage.image_data_url} alt="Generated interior design concept" /> : null}
              {conceptImage && !conceptImage.image_data_url ? <pre>{conceptImage.image_prompt}</pre> : null}
              {design ? (
                <div className="studio-action-row">
                  <Link className="secondary-button" href={`/design/${design.design_id}/brief`}>Open export brief</Link>
                  <button className="secondary-button" type="button" onClick={reviseDesign} disabled={loading}>Revise</button>
                  <input value={revisionMessage} onChange={(event) => setRevisionMessage(event.target.value)} aria-label="Revision message" />
                </div>
              ) : null}
            </section>

            <div className="workspace-tabs" role="tablist" aria-label="Design workspace tabs">
              {tabs.map((tab) => (
                <button key={tab} className={activeTab === tab ? "workspace-tab active" : "workspace-tab"} type="button" onClick={() => setActiveTab(tab)}>
                  {tab === "shopping" ? "Shopping list" : tab}
                </button>
              ))}
            </div>

            {activeTab === "items" ? (
              <div className="workspace-item-grid" aria-label="Grounded item cards">
                {slots.map((slot) => {
                  const item = slot.selected_item as CatalogueItem;
                  const vastuBadge = design?.critic_verdict.vastu_result?.item_results.find((result) => result.item_id === item.item_id)?.badge;
                  return (
                    <article className="workspace-item-card" key={item.item_id}>
                      <img src={safeImagePath(item)} alt={item.title} onError={(event) => { event.currentTarget.src = "/product-placeholder.svg"; }} />
                      <div>
                        <span className="product-category">{item.product_type}</span>
                        <h2>{item.title}</h2>
                        <p>ID {item.item_id}: {item.width_cm} x {item.depth_cm} x {item.height_cm ?? "n/a"} cm - {item.material ?? "material n/a"} - {item.color ?? "colour n/a"}</p>
                        <p>{design?.critic_verdict.fit.notes.join(" ") || "Fit checked by backend."}</p>
                        <div className="item-meta-row">
                          <strong>{formatCurrency(item.price_inr)}</strong>
                          <span className="status hard">Zone {slot.placement_zone}</span>
                          {vastuEnabled ? <span className="status soft">Vastu {vastuBadge ?? design?.critic_verdict.vastu.status}</span> : null}
                        </div>
                        <p className="alternatives">Alternatives: {slot.alternatives.slice(0, 3).map((alternative) => `${alternative.item_id} ${alternative.title}`).join(", ")}</p>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : null}

            {activeTab === "vastu" ? (
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
                  <article className="workspace-rule-card"><strong>Palette suggestions</strong><p>{slots.map((slot) => slot.selected_item?.color).filter(Boolean).join(", ") || "Palette appears after backend selection."}</p></article>
                  <article className="workspace-rule-card"><strong>Actionable notes</strong><p>{design?.critic_verdict.vastu_result?.notes.join(" ") || design?.critic_verdict.vastu.notes.join(" ") || "No Vastu action required."}</p></article>
                </aside>
              </div>
            ) : null}

            {activeTab === "shopping" ? (
              <div className="workspace-shopping-panel" aria-label="Shopping list">
                <div className="budget-panel workspace-budget">
                  <div><span>Total</span><strong>{formatCurrency(backendTotal)}</strong></div>
                  <div><span>Budget</span><strong>{formatCurrency(budget)}</strong></div>
                  <div className="budget-bar" aria-label="Budget bar status"><span style={{ width: `${budgetPercent}%` }} /></div>
                  <p>{budgetStatus} budget. Displayed total {exactTotal ? "matches" : "does not match"} backend item sum.</p>
                </div>
                <div className="shopping-list">
                  {slots.map((slot) => {
                    const item = slot.selected_item as CatalogueItem;
                    return <article className="product-row" key={`shopping-${item.item_id}`}><div><span className="product-category">{slot.slot.category}</span><h3>{item.title}</h3><p>{item.item_id}</p></div><strong>{formatCurrency(item.price_inr)}</strong></article>;
                  })}
                </div>
              </div>
            ) : null}
          </div>
        </section>
      )}
    </section>
  );
}
