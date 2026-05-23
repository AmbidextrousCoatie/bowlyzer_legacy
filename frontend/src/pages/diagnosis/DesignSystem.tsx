import { useState, type ReactNode } from "react";
import { SegmentedControl } from "../../components/SegmentedControl";
import { useTranslations } from "../../hooks/useTranslations";
import {
  BRAND_PRIMARY,
  PALETTE_SHOWCASE,
  PRIMARY_RAMP,
  STATUS_COLORS,
} from "../../lib/design-tokens";
import { TOURNAMENT_CUT_ROW_COLORS } from "../../lib/color-utils";

const SEMANTIC_SWATCHES: Array<{ token: string; className: string }> = [
  { token: "background", className: "bg-background border border-border" },
  { token: "surface", className: "bg-surface border border-border" },
  { token: "surface-subtle", className: "bg-surface-subtle border border-border" },
  { token: "surface-raised", className: "bg-surface-raised border border-border shadow-2" },
  { token: "accent", className: "bg-accent text-accent-foreground" },
  { token: "accent-tint", className: "bg-accent-tint border border-border" },
  { token: "foreground", className: "bg-foreground text-background" },
  { token: "muted", className: "bg-muted text-background" },
];

export function DesignSystem() {
  const { t } = useTranslations();
  const [segment, setSegment] = useState<"game" | "spiel">("game");

  return (
    <div className="mx-auto max-w-[1080px] px-4 pt-8 pb-24 lg:px-8 lg:pt-12">
      <header className="mb-8 lg:mb-10">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.diagnosis.eyebrow", "Diagnose")}
        </p>
        <h1 className="text-h1 mb-3">
          {t("ui.diagnosis.design_system_title", "Design System")}
        </h1>
        <p className="text-body text-muted max-w-[72ch]">
          {t(
            "ui.diagnosis.design_system_desc",
            "UI-Chrome an rainbowPastel gekoppelt (Brand = Index 0). Chart-Paletten unverändert aus ColorUtils. Spec: designsystem/design-system.md",
          )}
        </p>
      </header>

      <div className="flex flex-col gap-12">
        <DsSection title={t("ui.ds.data_palettes", "Daten-Paletten (ColorUtils)")}>
          <p className="text-small text-muted mb-5 max-w-[72ch]">
            {t(
              "ui.ds.data_palettes_desc",
              "Serienfarben für Charts und Tabulator — nicht überschreiben. UI-Akzent und Status leiten sich von rainbowPastel ab.",
            )}
          </p>
          {PALETTE_SHOWCASE.map((palette) => (
            <div key={palette.name} className="mb-8 last:mb-0">
              <h3 className="text-h3 mb-1 font-mono">{palette.name}</h3>
              <p className="text-small text-muted mb-3">{palette.description}</p>
              <div className="flex overflow-hidden rounded-sm border border-border">
                {palette.colors.map((hex, index) => (
                  <PaletteStripCell
                    key={`${palette.name}-${index}`}
                    index={index}
                    hex={hex}
                    semanticLabel={semanticLabelForIndex(palette.name, index)}
                  />
                ))}
              </div>
              <p className="mt-2 text-caption text-muted">
                Semantik: positive → [{palette.semantics.positive}], negative → [
                {palette.semantics.negative}], highlight → [{palette.semantics.highlight}]
              </p>
            </div>
          ))}
          <div className="mt-6 rounded-sm border border-border bg-surface-subtle px-4 py-3">
            <p className="text-label uppercase text-muted mb-2">rainbowPastel · Verwendung</p>
            <ul className="text-small text-muted space-y-1 list-disc pl-4">
              <li>
                Brand / Akzent: <span className="font-mono text-foreground">{BRAND_PRIMARY}</span> [0]
              </li>
              <li>
                Turnier-Cut: inside{" "}
                <span className="font-mono">{TOURNAMENT_CUT_ROW_COLORS.inside}</span>, on{" "}
                <span className="font-mono">{TOURNAMENT_CUT_ROW_COLORS.on}</span>, outside{" "}
                <span className="font-mono">{TOURNAMENT_CUT_ROW_COLORS.outside}</span>
              </li>
            </ul>
          </div>
        </DsSection>

        <DsSection title={t("ui.ds.typography", "Typografie")}>
          <div className="flex flex-col gap-4">
            <p className="text-display">Display 56</p>
            <p className="text-h1">Heading 1</p>
            <p className="text-h2">Heading 2</p>
            <p className="text-h3">Heading 3</p>
            <p className="text-body">
              Body — Bowling-Statistiken mit tabellarischen Ziffern (tnum) in der ganzen App.
            </p>
            <p className="text-small text-muted">Small — Filter-Hinweise, Meta-Zeilen</p>
            <p className="text-caption">Caption — Steuerelemente, Chips</p>
            <p className="text-label uppercase text-muted">Label · Eyebrow</p>
          </div>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <StatSample label="Stat XL" value="218,4" className="text-stat-xl" delta="+12,3" />
            <StatSample label="Stat L" value="187" className="text-stat-lg" />
            <StatSample label="Stat M" value="4:2" className="text-stat-md" delta="−1" negative />
          </div>
          <p className="mt-4 font-mono text-small text-muted">
            Mono cell — <span className="text-foreground">Pos 3 · 642 · 58,2 %</span>
          </p>
        </DsSection>

        <DsSection title={t("ui.ds.semantic_colors", "Semantische Farben")}>
          <p className="text-small text-muted mb-4">
            {t("ui.ds.theme_hint", "Theme umschalten: Sonne/Mond in der Sidebar.")}
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {SEMANTIC_SWATCHES.map((swatch) => (
              <Swatch key={swatch.token} label={swatch.token} className={swatch.className} />
            ))}
          </div>
        </DsSection>

        <DsSection title={t("ui.ds.primary_ramp", "Primary-Rampe (UI)")}>
          <p className="text-small text-muted mb-4">
            Abgeleitet von rainbowPastel[0] ({BRAND_PRIMARY}); primary-500 = Paletten-Teal.
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
            {PRIMARY_RAMP.map((step) => (
              <div key={step.token} className="overflow-hidden rounded-sm border border-border">
                <div className="h-10" style={{ backgroundColor: step.hex }} />
                <div className="bg-surface px-2 py-1.5">
                  <p className="text-caption font-medium">{step.token}</p>
                  <p className="font-mono text-[10px] text-muted">{step.hex}</p>
                </div>
              </div>
            ))}
          </div>
        </DsSection>

        <DsSection title={t("ui.ds.status", "Status")}>
          <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {(
              [
                ["success", STATUS_COLORS.success],
                ["warning", STATUS_COLORS.warning],
                ["danger", STATUS_COLORS.danger],
                ["info", STATUS_COLORS.info],
              ] as const
            ).map(([name, hex]) => (
              <div key={name} className="overflow-hidden rounded-sm border border-border">
                <div className="h-8" style={{ backgroundColor: hex }} />
                <p className="bg-surface px-2 py-1 font-mono text-[10px] text-muted">
                  {name} · {hex}
                </p>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-4 text-body">
            <span className="text-success-fg">+2 Siege (success)</span>
            <span className="text-warning">Achtung (warning)</span>
            <span className="text-danger-fg">−14 Pins (danger)</span>
            <span className="text-info">Hinweis (info)</span>
            <span className="text-highlight-fg">Highlight [9]</span>
          </div>
        </DsSection>

        <DsSection title={t("ui.ds.buttons", "Buttons")}>
          <div className="flex flex-col gap-6">
            {(["sm", "md", "lg"] as const).map((size) => (
              <div key={size} className="flex flex-wrap items-center gap-2">
                <DsButton variant="primary" size={size}>
                  Primary
                </DsButton>
                <DsButton variant="secondary" size={size}>
                  Secondary
                </DsButton>
                <DsButton variant="ghost" size={size}>
                  Ghost
                </DsButton>
                <DsButton variant="danger" size={size}>
                  Danger
                </DsButton>
                <span className="text-caption text-subtle w-full sm:w-auto sm:ml-2">{size}</span>
              </div>
            ))}
          </div>
        </DsSection>

        <DsSection title={t("ui.ds.segmented", "Segmented Control")}>
          <SegmentedControl
            value={segment}
            onChange={setSegment}
            ariaLabel={t("ui.ds.segmented_aria", "Beispiel-Umschalter")}
            options={[
              { value: "game", label: "Game" },
              { value: "spiel", label: "Spiel" },
            ]}
          />
          <p className="mt-3 text-small text-muted">
            {t("ui.ds.segmented_value", "Aktiv")}: <span className="font-mono">{segment}</span>
          </p>
        </DsSection>

        <DsSection title={t("ui.ds.cards", "Cards & KPI")}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="rounded-sm border border-border bg-surface px-4 py-3">
              <p className="text-label uppercase text-muted mb-1">Default card</p>
              <p className="text-body">1 px border, keine Schattenfläche.</p>
            </div>
            <div className="rounded-sm border border-accent bg-accent-tint px-4 py-3">
              <p className="text-label uppercase text-accent mb-1">Winner accent</p>
              <p className="font-mono text-stat-md tabular-nums">1. Platz</p>
            </div>
            <StatSample label="Durchschnitt" value="192,7" className="text-h2" embedded />
          </div>
        </DsSection>

        <DsSection title={t("ui.ds.borders", "Rahmen & Elevation")}>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-sm border border-border bg-surface px-4 py-6 text-center text-small text-muted">
              border (default)
            </div>
            <div className="rounded-sm border border-border-strong bg-surface px-4 py-6 text-center text-small text-muted">
              border-strong
            </div>
            <div className="rounded-md border border-border bg-surface-raised px-4 py-6 text-center text-small text-muted shadow-2 sm:col-span-2">
              surface-raised · shadow-2 (Popover-Niveau)
            </div>
          </div>
        </DsSection>

        <DsSection title={t("ui.ds.radius", "Radius")}>
          <div className="flex flex-wrap gap-3">
            <RadiusChip label="radius-xs" className="rounded-xs" />
            <RadiusChip label="radius-sm" className="rounded-sm" />
            <RadiusChip label="radius-md" className="rounded-md" />
            <RadiusChip label="radius-lg" className="rounded-lg" />
          </div>
        </DsSection>
      </div>
    </div>
  );
}

function DsSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-border pt-8 first:border-t-0 first:pt-0">
      <h2 className="text-h2 mb-5">{title}</h2>
      {children}
    </section>
  );
}

function semanticLabelForIndex(paletteName: "rainbowPastel" | "harmonic10", index: number): string | null {
  const palette = PALETTE_SHOWCASE.find((p) => p.name === paletteName);
  if (!palette) return null;
  const { positive, negative, highlight } = palette.semantics;
  if (index === positive) return "positive";
  if (index === negative) return "negative";
  if (index === highlight) return "highlight";
  if (paletteName === "rainbowPastel" && index === 0) return "brand";
  return null;
}

function PaletteStripCell({
  index,
  hex,
  semanticLabel,
}: {
  index: number;
  hex: string;
  semanticLabel: string | null;
}) {
  return (
    <div className="relative min-w-0 flex-1">
      <div className="h-14 w-full" style={{ backgroundColor: hex }} title={hex} />
      <div className="border-t border-border bg-surface px-1 py-1 text-center">
        <p className="font-mono text-[10px] text-foreground">{index}</p>
        <p className="font-mono text-[9px] text-muted truncate" title={hex}>
          {hex}
        </p>
        {semanticLabel ? (
          <p className="text-[9px] font-medium uppercase tracking-wide text-accent">{semanticLabel}</p>
        ) : null}
      </div>
    </div>
  );
}

function Swatch({ label, className }: { label: string; className: string }) {
  return (
    <div className="overflow-hidden rounded-sm border border-border">
      <div className={`h-12 ${className}`} />
      <p className="bg-surface px-2 py-1.5 text-caption font-medium">{label}</p>
    </div>
  );
}

function StatSample({
  label,
  value,
  className,
  delta,
  negative,
  embedded,
}: {
  label: string;
  value: string;
  className: string;
  delta?: string;
  negative?: boolean;
  embedded?: boolean;
}) {
  const body = (
    <>
      <p className="text-label uppercase text-muted mb-1">{label}</p>
      <p className={`font-mono tabular-nums text-foreground ${className}`}>{value}</p>
      {delta ? (
        <p className={`mt-1 font-mono text-caption ${negative ? "text-danger-fg" : "text-success-fg"}`}>
          {delta}
        </p>
      ) : null}
    </>
  );
  if (embedded) {
    return <div className="rounded-sm border border-border bg-surface px-4 py-3">{body}</div>;
  }
  return <div className="rounded-sm border border-border bg-surface px-4 py-3">{body}</div>;
}

function RadiusChip({ label, className }: { label: string; className: string }) {
  return (
    <div
      className={`flex h-14 w-24 items-center justify-center border border-border bg-surface-subtle text-caption text-muted ${className}`}
    >
      {label}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

const BUTTON_SIZE: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-caption",
  md: "h-8 px-3 text-small",
  lg: "h-10 px-4 text-body",
};

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-accent-foreground hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  secondary:
    "border border-border bg-transparent text-foreground hover:border-border-strong hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  ghost:
    "text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
  danger:
    "border border-danger/30 text-danger-fg hover:bg-danger/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
};

function DsButton({
  variant,
  size,
  children,
}: {
  variant: ButtonVariant;
  size: ButtonSize;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center rounded-sm font-medium transition-colors duration-120 ${BUTTON_SIZE[size]} ${BUTTON_VARIANT[variant]}`}
    >
      {children}
    </button>
  );
}
