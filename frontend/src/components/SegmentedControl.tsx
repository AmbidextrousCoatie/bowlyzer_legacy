type SegmentedControlProps<T extends string> = {
  value: T;
  onChange: (value: T) => void;
  options: Array<{ value: T; label: string }>;
  ariaLabel?: string;
};

export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
}: SegmentedControlProps<T>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="inline-flex rounded-sm border border-border bg-surface p-[3px]"
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          aria-pressed={value === opt.value}
          onClick={() => onChange(opt.value)}
          className={
            "rounded-xs px-3 py-1 text-caption font-medium transition-colors duration-120 " +
            (value === opt.value
              ? "bg-accent text-accent-foreground"
              : "text-muted hover:text-foreground")
          }
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
