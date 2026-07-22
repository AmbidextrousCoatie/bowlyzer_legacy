from pathlib import Path

root = Path(r"c:\Users\cfell\repositories\bowlyzer_deploy\frontend\src")

patches = [
    (
        root / "pages/league/LeagueStats.tsx",
        'import { ContextualHint } from "../../components/ContextualHint";\nimport { Link } from "react-router-dom";',
        'import { ContextualHint } from "../../components/ContextualHint";\nimport { TopicPageHeader } from "../../components/TopicPageHeader";\nimport { Link } from "react-router-dom";',
        """      <header className="mb-6 max-lg:landscape:hidden lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("league_statistics", "Bowl-A-Lyzer")}
        </p>
        <h1 className="text-h1">
          {t("league", "Liga")} ·{" "}
          <span className="text-muted font-normal">
            {t("season", "Saison")} <span className="font-mono">{seasonHeading}</span>
          </span>
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.league.page_desc",
            "Ligatabellen und Spieltag-Ergebnisse — wähle Saison, Liga und Spieltag in der Filterleiste.",
          )}
        </p>
      </header>""",
        """      <TopicPageHeader
        topic="league"
        eyebrow={t("league_statistics", "Bowl-A-Lyzer")}
        hideOnLandscape
        title={
          <>
            {t("league", "Liga")} ·{" "}
            <span className="text-muted font-normal">
              {t("season", "Saison")} <span className="font-mono">{seasonHeading}</span>
            </span>
          </>
        }
        description={t(
          "ui.league.page_desc",
          "Ligatabellen und Spieltag-Ergebnisse — wähle Saison, Liga und Spieltag in der Filterleiste.",
        )}
      />""",
    ),
    (
        root / "pages/player/PlayerStats.tsx",
        'import { PlayerSearch } from "../../components/PlayerSearch";',
        'import { PlayerSearch } from "../../components/PlayerSearch";\nimport { TopicPageHeader } from "../../components/TopicPageHeader";',
        """      <header className="mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.player.title", "Bowl-A-Lyzer")}
        </p>
        <h1 className="text-h1">
          {t("ui.player.stats_headline", "Spielerstatistiken")} ·{" "}
          <span className="text-muted font-normal">{headlineSuffix}</span>
          {hasPlayerSelection && currentClub ? (
            <>
              {" "}
              · <span className="text-muted font-normal">{currentClub}</span>
            </>
          ) : null}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.player.page_desc",
            "Spieler suchen oder auswählen — Karrierestatistiken aus Liga und Turnieren.",
          )}
        </p>
      </header>""",
        """      <TopicPageHeader
        topic="player"
        eyebrow={t("ui.player.title", "Bowl-A-Lyzer")}
        className="mb-8"
        title={
          <>
            {t("ui.player.stats_headline", "Spielerstatistiken")} ·{" "}
            <span className="text-muted font-normal">{headlineSuffix}</span>
            {hasPlayerSelection && currentClub ? (
              <>
                {" "}
                · <span className="text-muted font-normal">{currentClub}</span>
              </>
            ) : null}
          </>
        }
        description={t(
          "ui.player.page_desc",
          "Spieler suchen oder auswählen — Karrierestatistiken aus Liga und Turnieren.",
        )}
      />""",
    ),
    (
        root / "pages/team/TeamStats.tsx",
        'import { ClubSearch } from "../../components/ClubSearch";',
        'import { ClubSearch } from "../../components/ClubSearch";\nimport { TopicPageHeader } from "../../components/TopicPageHeader";',
        """      <header className="mb-6 lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">{t("ui.team.eyebrow", "Akteure")}</p>
        <h1 className="text-h1">
          {t("ui.team.page_title", "Club")}
          {club ? (
            <>
              {" "}
              · <span className="font-normal text-muted">{resolvedClub || club}</span>
            </>
          ) : null}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.team.page_desc",
            "Club-Übersicht mit allen Mannschaften — Detailanalyse pro Team wie in der bisherigen Mannschaftsansicht.",
          )}
        </p>
      </header>""",
        """      <TopicPageHeader
        topic="club"
        eyebrow={t("ui.team.eyebrow", "Akteure")}
        title={
          <>
            {t("ui.team.page_title", "Club")}
            {club ? (
              <>
                {" "}
                · <span className="font-normal text-muted">{resolvedClub || club}</span>
              </>
            ) : null}
          </>
        }
        description={t(
          "ui.team.page_desc",
          "Club-Übersicht mit allen Mannschaften — Detailanalyse pro Team wie in der bisherigen Mannschaftsansicht.",
        )}
      />""",
    ),
    (
        root / "pages/tournament/TournamentStats.tsx",
        'import { useTranslations } from "../../hooks/useTranslations";',
        'import { useTranslations } from "../../hooks/useTranslations";\nimport { TopicPageHeader } from "../../components/TopicPageHeader";',
        """      <header className="mb-6 max-lg:landscape:hidden lg:mb-8">
        <p className="text-label uppercase text-muted mb-2">
          {t("ui.tournament.title", "Bowl-A-Lyzer")}
        </p>
        <h1 className="text-h1">
          {t("ui.tournament.title", "Turnier")}
          {tournament ? (
            <>
              {" "}
              · <span className="text-muted font-normal">{tournament}</span>
            </>
          ) : null}
        </h1>
        <p className="text-body text-muted mt-2 max-w-[72ch]">
          {t(
            "ui.tournament.page_desc",
            "Meisterschaftsergebnisse nach Saison und Turnier — Format-Details über das ℹ-Symbol.",
          )}
        </p>
      </header>""",
        """      <TopicPageHeader
        topic="tournament"
        eyebrow={t("ui.tournament.title", "Bowl-A-Lyzer")}
        hideOnLandscape
        title={
          <>
            {t("ui.tournament.title", "Turnier")}
            {tournament ? (
              <>
                {" "}
                · <span className="text-muted font-normal">{tournament}</span>
              </>
            ) : null}
          </>
        }
        description={t(
          "ui.tournament.page_desc",
          "Meisterschaftsergebnisse nach Saison und Turnier — Format-Details über das ℹ-Symbol.",
        )}
      />""",
    ),
]

for path, old_imp, new_imp, old_hdr, new_hdr in patches:
    text = path.read_text(encoding="utf-8")
    if "TopicPageHeader" in text and old_hdr not in text:
        print(f"skip {path.name} (already patched)")
        continue
    if old_imp in text and new_imp not in text:
        text = text.replace(old_imp, new_imp, 1)
    if old_hdr in text:
        text = text.replace(old_hdr, new_hdr, 1)
        path.write_text(text, encoding="utf-8")
        print(f"patched {path.name}")
    else:
        print(f"WARN header not found in {path.name}")

# Club300
path = root / "pages/Club300.tsx"
text = path.read_text(encoding="utf-8")
if "TopicPageHeader" not in text:
    text = text.replace(
        'import { useMemo } from "react";\nimport { Star } from "lucide-react";',
        'import { useMemo } from "react";\nimport { TopicPageHeader } from "../components/TopicPageHeader";',
    )
old = """      <header className="mb-10">
        <p className="text-label uppercase text-muted mb-2">{t("ui.nav.group_start", "Start")}</p>
        <div className="flex items-start gap-3">
          <Star className="mt-1 h-7 w-7 shrink-0 text-accent" strokeWidth={1.75} aria-hidden />
          <div>
            <h1 className="text-h1">{t("ui.club300.title", "Club 300")}</h1>
            <p className="text-body text-muted mt-2 max-w-[72ch]">{subtitle}</p>
          </div>
        </div>
      </header>"""
new = """      <TopicPageHeader
        topic="club300"
        eyebrow={t("ui.nav.group_start", "Start")}
        className="mb-10"
        title={t("ui.club300.title", "Club 300")}
        description={subtitle}
      />"""
if old in text:
    text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print("patched Club300.tsx")

# Glossary
path = root / "pages/Glossary.tsx"
text = path.read_text(encoding="utf-8")
if "TopicPageHeader" not in text:
    text = text.replace(
        'import { GLOSSARY_ENTRIES } from "../lib/homeContent";',
        'import { GLOSSARY_ENTRIES } from "../lib/homeContent";\nimport { TopicPageHeader } from "../components/TopicPageHeader";',
    )
old = """      <header className="mb-10">
        <p className="text-label uppercase text-muted mb-2">Bowl-A-Lyzer</p>
        <h1 className="text-h1 mb-3">Glossar</h1>
        <p className="text-body text-muted leading-relaxed">
          Kurze Erklärungen zu Begriffen in Liga- und Turnierergebnissen.
        </p>
      </header>"""
new = """      <TopicPageHeader
        topic="glossary"
        eyebrow="Bowl-A-Lyzer"
        className="mb-10"
        title="Glossar"
        description="Kurze Erklärungen zu Begriffen in Liga- und Turnierergebnissen."
      />"""
if old in text:
    text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print("patched Glossary.tsx")

# Clubpokal
path = root / "pages/ClubpokalPlaceholder.tsx"
text = path.read_text(encoding="utf-8")
if "TopicPageHeader" not in text:
    text = text.replace(
        'import { CLUBPOKAL_PLACEHOLDER } from "../lib/homeContent";',
        'import { CLUBPOKAL_PLACEHOLDER } from "../lib/homeContent";\nimport { TopicPageHeader } from "../components/TopicPageHeader";',
    )
old = """      <header className="mb-8">
        <p className="text-label uppercase text-muted mb-2">Bowl-A-Lyzer</p>
        <h1 className="text-h1 mb-3">{CLUBPOKAL_PLACEHOLDER.title}</h1>
        <p className="text-h3 text-muted">{CLUBPOKAL_PLACEHOLDER.headline}</p>
      </header>

      <p className="text-body text-muted leading-relaxed max-w-[72ch]">{CLUBPOKAL_PLACEHOLDER.body}</p>"""
new = """      <TopicPageHeader
        topic="clubpokal"
        eyebrow="Bowl-A-Lyzer"
        className="mb-8"
        title={CLUBPOKAL_PLACEHOLDER.title}
        description={
          <>
            <span className="block text-h3 text-muted mb-4">{CLUBPOKAL_PLACEHOLDER.headline}</span>
            {CLUBPOKAL_PLACEHOLDER.body}
          </>
        }
      />"""
if old in text:
    text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print("patched ClubpokalPlaceholder.tsx")

print("done")
