import { formatCurrency, products } from "../data";

export default function CataloguePage() {
  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">Grounding layer</span>
        <h1>Catalogue</h1>
        <p>
          The app uses a cleaned furniture catalogue with categories, prices, dimensions,
          style tags, material, and finish. This sample powers the planner prototype.
        </p>
      </section>

      <section className="catalogue-grid">
        {products.map((product) => (
          <article className="catalogue-card" key={product.id}>
            <div className="product-swatch">
              <span>{product.category.slice(0, 2).toUpperCase()}</span>
            </div>
            <div>
              <span className="product-id">{product.id}</span>
              <h2>{product.name}</h2>
              <p>
                {product.width} x {product.depth} x {product.height} cm - {product.material}
              </p>
              <div className="tag-row">
                {product.style.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </div>
            <strong>{formatCurrency(product.price)}</strong>
          </article>
        ))}
      </section>
    </main>
  );
}
