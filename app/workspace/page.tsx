import { WorkspaceClient } from "../components/WorkspaceClient";

export default function WorkspacePage() {
  return (
    <main className="page-shell workspace-page">
      <section className="workflow-hero" aria-label="FormaOS workflow">
        <div>
          <span className="eyebrow">Homeowner design intake</span>
          <h1>Upload room context, answer a few design questions, then generate a saved concept.</h1>
          <p>
            FormaOS branches for renovations and new spaces, uses photos and dimensions
            as context, asks a short designer questionnaire, checks products and Vastu
            placement, then prepares the final image-generation concept.
          </p>
        </div>
        <ol className="workflow-steps">
          <li><span>1</span> Space type</li>
          <li><span>2</span> Photos and questions</li>
          <li><span>3</span> Checked plan</li>
          <li><span>4</span> Concept and export</li>
        </ol>
      </section>
      <WorkspaceClient />
    </main>
  );
}
