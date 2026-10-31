import { metrics } from "../data";

export default function ResearchPage() {
  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">Evaluation</span>
        <h1>Research</h1>
        <p>
          The research angle is measurable: compare grounded plans against image-only
          outputs and score whether the result can actually be acted on.
        </p>
      </section>

      <section className="metric-strip research-metrics">
        {metrics.map((metric) => (
          <article key={metric.label}>
            <strong>{metric.value}</strong>
            <span>{metric.label}</span>
            <p>{metric.note}</p>
          </article>
        ))}
      </section>

      <section className="comparison-grid">
        <article>
          <h2>Image-only baseline</h2>
          <ul>
            <li>Produces a visual scene.</li>
            <li>Does not guarantee real products.</li>
            <li>Does not know dimensions or total cost.</li>
            <li>Leaves the user with interpretation work.</li>
          </ul>
        </article>
        <article>
          <h2>Grounded FormaOS output</h2>
          <ul>
            <li>Produces a visual concept and real product list.</li>
            <li>Uses item dimensions and prices.</li>
            <li>Checks room fit and budget before delivery.</li>
            <li>Creates a brief a designer can act on.</li>
          </ul>
        </article>
      </section>
    </main>
  );
}
