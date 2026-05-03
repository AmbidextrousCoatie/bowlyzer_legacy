import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { PlayerSearchEntry } from "../hooks/usePlayer";

type PlayerSearchProps = {
  value: string;
  players: PlayerSearchEntry[];
  isLoading?: boolean;
  placeholder?: string;
  ariaLabel?: string;
  onSelect: (entry: PlayerSearchEntry | null) => void;
};

const MAX_RESULTS = 50;

export function PlayerSearch({
  value,
  players,
  isLoading,
  placeholder,
  ariaLabel,
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
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const matches = useMemo(() => {
    const term = draft.trim().toLowerCase();
    if (!term) return players.slice(0, MAX_RESULTS);
    return players.filter((p) => p.name.toLowerCase().includes(term)).slice(0, MAX_RESULTS);
  }, [draft, players]);

  useEffect(() => {
    setActiveIndex(0);
  }, [draft]);

  function commit(entry: PlayerSearchEntry | null) {
    if (!entry) {
      onSelect(null);
      setOpen(false);
      return;
    }
    setDraft(entry.name);
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
        const exact = players.find((p) => p.name.toLowerCase() === draft.trim().toLowerCase());
        if (exact) commit(exact);
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

  return (
    <div ref={containerRef} className="relative w-full max-w-xs">
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
        className="h-9 w-full rounded-sm border border-border bg-surface px-2.5 text-small text-foreground hover:border-border-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60"
      />
      {open && matches.length > 0 && (
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
              {entry.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
