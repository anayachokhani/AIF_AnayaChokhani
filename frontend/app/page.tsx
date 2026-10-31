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

const styleRows = [
  ["Modern", "Clean lines, warm neutrals, walnut, black metal."],
  ["Japandi", "Low furniture, linen, clay, oak, calm negative space."],
  ["Boho", "Layered textiles, cane, terracotta, plants, collected objects."],
  ["Industrial", "Cognac leather, black steel, brick, concrete, reclaimed wood."],
];

const features = [
  ["Existing-room redesign", "Upload a room photo and the design image keeps your real windows, walls, layout, and camera angle."],
  ["Sourceable products", "Furniture and decor are grounded against catalogue items with photos, dimensions, prices, and fit checks."],
  ["Complete material list", "The final plan includes paint, curtains, plants, wall art, showpieces, lighting, and soft furnishings."],
  ["Saved projects", "Every generated design is attached to the homeowner account and can be opened again later."],
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

        <section className="ys-landing-section ys-styles-section" id="styles">
          <div className="ys-section-kicker">Styles</div>
          <div className="ys-section-heading">
            <h2>Distinct looks, not generic rooms.</h2>
            <p>
              YourSpace treats each style as a design system: furniture shapes,
              palette, materials, lighting, art, and styling all change together.
            </p>
          </div>
          <div className="ys-style-preview-grid">
            {styleRows.map(([name, text]) => (
              <article key={name}>
                <img src={`/style-images/${name.toLowerCase()}.png`} alt={`${name} interior style`} />
                <div>
                  <strong>{name}</strong>
                  <p>{text}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="ys-landing-section" id="features">
          <div className="ys-section-kicker">Features</div>
          <div className="ys-feature-list">
            {features.map(([title, text]) => (
              <article key={title}>
                <span />
                <h2>{title}</h2>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="ys-landing-section ys-pricing-section" id="pricing">
          <div>
            <div className="ys-section-kicker">Pricing</div>
            <h2>Start with a guided design brief.</h2>
            <p>
              The prototype keeps pricing simple: sign in, create a project, upload
              your room, generate a design, and review the itemized plan.
            </p>
          </div>
          <Link className="ys-solid-button large" href="/login?next=/workspace">Start designing</Link>
        </section>

        <section className="ys-landing-section ys-about-section" id="about">
          <div className="ys-section-kicker">About us</div>
          <h2>Interior design that respects the actual home.</h2>
          <p>
            YourSpace is built for homeowners who need practical design decisions,
            not moodboards alone. It combines uploaded room context, a short
            questionnaire, AI image editing, Vastu-aware placement, and a sourceable
            product and material list.
          </p>
        </section>
      </section>
    </main>
  );
}
