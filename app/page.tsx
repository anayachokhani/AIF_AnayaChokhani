import Link from "next/link";
import { BeforeAfterSlider } from "./components/BeforeAfterSlider";

const steps = [
  ["Upload", "1. Upload your space", "Add photos and room dimensions."],
  ["Chat", "2. Tell us your style", "Answer a few quick questions."],
  ["Sparkles", "3. Get AI designs", "Beautiful concepts tailored to your space."],
  ["Bag", "4. Shop real items", "Handpicked furniture that fits your room and budget."],
];

const benefits = [
  ["Tag", "Real items"],
  ["Leaf", "Vastu aware"],
  ["Wallet", "Budget smart"],
];

export default function OverviewPage() {
  return (
    <main className="ys-landing">
      <section className="ys-landing-card">
        <header className="ys-landing-nav">
          <Link className="ys-logo" href="/" aria-label="YourSpace home">
            <img className="ys-logo-image" src="/yourspace-logo.png" alt="" />
            <strong>YourSpace</strong>
          </Link>
          <nav aria-label="Landing navigation">
            <a href="#how">How it works</a>
            <a href="#styles">Styles</a>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <a href="#about">About us</a>
          </nav>
          <div>
            <Link className="ys-outline-button" href="/login?next=/workspace">Log in</Link>
            <Link className="ys-solid-button" href="/login?next=/workspace">Get started</Link>
          </div>
        </header>

        <div className="ys-hero-grid">
          <div className="ys-hero-copy">
            <h1>AI-designed homes, <span>grounded</span> in reality.</h1>
            <p>
              Upload your space, tell us your style and budget, and get beautiful
              designs with real furniture that fit your home.
            </p>
            <div className="ys-hero-actions">
              <Link className="ys-solid-button large" href="/login?next=/workspace">Start designing</Link>
              <Link className="ys-outline-button large" href="#how">See how it works</Link>
            </div>
            <div className="ys-benefits">
              {benefits.map(([icon, label]) => (
                <span key={label} data-icon={icon}>{label}</span>
              ))}
            </div>
          </div>

          <div className="ys-hero-room" aria-label="Designed living room preview">
            <BeforeAfterSlider />
            <div className="ys-hero-stats">
              <article><span>Est. budget</span><strong>Rs 2,45,000</strong></article>
              <article><span>Items used</span><strong>24</strong></article>
              <article><span>Fits your room</span><strong>Perfect</strong></article>
              <article><span>Vastu score</span><strong>92/100</strong></article>
            </div>
          </div>
        </div>

        <section className="ys-four-steps" id="how">
          <h2>Design your space in <span>4</span> simple steps</h2>
          <div>
            {steps.map(([icon, title, text]) => (
              <article key={title}>
                <span className="ys-step-icon" data-icon={icon} />
                <strong>{title}</strong>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}
