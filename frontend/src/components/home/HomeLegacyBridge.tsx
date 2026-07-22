import { HOME_LEGACY_BRIDGE } from "../../lib/homeContent";

export function HomeLegacyBridge() {
  return (
    <aside
      className="rounded-sm border border-border bg-surface-subtle px-5 py-4"
      aria-label={HOME_LEGACY_BRIDGE.title}
    >
      <h2 className="text-h3 mb-2">{HOME_LEGACY_BRIDGE.title}</h2>
      <p className="text-body text-muted leading-relaxed">{HOME_LEGACY_BRIDGE.body}</p>
    </aside>
  );
}
