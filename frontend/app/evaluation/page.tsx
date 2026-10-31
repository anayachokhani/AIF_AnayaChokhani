const rows = [
  {
    metric: "Fit rate",
    formaos: "Target 85%+",
    baseline: "Usually unknown",
    definition: "Selected items whose dimensions fit the stated room and slot constraints.",
  },
  {
    metric: "Budget accuracy",
    formaos: "Target 90%+",
    baseline: "Usually unknown",
    definition: "Designs whose selected item total is within the user's budget.",
  },
  {
    metric: "Sourceability",
    formaos: "Target 100%",
    baseline: "Near 0% for raw image",
    definition: "Selected items that map to real catalogue entries.",
  },
  {
    metric: "Vastu compliance",
    formaos: "Tracked when enabled",
    baseline: "Not measured",
    definition: "Rule score when the user requests Vastu guidance.",
  },
];

export default function EvaluationPage() {
  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">Metrics evidence</span>
        <h1>Evaluation</h1>
        <p>
          The evaluation task freezes test briefs and compares FormaOS with an image-only
          or ungrounded baseline using the same metric definitions.
        </p>
      </section>

      <section className="evaluation-table" aria-label="Evaluation metric table">
        <div className="table-row table-head">
          <span>Metric</span>
          <span>FormaOS</span>
          <span>Baseline</span>
          <span>Definition</span>
        </div>
        {rows.map((row) => (
          <div className="table-row" key={row.metric}>
            <strong>{row.metric}</strong>
            <span>{row.formaos}</span>
            <span>{row.baseline}</span>
            <p>{row.definition}</p>
          </div>
        ))}
      </section>

      <section className="logic-panel">
        <h2>Current status</h2>
        <p>
          T20 is frozen: `data/eval/test_briefs.json` contains 10 briefs, the
          ungrounded baseline is defined, both systems share one output schema,
          and metric definitions are fixed before final scoring.
        </p>
      </section>
    </main>
  );
}
