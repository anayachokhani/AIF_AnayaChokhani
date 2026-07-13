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
        <span className="eyebrow">Design checks</span>
        <h1>Every generated room gets checked before it is saved.</h1>
        <p>
          The image is only the concept. The saved plan carries the practical checks:
          product sourceability, room fit, total budget, category coverage, and optional
          Vastu guidance.
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
          If a hard check fails, FormaOS revises the plan by swapping the failing item,
          lowering optional accents, or simplifying the room plan. Failed versions are
          still saved with repair notes so the homeowner can understand what changed.
        </p>
      </section>
    </main>
  );
}
