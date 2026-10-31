"use client";

import { type CSSProperties, useState } from "react";

type BeforeAfterSliderProps = {
  beforeSrc?: string;
  afterSrc?: string;
  beforeAlt?: string;
  afterAlt?: string;
  className?: string;
};

export function BeforeAfterSlider({
  beforeSrc = "/before-interior.png",
  afterSrc = "/landing-interior.png",
  beforeAlt = "Room before redesign",
  afterAlt = "Room after redesign",
  className = "",
}: BeforeAfterSliderProps = {}) {
  const [split, setSplit] = useState(52);
  const sliderStyle = { "--split": `${split}%` } as CSSProperties;

  return (
    <div className={`ys-before-after ${className}`.trim()} style={sliderStyle}>
      <img
        className="ys-ba-image ys-ba-after"
        src={afterSrc}
        alt={afterAlt}
      />
      <img
        className="ys-ba-image ys-ba-before"
        src={beforeSrc}
        alt={beforeAlt}
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
