import { useEffect, useId, useMemo, useRef, useState } from "react";
import { rankFuzzyStrings } from "../lib/fuzzySearch";

type ClubSearchProps = {
  value: string;
  clubs: string[];
  isLoading?: boolean;
  placeholder?: string;
  ariaLabel?: string;
  onSelect: (club: string | null) => void;
};

const MAX_RESULTS = 50;

export function ClubSearch({
  value,
  clubs,
  isLoading,
  placeholder,
  ariaLabel,
  onSelect,
}: ClubSearchProps) {
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
    () => rankFuzzyStrings(draft, clubs, MAX_RESULTS),
    [draft, clubs],
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [draft]);

  function commit(club: string | null) {
    if (!club) {
      onSelect(null);
      setOpen(false);
      return;
    }
    setDraft(club);
    onSelect(club);
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
        const exact = clubs.find((c) => c.toLowerCase() === draft.trim().toLowerCase());
        if (exact) commit(exact);
      }
    } else if (e.key === "Escape" && open) {
      e.stopPropagation();
      setOpen(false);
    }
  }

  function onChange(e: React.ChangeEvent<HTMLInputElement>) {
    setDraft(e.target.value);
    setOpen(true);
    if (e.target.value === "") onSelect(null);
  }

  return (
    <div className="relative w-full min-w-[min(100%,320px)] max-w-md">
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
      {open && !isLoading && matches.length > 0 && (
        <ul
          id={listboxId}
          role="listbox"
          className="absolute left-0 right-0 z-20 mt-1 max-h-72 overflow-auto rounded-sm border border-border bg-surface shadow-2"
        >
          {matches.map((club, idx) => (
            <li
              key={club}
              role="option"
              aria-selected={idx === activeIndex}
              onMouseDown={(e) => {
                e.preventDefault();
                commit(club);
              }}
              onMouseEnter={() => setActiveIndex(idx)}
              className={
                "cursor-pointer px-2.5 py-1.5 text-small " +
                (idx === activeIndex ? "bg-accent-tint text-foreground" : "text-foreground")
              }
            >
              {club}
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
