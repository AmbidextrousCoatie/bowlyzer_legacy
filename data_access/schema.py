from dataclasses import dataclass


@dataclass
class Columns:
    season: str = 'Season'
    week: str = 'Week'
    date: str = 'Date'
    league_name: str = 'League'
    players_per_team: str = 'Players per Team'
    location: str = 'Location'
    round_number: str = 'Round Number'
    match_number: str = 'Match Number'
    team_name: str = 'Team'
    position: str = 'Position'
    player_name: str = 'Player'
    player_id: str = 'Player ID'
    team_name_opponent: str = 'Opponent'
    score: str = 'Score'
    points: str = 'Points'
    input_data: str = 'Input Data'
    computed_data: str = 'Computed Data'
    
    # New tournament-specific fields
    event_type: str = 'Event Type'  # 'league' or 'tournament'
    event_name: str = 'Event Name'  # Generic event name (league or tournament)
    round_name: str = 'Round Name'  # Tournament stage name (Vorlauf, Zwischenlauf, Finale)
    club: str = 'Club'  # Player club/team label
    game_number: str = 'Game Number'  # Game within series (reuses round_number concept)
    handicap: str = 'Handicap'  # Per-game handicap for tournaments
    apriori_average: str = 'A Priori Average'  # Sheet a priori average (club handicap basis)
    handicap_reference: str = 'Handicap Reference'  # Reference score used with a priori for hcp formula
    stage_rank: str = 'Stage Rank'  # Rank within current stage after each game
    cumulative_score: str = 'Cumulative Score'  # Running score in current stage
    cut_line: str = 'Cut Line'  # Current cut threshold score for stage

    def __str__(self):
        return str(self.get_column_names())

    def get_column_names(self, selection=None):
        if selection is None:
            return [self.season, self.week, self.date, self.league_name, self.players_per_team, self.location, self.round_number, 
                    self.match_number, self.team_name, self.position, self.player_name, self.player_id, self.team_name_opponent,
                    self.score, self.points, self.input_data, self.computed_data, self.event_type, self.event_name, 
                    self.round_name, self.club, self.game_number, self.handicap, self.apriori_average,
                    self.handicap_reference, self.stage_rank, self.cumulative_score, self.cut_line]
        
@dataclass
class ColumnsExtra:
    position: str = '#'
    score_average: str = 'Average'
    score_average_weekly: str = 'ScoreAverageWeekly'
    score_weekly: str = 'ScoreWeekly'
    points_weekly: str = 'PointsWeekly'
    position_change: str = 'PositionChange'
    points_cumulative: str = 'PointsCumulative'
    position_weekly: str = 'PositionWeekly'
    position_cumulative: str = 'PositionCumulative' 
    margin: str = 'WinMargin'
