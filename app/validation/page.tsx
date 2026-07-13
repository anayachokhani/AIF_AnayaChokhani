const checks = [
  {
    title: "Sourceability",
    status: "Hard pass",
    detail: "Every output item must have a catalogue ID, category, dimensions, and price.",
  },
  {
    title: "2D fit",
    status: "Hard pass",
    detail: "Large furniture must fit within conservative wall and depth limits for the room.",
  },
  {
    title: "Budget",
    status: "Hard pass",
    detail: "The summed item prices must be less than or equal to the user's budget.",
  },
  {
    title: "Category coverage",
    status: "Hard pass",
    detail: "The living-room plan needs a sofa, table, rug, storage, and lighting slot.",
  },
  {
    title: "Vastu guidance",
    status: "Soft warning",
    detail: "Optional rules can suggest placement preferences without blocking the entire plan.",
  },
];

export default function ValidationPage() {
  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">Critic layer</span>
        <h1>Validation</h1>
        <p>
          FormaOS treats the visual as a concept and the validation results as the source
          of truth for whether the plan is buildable.
        </p>
      </section>

      <section className="validation-list">
        {checks.map((check) => (
          <article key={check.title} className="validation-card">
            <div>
              <span className={check.status === "Hard pass" ? "status hard" : "status soft"}>
                {check.status}
              </span>
              <h2>{check.title}</h2>
            </div>
            <p>{check.detail}</p>
          </article>
        ))}
      </section>

      <section className="logic-panel">
        <h2>Revision rule</h2>
        <p>
          If any hard check fails, the Reviser swaps the failing item, lowers optional
          accents, or simplifies the room plan. The MVP uses a retry cap so the system
          stays predictable during demos.
        </p>
      </section>
    </main>
  );
}
