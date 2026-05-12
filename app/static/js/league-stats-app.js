/**
 * LeagueStatsApp - Main application coordinator for league statistics page
 * Manages content blocks and state synchronization
 */
function bowlyzerVlog(...args) {
    if (typeof window !== 'undefined' && window.isBowlyzerVerboseUi && window.isBowlyzerVerboseUi()) {
        console.log(...args);
    }
}

class LeagueStatsApp {
    constructor() {
        this.contentBlocks = new Map();
        this.currentState = {
            season: null,
            league: null,
            league_long: null,
            week: null,
            round: null,
            team: null
        };
        this.urlStateManager = new URLStateManager();
        this.contentRenderer = new LeagueStatsContentRenderer();
        this.filterManager = null;
        
        // Debouncing for content updates
        this.contentUpdateTimeout = null;
        this.isRenderingContent = false;
    }

    async initialize() {
        try {
            bowlyzerVlog('🚀 Initializing LeagueStatsApp...');
            
            // Get initial state from URL (URLStateManager initializes in constructor)
            this.currentState = { ...this.currentState, ...this.urlStateManager.getState() };

            // Resolve "latest" placeholders for season/week if requested
            const resolvedInitial = await this.resolveLatestSelections(this.currentState);
            // If anything changed, update URL state (replaceHistory to avoid extra entry)
            if (JSON.stringify(resolvedInitial) !== JSON.stringify(this.currentState)) {
                this.currentState = resolvedInitial;
                this.urlStateManager.setState(this.currentState, /*replaceHistory*/ true);
            } else {
                this.currentState = resolvedInitial;
            }
            
            // Initialize content blocks
            await this.initializeContentBlocks();
            
            // Set up event listeners
            this.setupEventListeners();
            
            // Wait a bit for filter manager to finish processing initial state
            // This ensures the default league is set before we render content
            await new Promise(resolve => setTimeout(resolve, 100));
            
            // Get the final state after filter manager processing
            this.currentState = { ...this.currentState, ...this.urlStateManager.getState() };
            // Re-resolve latest in case filter manager didn't set concrete values yet
            const resolvedPostButtons = await this.resolveLatestSelections(this.currentState);
            if (JSON.stringify(resolvedPostButtons) !== JSON.stringify(this.currentState)) {
                this.currentState = resolvedPostButtons;
                this.urlStateManager.setState(this.currentState, /*replaceHistory*/ true);
            } else {
                this.currentState = resolvedPostButtons;
            }
            
            // Initial render with final state
            await this.renderContent();
            
            bowlyzerVlog('✅ LeagueStatsApp initialized successfully');
        } catch (error) {
            console.error('❌ Error initializing LeagueStatsApp:', error);
            throw error;
        }
    }

    async initializeContentBlocks() {
        bowlyzerVlog('🧱 Initializing content blocks...');
        
        try {
            // Create content blocks FIRST (they initialize in their constructors)
            bowlyzerVlog('🔄 Creating SeasonLeagueStandingsBlock...');
            const seasonLeagueStandingsBlock = new SeasonLeagueStandingsBlock();
            bowlyzerVlog('🔄 Creating LeagueAggregationBlock...');
            const leagueAggregationBlock = new LeagueAggregationBlock();
            bowlyzerVlog('🔄 Creating LeagueSeasonOverviewBlock...');
            const leagueSeasonOverviewBlock = new LeagueSeasonOverviewBlock();
            bowlyzerVlog('🔄 Creating SeasonOverviewBlock...');
            const seasonOverviewBlock = new SeasonOverviewBlock();
            bowlyzerVlog('🔄 Creating MatchDayBlock...');
            const matchDayBlock = new MatchDayBlock();
            bowlyzerVlog('🔄 Creating TeamDetailsBlock...');
            const teamDetailsBlock = new TeamDetailsBlock();
            bowlyzerVlog('🔄 Creating TeamPerformanceBlock...');
            const teamPerformanceBlock = new TeamPerformanceBlock();
            bowlyzerVlog('🔄 Creating GameOverviewBlock...');
            const gameOverviewBlock = new GameOverviewBlock();
            bowlyzerVlog('🔄 Creating GameTeamDetailsBlock...');
            const gameTeamDetailsBlock = new GameTeamDetailsBlock();
            
            // Store blocks (no filter-controls block needed anymore)
            this.contentBlocks.set('season-league-standings', seasonLeagueStandingsBlock);
            this.contentBlocks.set('league-aggregation', leagueAggregationBlock);
            this.contentBlocks.set('league-season-overview', leagueSeasonOverviewBlock);
            this.contentBlocks.set('season-overview', seasonOverviewBlock);
            this.contentBlocks.set('matchday', matchDayBlock);
            this.contentBlocks.set('team-details', teamDetailsBlock);
            this.contentBlocks.set('team-performance', teamPerformanceBlock);
            this.contentBlocks.set('game-overview', gameOverviewBlock);
            this.contentBlocks.set('game-team-details', gameTeamDetailsBlock);
            
            bowlyzerVlog('✅ Content blocks initialized');
            
            // Initialize centralized button manager for league mode with content rendering callback
            this.buttonManager = new CentralizedButtonManager(this.urlStateManager, 'league', (state) => {
                bowlyzerVlog('🔄 LeagueStatsApp: Button state changed, rendering content:', state);
                bowlyzerVlog('🔄 LeagueStatsApp: State keys:', Object.keys(state));
                bowlyzerVlog('🔄 LeagueStatsApp: Round value:', state.round, 'Type:', typeof state.round);
                this.currentState = { ...state };
                this.renderContent();
            });
            await this.buttonManager.initialize();
            
        } catch (error) {
            console.error('❌ Error initializing content blocks:', error);
            throw error;
        }
    }

    setupEventListeners() {
        // Listen for filter changes from the filter controls block
        document.addEventListener('filterChange', (event) => {
            this.handleStateChange(event.detail);
        });

        // Listen for external events (data source changes, palette changes)
        window.handleDataSourceChange = () => {
            bowlyzerVlog('📊 Data source changed - refreshing content');
            this.renderContent();
        };
        
        // Listen for database changes
        window.addEventListener('databaseChanged', (event) => {
            bowlyzerVlog('🔄 Database changed event received:', event.detail);
            this.handleDatabaseChange(event.detail.database);
        });
        
        // Listen for language changes
        window.addEventListener('languageChanged', (event) => {
            bowlyzerVlog('🔄 Language changed event received:', event.detail);
            this.handleLanguageChange(event.detail.language);
        });

        window.handlePaletteChange = () => {
            bowlyzerVlog('🎨 Palette changed - refreshing content');
            this.renderContent();
        };

        // For backward compatibility
        window.refreshAllCharts = () => {
            this.renderContent();
        };
    }

    async handleStateChange(newState) {
        bowlyzerVlog('🔄 State changed:', newState);
        
        // Check if state actually changed to prevent unnecessary updates
        const stateChanged = JSON.stringify(this.currentState) !== JSON.stringify(newState);
        
        // Update current state
        this.currentState = await this.resolveLatestSelections({ ...newState });
        
        // Always render content on initial load or if state changed
        if (!stateChanged && Object.values(this.currentState).some(val => val && val !== '')) {
            bowlyzerVlog('Initial load with state, rendering content');
        } else if (!stateChanged) {
            bowlyzerVlog('State unchanged, skipping update');
            return;
        }
        
        // Update URL (debounced)
        this.urlStateManager.setState(this.currentState);
        
        // Debounce content rendering to prevent excessive updates
        if (this.contentUpdateTimeout) {
            clearTimeout(this.contentUpdateTimeout);
        }
        
        this.contentUpdateTimeout = setTimeout(() => {
            this.renderContent();
        }, 200); // 200ms debounce for content updates
    }

    /**
     * Resolve "latest" for season/week by querying backend for available values.
     * Does NOT assign defaults when parameters are empty; only when explicitly set to 'latest'.
     */
    async resolveLatestSelections(state) {
        const resolved = { ...state };
        try {
            // Division-only deep links should land in league-centric view (no season default).
            // If division is present but league is missing, pick first available league in that division.
            if (resolved.division && !resolved.league) {
                const query = new URLSearchParams();
                query.set('division', String(resolved.division));
                if (resolved.season) {
                    query.set('season', String(resolved.season));
                }
                const resp = await fetchWithDatabase(`/league/get_available_leagues?${query.toString()}`);
                const leagues = await resp.json();
                if (Array.isArray(leagues) && leagues.length > 0) {
                    const firstLeague = leagues[0];
                    const shortName =
                        (firstLeague && typeof firstLeague === 'object')
                            ? (firstLeague.short_name || firstLeague.value || '')
                            : String(firstLeague || '');
                    const longName =
                        (firstLeague && typeof firstLeague === 'object')
                            ? (firstLeague.long_name || '')
                            : '';
                    if (shortName) {
                        resolved.league = shortName;
                        resolved.league_long = longName || resolved.league_long || '';
                    }
                }
            }

            // Resolve latest season
            if (resolved.season === 'latest') {
                const resp = await fetchWithDatabase('/league/get_available_seasons');
                const seasons = await resp.json();
                if (Array.isArray(seasons) && seasons.length > 0) {
                    // numeric or sortable strings; pick max
                    const latestSeason = seasons.reduce((a,b) => (String(a) > String(b) ? a : b));
                    resolved.season = latestSeason;
                }
            }
            // Resolve latest week (requires season and league to be known)
            if (resolved.week === 'latest' && resolved.season && resolved.league) {
                const resp = await fetchWithDatabase(`/league/get_available_weeks?season=${encodeURIComponent(resolved.season)}&league=${encodeURIComponent(resolved.league)}`);
                const weeks = await resp.json();
                if (Array.isArray(weeks) && weeks.length > 0) {
                    const latestWeek = Math.max(...weeks.map(Number).filter(n => !Number.isNaN(n)));
                    resolved.week = latestWeek;
                }
            }
        } catch (e) {
            console.warn('resolveLatestSelections: failed to resolve latest values', e);
        }
        return resolved;
    }
    
    /**
     * Handle database changes
     */
    async handleDatabaseChange(newDatabase) {
        bowlyzerVlog('🔄 Handling database change to:', newDatabase);
        
        try {
            // Update URL state with new database
            const currentState = this.urlStateManager.getState();
            const newState = {
                ...currentState,
                database: newDatabase,
                team: '', // Reset team selection
                season: '', // Reset season selection
                week: '', // Reset week selection
                league: '' // Reset league selection
            };
            
            // Update URL state
            this.urlStateManager.setState(newState);
            
            // Reinitialize button manager with new state
            if (this.buttonManager) {
                await this.buttonManager.handleStateChange(newState);
            }
            
            // Render content with new state
            this.renderContent();
            
            bowlyzerVlog('✅ Database change handled successfully');
            
        } catch (error) {
            console.error('❌ Error handling database change:', error);
        }
    }
    
    /**
     * Handle language changes
     */
    async handleLanguageChange(newLanguage) {
        bowlyzerVlog('🔄 Handling language change to:', newLanguage);
        
        try {
            // Re-render all content to update translations
            this.renderContent();
            
            bowlyzerVlog('✅ Language change handled successfully');
            
        } catch (error) {
            console.error('❌ Error handling language change:', error);
        }
    }

    async renderContent() {
        if (this.isRenderingContent) {
            bowlyzerVlog('Content rendering already in progress, skipping');
            return;
        }
        
        try {
            this.isRenderingContent = true;
            bowlyzerVlog('🎨 Rendering content for state:', this.currentState);
            bowlyzerVlog('🎨 Available content blocks:', Array.from(this.contentBlocks.keys()));
            
            // Check if we have any content blocks
            if (this.contentBlocks.size === 0) {
                console.warn('⚠️ LeagueStatsApp: No content blocks available for rendering');
                return;
            }
            
            // Render all content blocks in parallel for better performance
            const renderPromises = Array.from(this.contentBlocks.entries()).map(async ([blockName, block]) => {
                try {
                    bowlyzerVlog(`🔄 Rendering block: ${blockName} with state:`, {
                        season: this.currentState.season,
                        league: this.currentState.league,
                        week: this.currentState.week,
                        round: this.currentState.round,
                        team: this.currentState.team
                    });
                    await block.render(this.currentState);
                    bowlyzerVlog(`✅ Rendered block: ${blockName}`);
                } catch (error) {
                    console.error(`❌ Error rendering block ${blockName}:`, error);
                }
            });
            
            await Promise.all(renderPromises);
            bowlyzerVlog('✅ Content rendering complete');
            
        } catch (error) {
            console.error('❌ Error during content rendering:', error);
        } finally {
            this.isRenderingContent = false;
        }
    }

    // Public methods for external access
    getCurrentState() {
        return { ...this.currentState };
    }

    async setState(newState) {
        await this.handleStateChange(newState);
    }

    getContentBlock(blockName) {
        return this.contentBlocks.get(blockName);
    }
}

/**
 * LeagueStatsContentRenderer - Specialized content renderer for league stats
 */
class LeagueStatsContentRenderer {
    constructor() {
        this.contentBlocks = [];
    }

    addContentBlock(block) {
        this.contentBlocks.push(block);
    }

    async renderContent(state) {
        const renderPromises = this.contentBlocks.map(async (block) => {
            try {
                await block.render(state);
            } catch (error) {
                console.error(`Error rendering content block:`, error);
            }
        });

        await Promise.all(renderPromises);
    }
}

// Global initialization
let leagueStatsApp;

document.addEventListener('DOMContentLoaded', async () => {
    try {
        bowlyzerVlog('📄 DOM loaded, initializing LeagueStatsApp...');
        
        leagueStatsApp = new LeagueStatsApp();
        await leagueStatsApp.initialize();
        
        // Make app globally accessible for debugging
        window.leagueStatsApp = leagueStatsApp;
        
    } catch (error) {
        console.error('❌ Failed to initialize LeagueStatsApp:', error);
        
        // Show error message to user
        const container = document.querySelector('.container-fluid');
        if (container) {
            container.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <h4 class="alert-heading">${typeof t === 'function' ? t('status.initialization_error.title', 'Initialization Error') : 'Initialization Error'}</h4>
                    <p>${typeof t === 'function' ? t('status.initialization_error.message', 'Failed to initialize the league statistics application. Please refresh the page.') : 'Failed to initialize the league statistics application. Please refresh the page.'}</p>
                    <hr>
                    <p class="mb-0">Error: ${error.message}</p>
                </div>
            `;
        }
    }
});