import { X } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { rankFuzzyStrings } from "../lib/fuzzySearch";

type ClubMultiSearchProps = {
  selected: string[];
  clubs: string[];
  isLoading?: boolean;
  placeholder?: string;
  ariaLabel?: string;
  removeChipAriaLabel?: (club: string) => string;
  onChange: (clubs: string[]) => void;
};

const MAX_RESULTS = 50;

export function ClubMultiSearch({
  selected,
  clubs,
  isLoading,
  placeholder,
  ariaLabel,
  removeChipAriaLabel = (club) => `${club} entfernen`,
  onChange,
}: ClubMultiSearchProps) {
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const computeMatches = useCallback(
    (d: string, selectedIds: string[]) => {
      const ranked = rankFuzzyStrings(d, clubs, MAX_RESULTS);
      const sel = new Set(selectedIds);
      return ranked.filter((c) => !sel.has(c));
    },
    [clubs],
  );

  const matches = useMemo(
    () => computeMatches(draft, selected),
    [computeMatches, draft, selected],
  );

  function addClub(club: string) {
    if (!club || selected.includes(club)) return;
    const nextSelected = [...selected, club];
    onChange(nextSelected);
    const remaining = computeMatches(draft, nextSelected);
    if (remaining.length === 0) {
      setDraft("");
    }
    setActiveIndex(0);
    setOpen(true);
    inputRef.current?.focus();
  }

  function removeClub(club: string) {
    onChange(selected.filter((c) => c !== club));
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) =>
        Math.min(i + 1, Math.max(matches.length - 1, 0)),
      );
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (open && matches[activeIndex]) {
        e.preventDefault();
        addClub(matches[activeIndex]);
      } else {
        const exact = clubs.find(
          (c) =>
            !selected.includes(c) && c.toLowerCase() === draft.trim().toLowerCase(),
        );
        if (exact) addClub(exact);
      }
    } else if (e.key === "Escape" && open) {
      e.stopPropagation();
      setOpen(false);
    } else if (e.key === "Backspace" && draft === "" && selected.length > 0) {
      removeClub(selected[selected.length - 1]);
    }
  }

  function onChangeInput(e: React.ChangeEvent<HTMLInputElement>) {
    setDraft(e.target.value);
    setActiveIndex(0);
    setOpen(true);
  }

  return (
    <div ref={containerRef} className="relative w-full min-w-[min(100%,320px)] max-w-xl">
      {selected.length > 0 ? (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {selected.map((club) => (
            <span
              key={club}
              className="inline-flex max-w-full items-center gap-0.5 rounded-sm border border-border bg-surface-subtle py-0.5 pl-2 pr-0.5 text-small text-foreground"
            >
              <span className="truncate">{club}</span>
              <button
                type="button"
                onClick={() => removeClub(club)}
                aria-label={removeChipAriaLabel(club)}
                className="grid shrink-0 place-items-center rounded-sm p-0.5 text-muted hover:bg-surface hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
              >
                <X size={14} strokeWidth={1.75} aria-hidden />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={onChangeInput}
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
                  addClub(club);
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
    </div>
  );
}
