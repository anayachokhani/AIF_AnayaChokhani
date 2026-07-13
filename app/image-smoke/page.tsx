import { imageSmokeItems } from "./smoke-items";

export default function ImageSmokePage() {
  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">T6 smoke check</span>
        <h1>Catalogue Images</h1>
        <p>
          Sampled curated catalogue items with mapped ABO product imagery and
          placeholder fallback only where no local source image is available.
        </p>
      </section>

      <section className="image-smoke-grid" aria-label="Catalogue image smoke test">
        {imageSmokeItems.map((product) => (
          <article className="image-card" key={product.itemId}>
            <img src={product.imageSrc} alt={product.title} />
            <div>
              <span className="product-id">{product.itemId}</span>
              <h2>{product.title}</h2>
              <p>{product.category}</p>
              <p>{product.dimensions}</p>
              <strong>{product.price}</strong>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
