import { X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { PlayerSearchEntry } from "../hooks/usePlayer";
import { rankFuzzyBy } from "../lib/fuzzySearch";
import { formatPlayerSearchLabel, playerSearchHaystack } from "../lib/playerSearchLabel";

type PlayerSearchProps = {
  value: string;
  players: PlayerSearchEntry[];
  isLoading?: boolean;
  placeholder?: string;
  ariaLabel?: string;
  clearAriaLabel?: string;
  autoFocus?: boolean;
  onSelect: (entry: PlayerSearchEntry | null) => void;
};

const MAX_RESULTS = 50;

export function PlayerSearch({
  value,
  players,
  isLoading,
  placeholder,
  ariaLabel,
  clearAriaLabel = "Clear",
  autoFocus,
  onSelect,
}: PlayerSearchProps) {
  const [draft, setDraft] = useState(value);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();

  useEffect(() => {
    setDraft(value);
  }, [value]);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const matches = useMemo(
    () => rankFuzzyBy(draft, players, playerSearchHaystack, MAX_RESULTS),
    [draft, players],
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [draft]);

  function commit(entry: PlayerSearchEntry | null) {
    if (!entry) {
      onSelect(null);
      setOpen(false);
      return;
    }
    setDraft(formatPlayerSearchLabel(entry));
    onSelect(entry);
    setOpen(false);
    inputRef.current?.blur();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) => Math.min(i + 1, Math.max(matches.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (open && matches[activeIndex]) {
        e.preventDefault();
        commit(matches[activeIndex]);
      } else {
        const trimmed = draft.trim();
        if (/^\d+$/.test(trimmed)) {
          const byId = players.find((p) => p.id === trimmed);
          if (byId) commit(byId);
          return;
        }
        const byLabel = players.find(
          (p) => formatPlayerSearchLabel(p).toLowerCase() === trimmed.toLowerCase(),
        );
        if (byLabel) {
          commit(byLabel);
          return;
        }
        const byName = players.filter(
          (p) => p.name.toLowerCase() === trimmed.toLowerCase(),
        );
        if (byName.length === 1) commit(byName[0]);
      }
    } else if (e.key === "Escape") {
      if (open) {
        e.stopPropagation();
        setOpen(false);
      }
    }
  }

  function onChange(e: React.ChangeEvent<HTMLInputElement>) {
    setDraft(e.target.value);
    setOpen(true);
    if (e.target.value === "") onSelect(null);
  }

  function clear() {
    setDraft("");
    onSelect(null);
    setOpen(false);
    inputRef.current?.focus();
  }

  const showClear = !isLoading && draft.trim().length > 0;

  return (
    <div
      ref={containerRef}
      className="relative w-full min-w-[min(100%,320px)] max-w-md"
    >
      <input
        ref={inputRef}
        type="text"
        value={draft}
        onChange={onChange}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        aria-label={ariaLabel}
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-expanded={open}
        autoComplete="off"
        spellCheck={false}
        disabled={isLoading}
        autoFocus={autoFocus}
        className={
          "h-9 w-full rounded-sm border border-border bg-surface text-small text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60 " +
          (showClear ? "pl-2.5 pr-8" : "px-2.5")
        }
      />
      {showClear ? (
        <button
          type="button"
          onClick={clear}
          aria-label={clearAriaLabel}
          className="absolute right-1 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded-sm text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <X size={16} strokeWidth={1.75} aria-hidden />
        </button>
      ) : null}
      {open && !isLoading && matches.length > 0 && (
        <ul
          id={listboxId}
          role="listbox"
          className="absolute left-0 right-0 z-20 mt-1 max-h-72 overflow-auto rounded-sm border border-border bg-surface shadow-2"
        >
          {matches.map((entry, idx) => (
            <li
              key={`${entry.id}-${entry.name}`}
              role="option"
              aria-selected={idx === activeIndex}
              onMouseDown={(e) => {
                e.preventDefault();
                commit(entry);
              }}
              onMouseEnter={() => setActiveIndex(idx)}
              className={
                "cursor-pointer px-2.5 py-1.5 text-small " +
                (idx === activeIndex ? "bg-accent-tint text-foreground" : "text-foreground")
              }
            >
              {formatPlayerSearchLabel(entry)}
            </li>
          ))}
        </ul>
      )}
      {open && !isLoading && draft.trim() && matches.length === 0 && (
        <p className="absolute left-0 right-0 z-20 mt-1 rounded-sm border border-border bg-surface px-2.5 py-2 text-small text-muted shadow-2">
          —
        </p>
      )}
    </div>
  );
}
