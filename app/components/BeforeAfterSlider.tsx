"use client";

import { type CSSProperties, useState } from "react";

export function BeforeAfterSlider() {
  const [split, setSplit] = useState(52);
  const sliderStyle = { "--split": `${split}%` } as CSSProperties;

  return (
    <div className="ys-before-after" style={sliderStyle}>
      <img
        className="ys-ba-image ys-ba-after"
        src="/landing-interior.png"
        alt="After interior design with warm green cabinetry, layered seating, and styled decor"
      />
      <img
        className="ys-ba-image ys-ba-before"
        src="/before-interior.png"
        alt="Before interior with a plain wall, existing seating, and basic furniture"
      />
      <span className="ys-ba-label ys-ba-label-before">Before</span>
      <span className="ys-ba-label ys-ba-label-after">After</span>
      <span className="ys-ba-divider" aria-hidden="true" />
      <span className="ys-ba-handle" aria-hidden="true">
        <span />
      </span>
      <input
        className="ys-ba-range"
        type="range"
        min="0"
        max="100"
        value={split}
        aria-label="Reveal before and after interior design"
        onChange={(event) => setSplit(Number(event.target.value))}
      />
    </div>
  );
}
