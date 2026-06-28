// FAIL: three near-identical card components with duplicated render + behavior
// that should be extracted into one reusable, parameterized card.

function formatCents(cents) {
  return `$${(cents / 100).toFixed(2)}`;
}

export function ProductCard({ product, onSelect }) {
  const isAvailable = product.stock > 0 && !product.discontinued;
  return (
    <article className="card" onClick={() => onSelect(product.id)}>
      <img className="card__media" src={product.image} alt={product.name} />
      <h3 className="card__title">{product.name}</h3>
      <p className="card__price">{formatCents(product.priceCents)}</p>
      <span className={isAvailable ? "card__badge--ok" : "card__badge--off"}>
        {isAvailable ? "In stock" : "Unavailable"}
      </span>
    </article>
  );
}

export function ServiceCard({ service, onSelect }) {
  const isAvailable = service.stock > 0 && !service.discontinued;
  return (
    <article className="card" onClick={() => onSelect(service.id)}>
      <img className="card__media" src={service.image} alt={service.name} />
      <h3 className="card__title">{service.name}</h3>
      <p className="card__price">{formatCents(service.priceCents)}</p>
      <span className={isAvailable ? "card__badge--ok" : "card__badge--off"}>
        {isAvailable ? "In stock" : "Unavailable"}
      </span>
    </article>
  );
}

export function BundleCard({ bundle, onSelect }) {
  const isAvailable = bundle.stock > 0 && !bundle.discontinued;
  return (
    <article className="card" onClick={() => onSelect(bundle.id)}>
      <img className="card__media" src={bundle.image} alt={bundle.name} />
      <h3 className="card__title">{bundle.name}</h3>
      <p className="card__price">{formatCents(bundle.priceCents)}</p>
      <span className={isAvailable ? "card__badge--ok" : "card__badge--off"}>
        {isAvailable ? "In stock" : "Unavailable"}
      </span>
    </article>
  );
}
