class TeamPerformanceBlock {
    constructor() {
        this.containerId = 'team-performance';
        this.chartContainerId = 'team-performance-chart';
        this.container = document.getElementById(this.containerId);
        this.currentFilter = 'both'; // 'points', 'score', 'both'
        this.columnMetadata = null; // Store column info for filtering
        this.localTeamColor = null; // Deterministic color for this block render
    }

    shouldRender(state) {
        return state.league && state.season && state.team && !state.week;
    }

    async render(state = {}) {
        try {
            // Check if required dependencies are met
            if (!this.shouldRender(state)) {
                this.hide();
                return;
            }

            this.show();
            
            // Fetch data
            const data = await this.fetchData(state);
            
            
            if (!data || !data.performance_data || !data.performance_data.data || Object.keys(data.performance_data.data).length === 0) {
                this.renderError(typeof t === 'function' ? t('no_data', 'No performance data available for the selected team.') : 'No performance data available for the selected team.');
                return;
            }

            if (!this.container) {
                console.error(`${this.containerId}: Container not found`);
                return;
            }

            // Deterministic color assignment for this block only:
            // all players first, then team/team-average next color.
            this.initializeLocalColorOrder(data);

            // Create the card structure - Top: Performance Table, Middle: Graphs side by side
            this.container.innerHTML = `
                <div class="card mb-4">
                    <div class="card-header">
                        <h5>${data.team} - ${typeof t === 'function' ? t('ui.team_performance.title', 'Performance Analysis') : 'Performance Analysis'}</h5>
                        <!--<p class="mb-0 text-muted">${typeof t === 'function' ? t('ui.team_performance.description', 'Individual player scores and team performance over time') : 'Individual player scores and team performance over time'}</p>-->
                    </div>
                    <div class="card-body">
                        <!-- Performance Table (Top) -->
                        <div class="row mb-4">
                            <div class="col-12">
                                <div class="card">
                                    <div class="card-header">
                                        <h6>${typeof t === 'function' ? t('ui.team_performance.individual', 'Individual Player Performance') : 'Individual Player Performance'}</h6>
                                        <!--<p class="mb-0 text-muted small">${typeof t === 'function' ? t('ui.team_performance.individual_desc', 'Player scores per week with totals and averages per game') : 'Player scores per week with totals and averages per game'}</p>-->
                                    </div>
                                    <div class="card-body">
                                        <div id="team-performance-table"></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Performance Charts (Middle - Side by Side) -->
                        <div class="row mb-4">
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-header">
                                        <h6>${typeof t === 'function' ? t('score_per_match_day', 'Score per Match Day') : 'Score per Match Day'}</h6>
                                    </div>
                                    <div class="card-body">
                                        <div id="${this.chartContainerId}-bubble" style="height: 400px;"></div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-header">
                                        <h6>${typeof t === 'function' ? t('ui.win_percentage.weekly', 'Weekly Win %') : 'Weekly Win %'}</h6>
                                    </div>
                                    <div class="card-body">
                                        <div id="team-win-percentage-chart-bubble" style="height: 400px;"></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- League Season Trend Charts (All teams gray, selected team highlighted) -->
                        <div class="row mb-4">
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-header">
                                        <h6>${typeof t === 'function' ? t('points_in_season_progress', 'Points in Season Progress') : 'Points in Season Progress'}</h6>
                                    </div>
                                    <div class="card-body">
                                        <div id="team-league-points-trend-chart" style="height: 320px;"></div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-header">
                                        <h6>${typeof t === 'function' ? t('position_in_season_progress', 'Position in Season Progress') : 'Position in Season Progress'}</h6>
                                    </div>
                                    <div class="card-body">
                                        <div id="team-league-position-trend-chart" style="height: 320px;"></div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Win Percentage Table (Bottom) -->
                        <div class="row">
                            <div class="col-12">
                                <div class="card">
                                    <div class="card-header">
                                        <h6>${typeof t === 'function' ? t('ui.win_percentage.individual', 'Individual Player Win Percentages') : 'Individual Player Win Percentages'}</h6>
                                        <p class="mb-0 text-muted small">${typeof t === 'function' ? t('ui.win_percentage.individual_desc', 'Player win percentages per week with totals') : 'Player win percentages per week with totals'}</p>
                                    </div>
                                    <div class="card-body">
                                        <div id="team-win-percentage-table"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            // Load league-wide season trend charts with selected team highlight.
            // This also seeds the team color map with full league team ordering.
            await this.loadLeagueSeasonTrendCharts(state);

            // Fetch and render tables and charts
            await Promise.all([
                this.loadPerformanceTable(state),
                this.loadWinPercentageTable(state)
            ]);
            
            // Render the performance bubble chart
            this.renderBubbleChart(data);
            
            // Fetch and render win percentage data for the second graph
            const winPercentageData = await this.fetchWinPercentageData(state);
            if (winPercentageData && winPercentageData.win_percentage_data) {
                this.renderWinPercentageBubbleChart(winPercentageData);
            }
            
        } catch (error) {
            console.error('Error rendering team performance analysis:', error);
            this.renderError(typeof t === 'function' ? t('error_loading_data', 'Failed to load team performance analysis data') : 'Failed to load team performance analysis data');
        }
    }

    async fetchData(filterState) {
        const url = new URL('/league/get_team_analysis', window.location.origin);
        
        // Add required parameters
        url.searchParams.append('league', filterState.league);
        url.searchParams.append('season', filterState.season);
        url.searchParams.append('team', filterState.team);
        
        // Add database parameter
        const database = getCurrentDatabase();
        if (database) {
            url.searchParams.append('database', database);
        }

        
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(`API Error: ${data.error}`);
        }
        
        return data;
    }

    hide() {
        if (this.container) {
            this.container.style.display = 'none';
        }
    }

    show() {
        if (this.container) {
            this.container.style.display = 'block';
        }
    }

    getExistingTeamColor(teamName, aliases = []) {
        const normalizedTeamName = teamName ? String(teamName).trim() : '';
        const normalizedAliases = [normalizedTeamName, ...aliases]
            .map(alias => (alias ? String(alias).trim() : ''))
            .filter(Boolean);
        const playerMap = (window.ColorUtils && window.ColorUtils.playerColorMap) || window.playerColorMap;
        if (!playerMap || typeof playerMap !== 'object') return null;
        for (const alias of normalizedAliases) {
            if (playerMap[alias]) return playerMap[alias];
        }
        return null;
    }

    initializeLocalColorOrder(analysisData) {
        if (!analysisData) return;
        const teamName = analysisData?.team ? String(analysisData.team).trim() : '';
        if (!teamName) return;

        const teamAliases = [`${teamName} (Team)`, `${teamName} (Team Average)`];
        const aliasSet = new Set(teamAliases.map(a => String(a).trim()));

        const orderedPlayers = Array.isArray(analysisData?.player_order_by_average)
            ? analysisData.player_order_by_average.map(name => String(name).trim()).filter(Boolean)
            : [];

        const fallbackPlayers = analysisData?.performance_data?.data
            ? Object.keys(analysisData.performance_data.data)
                .map(name => String(name).trim())
                .filter(name => name && !aliasSet.has(name))
            : [];

        const players = orderedPlayers.length ? orderedPlayers : fallbackPlayers;
        const orderedPlayersUnique = [...new Set(players)];
        if (!orderedPlayersUnique.length) return;

        const getColorAt = (index) => {
            if (window.ColorUtils && typeof window.ColorUtils.getPaletteColor === 'function') {
                return window.ColorUtils.getPaletteColor(index);
            }
            const fallback = ['#6bbf59', '#4f86c6', '#f28e2b', '#b07aa1', '#76b7b2', '#e15759'];
            return fallback[index % fallback.length];
        };

        // Build deterministic local mapping:
        // players first, then ONE team color slot; aliases reuse that same team color.
        const localMap = {};
        orderedPlayersUnique.forEach((name, idx) => {
            localMap[name] = getColorAt(idx);
        });
        const teamColor = getColorAt(orderedPlayersUnique.length);
        localMap[teamName] = teamColor;
        teamAliases.forEach(alias => {
            localMap[String(alias).trim()] = teamColor;
        });

        // Apply map to BOTH stores so getTeamColor/teamColorMap/playerColorMap all resolve identically.
        const playerMap = (window.ColorUtils && window.ColorUtils.playerColorMap) || window.playerColorMap;
        const teamMap = (window.ColorUtils && window.ColorUtils.teamColorMap) || window.teamColorMap;
        if (playerMap && typeof playerMap === 'object') {
            Object.keys(localMap).forEach(name => {
                playerMap[name] = localMap[name];
            });
        }
        if (teamMap && typeof teamMap === 'object') {
            Object.keys(localMap).forEach(name => {
                teamMap[name] = localMap[name];
            });
        }

        this.localTeamColor = teamColor || null;
    }

    seedPlayerAndTeamColors(playerNames = [], teamAliases = []) {
        // Intentionally no-op: colors are initialized once via initializeLocalColorOrder()
        // to prevent cross-view carry-over and per-widget reshuffling.
        return;
    }

    async loadPerformanceTable(state) {
        const url = new URL('/league/get_team_performance_table', window.location.origin);
        url.searchParams.append('league', state.league);
        url.searchParams.append('season', state.season);
        url.searchParams.append('team', state.team);
        
        const database = getCurrentDatabase();
        if (database) {
            url.searchParams.append('database', database);
        }

        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const tableData = await response.json();
            
            if (tableData.error) {
                throw new Error(`API Error: ${tableData.error}`);
            }

            // Extract player names for color mapping (from data, excluding team average)
            // Normalize player names (trim whitespace) for consistent color mapping
            const teamAverageKey = `${state.team} (Team Average)`;
            if (tableData.data && Array.isArray(tableData.data)) {
                const playerNames = tableData.data
                    .map(row => row.player_name ? String(row.player_name).trim() : null)
                    .filter(name => name && name !== teamAverageKey);
                this.seedPlayerAndTeamColors(playerNames, [teamAverageKey, `${state.team} (Team)`]);
            }

            // Store column metadata for filtering
            this.storeColumnMetadata(tableData);

            // Pass directly to createTableTabulator (like timetable)
            if (typeof createTableTabulator === 'function') {
                createTableTabulator('team-performance-table', tableData, {
                    disablePositionCircle: false, // Enable colored circles based on player names
                    enableSpecialRowStyling: true,
                    disableTeamColorUpdate: true // We handle player colors manually
                });
            }

            // Apply current filter after table is created
            setTimeout(() => {
                this.applyFilter(this.currentFilter);
            }, 200);
        } catch (error) {
            console.error('Error loading performance table:', error);
        }
    }

    async fetchWinPercentageData(filterState) {
        try {
            const url = new URL('/league/get_team_analysis', window.location.origin);
            
            // Add required parameters
            url.searchParams.append('league', filterState.league);
            url.searchParams.append('season', filterState.season);
            url.searchParams.append('team', filterState.team);
            
            // Add database parameter
            const database = getCurrentDatabase();
            if (database) {
                url.searchParams.append('database', database);
            }
            
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.error) {
                throw new Error(`API Error: ${data.error}`);
            }
            
            return data;
        } catch (error) {
            console.error('Error fetching win percentage data:', error);
            return null;
        }
    }

    async loadLeagueSeasonTrendCharts(state) {
        try {
            const pointsResp = await fetchWithDatabase(
                `/league/get_team_points?season=${encodeURIComponent(state.season)}&league=${encodeURIComponent(state.league)}`
            );
            const positionsResp = await fetchWithDatabase(
                `/league/get_team_positions?season=${encodeURIComponent(state.season)}&league=${encodeURIComponent(state.league)}`
            );
            if (!pointsResp.ok || !positionsResp.ok) {
                throw new Error(`HTTP ${pointsResp.status}/${positionsResp.status}`);
            }
            const pointsData = await pointsResp.json();
            const positionsData = await positionsResp.json();

            this.renderMutedLeagueTrendChart({
                containerId: 'team-league-points-trend-chart',
                seriesData: (pointsData && pointsData.data_accumulated) ? pointsData.data_accumulated : (pointsData?.data || {}),
                selectedTeam: state.team,
                invertY: false,
                yAxisName: typeof t === 'function' ? t('points', 'Points') : 'Points',
            });

            this.renderMutedLeagueTrendChart({
                containerId: 'team-league-position-trend-chart',
                seriesData: positionsData?.data || {},
                selectedTeam: state.team,
                invertY: true,
                yAxisName: typeof t === 'function' ? t('position', 'Position') : 'Position',
            });
        } catch (err) {
            console.error('Error loading league season trend charts:', err);
        }
    }

    renderMutedLeagueTrendChart({ containerId, seriesData, selectedTeam, invertY = false, yAxisName = '' }) {
        const el = document.getElementById(containerId);
        if (!el || typeof echarts === 'undefined') return;
        const existing = echarts.getInstanceByDom(el);
        if (existing) existing.dispose();
        const chart = echarts.init(el);

        const teamNames = Object.keys(seriesData || {});
        if (!teamNames.length) {
            chart.setOption({ title: { text: 'No data', left: 'center', top: 'middle' } });
            return;
        }

        const firstSeries = seriesData[teamNames[0]] || [];
        const labels = Array.from({ length: firstSeries.length }, (_, i) => i + 1);
        const selectedTeamNorm = String(selectedTeam || '').trim().toLowerCase();
        if (window.ColorUtils && typeof window.ColorUtils.updateTeamColorMap === 'function') {
            window.ColorUtils.updateTeamColorMap(teamNames.map(name => String(name).trim()));
        }
        const selectedColor =
            this.localTeamColor ||
            (window.ColorUtils && typeof window.ColorUtils.getTeamColor === 'function' && window.ColorUtils.getTeamColor(String(selectedTeam || '').trim())) ||
            (window.ColorUtils && typeof window.ColorUtils.getThemeColor === 'function' && window.ColorUtils.getThemeColor('primary')) ||
            '#1f77b4';
        const mutedColor = 'rgba(120,120,120,0.45)';

        const series = teamNames.map((team) => {
            const isSelected = String(team).trim().toLowerCase() === selectedTeamNorm;
            const vals = (seriesData[team] || []).map(v => (v === null || v === undefined ? null : Number(v)));
            return {
                name: team,
                type: 'line',
                data: vals,
                smooth: false,
                showSymbol: false,
                lineStyle: { width: isSelected ? 3 : 1.5, color: isSelected ? selectedColor : mutedColor },
                itemStyle: { color: isSelected ? selectedColor : mutedColor },
                z: isSelected ? 3 : 1,
            };
        });

        chart.setOption({
            animation: false,
            tooltip: { trigger: 'axis' },
            grid: { top: 20, left: 45, right: 20, bottom: 40 },
            xAxis: {
                type: 'category',
                data: labels,
                name: typeof t === 'function' ? t('week', 'Week') : 'Week',
                nameLocation: 'middle',
                nameGap: 28,
            },
            yAxis: {
                type: 'value',
                name: yAxisName,
                inverse: !!invertY,
                min: invertY ? 1 : undefined,
            },
            series,
        });

        const resizeHandler = () => chart.resize();
        if (el._echartResizeHandler) {
            window.removeEventListener('resize', el._echartResizeHandler);
        }
        window.addEventListener('resize', resizeHandler);
        el._echartResizeHandler = resizeHandler;
    }

    async loadWinPercentageTable(state) {
        const url = new URL('/league/get_team_win_percentage_table', window.location.origin);
        url.searchParams.append('league', state.league);
        url.searchParams.append('season', state.season);
        url.searchParams.append('team', state.team);
        
        const database = getCurrentDatabase();
        if (database) {
            url.searchParams.append('database', database);
        }

        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const tableData = await response.json();
            
            if (tableData.error) {
                throw new Error(`API Error: ${tableData.error}`);
            }

            // Extract player names for color mapping (from data, excluding team)
            // Normalize player names (trim whitespace) for consistent color mapping
            const teamKey = `${state.team} (Team)`;
            if (tableData.data && Array.isArray(tableData.data)) {
                const playerNames = tableData.data
                    .map(row => row.player_name ? String(row.player_name).trim() : null)
                    .filter(name => name && name !== teamKey);
                this.seedPlayerAndTeamColors(playerNames, [teamKey, `${state.team} (Team Average)`]);
            }

            // Pass directly to createTableTabulator (like timetable)
            if (typeof createTableTabulator === 'function') {
                createTableTabulator('team-win-percentage-table', tableData, {
                    disablePositionCircle: false, // Enable colored circles based on player names
                    enableSpecialRowStyling: true,
                    disableTeamColorUpdate: true // We handle player colors manually
                });
            }
        } catch (error) {
            console.error('Error loading win percentage table:', error);
        }
    }

    renderWinPercentageBubbleChart(data) {
        const chartContainer = document.getElementById('team-win-percentage-chart-bubble');
        if (!chartContainer) {
            console.error('Win percentage bubble chart container not found');
            return;
        }

        if (typeof createScatterChartMultiAxis !== 'function') {
            console.error('createScatterChartMultiAxis function not available');
            return;
        }

        // Extract data from SeriesData format
        const winPercentageData = data.win_percentage_data;
        const labels = data.weeks;
        const teamKey = `${data.team} (Team)`;
        const playerOrder = Array.isArray(data.player_order_by_average) ? data.player_order_by_average : [];
        
        // Ensure player colors are set - normalize player names (trim whitespace)
        const playerNames = playerOrder.length
            ? playerOrder.map(name => String(name).trim()).filter(name => name && name !== teamKey)
            : Object.keys(winPercentageData.data)
                .map(name => String(name).trim())
                .filter(name => name !== teamKey);
        this.seedPlayerAndTeamColors(playerNames, [teamKey, `${data.team} (Team Average)`]);
        
        // Convert SeriesData format to scatter chart format
        const chartData = {};
        
        // Process each player/team in the win percentage data
        const dataKeys = playerOrder.length
            ? playerNames.concat(Object.keys(winPercentageData.data).filter(name => name !== teamKey && !playerNames.includes(name)))
            : Object.keys(winPercentageData.data);
        dataKeys.forEach(playerName => {
            const playerData = winPercentageData.data[playerName];
            // Filter out null/undefined values for chart display
            chartData[playerName] = playerData.map(value => 
                value === null || value === undefined ? null : value
            );
        });
        if (winPercentageData.data[teamKey]) {
            chartData[teamKey] = winPercentageData.data[teamKey].map(value =>
                value === null || value === undefined ? null : value
            );
        }

        // Generate week labels
        const weekLabel = typeof t === 'function' ? t('week', 'Week') : 'Week';
        const weekLabels = labels.map((week, index) => `${weekLabel} ${index + 1}`);

        // Create scatter chart using existing function
        const winPercentageLabel = typeof t === 'function' ? t('ui.win_percentage.win_percentage', 'Win %') : 'Win %';
        createScatterChartMultiAxis(
            chartData,
            Object.keys(chartData),
            'team-win-percentage-chart-bubble',
            (typeof t === 'function' ? t('ui.win_percentage.weekly', 'Weekly Win %') : 'Weekly Win %'),
            weekLabels,
            {
                minValue: 0,
                maxValue: 100,
                tooltipValueLabel: winPercentageLabel
            }
        );
    }

    renderBubbleChart(data) {
        const chartContainer = document.getElementById(`${this.chartContainerId}-bubble`);
        if (!chartContainer) {
            console.error(`${this.containerId}: Bubble chart container not found`);
            return;
        }

        if (typeof createScatterChartMultiAxis !== 'function') {
            console.error('createScatterChartMultiAxis function not available');
            return;
        }

        // Extract data from SeriesData format
        const performanceData = data.performance_data;
        const labels = data.weeks;
        const teamAverageKey = `${data.team} (Team Average)`;
        const playerOrder = Array.isArray(data.player_order_by_average) ? data.player_order_by_average : [];
        
        // Ensure player colors are set (should already be set from createPerformanceTable, but ensure it)
        // Normalize player names (trim whitespace) for consistent color mapping
        const playerNames = playerOrder.length
            ? playerOrder.map(name => String(name).trim()).filter(name => name && name !== teamAverageKey)
            : Object.keys(performanceData.data)
                .map(name => String(name).trim())
                .filter(name => name !== teamAverageKey);
        this.seedPlayerAndTeamColors(playerNames, [teamAverageKey, `${data.team} (Team)`]);
        
        // Convert SeriesData format to scatter chart format
        // The scatter chart expects data in the same format as line chart
        const chartData = {};
        
        // Process each player/team in the performance data
        const dataKeys = playerOrder.length
            ? playerNames.concat(Object.keys(performanceData.data).filter(name => name !== teamAverageKey && !playerNames.includes(name)))
            : Object.keys(performanceData.data);
        dataKeys.forEach(playerName => {
            const playerData = performanceData.data[playerName];
            // Filter out null/undefined values for chart display
            chartData[playerName] = playerData.map(value => 
                value === null || value === undefined ? null : value
            );
        });
        if (performanceData.data[teamAverageKey]) {
            chartData[teamAverageKey] = performanceData.data[teamAverageKey].map(value =>
                value === null || value === undefined ? null : value
            );
        }

        // Generate week labels
        const weekLabel = typeof t === 'function' ? t('week', 'Week') : 'Week';
        const weekLabels = labels.map((week, index) => `${weekLabel} ${index + 1}`);

        // Create scatter chart using existing function (getTeamColor will check playerColorMap as fallback)
        // Normalize circle sizes: values 150-250 map to circle sizes 20-80
        const pointsLabel = typeof t === 'function' ? t('pins', 'Punkte') : 'Punkte';
        createScatterChartMultiAxis(
            chartData,
            Object.keys(chartData),
            `${this.chartContainerId}-bubble`,
            (typeof t === 'function' ? t('points_per_match_day', 'Points per Match Day') : 'Points per Match Day'),
            weekLabels,
            {
                minValue: 160,
                maxValue: 230,
                tooltipValueLabel: pointsLabel
                //minCircleSize: 20,
                //maxCircleSize: 80
            }
        );
    }

    storeColumnMetadata(tableData) {
        // Extract all column fields and categorize them
        this.columnMetadata = {
            allFields: [],
            pointsFields: [],
            scoreFields: [],
            otherFields: []
        };

        if (!tableData.columns) {
            return;
        }

        // Flatten column structure to get all fields
        const flattenColumns = (columns) => {
            const fields = [];
            columns.forEach((group) => {
                if (group.columns && Array.isArray(group.columns)) {
                    group.columns.forEach((col) => {
                        if (col.field) {
                            fields.push(col.field);
                        }
                    });
                }
            });
            return fields;
        };

        const allFields = flattenColumns(tableData.columns);
        this.columnMetadata.allFields = allFields;

        // Categorize fields: points vs score
        allFields.forEach((field) => {
            const fieldLower = field.toLowerCase();
            // Check for points first (to catch avg_points, etc.)
            if (fieldLower.includes('points')) {
                this.columnMetadata.pointsFields.push(field);
            } else if (fieldLower.includes('score') || fieldLower.startsWith('week_')) {
                // Score fields: anything with "score" or week columns (week_1, week_2, etc.)
                this.columnMetadata.scoreFields.push(field);
            } else {
                // Other fields (player_name, player_initials, totals, etc.) - always show
                this.columnMetadata.otherFields.push(field);
            }
        });
    }

    attachFilterListeners() {
        // Use event delegation on document to catch events from dynamically created buttons
        // Remove any existing listener first to avoid duplicates
        if (this._filterListener) {
            document.removeEventListener('change', this._filterListener);
        }
        
        this._filterListener = (event) => {
            if (event.target.name === 'performanceFilter') {
                this.currentFilter = event.target.value;
                this.applyFilter(this.currentFilter);
            }
        };
        
        document.addEventListener('change', this._filterListener);
        
        // Wait for DOM to be ready, then verify buttons exist and set default
        setTimeout(() => {
            const defaultButton = document.getElementById('performanceFilterBoth');
            const pointsButton = document.getElementById('performanceFilterPoints');
            const scoreButton = document.getElementById('performanceFilterScore');
            
            if (!defaultButton || !pointsButton || !scoreButton) {
                console.warn('⚠️ Filter buttons not found in DOM!');
                return;
            }
            
            // Set default checked state
            defaultButton.checked = true;
            this.currentFilter = 'both';
            
            // Ensure visual state is correct
            const labels = document.querySelectorAll('label[for^="performanceFilter"]');
            labels.forEach(label => {
                const inputId = label.getAttribute('for');
                const input = document.getElementById(inputId);
                if (input && input.checked) {
                    label.classList.add('active');
                } else {
                    label.classList.remove('active');
                }
            });
            
        }, 100);
    }

    applyFilter(filterType) {
        const tableInstance = window['team-performance-tableInstance'];
        if (!tableInstance || !this.columnMetadata) {
            return;
        }

        const { pointsFields, scoreFields, otherFields } = this.columnMetadata;

        // Determine which fields to show
        let fieldsToShow = [];
        let fieldsToHide = [];

        if (filterType === 'points') {
            fieldsToShow = [...pointsFields, ...otherFields];
            fieldsToHide = scoreFields;
        } else if (filterType === 'score') {
            fieldsToShow = [...scoreFields, ...otherFields];
            fieldsToHide = pointsFields;
        } else {
            // 'both' - show all
            fieldsToShow = [...pointsFields, ...scoreFields, ...otherFields];
            fieldsToHide = [];
        }

        // Apply show/hide to columns
        try {
            // Get all columns from Tabulator
            const allColumns = tableInstance.getColumns();
            
            allColumns.forEach((column) => {
                const field = column.getField();
                if (!field) {
                    return; // Skip group headers
                }

                if (fieldsToHide.includes(field)) {
                    column.hide();
                } else if (fieldsToShow.includes(field)) {
                    column.show();
                }
            });
        } catch (error) {
            console.error('Error applying filter:', error);
        }
    }

    renderError(message) {
        if (this.container) {
            this.container.innerHTML = `
                <div class="card mb-4">
                    <div class="card-header">
                        <h5>${typeof t === 'function' ? t('block.team_performance.title', 'Team Performance Analysis') : 'Team Performance Analysis'}</h5>
                    </div>
                    <div class="card-body">
                        <div class="alert alert-warning" role="alert">
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            ${message}
                        </div>
                    </div>
                </div>
            `;
        }
    }
}
