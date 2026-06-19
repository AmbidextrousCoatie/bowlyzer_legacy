import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { LanguageProvider } from "./context/LanguageContext";
import { MobileNavProvider } from "./context/MobileNavContext";
import { NavigationQuerySanitizer } from "./components/NavigationQuerySanitizer";
import { Sidebar } from "./components/Sidebar";
import { ClubMatrix } from "./pages/diagnosis/ClubMatrix";
import { LeagueWeekMatrix } from "./pages/diagnosis/LeagueWeekMatrix";
import { LeagueStandingsValidation } from "./pages/diagnosis/LeagueStandingsValidation";
import { DataOddities } from "./pages/diagnosis/DataOddities";
import { DataPipeline } from "./pages/diagnosis/DataPipeline";
import { DesignSystem } from "./pages/diagnosis/DesignSystem";
import { LeagueStats } from "./pages/league/LeagueStats";
import { PlayerStats } from "./pages/player/PlayerStats";
import { TeamStats } from "./pages/team/TeamStats";
import { TournamentStats } from "./pages/tournament/TournamentStats";
import { Home } from "./pages/Home";
import { Impressum } from "./pages/Impressum";
import { queryClient } from "./lib/queryClient";

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <BrowserRouter>
          <NavigationQuerySanitizer />
          <MobileNavProvider>
          <div className="flex min-h-screen flex-col bg-background lg:flex-row">
            <Sidebar />
            <main className="flex-1 min-w-0">
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/liga" element={<LeagueStats />} />
                <Route path="/turnier" element={<TournamentStats />} />
                <Route path="/club" element={<TeamStats />} />
                <Route path="/mannschaft" element={<LegacyMannschaftRedirect />} />
                <Route path="/spieler" element={<PlayerStats />} />
                <Route path="/diagnose/club-matrix" element={<ClubMatrix />} />
                <Route path="/diagnose/liga-wochen" element={<LeagueWeekMatrix />} />
                <Route path="/diagnose/liga-validierung" element={<LeagueStandingsValidation />} />
                <Route path="/diagnose/daten-anomalien" element={<DataOddities />} />
                <Route path="/diagnose/datenpipeline" element={<DataPipeline />} />
                <Route path="/diagnose/design-system" element={<DesignSystem />} />
                <Route path="/impressum" element={<Impressum />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </main>
          </div>
          </MobileNavProvider>
        </BrowserRouter>
      </LanguageProvider>
    </QueryClientProvider>
  );
}

/** Preserve query string when renaming `/mannschaft` → `/club`. */
function LegacyMannschaftRedirect() {
  const { search } = useLocation();
  return <Navigate to={`/club${search}`} replace />;
}

function NotFound() {
  return (
    <div className="mx-auto max-w-[1080px] px-8 pt-12 pb-24">
      <p className="text-label uppercase text-muted mb-2">404</p>
      <h1 className="text-h1">Seite nicht gefunden</h1>
    </div>
  );
}

export default App;
