const phases = [
  {
    label: "Phase 1",
    title: "Living-room MVP",
    items: ["Static catalogue", "Interactive planner", "Fit and budget checks", "Demo scenarios"],
  },
  {
    label: "Phase 2",
    title: "Agent orchestration",
    items: ["Planner node", "Grounder node", "Critic node", "Reviser retry loop"],
  },
  {
    label: "Phase 3",
    title: "Better grounding",
    items: ["Retailer feeds", "Product image matching", "More room types", "Exportable PDFs"],
  },
  {
    label: "Phase 4",
    title: "Designer handoff",
    items: ["Shareable briefs", "Annotated constraints", "User study flow", "Marketplace-ready data"],
  },
];

export default function RoadmapPage() {
  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">Build sequence</span>
        <h1>Roadmap</h1>
        <p>
          The app starts as a focused proof of buildability, then grows toward an agentic
          interior-design workflow with real catalogue integrations.
        </p>
      </section>

      <section className="roadmap">
        {phases.map((phase) => (
          <article key={phase.label} className="roadmap-card">
            <span>{phase.label}</span>
            <h2>{phase.title}</h2>
            <ul>
              {phase.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
        ))}
      </section>
    </main>
  );
}
