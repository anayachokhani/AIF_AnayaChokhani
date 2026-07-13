import Link from "next/link";
import { buildSteps, metrics } from "./data";

export default function OverviewPage() {
  return (
    <main className="page-shell">
      <section className="hero-section">
        <div className="hero-copy">
          <span className="eyebrow">Grounded home design MVP</span>
          <h1>FormaOS turns a room idea into a buildable plan.</h1>
          <p>
            The prototype focuses on one sharp claim: every suggested item should be real,
            priced, dimensioned, and checked against the user's room before it reaches the
            final brief.
          </p>
          <div className="hero-actions">
            <Link className="primary-button" href="/planner">
              Open planner
            </Link>
            <Link className="secondary-button" href="/validation">
              View checks
            </Link>
          </div>
        </div>
        <div className="hero-board" aria-label="FormaOS workflow summary">
          {buildSteps.map((step, index) => (
            <div className="step-card" key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <p>{step}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section-grid">
        <article className="feature-panel">
          <h2>What is different</h2>
          <p>
            A raw image generator can produce a beautiful scene, but it does not know
            whether the sofa exists, fits, or stays within budget. FormaOS puts retrieval
            and verification underneath the visual layer.
          </p>
        </article>
        <article className="feature-panel">
          <h2>MVP scope</h2>
          <p>
            The first version is living-room only, with a curated catalogue, 2D fit
            checking, budget checks, optional Vastu guidance, and a shareable design
            brief.
          </p>
        </article>
      </section>

      <section className="metric-strip">
        {metrics.map((metric) => (
          <article key={metric.label}>
            <strong>{metric.value}</strong>
            <span>{metric.label}</span>
            <p>{metric.note}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
