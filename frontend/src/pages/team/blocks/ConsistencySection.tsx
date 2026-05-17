import type { ConsistencyMetrics } from "../../../hooks/useTeam";

type Props = {
  data: ConsistencyMetrics;
  t: (key: string, fallback?: string) => string;
};

export function ConsistencySection({ data, t }: Props) {
  if (data.error) {
    return (
      <p className="text-small text-muted p-4">
        {data.error}
      </p>
    );
  }

  return (
    <div className="grid gap-6 p-4 sm:grid-cols-2 lg:p-5">
      <MetricsTable
        title={t("ui.consistency.basic_stats", "Basis-Statistik")}
        rows={[
          [t("ui.consistency.mean", "Schnitt"), data.mean_score],
          [t("ui.consistency.std", "Standardabweichung"), data.std_deviation],
          [t("ui.consistency.cv", "Variationskoeffizient"), data.coefficient_of_variation != null ? `${data.coefficient_of_variation}%` : null],
          [t("ui.consistency.rating", "Konstanz"), data.consistency_rating],
        ]}
      />
      <MetricsTable
        title={t("ui.consistency.score_range", "Ergebnis-Spanne")}
        rows={[
          [t("ui.consistency.max", "Höchstes"), data.max_score],
          [t("ui.consistency.min", "Niedrigstes"), data.min_score],
          [t("ui.consistency.range", "Spanne"), data.score_range],
          [t("ui.consistency.iqr", "IQR"), data.iqr],
        ]}
      />
    </div>
  );
}

function MetricsTable({
  title,
  rows,
}: {
  title: string;
  rows: Array<[string, string | number | null | undefined]>;
}) {
  return (
    <div>
      <h3 className="text-h3 mb-2">{title}</h3>
      <table className="w-full text-small">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="border-b border-border last:border-0">
              <td className="py-2 text-muted">{label}</td>
              <td className="py-2 text-right font-mono tabular-nums font-semibold">
                {value ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
