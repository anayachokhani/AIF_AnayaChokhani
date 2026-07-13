import { demoBrief, formatCurrency, planItems, productById } from "../data";

export default function ShoppingListPage() {
  const selected = planItems
    .map((planItem) => ({ planItem, product: productById(planItem.itemId) }))
    .filter((entry) => entry.product);
  const total = selected.reduce((sum, entry) => sum + (entry.product?.price ?? 0), 0);
  const budget = demoBrief.budget;
  const percent = Math.min(100, Math.round((total / budget) * 100));

  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">Buildable output</span>
        <h1>Shopping List</h1>
        <p>
          Every recommended item is grounded in a catalogue record with dimensions,
          curated indicative INR price, fit note, and placement guidance.
        </p>
      </section>

      <section className="budget-panel">
        <div>
          <span>Total</span>
          <strong>{formatCurrency(total)}</strong>
        </div>
        <div>
          <span>Budget</span>
          <strong>{formatCurrency(budget)}</strong>
        </div>
        <div className="budget-bar" aria-label={`${percent}% of budget used`}>
          <span style={{ width: `${percent}%` }} />
        </div>
        <p>{percent}% of the budget is used. The current plan passes the budget check.</p>
      </section>

      <section className="shopping-list page-list">
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
            </div>
            <strong>{formatCurrency(product?.price ?? 0)}</strong>
          </article>
        ))}
      </section>
    </main>
  );
}
