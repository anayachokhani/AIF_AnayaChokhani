"use client";

import type { FormEvent } from "react";
import { useMemo, useState } from "react";
import { formatCurrency, products } from "../data";

const requiredCategories = ["Sofa", "Coffee table", "Rug", "Storage", "Lighting"];
const directionOptions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "C"];
const unitOptions = {
  cm: { label: "cm", minWidth: 240, maxWidth: 520, minDepth: 260, maxDepth: 620, step: 10 },
  ft: { label: "ft", minWidth: 8, maxWidth: 18, minDepth: 8, maxDepth: 22, step: 0.5 },
  m: { label: "m", minWidth: 2.4, maxWidth: 5.5, minDepth: 2.6, maxDepth: 6.5, step: 0.1 },
};

type Unit = keyof typeof unitOptions;

function toCm(value: number, unit: Unit) {
  if (unit === "cm") return value;
  if (unit === "m") return value * 100;
  return value * 30.48;
}

function scoreProduct(styles: string[], brief: string) {
  const normalized = brief.toLowerCase();
  return styles.reduce((score, tag) => {
    return normalized.includes(tag) ? score + 3 : score + (normalized.includes(tag.split(" ")[0]) ? 1 : 0);
  }, 0);
}

function splitWords(value: string) {
  return value
    .toLowerCase()
    .split(/[, ]+/)
    .map((word) => word.trim())
    .filter(Boolean);
}

function constraintsFromStyle(value: string) {
  const normalized = value.toLowerCase();
  const constraints = [];
  if (normalized.includes("kid") || normalized.includes("child")) constraints.push("kid-friendly");
  if (normalized.includes("play")) constraints.push("play space");
  if (normalized.includes("storage")) constraints.push("extra storage");
  return constraints;
}

export function PlannerTool() {
  const [roomType, setRoomType] = useState("living_room");
  const [units, setUnits] = useState<Unit>("cm");
  const [width, setWidth] = useState(360);
  const [depth, setDepth] = useState(420);
  const [budget, setBudget] = useState(85000);
  const [style, setStyle] = useState("warm modern family storage");
  const [vastu, setVastu] = useState(true);
  const [mainDoor, setMainDoor] = useState("N");
  const [compass, setCompass] = useState("N");
  const [sessionStatus, setSessionStatus] = useState("No backend session yet");

  const plan = useMemo(() => {
    const widthCm = toCm(width, units);
    const depthCm = toCm(depth, units);
    const maxItemWidth = widthCm * 0.68;
    const maxItemDepth = depthCm * 0.42;
    const selected = requiredCategories.map((category) => {
      const matches = products
        .filter((product) => product.category === category)
        .map((product) => ({
          ...product,
          score: scoreProduct(product.style, style),
          fits: product.width <= maxItemWidth && product.depth <= maxItemDepth,
        }))
        .sort((a, b) => Number(b.fits) - Number(a.fits) || b.score - a.score || a.price - b.price);

      return matches[0];
    });

    const total = selected.reduce((sum, product) => sum + product.price, 0);
    const fitPass = selected.every((product) => product.fits);
    const budgetPass = total <= budget;
    const revision =
      !budgetPass || !fitPass
        ? "The critic would revise this plan by replacing oversized or expensive items before final delivery."
        : "All hard checks pass for this first draft.";

    return {
      selected,
      total,
      widthCm,
      depthCm,
      fitPass,
      budgetPass,
      sourcePass: selected.every(Boolean),
      vastuNote: vastu
        ? `Vastu guidance enabled: compass ${compass}, main door ${mainDoor}; keep the heaviest storage on the south or west wall and prefer seating that faces north or east.`
        : "Vastu guidance disabled for this run.",
      revision,
    };
  }, [width, depth, units, budget, style, vastu, mainDoor, compass]);

  const currentUnit = unitOptions[units];
  const roomBrief = {
    room_type: roomType,
    width,
    depth,
    units,
    budget_inr: budget,
    style_words: splitWords(style),
    constraints: constraintsFromStyle(style),
    vastu_enabled: vastu,
    main_door_direction: mainDoor,
    compass_direction: compass,
  };

  async function createBackendSession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSessionStatus("Saving room brief...");
    try {
      const response = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ brief: roomBrief }),
      });
      if (!response.ok) {
        setSessionStatus("Backend rejected the room brief");
        return;
      }
      const payload = await response.json();
      setSessionStatus(`Session ${payload.session_id}`);
    } catch {
      setSessionStatus("Backend unavailable");
    }
  }

  return (
    <div className="planner-grid">
      <form className="control-panel" aria-label="Room planning controls" onSubmit={createBackendSession}>
        <label>
          Room type
          <select
            className="select-input"
            value={roomType}
            onChange={(event) => setRoomType(event.target.value)}
            aria-label="Room type"
          >
            <option value="living_room">Living room</option>
            <option value="bedroom">Bedroom</option>
            <option value="study">Study</option>
          </select>
        </label>
        <label>
          Units
          <select
            className="select-input"
            value={units}
            onChange={(event) => {
              const next = event.target.value as Unit;
              setUnits(next);
              setWidth(next === "cm" ? 360 : next === "ft" ? 12 : 3.6);
              setDepth(next === "cm" ? 420 : next === "ft" ? 14 : 4.2);
            }}
            aria-label="Measurement units"
          >
            <option value="cm">Centimeters</option>
            <option value="ft">Feet</option>
            <option value="m">Meters</option>
          </select>
        </label>
        <label>
          Room width
          <span>
            {width} {currentUnit.label} ({Math.round(plan.widthCm)} cm)
          </span>
          <input
            type="range"
            min={currentUnit.minWidth}
            max={currentUnit.maxWidth}
            step={currentUnit.step}
            value={width}
            onChange={(event) => setWidth(Number(event.target.value))}
          />
        </label>
        <label>
          Room depth
          <span>
            {depth} {currentUnit.label} ({Math.round(plan.depthCm)} cm)
          </span>
          <input
            type="range"
            min={currentUnit.minDepth}
            max={currentUnit.maxDepth}
            step={currentUnit.step}
            value={depth}
            onChange={(event) => setDepth(Number(event.target.value))}
          />
        </label>
        <label>
          Budget
          <span>{formatCurrency(budget)}</span>
          <input
            type="range"
            min="40000"
            max="160000"
            step="5000"
            value={budget}
            onChange={(event) => setBudget(Number(event.target.value))}
          />
        </label>
        <label>
          Style brief
          <input
            className="text-input"
            value={style}
            onChange={(event) => setStyle(event.target.value)}
            aria-label="Style brief"
          />
        </label>
        <label>
          Main door direction
          <select
            className="select-input"
            value={mainDoor}
            onChange={(event) => setMainDoor(event.target.value)}
            aria-label="Main door direction"
          >
            {directionOptions.map((direction) => (
              <option key={direction} value={direction}>
                {direction}
              </option>
            ))}
          </select>
        </label>
        <label>
          Compass direction
          <select
            className="select-input"
            value={compass}
            onChange={(event) => setCompass(event.target.value)}
            aria-label="Compass direction"
          >
            {directionOptions.map((direction) => (
              <option key={direction} value={direction}>
                {direction}
              </option>
            ))}
          </select>
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={vastu}
            onChange={(event) => setVastu(event.target.checked)}
          />
          Apply Vastu guidance
        </label>
        <div className="state-summary" aria-label="Normalized room state">
          <strong>RoomBrief</strong>
          <span>{roomType.replace("_", " ")}</span>
          <span>
            {Math.round(plan.widthCm)} x {Math.round(plan.depthCm)} cm
          </span>
          <span>{formatCurrency(budget)}</span>
          <span>{sessionStatus}</span>
        </div>
        <button className="primary-action" type="submit">
          Save RoomBrief
        </button>
      </form>

      <section className="result-panel" aria-label="Generated buildable plan">
        <div className="room-preview">
          <div className="wall north">N</div>
          <div className="room-area">
            <span className="furniture sofa">Sofa</span>
            <span className="furniture table">Table</span>
            <span className="furniture rug">Rug</span>
            <span className="furniture storage">Storage</span>
            <span className="furniture lamp">Lamp</span>
          </div>
        </div>

        <div className="checks">
          <span className={plan.sourcePass ? "check pass" : "check fail"}>Sourceable</span>
          <span className={plan.fitPass ? "check pass" : "check fail"}>Fits room</span>
          <span className={plan.budgetPass ? "check pass" : "check fail"}>Within budget</span>
        </div>

        <div className="total-row">
          <span>Total plan cost</span>
          <strong>{formatCurrency(plan.total)}</strong>
        </div>

        <div className="shopping-list">
          {plan.selected.map((product) => (
            <article key={product.id} className="product-row">
              <div>
                <span className="product-category">{product.category}</span>
                <h3>{product.name}</h3>
                <p>
                  {product.width} x {product.depth} x {product.height} cm - {product.material} -{" "}
                  {product.finish}
                </p>
              </div>
              <strong>{formatCurrency(product.price)}</strong>
            </article>
          ))}
        </div>

        <p className="note">{plan.vastuNote}</p>
        <p className="note">{plan.revision}</p>
      </section>
    </div>
  );
}
