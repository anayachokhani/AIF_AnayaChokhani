import { ZoneGrid } from "../components/ZoneGrid";
import { planItems, productById } from "../data";

export default function VastuPage() {
  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">Opt-in rule layer</span>
        <h1>Vastu</h1>
        <p>
          The MVP uses a simple 3 by 3 zone model and deterministic rule notes. It is
          shown as guidance, not as an authoritative professional claim.
        </p>
      </section>

      <section className="vastu-layout">
        <ZoneGrid items={planItems} />

        <div className="vastu-notes">
          <div className="score-card">
            <span>Vastu score</span>
            <strong>82</strong>
            <p>Good alignment with storage, seating, and lighting guidance.</p>
          </div>
          {planItems.map((planItem) => {
            const product = productById(planItem.itemId);
            return (
              <article className="validation-card" key={planItem.itemId}>
                <div>
                  <span className="status hard">Guidance</span>
                  <h2>{planItem.slot}</h2>
                </div>
                <p>
                  {product?.name}: {planItem.vastu}
                </p>
              </article>
            );
          })}
        </div>
      </section>
    </main>
  );
}
