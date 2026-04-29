import type { HonorCardView } from "../types";

type Props = { cards: HonorCardView[] };

export default function HonorCards({ cards }: Props) {
  if (cards.length === 0) return <p>No honor cards available.</p>;
  return (
    <div className="cardsGrid">
      {cards.map((card, idx) => (
        <div key={`hc-${idx}`} className="honorCard">
          <h4>{card.title}</h4>
          {card.items.length > 0 ? (
            <ul>
              {card.items.map((it, itIdx) => (
                <li key={`hc-item-${idx}-${itIdx}`}>
                  <strong>{it.label}:</strong> {it.value}
                </li>
              ))}
            </ul>
          ) : (
            <pre>{JSON.stringify(card.raw ?? {}, null, 2)}</pre>
          )}
        </div>
      ))}
    </div>
  );
}
