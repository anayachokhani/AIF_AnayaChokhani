import Link from "next/link";
import { attempts, demoBrief } from "../data";

const messages = [
  {
    role: "User",
    text: "I have a 10 by 12 ft living room. Budget is Rs 85,000. I want warm wood, storage, kid-friendly seating, and Vastu guidance.",
  },
  {
    role: "FormaOS",
    text: "I captured a living-room brief with budget, style, storage, child-safe layout, and opt-in Vastu checks. I will plan the slots next.",
  },
  {
    role: "FormaOS",
    text: "Required slots: compact sofa, coffee table, rug, low storage, and warm lighting. I will ground each slot in catalogue items and run checks.",
  },
];

export default function ChatPage() {
  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">Frontend workspace</span>
        <h1>Chat</h1>
        <p>
          The chat page captures the user's room brief and keeps the design state visible
          while the planner, grounder, critic, and reviser work.
        </p>
      </section>

      <section className="workspace-grid">
        <div className="chat-panel">
          <div className="chat-thread">
            {messages.map((message) => (
              <article
                key={message.text}
                className={message.role === "User" ? "message user-message" : "message system-message"}
              >
                <span>{message.role}</span>
                <p>{message.text}</p>
              </article>
            ))}
          </div>
          <div className="chat-input-row">
            <input
              aria-label="Message FormaOS"
              value="Make the sofa cheaper but keep the warm modern look."
              readOnly
            />
            <Link className="primary-button" href="/planner">
              Run plan
            </Link>
          </div>
        </div>

        <aside className="state-panel">
          <h2>Current room state</h2>
          <dl>
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
              <dd>Rs 85,000</dd>
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
        </aside>
      </section>
    </main>
  );
}
