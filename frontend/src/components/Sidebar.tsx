import { useEffect, useState } from "react";
import {
  Award,
  Building2,
  AlertTriangle,
  CalendarRange,
  ChevronsLeft,
  ChevronsRight,
  Home as HomeIcon,
  Menu,
  Search,
  FileText,
  Settings,
  SunMoon,
  Trophy,
  User,
  Users,
  X,
} from "lucide-react";
import { Link, NavLink, useSearchParams } from "react-router-dom";
import { DatabaseSelector } from "./DatabaseSelector";
import { useMobileNav } from "../context/MobileNavContext";

const DIAGNOSIS_GROUP_LABEL = "Diagnose";

type Theme = "light" | "dark";
type Lang = "de" | "en";

type NavItem = {
  path: string;
  label: string;
  icon: typeof Trophy;
};

type NavGroup = {
  label: string;
  items: ReadonlyArray<NavItem>;
};

const NAV_GROUPS: ReadonlyArray<NavGroup> = [
  {
    label: "Start",
    items: [{ path: "/", label: "Übersicht", icon: HomeIcon }],
  },
  {
    label: "Spielbetrieb",
    items: [
      { path: "/liga", label: "Liga", icon: Trophy },
      { path: "/turnier", label: "Turnier", icon: Award },
    ],
  },
  {
    label: "Akteure",
    items: [
      { path: "/mannschaft", label: "Mannschaft", icon: Users },
      { path: "/spieler", label: "Spieler", icon: User },
    ],
  },
  {
    label: "Diagnose",
    items: [
      { path: "/diagnose/club-matrix", label: "Club-Matrix", icon: Building2 },
      { path: "/diagnose/liga-wochen", label: "Liga-Wochen", icon: CalendarRange },
      { path: "/diagnose/daten-anomalien", label: "Anomalien", icon: AlertTriangle },
    ],
  },
];

const LANG_LABEL: Record<Lang, { flag: string; name: string }> = {
  de: { flag: "🇩🇪", name: "Deutsch" },
  en: { flag: "🇺🇸", name: "English" },
};

export function Sidebar() {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem("sidebar:collapsed") === "true";
  });
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window === "undefined") return "light";
    return (localStorage.getItem("ds:theme") as Theme) ?? "light";
  });
  const [lang, setLang] = useState<Lang>("de");
  const { mobileOpen, openMobileNav, closeMobileNav, leagueCompactChrome } = useMobileNav();
  const [searchParams] = useSearchParams();
  const querySuffix = searchParams.toString() ? `?${searchParams.toString()}` : "";

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("ds:theme", theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("sidebar:collapsed", String(collapsed));
  }, [collapsed]);

  return (
    <>
      {/* Mobile top bar */}
      <div
        className={
          "lg:hidden sticky top-0 z-30 flex items-center justify-between border-b border-border bg-background px-4 py-3 " +
          (leagueCompactChrome ? "max-lg:landscape:hidden" : "")
        }
      >
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label="Menü öffnen"
            onClick={openMobileNav}
            className="grid h-9 w-9 place-items-center rounded-sm text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <Menu size={18} strokeWidth={1.75} />
          </button>
          <Brand />
        </div>
      </div>

      {/* Mobile drawer overlay */}
      {mobileOpen && (
        <button
          type="button"
          aria-label="Menü schließen"
          onClick={closeMobileNav}
          className="lg:hidden fixed inset-0 z-40 bg-zinc-950/40 backdrop-blur-sm"
        />
      )}

      <aside
        data-collapsed={collapsed}
        className={
          "group/sidebar flex flex-col border-r border-border bg-surface " +
          // desktop: persistent, width depends on collapsed
          "lg:sticky lg:top-0 lg:h-screen " +
          (collapsed ? "lg:w-[56px]" : "lg:w-[240px]") +
          " " +
          // mobile: drawer
          "fixed inset-y-0 left-0 z-50 w-[260px] transition-transform " +
          (mobileOpen ? "translate-x-0" : "-translate-x-full") +
          " lg:translate-x-0"
        }
      >
        {/* Header / brand + collapse toggle */}
        <div
          className={
            "flex items-center border-b border-border " +
            (collapsed ? "lg:justify-center lg:px-0" : "px-3") +
            " h-14 justify-between px-3"
          }
        >
          {(!collapsed || mobileOpen) && <Brand />}
          <button
            type="button"
            aria-label={collapsed ? "Sidebar ausklappen" : "Sidebar einklappen"}
            onClick={() => setCollapsed((c) => !c)}
            className="hidden lg:grid h-7 w-7 place-items-center rounded-xs text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            {collapsed ? (
              <ChevronsRight size={16} strokeWidth={1.75} />
            ) : (
              <ChevronsLeft size={16} strokeWidth={1.75} />
            )}
          </button>
          <button
            type="button"
            aria-label="Menü schließen"
            onClick={closeMobileNav}
            className="lg:hidden grid h-8 w-8 place-items-center rounded-xs text-muted hover:text-foreground"
          >
            <X size={18} strokeWidth={1.75} />
          </button>
        </div>

        {/* Search */}
        <div className={"px-3 pt-3 " + (collapsed ? "lg:px-2" : "")}>
          <SearchTrigger collapsed={collapsed && !mobileOpen} />
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-2 pt-4 pb-2">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="mb-4 last:mb-0">
              <p
                className={
                  "text-label uppercase text-subtle mb-1 px-2 " +
                  (collapsed && !mobileOpen ? "lg:hidden" : "")
                }
              >
                {group.label}
              </p>
              <ul className="flex flex-col gap-0.5">
                {group.items.map((item) => (
                  <li key={item.path}>
                    <NavRow
                      item={item}
                      to={`${item.path}${querySuffix}`}
                      collapsed={collapsed && !mobileOpen}
                      onNavigate={closeMobileNav}
                    />
                  </li>
                ))}
                {group.label === DIAGNOSIS_GROUP_LABEL && (
                  <li className="mt-2 pt-2 border-t border-border">
                    <DatabaseSelector
                      variant="sidebar"
                      collapsed={collapsed && !mobileOpen}
                    />
                  </li>
                )}
              </ul>
            </div>
          ))}
        </nav>

        <div className={"px-2 pb-2 " + (collapsed && !mobileOpen ? "lg:px-1" : "")}>
          <NavLink
            to={`/impressum${querySuffix}`}
            onClick={closeMobileNav}
            title={collapsed && !mobileOpen ? "Impressum" : undefined}
            className={({ isActive }) =>
              "flex h-9 items-center gap-2.5 rounded-sm px-2 text-small transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
              (isActive ? "bg-accent-tint text-foreground" : "text-muted hover:text-foreground") +
              (collapsed && !mobileOpen ? " lg:justify-center lg:px-0" : "")
            }
          >
            <FileText size={16} strokeWidth={1.75} />
            <span className={collapsed && !mobileOpen ? "lg:hidden" : ""}>Impressum</span>
          </NavLink>
        </div>

        {/* Footer micro-controls */}
        <div
          className={
            "border-t border-border p-2 " +
            (collapsed && !mobileOpen
              ? "lg:flex lg:flex-col lg:items-center lg:gap-1"
              : "flex items-center justify-between")
          }
        >
          <button
            type="button"
            aria-label={theme === "light" ? "Dunkles Theme" : "Helles Theme"}
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            className="grid h-9 w-9 place-items-center rounded-xs text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            title="Theme"
          >
            <SunMoon size={18} strokeWidth={1.75} />
          </button>

          <LanguageButton lang={lang} onChange={setLang} />

          <button
            type="button"
            aria-label="Einstellungen"
            className="grid h-9 w-9 place-items-center rounded-xs text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            title="Einstellungen"
          >
            <Settings size={18} strokeWidth={1.75} />
          </button>
        </div>
      </aside>
    </>
  );
}

function Brand() {
  return (
    <Link
      to="/"
      className="flex items-center gap-2 rounded-sm hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <div className="grid h-7 w-7 place-items-center rounded-xs bg-accent text-accent-foreground font-mono text-caption font-semibold">
        BL
      </div>
      <span className="text-body font-semibold tracking-tight text-foreground">Bowl-A-Lyzer</span>
    </Link>
  );
}

function SearchTrigger({ collapsed }: { collapsed: boolean }) {
  if (collapsed) {
    return (
      <button
        type="button"
        aria-label="Suche"
        title="Suche · ⌘K"
        className="grid h-9 w-full place-items-center rounded-sm text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        <Search size={16} strokeWidth={1.75} />
      </button>
    );
  }
  return (
    <button
      type="button"
      className="flex h-9 w-full items-center gap-2 rounded-sm border border-border bg-surface-subtle px-2.5 text-small text-muted hover:border-border-strong hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <Search size={14} strokeWidth={1.75} />
      <span className="flex-1 text-left">Suche</span>
      <kbd className="rounded-xs border border-border bg-surface px-1.5 font-mono text-[10px] text-subtle">
        ⌘K
      </kbd>
    </button>
  );
}

function NavRow({
  item,
  to,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  to: string;
  collapsed: boolean;
  onNavigate: () => void;
}) {
  const Icon = item.icon;
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      title={collapsed ? item.label : undefined}
      className={({ isActive }) =>
        "group/row relative flex h-9 items-center gap-2.5 rounded-sm px-2 text-small transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
        (isActive ? "bg-accent-tint text-foreground" : "text-muted hover:text-foreground")
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span
              aria-hidden
              className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-accent"
            />
          )}
          <Icon size={16} strokeWidth={1.75} className={isActive ? "text-accent" : ""} />
          <span className={collapsed ? "lg:hidden" : ""}>{item.label}</span>
        </>
      )}
    </NavLink>
  );
}

function LanguageButton({ lang, onChange }: { lang: Lang; onChange: (l: Lang) => void }) {
  return (
    <button
      type="button"
      aria-label={`Sprache · ${LANG_LABEL[lang].name}`}
      title={`Sprache · ${LANG_LABEL[lang].name}`}
      onClick={() => onChange(lang === "de" ? "en" : "de")}
      className="grid h-9 w-9 place-items-center rounded-xs text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <span className="text-base leading-none">{LANG_LABEL[lang].flag}</span>
    </button>
  );
}
