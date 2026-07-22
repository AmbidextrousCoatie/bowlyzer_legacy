import { useEffect, useState } from "react";
import {
  Award,
  BookOpen,
  Building2,
  AlertTriangle,
  CalendarRange,
  ClipboardCheck,
  LayoutGrid,
  Palette,
  ChevronsLeft,
  ChevronsRight,
  HelpCircle,
  Home as HomeIcon,
  Medal,
  Menu,
  FileText,
  Settings,
  Star,
  SunMoon,
  Trophy,
  User,
  Users,
  Workflow,
  X,
} from "lucide-react";
import { Link, NavLink, useSearchParams } from "react-router-dom";
import { AppLogo } from "./AppLogo";
import { DatabaseSelector } from "./DatabaseSelector";
import { MyClubControl } from "./MyClubControl";
import { useLanguage, type AppLanguage } from "../context/LanguageContext";
import { useTranslations } from "../hooks/useTranslations";
import { useMobileNav } from "../context/MobileNavContext";
import { querySuffixForPath } from "../lib/navigationQuery";
import {
  type HomeTopicPaletteKey,
  homePaletteColorForTopic,
  topicTintStyle,
} from "../lib/homePalette";

type Theme = "light" | "dark";
type NavItemDef = {
  path: string;
  labelKey?: string;
  fallback: string;
  icon: typeof Trophy;
  topicKey?: HomeTopicPaletteKey;
};

type NavGroupDef = {
  labelKey: string;
  fallback: string;
  items: ReadonlyArray<NavItemDef>;
};

const SHOW_DIAGNOSIS = import.meta.env.DEV;

const NAV_GROUPS: ReadonlyArray<NavGroupDef> = [
  {
    labelKey: "ui.nav.group_start",
    fallback: "Start",
    items: [
      { path: "/", labelKey: "ui.nav.home", fallback: "Übersicht", icon: HomeIcon },
      {
        path: "/warum-bowlyzer",
        labelKey: "ui.nav.why",
        fallback: "Warum Bowl-A-Lyzer?",
        icon: HelpCircle,
      },
      {
        path: "/club-300",
        labelKey: "ui.nav.club_300",
        fallback: "Club 300",
        icon: Star,
        topicKey: "club300",
      },
      {
        path: "/glossar",
        labelKey: "ui.nav.glossary",
        fallback: "Glossar",
        icon: BookOpen,
        topicKey: "glossary",
      },
    ],
  },
  {
    labelKey: "ui.nav.group_actors",
    fallback: "Akteure",
    items: [
      { path: "/spieler", labelKey: "player", fallback: "Spieler", icon: User, topicKey: "player" },
      {
        path: "/club",
        labelKey: "ui.team.page_title",
        fallback: "Club",
        icon: Users,
        topicKey: "club",
      },
    ],
  },
  {
    labelKey: "ui.nav.group_play",
    fallback: "Spielbetrieb",
    items: [
      { path: "/liga", labelKey: "league", fallback: "Liga", icon: Trophy, topicKey: "league" },
      {
        path: "/turnier",
        labelKey: "ui.tournament.tournament",
        fallback: "Turnier",
        icon: Award,
        topicKey: "tournament",
      },
      {
        path: "/clubpokal",
        labelKey: "ui.nav.clubpokal",
        fallback: "Clubpokal",
        icon: Medal,
        topicKey: "clubpokal",
      },
    ],
  },
  ...(SHOW_DIAGNOSIS
    ? ([
        {
          labelKey: "ui.nav.group_diagnosis",
          fallback: "Diagnose",
          items: [
            { path: "/diagnose/design-system", fallback: "Designsystem", icon: Palette },
            { path: "/diagnose/club-matrix", fallback: "Club-Matrix", icon: Building2 },
            { path: "/diagnose/liga-wochen", fallback: "Liga-Übersicht", icon: CalendarRange },
            {
              path: "/diagnose/turnier-uebersicht",
              fallback: "Turnier-Übersicht",
              icon: LayoutGrid,
            },
            { path: "/diagnose/validierung", fallback: "Validierung", icon: ClipboardCheck },
            { path: "/diagnose/daten-anomalien", fallback: "Anomalien", icon: AlertTriangle },
            { path: "/diagnose/datenpipeline", fallback: "Datenpipeline", icon: Workflow },
          ],
        },
      ] as const satisfies ReadonlyArray<NavGroupDef>)
    : []),
];

const LANG_LABEL: Record<AppLanguage, { flag: string; name: string }> = {
  de: { flag: "🇩🇪", name: "Deutsch" },
  en: { flag: "🇺🇸", name: "English" },
};

function navLabel(t: (key: string, fallback?: string) => string, item: NavItemDef): string {
  return item.labelKey ? t(item.labelKey, item.fallback) : item.fallback;
}

export function Sidebar() {
  const { t } = useTranslations();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem("sidebar:collapsed") === "true";
  });
  const [theme, setTheme] = useState<Theme>(() => {
    if (typeof window === "undefined") return "light";
    return (localStorage.getItem("ds:theme") as Theme) ?? "light";
  });
  const { language, toggleLanguage } = useLanguage();
  const { mobileOpen, openMobileNav, closeMobileNav, compactPageChrome } = useMobileNav();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("ds:theme", theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem("sidebar:collapsed", String(collapsed));
  }, [collapsed]);

  return (
    <>
      <div
        className={
          "lg:hidden sticky top-0 z-30 flex items-center justify-between border-b border-border bg-background px-4 py-3 " +
          (compactPageChrome ? "max-lg:landscape:hidden" : "")
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
          "lg:sticky lg:top-0 lg:h-screen " +
          (collapsed ? "lg:w-[56px]" : "lg:w-[240px]") +
          " " +
          "fixed inset-y-0 left-0 z-50 w-[260px] transition-transform " +
          (mobileOpen ? "translate-x-0" : "-translate-x-full") +
          " lg:translate-x-0"
        }
      >
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

        <div className={"px-3 pt-3 " + (collapsed ? "lg:px-2" : "")}>
          <MyClubControl
            collapsed={collapsed && !mobileOpen}
            onExpand={() => setCollapsed(false)}
          />
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pt-4 pb-2">
          {NAV_GROUPS.map((group) => (
            <div key={group.labelKey} className="mb-4 last:mb-0">
              <p
                className={
                  "text-label uppercase text-subtle mb-1 px-2 " +
                  (collapsed && !mobileOpen ? "lg:hidden" : "")
                }
              >
                {t(group.labelKey, group.fallback)}
              </p>
              <ul className="flex flex-col gap-0.5">
                {group.items.map((item) => (
                  <li key={item.path}>
                    <NavRow
                      label={navLabel(t, item)}
                      item={item}
                      to={`${item.path}${querySuffixForPath(item.path, searchParams)}`}
                      collapsed={collapsed && !mobileOpen}
                      onNavigate={closeMobileNav}
                    />
                  </li>
                ))}
                {SHOW_DIAGNOSIS && group.labelKey === "ui.nav.group_diagnosis" && (
                  <li className="mt-2 pt-2 border-t border-border">
                    <DatabaseSelector variant="sidebar" collapsed={collapsed && !mobileOpen} />
                  </li>
                )}
              </ul>
            </div>
          ))}
        </nav>

        <div className={"px-2 pb-2 " + (collapsed && !mobileOpen ? "lg:px-1" : "")}>
          <NavLink
            to={`/impressum${querySuffixForPath("/impressum", searchParams)}`}
            onClick={closeMobileNav}
            title={collapsed && !mobileOpen ? t("ui.nav.impressum", "Impressum") : undefined}
            className={({ isActive }) =>
              "flex h-9 items-center gap-2.5 rounded-sm px-2 text-small transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
              (isActive ? "bg-accent-tint text-foreground" : "text-muted hover:text-foreground") +
              (collapsed && !mobileOpen ? " lg:justify-center lg:px-0" : "")
            }
          >
            <FileText size={16} strokeWidth={1.75} />
            <span className={collapsed && !mobileOpen ? "lg:hidden" : ""}>
              {t("ui.nav.impressum", "Impressum")}
            </span>
          </NavLink>
        </div>

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

          <LanguageButton
            lang={language}
            onToggle={() => {
              void toggleLanguage().catch(() => undefined);
            }}
          />

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
  const [searchParams] = useSearchParams();
  return (
    <Link
      to={`/${querySuffixForPath("/", searchParams)}`}
      aria-label="Bowl-A-Lyzer — Startseite"
      className="flex items-center gap-2 rounded-sm hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <AppLogo size={28} />
      <span className="text-body font-semibold tracking-tight text-foreground">Bowl-A-Lyzer</span>
    </Link>
  );
}

function NavRow({
  label,
  item,
  to,
  collapsed,
  onNavigate,
}: {
  label: string;
  item: NavItemDef;
  to: string;
  collapsed: boolean;
  onNavigate: () => void;
}) {
  const Icon = item.icon;
  const topicKey = item.topicKey;

  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      title={collapsed ? label : undefined}
      className={({ isActive }) =>
        "group/row relative flex h-9 items-center gap-2.5 rounded-sm px-2 text-small transition-colors hover:bg-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring " +
        (isActive ? "text-foreground" : "text-muted hover:text-foreground") +
        (isActive && !topicKey ? " bg-accent-tint" : "")
      }
      style={({ isActive }) => (isActive && topicKey ? topicTintStyle(topicKey) : undefined)}
    >
      {({ isActive }) => {
        const accentColor =
          isActive && topicKey ? homePaletteColorForTopic(topicKey) : undefined;
        return (
          <>
            {isActive && (
              <span
                aria-hidden
                className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-accent"
                style={accentColor ? { backgroundColor: accentColor } : undefined}
              />
            )}
            <Icon
              size={16}
              strokeWidth={1.75}
              className={isActive && !topicKey ? "text-accent" : ""}
              style={accentColor ? { color: accentColor } : undefined}
            />
            <span className={collapsed ? "lg:hidden" : ""}>{label}</span>
          </>
        );
      }}
    </NavLink>
  );
}

function LanguageButton({ lang, onToggle }: { lang: AppLanguage; onToggle: () => void }) {
  return (
    <button
      type="button"
      aria-label={`Sprache · ${LANG_LABEL[lang].name}`}
      title={`Sprache · ${LANG_LABEL[lang].name}`}
      onClick={onToggle}
      className="grid h-9 w-9 place-items-center rounded-xs text-muted hover:bg-surface-subtle hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      <span className="text-sm font-semibold leading-none tracking-tight">
        {lang.toUpperCase()}
      </span>
    </button>
  );
}
