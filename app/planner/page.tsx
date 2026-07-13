import { PlannerTool } from "../components/PlannerTool";

export default function PlannerPage() {
  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">MVP workspace</span>
        <h1>Planner</h1>
        <p>
          Enter room constraints and style intent. The prototype selects catalogue items,
          checks budget and fit, and shows the buildable plan output.
        </p>
      </section>
      <PlannerTool />
    </main>
  );
}
