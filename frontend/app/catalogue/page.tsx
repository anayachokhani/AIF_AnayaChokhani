import { formatCurrency, products } from "../data";

export default function CataloguePage() {
  return (
    <main className="page-shell">
      <section className="page-heading">
        <span className="eyebrow">Product grounding</span>
        <h1>Furniture options the design can actually use.</h1>
        <p>
          FormaOS does not stop at a pretty picture. Each concept is grounded in
          catalogue items with size, price, material, style tags, and alternatives so
          the homeowner can move from image to shopping plan.
        </p>
      </section>

      <section className="catalogue-grid">
        {products.map((product) => (
          <article className="catalogue-card" key={product.id}>
            <div className="catalogue-image-frame">
              <img src={product.imageSrc} alt={product.name} />
              <span>{product.category}</span>
            </div>
            <div className="catalogue-card-body">
              <div className="catalogue-card-heading">
                <span className="product-id">{product.id}</span>
                <strong>{formatCurrency(product.price)}</strong>
              </div>
              <h2>{product.name}</h2>
              <dl className="catalogue-meta">
                <div>
                  <dt>Size</dt>
                  <dd>{product.width} x {product.depth} x {product.height} cm</dd>
                </div>
                <div>
                  <dt>Material</dt>
                  <dd>{product.material}</dd>
                </div>
                <div>
                  <dt>Finish</dt>
                  <dd>{product.finish}</dd>
                </div>
              </dl>
              <div className="tag-row">
                {product.style.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </div>
            </div>
          </article>
        ))}
      </section>
    </main>
  );
}
