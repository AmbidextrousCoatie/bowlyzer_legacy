"""Smoke-test Clubmeisterschaft finals bracket after import."""
from app.services.tournament_service import TournamentService

SEASON = "25/26"
TOURNAMENT = "Clubmeisterschaft Donaubowler 2026"

svc = TournamentService(database="db_tournament_regions_2026_gf")
df = svc._get_tournament_df(season=SEASON, tournament=TOURNAMENT)
print("rows", len(df))
print("rounds", sorted(df["Round Name"].astype(str).unique().tolist()) if "Round Name" in df.columns else sorted(df.iloc[:, 0:0]))
# column names from schema
from data_access.schema import Columns
print("round names", sorted(df[Columns.round_name].astype(str).unique().tolist()))
print("ko rows", int(df[Columns.round_name].astype(str).str.contains("KO|Eliminierung|Stepladder", case=False, regex=True).sum()))

bracket = svc._build_ko_bracket_payload(SEASON, TOURNAMENT, df=df)
print("format", bracket.get("ko_bracket_format"), "basis", bracket.get("ko_decision_basis"))
print("matches", [(m["key"], m.get("phase"), m.get("kind"), m.get("advancer") or m.get("winner")) for m in bracket.get("matches") or []])
print("placements", bracket.get("placements"))
