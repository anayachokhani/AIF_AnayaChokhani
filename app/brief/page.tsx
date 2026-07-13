"use client";

import { attempts, demoBrief, formatCurrency, planItems, productById } from "../data";

export default function BriefPage() {
  const selected = planItems
    .map((planItem) => ({ planItem, product: productById(planItem.itemId) }))
    .filter((entry) => entry.product);
  const total = selected.reduce((sum, entry) => sum + (entry.product?.price ?? 0), 0);

  return (
    <main className="page-shell printable-page">
      <section className="page-heading brief-heading">
        <span className="eyebrow">Shareable artifact</span>
        <h1>Export Brief</h1>
        <p>
          A designer or homeowner can read this page without the chat history and still
          understand the room, selected items, checks, and cost.
        </p>
        <button className="secondary-button print-button" type="button" onClick={() => globalThis.print()}>
          Print brief
        </button>
      </section>

      <section className="brief-grid">
        <article className="feature-panel">
          <h2>Room brief</h2>
          <dl className="brief-list">
            <div>
              <dt>Room</dt>
              <dd>{demoBrief.roomType}</dd>
            </div>
            <div>
              <dt>Dimensions</dt>
              <dd>{demoBrief.dimensions}</dd>
            </div>
            <div>
              <dt>Budget</dt>
              <dd>{formatCurrency(demoBrief.budget)}</dd>
            </div>
            <div>
              <dt>Style</dt>
              <dd>{demoBrief.style}</dd>
            </div>
            <div>
              <dt>Vastu</dt>
              <dd>{demoBrief.vastu}</dd>
            </div>
          </dl>
        </article>

        <article className="feature-panel">
          <h2>Checks</h2>
          <div className="checks always-visible">
            <span className="check pass">Sourceable</span>
            <span className="check pass">Fits room</span>
            <span className="check pass">Within budget</span>
            <span className="check pass">Vastu guidance reviewed</span>
          </div>
          <p className="note">
            Total selected item cost is {formatCurrency(total)}. Prices are curated
            indicative demo values because ABO does not provide prices.
          </p>
        </article>
      </section>

      <section className="shopping-list page-list brief-items">
        {selected.map(({ planItem, product }) => (
          <article className="product-row detailed-row" key={planItem.itemId}>
            <div>
              <span className="product-category">{planItem.slot}</span>
              <h2>{product?.name}</h2>
              <p>
                {product?.width} x {product?.depth} x {product?.height} cm - {product?.material} -{" "}
                {product?.finish}
              </p>
              <p>{planItem.fitNote}</p>
              <p>{planItem.vastu}</p>
            </div>
            <strong>{formatCurrency(product?.price ?? 0)}</strong>
          </article>
        ))}
      </section>

      <section className="logic-panel">
        <h2>Attempt log</h2>
        <div className="attempt-list">
          {attempts.map((attempt) => (
            <article key={attempt.name}>
              <strong>{attempt.name}</strong>
              <span className={attempt.result === "Passed" ? "status hard" : "status fail-status"}>
                {attempt.result}
              </span>
              <p>{attempt.note}</p>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
