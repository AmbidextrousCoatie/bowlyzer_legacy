import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { MobileNavProvider } from "./context/MobileNavContext";
import { Sidebar } from "./components/Sidebar";
import { ClubMatrix } from "./pages/diagnosis/ClubMatrix";
import { LeagueWeekMatrix } from "./pages/diagnosis/LeagueWeekMatrix";
import { LeagueStats } from "./pages/league/LeagueStats";
import { PlayerStats } from "./pages/player/PlayerStats";
import { TeamStats } from "./pages/team/TeamStats";
import { TournamentStats } from "./pages/tournament/TournamentStats";
import { queryClient } from "./lib/queryClient";

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <MobileNavProvider>
          <div className="flex min-h-screen flex-col bg-background lg:flex-row">
            <Sidebar />
            <main className="flex-1 min-w-0">
              <Routes>
                <Route path="/" element={<Navigate to="/liga" replace />} />
                <Route path="/liga" element={<LeagueStats />} />
                <Route path="/turnier" element={<TournamentStats />} />
                <Route path="/mannschaft" element={<TeamStats />} />
                <Route path="/spieler" element={<PlayerStats />} />
                <Route path="/diagnose/club-matrix" element={<ClubMatrix />} />
                <Route path="/diagnose/liga-wochen" element={<LeagueWeekMatrix />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </main>
          </div>
        </MobileNavProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
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
