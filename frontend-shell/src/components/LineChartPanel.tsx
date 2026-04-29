type SeriesPath = { name: string; color: string; d: string };

type Props = {
  title: string;
  width: number;
  height: number;
  min: number;
  max: number;
  seriesPaths: SeriesPath[];
  rawPayload?: unknown;
};

export default function LineChartPanel({ title, width, height, min, max, seriesPaths, rawPayload }: Props) {
  return (
    <>
      <h2>{title}</h2>
      <svg viewBox={`0 0 ${width} ${height}`} className="lineChart" role="img" aria-label={`${title} line chart`}>
        {seriesPaths.map((s) => (
          <polyline
            key={s.name}
            points={s.d}
            fill="none"
            stroke={s.color}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
      </svg>
      <div className="legend">
        {seriesPaths.map((s) => (
          <span key={`legend-${s.name}`} className="legendItem">
            <i style={{ backgroundColor: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
      <p className="axisHint">
        y range: {min.toFixed(2)} - {max.toFixed(2)}
      </p>
      {rawPayload !== undefined ? (
        <details>
          <summary>Raw chart payload</summary>
          <pre>{JSON.stringify(rawPayload, null, 2)}</pre>
        </details>
      ) : null}
    </>
  );
}
