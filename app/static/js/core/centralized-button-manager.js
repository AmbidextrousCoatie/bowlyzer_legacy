/**
 * Centralized Button Manager
 * 
 * Robust, centralized system for managing filter buttons with constraint-based updates
 * Handles the complete lifecycle: fetch candidates, populate buttons, manage state
 */

function bowlyzerVlog(...args) {
    if (typeof window !== 'undefined' && window.isBowlyzerVerboseUi && window.isBowlyzerVerboseUi()) {
        bowlyzerVlog(...args);
    }
}

class CentralizedButtonManager {
    constructor(urlStateManager, mode = 'league', onStateChange = null) {
        this.urlStateManager = urlStateManager;
        this.mode = mode; // 'team' or 'league'
        this.isInitializing = false;
        this.isProcessingUpdate = false;
        this.onStateChange = onStateChange; // Callback for state changes
        
        // Button group definitions with their dependencies and order
        this.buttonGroups = {
            season: {
                order: 1,
                dependencies: [],
                endpoint: '/league/get_available_seasons',
                containerId: 'buttonsSeason',
                name: 'season'
            },
            division: {
                order: 2,
                dependencies: [],
                endpoint: '/league/get_available_divisions',
                containerId: 'buttonsDivision',
                name: 'division'
            },
            league: {
                order: 3,
                dependencies: ['division'],
                endpoint: '/league/get_available_leagues',
                containerId: 'buttonsLeague',
                name: 'league'
            },
            week: {
                order: 4,
                dependencies: ['season', 'league'],
                endpoint: '/league/get_available_weeks',
                containerId: 'buttonsWeek',
                name: 'week'
            },
            round: {
                order: 5,
                dependencies: ['season', 'league', 'week'],
                endpoint: '/league/get_available_rounds',
                containerId: 'buttonsRound',
                name: 'round'
            },
            team: {
                order: 6,
                dependencies: ['season', 'league'],
                endpoint: '/league/get_available_teams',
                containerId: 'buttonsTeam',
                name: 'team'
            }
        };
        
        // Current state and constraints
        this.currentState = {};
        this.constraints = {};
        this.availableCandidates = {};
        this.selectedValues = {};
        this.leagueMetadata = new Map();
        
        // Track which button group triggered the update
        this.triggerGroup = null;
        
        // Listen for state changes from URL manager
        this.urlStateManager.onStateChange((state) => {
            this.handleStateChange(state);
        });
    }
    
    /**
     * Initialize the button manager
     */
    async initialize() {
        this.isInitializing = true;
        
        try {
            // Set up event listeners
            this.setupButtonEventListeners();
            
            // Get current state and handle initial setup
            const currentState = this.urlStateManager.getState();
            await this.handleInitialState(currentState);
            
        } catch (error) {
            console.error('❌ CentralizedButtonManager: Initialization failed:', error);
        } finally {
            this.isInitializing = false;
        }
    }
    
    /**
     * Handle initial state from URL parameters
     */
    async handleInitialState(state) {
        bowlyzerVlog('🚀 CentralizedButtonManager: Handling initial state:', state);
        
        // Store current state
        this.currentState = { ...state };
        this.selectedValues = { ...state };
        
        // Start with no constraints - load all available data
        this.constraints = {};
        
        // Process all button groups in order
        await this.processAllButtonGroups();
    }
    
    /**
     * Handle state changes from URL manager
     */
    async handleStateChange(newState) {
        if (this.isInitializing || this.isProcessingUpdate) {
            bowlyzerVlog('⚠️ CentralizedButtonManager: Skipping state change - isInitializing:', this.isInitializing, 'isProcessingUpdate:', this.isProcessingUpdate);
            return;
        }
        
        bowlyzerVlog('🔄 CentralizedButtonManager: State changed:', newState);
        bowlyzerVlog('🔄 CentralizedButtonManager: Previous state:', this.currentState);
        
        // Find which button group changed
        this.triggerGroup = this.findChangedButtonGroup(newState);
        
        if (!this.triggerGroup) {
            bowlyzerVlog('⚠️ CentralizedButtonManager: No trigger group found, skipping update');
            return;
        }
        
        bowlyzerVlog(`🎯 CentralizedButtonManager: Trigger group: ${this.triggerGroup}`);
        
        // Update current state
        this.currentState = { ...newState };
        this.selectedValues = { ...newState };
        
        // Update constraints for the changed group
        if (this.triggerGroup && newState[this.triggerGroup]) {
            this.constraints[this.triggerGroup] = newState[this.triggerGroup];
            bowlyzerVlog(`🎯 CentralizedButtonManager: Updated constraints for trigger group ${this.triggerGroup}:`, this.constraints);
        }
        
        // Process button groups with constraint-based updates
        await this.processAllButtonGroups();
    }
    
    /**
     * Find which button group triggered the change
     */
    findChangedButtonGroup(newState) {
        bowlyzerVlog('🔍 CentralizedButtonManager: Finding changed button group...');
        for (const [groupName, groupConfig] of Object.entries(this.buttonGroups)) {
            const oldValue = this.currentState[groupConfig.name];
            const newValue = newState[groupConfig.name];
            
            bowlyzerVlog(`🔍 CentralizedButtonManager: Checking ${groupName} - old: "${oldValue}", new: "${newValue}"`);
            
            if (oldValue !== newValue) {
                bowlyzerVlog(`🎯 CentralizedButtonManager: Found changed group: ${groupName}`);
                return groupName;
            }
        }
        bowlyzerVlog('⚠️ CentralizedButtonManager: No changed group found');
        return null;
    }
    
    /**
     * Process all button groups in dependency order
     */
    async processAllButtonGroups() {
        this.isProcessingUpdate = true;
        
        try {
            // Get button groups in order
            const groupsToProcess = this.getButtonGroupsInOrder();
            
            bowlyzerVlog('📋 CentralizedButtonManager: Processing groups:', groupsToProcess.map(g => g.name));
            bowlyzerVlog('📋 CentralizedButtonManager: Current constraints:', this.constraints);
            
            // Process each group sequentially
            for (const group of groupsToProcess) {
                await this.processButtonGroup(group);
            }
            
            // Trigger state change callback for content rendering
            if (this.onStateChange) {
                bowlyzerVlog('🔄 CentralizedButtonManager: Triggering state change callback with state:', this.currentState);
                bowlyzerVlog('🔄 CentralizedButtonManager: Callback function:', typeof this.onStateChange);
                try {
                    this.onStateChange(this.currentState);
                    bowlyzerVlog('✅ CentralizedButtonManager: State change callback executed successfully');
                } catch (error) {
                    console.error('❌ CentralizedButtonManager: Error in state change callback:', error);
                }
            } else {
                console.warn('⚠️ CentralizedButtonManager: No state change callback registered');
            }
            
        } catch (error) {
            console.error('❌ CentralizedButtonManager: Error processing button groups:', error);
        } finally {
            this.isProcessingUpdate = false;
        }
    }
    
    /**
     * Get button groups in dependency order
     */
    getButtonGroupsInOrder() {
        const groups = Object.entries(this.buttonGroups)
            .map(([name, config]) => ({ name, ...config }))
            .sort((a, b) => a.order - b.order);
        
        // During initial load (no trigger group), process all groups
        // During state changes, exclude the trigger group
        if (this.triggerGroup) {
            return groups.filter(group => group.name !== this.triggerGroup);
        }
        
        return groups;
    }
    
    /**
     * Process a single button group
     */
    async processButtonGroup(group) {
        bowlyzerVlog(`🔧 CentralizedButtonManager: Processing group ${group.name}`);
        
        try {
            // Check if prerequisites are met
            if (!this.arePrerequisitesMet(group)) {
                bowlyzerVlog(`⚠️ CentralizedButtonManager: Prerequisites not met for ${group.name}`);
                bowlyzerVlog(`⚠️ CentralizedButtonManager: Clearing buttons for ${group.name}`);
                this.clearButtonGroup(group);
                return;
            }
            
            // Fetch candidates for this group
            const rawCandidates = await this.fetchCandidates(group);
            const candidates = this.normalizeCandidates(group, rawCandidates);
            
            if (!candidates || candidates.length === 0) {
                bowlyzerVlog(`⚠️ CentralizedButtonManager: No candidates for ${group.name}, clearing buttons`);
                this.clearButtonGroup(group);
                return;
            }
            
            // Store candidates
            this.availableCandidates[group.name] = candidates;
            
            // Check if current selection is still valid
            const currentSelection = this.selectedValues[group.name];
            const isValidSelection = currentSelection && candidates.some(candidate => 
                String(this.getCandidateValue(candidate, group.name)) === String(currentSelection)
            );
            
            if (isValidSelection) {
                bowlyzerVlog(`✅ CentralizedButtonManager: Keeping current selection for ${group.name}: ${currentSelection}`);
                // Add to constraints for next groups
                this.constraints[group.name] = currentSelection;
                if (group.name === 'league') {
                    const selectedCandidate = candidates.find(candidate => 
                        String(this.getCandidateValue(candidate, group.name)) === String(currentSelection)
                    );
                    const longName = selectedCandidate 
                        ? (selectedCandidate.longName || selectedCandidate.long_name || selectedCandidate.label || currentSelection) 
                        : '';
                    this.currentState.league_long = longName;
                    this.selectedValues.league_long = longName;
                    
                     // Ensure URL state also carries the long name (replace state to avoid new history entries)
                    const urlState = this.urlStateManager.getState();
                    if (longName && urlState.league_long !== longName) {
                        this.urlStateManager.setState({ league_long: longName }, true);
                    }
                }
            } else {
                bowlyzerVlog(`🔄 CentralizedButtonManager: Invalid selection for ${group.name}, clearing selection`);
                // Clear this group's selection and don't add constraints
                this.selectedValues[group.name] = '';
                this.currentState[group.name] = '';
                delete this.constraints[group.name];
                if (group.name === 'league') {
                    this.selectedValues.league_long = '';
                    this.currentState.league_long = '';
                }
            }
            
            // Always populate buttons with candidates, regardless of current selection validity
            bowlyzerVlog(`🎨 CentralizedButtonManager: Populating buttons for ${group.name} with ${candidates.length} candidates`);
            this.populateButtonGroup(group, candidates);
            
        } catch (error) {
            console.error(`❌ CentralizedButtonManager: Error processing group ${group.name}:`, error);
            this.showError(group, error.message);
        }
    }
    
    /**
     * Check if prerequisites are met for a button group
     */
    arePrerequisitesMet(group) {
        return group.dependencies.every(dep => this.selectedValues[dep]);
    }
    
    /**
     * Fetch candidates for a button group
     */
    async fetchCandidates(group) {
        const params = new URLSearchParams();
        
        // Add constraints as parameters
        Object.entries(this.constraints).forEach(([key, value]) => {
            if (value) {
                params.append(key, value);
                bowlyzerVlog(`🔗 CentralizedButtonManager: Adding constraint ${key}=${value} for ${group.name}`);
            }
        });
        
        // Add database parameter
        const urlParams = new URLSearchParams(window.location.search);
        const database = urlParams.get('database') || 'db_real_pipeline_gf';
        params.append('database', database);
        
        const url = `${group.endpoint}?${params.toString()}`;
        console.info('[API] GET', url);
        bowlyzerVlog(`CentralizedButtonManager: filter constraints for ${group.name}`, this.constraints);
        
        const response = await fetch(url);
        if (!response.ok) {
            console.error(`❌ CentralizedButtonManager: HTTP ${response.status} for ${group.name}: ${url}`);
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const candidates = await response.json();
        bowlyzerVlog(`📊 CentralizedButtonManager: Received candidates for ${group.name}:`, candidates);
        //console.log(`📊 CentralizedButtonManager: Candidate types:`, candidates.map(c => typeof c));
        
        return candidates;
    }
    
    /**
     * Populate button group with candidates
     */
    populateButtonGroup(group, candidates) {
        const container = document.getElementById(group.containerId);
        if (!container) {
            console.warn(`⚠️ CentralizedButtonManager: Container not found: ${group.containerId}`);
            return;
        }
        
        let selectedValue = this.selectedValues[group.name] || '';
        selectedValue = selectedValue != null ? String(selectedValue) : '';
        
        if (group.name === 'league') {
            this.leagueMetadata.clear();
        }
        
        bowlyzerVlog(`🎨 CentralizedButtonManager: Populating ${group.name} - current selection: "${selectedValue}", candidates:`, candidates);
        
        // Auto-select logic for season group ONLY when explicitly set to 'latest'
        if (group.name === 'season' && selectedValue === 'latest' && candidates.length > 0) {
            // Sort seasons and select the latest one
            const sortedCandidates = [...candidates].sort((a, b) => {
                const aNum = parseInt(a);
                const bNum = parseInt(b);
                if (!isNaN(aNum) && !isNaN(bNum)) return bNum - aNum; // Latest first
                return b.localeCompare(a); // String comparison, latest first
            });
            const latest = sortedCandidates[0];
            this.selectedValues[group.name] = latest;
            this.currentState[group.name] = latest;
            this.constraints[group.name] = latest;
            bowlyzerVlog(`🎯 CentralizedButtonManager: Resolved season 'latest' -> ${latest}`);
            this.urlStateManager.setState({ [group.name]: latest });
            selectedValue = latest;
        }
        
        // Auto-select logic for league group (if season is available but no league selected)
        // Only auto-select during initial load, not during state changes
        // DISABLED: No auto-selection of league to allow season-only view
        if (group.name === 'league' && !selectedValue && candidates.length > 0 && this.constraints.season && !this.triggerGroup) {
            // Don't auto-select league - let user choose or view season-only
            bowlyzerVlog(`🎯 CentralizedButtonManager: Skipping league auto-selection - allowing season-only view`);
        }
        
        // Auto-select logic for week group (if season and league are available but no week selected)
        // Only auto-select during initial load, not during state changes
        // DISABLED: No auto-selection of week since it requires league selection
        if (group.name === 'week' && !selectedValue && candidates.length > 0 && this.constraints.season && this.constraints.league && !this.triggerGroup) {
            // Don't auto-select week - requires league to be selected first
            bowlyzerVlog(`🎯 CentralizedButtonManager: Skipping week auto-selection - requires league selection first`);
        }
        
        // Create buttons HTML
        const buttonsHtml = candidates.map(candidate => {
            if (group.name === 'league') {
                const value = String(this.getCandidateValue(candidate, group.name));
                const longName = candidate.longName || candidate.long_name || candidate.label || value;
                const isChecked = value === selectedValue;
                const safeId = this.createSafeId(value, group.name);
                const escapedValue = this.escapeAttribute(value);
                const escapedLong = this.escapeAttribute(longName);
                const escapedLabel = this.escapeHtml(value);
                
                this.leagueMetadata.set(value, longName);
                
                return `
                    <input type="radio" class="btn-check" name="${group.name}" id="${group.name}_${safeId}" 
                           value="${escapedValue}" data-long-name="${escapedLong}" ${isChecked ? 'checked' : ''}>
                    <label class="btn btn-outline-primary" for="${group.name}_${safeId}" title="${this.escapeAttribute(longName)}">
                        ${escapedLabel}
                    </label>
                `;
            }
            
            if (group.name === 'division') {
                const value = String(this.getCandidateValue(candidate, group.name));
                const label = candidate.label || value;
                const isChecked = value === selectedValue;
                const safeId = this.createSafeId(value, group.name);
                const escapedValue = this.escapeAttribute(value);
                const escapedLabel = this.escapeHtml(label);
                
                return `
                    <input type="radio" class="btn-check" name="${group.name}" id="${group.name}_${safeId}" 
                           value="${escapedValue}" ${isChecked ? 'checked' : ''}>
                    <label class="btn btn-outline-primary" for="${group.name}_${safeId}">
                        ${escapedLabel}
                    </label>
                `;
            }
            
            const candidateStr = String(candidate);
            const isChecked = candidateStr === selectedValue;
            const safeId = this.createSafeId(candidateStr, group.name);
            const escapedValue = this.escapeAttribute(candidateStr);
            const escapedLabel = this.escapeHtml(candidateStr);
            
            return `
                <input type="radio" class="btn-check" name="${group.name}" id="${group.name}_${safeId}" 
                       value="${escapedValue}" ${isChecked ? 'checked' : ''}>
                <label class="btn btn-outline-primary" for="${group.name}_${safeId}">${escapedLabel}</label>
            `;
        }).join('');
        
        container.innerHTML = buttonsHtml;
        
        bowlyzerVlog(`✅ CentralizedButtonManager: Populated ${group.name} with ${candidates.length} candidates, selected: ${selectedValue}`);
        bowlyzerVlog(`✅ CentralizedButtonManager: Created ${candidates.length} buttons for ${group.name}`);
    }
    
    /**
     * Clear a button group
     */
    clearButtonGroup(group) {
        const container = document.getElementById(group.containerId);
        if (container) {
            const message = this.getClearMessage(group);
            container.innerHTML = `<span class="text-muted">${message}</span>`;
        }
        
        // Clear selection
        this.selectedValues[group.name] = '';
        this.currentState[group.name] = '';
        delete this.constraints[group.name];
        
        if (group.name === 'league') {
            this.leagueMetadata.clear();
            this.selectedValues.league_long = '';
            this.currentState.league_long = '';
            delete this.constraints.league_long;
        }
    }
    
    /**
     * Get appropriate message when clearing button group
     */
    getClearMessage(group) {
        const depNames = group.dependencies.map(dep => this.buttonGroups[dep].name).join(', ');
        
        // Special message for league group when no league is selected
        if (group.name === 'league' && !this.constraints.division) {
            return 'Wählen Sie zuerst eine Division aus';
        }
        
        return `Wählen Sie ${depNames} aus`;
    }
    
    /**
     * Show error message for a button group
     */
    showError(group, message) {
        const container = document.getElementById(group.containerId);
        if (container) {
            container.innerHTML = `
                <div class="alert alert-danger">
                    <strong>Error loading ${group.name}:</strong> ${message}
                </div>
            `;
        }
    }
    
    /**
     * Set up event listeners for button changes
     */
    setupButtonEventListeners() {
        // Use event delegation for all filter buttons
        document.addEventListener('change', async (event) => {
            const target = event.target;
            
            if (target.type === 'radio' && this.buttonGroups[target.name]) {
                const groupName = target.name;
                const value = target.value;
                
                bowlyzerVlog(`🎯 CentralizedButtonManager: Button changed - ${groupName}: ${value}`);
                
                // Update selected values and constraints, but NOT currentState yet
                this.selectedValues[groupName] = value;
                this.constraints[groupName] = value;
                
                const stateUpdate = { [groupName]: value };
                
                if (groupName === 'league') {
                    const longName = target.dataset.longName || this.getLeagueLongName(value) || '';
                    stateUpdate.league_long = longName;
                    this.selectedValues.league_long = longName;
                }

                // Keep the full combination if valid; otherwise drop lowest-priority
                // filters one by one until a valid combination is found.
                const sanitizedUpdate = await this.sanitizeStateUpdateForChangedGroup(groupName, stateUpdate);
                bowlyzerVlog(`🎯 CentralizedButtonManager: Updated constraints:`, this.constraints);
                
                // Update URL state (this will trigger handleStateChange)
                this.urlStateManager.setState(sanitizedUpdate);
            }
        });
        
        // Add click event listeners for deselection functionality
        document.addEventListener('click', (event) => {
            let target = event.target;
            
            // Find the radio input if clicking on label
            if (target.tagName === 'LABEL' && target.htmlFor) {
                const radioInput = document.getElementById(target.htmlFor);
                if (radioInput && radioInput.type === 'radio') {
                    target = radioInput;
                }
            }
            
            if (target.type === 'radio' && this.buttonGroups[target.name]) {
                const groupName = target.name;
                const value = target.value;
                const currentlySelected = this.selectedValues[groupName];
                
                // Check if clicking the same button that was already selected
                if (currentlySelected === value) {
                    bowlyzerVlog(`🎯 CentralizedButtonManager: Deselecting ${groupName}: ${value}`);
                    
                    // Prevent the default radio button behavior
                    event.preventDefault();
                    event.stopPropagation();
                    target.checked = false;
                    
                    // Clear selection and update state
                    this.selectedValues[groupName] = '';
                    
                    const cleared = {};
                    if (groupName === 'season') {
                        cleared.season = '';
                        cleared.division = '';
                        cleared.league = '';
                        cleared.league_long = '';
                        cleared.week = '';
                        cleared.round = '';
                        cleared.team = '';
                    } else if (groupName === 'division') {
                        cleared.division = '';
                        cleared.league = '';
                        cleared.league_long = '';
                        cleared.week = '';
                        cleared.round = '';
                        cleared.team = '';
                    } else if (groupName === 'league') {
                        this.selectedValues.league_long = '';
                        cleared.league = '';
                        cleared.league_long = '';
                        cleared.week = '';
                        cleared.round = '';
                        cleared.team = '';
                    } else if (groupName === 'week') {
                        cleared.week = '';
                        cleared.round = '';
                        cleared.team = '';
                    } else if (groupName === 'round') {
                        cleared.round = '';
                        cleared.team = '';
                    } else if (groupName === 'team') {
                        cleared.team = '';
                    }
                    
                    this.urlStateManager.setState(cleared);
                }
            }
        });
    }

    getFilterPriorityOrder() {
        return ['season', 'division', 'league', 'week', 'round', 'team'];
    }

    buildConstraintsFromState(state, groupName) {
        const params = {};
        const order = this.getFilterPriorityOrder();
        const groupIdx = order.indexOf(groupName);
        if (groupIdx < 0) return params;

        for (let i = 0; i < groupIdx; i++) {
            const key = order[i];
            const val = state[key];
            if (val) {
                params[key] = val;
            }
        }
        return params;
    }

    async fetchCandidatesForState(groupName, state) {
        const group = this.buttonGroups[groupName];
        if (!group) return [];

        // If dependencies are not met, this group cannot be validated as selected.
        const depsMet = group.dependencies.every(dep => state[dep]);
        if (!depsMet) return [];

        const params = new URLSearchParams();
        const constraints = this.buildConstraintsFromState(state, groupName);
        Object.entries(constraints).forEach(([key, value]) => {
            if (value) params.append(key, value);
        });

        const urlParams = new URLSearchParams(window.location.search);
        const database = urlParams.get('database') || 'db_real_pipeline_gf';
        params.append('database', database);

        const response = await fetch(`${group.endpoint}?${params.toString()}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const raw = await response.json();
        return this.normalizeCandidates(group, raw);
    }

    async isSelectionValidForGroup(groupName, state) {
        const selected = state[groupName];
        if (!selected) return true;

        const candidates = await this.fetchCandidatesForState(groupName, state);
        return candidates.some(candidate => String(this.getCandidateValue(candidate, groupName)) === String(selected));
    }

    async isCombinationValid(state) {
        const order = this.getFilterPriorityOrder();
        for (const groupName of order) {
            const selected = state[groupName];
            if (!selected) continue;
            const isValid = await this.isSelectionValidForGroup(groupName, state);
            if (!isValid) return false;
        }
        return true;
    }

    async sanitizeStateUpdateForChangedGroup(changedGroup, stateUpdate) {
        const currentUrlState = this.urlStateManager.getState();
        const candidateState = { ...currentUrlState, ...stateUpdate };
        const order = this.getFilterPriorityOrder();
        const changedIdx = order.indexOf(changedGroup);
        const topLevelGroups = new Set(['season', 'division']);

        // First try: keep everything.
        if (await this.isCombinationValid(candidateState)) {
            return stateUpdate;
        }

        // Drop lowest-priority selected filters one-by-one, keeping the changed group fixed.
        for (let idx = order.length - 1; idx > changedIdx; idx--) {
            const key = order[idx];
            if (topLevelGroups.has(changedGroup) && topLevelGroups.has(key)) {
                // Treat season/division as same priority: don't clear one when the other changes.
                continue;
            }
            if (!candidateState[key]) continue;
            candidateState[key] = '';
            if (key === 'league') {
                candidateState.league_long = '';
            }
            if (await this.isCombinationValid(candidateState)) {
                const merged = { ...stateUpdate };
                for (const k of order) {
                    if ((k in candidateState) && candidateState[k] !== currentUrlState[k] && !(k in merged)) {
                        merged[k] = candidateState[k];
                    }
                }
                if (candidateState.league_long !== currentUrlState.league_long && !('league_long' in merged)) {
                    merged.league_long = candidateState.league_long || '';
                }
                return merged;
            }
        }

        // Fallback: if still invalid, clear all lower-priority filters.
        const fallback = { ...stateUpdate };
        for (let idx = changedIdx + 1; idx < order.length; idx++) {
            const key = order[idx];
            if (topLevelGroups.has(changedGroup) && topLevelGroups.has(key)) {
                continue;
            }
            fallback[key] = '';
        }
        if (changedGroup !== 'league') {
            fallback.league_long = fallback.league ? (candidateState.league_long || '') : '';
        }
        return fallback;
    }
    
    normalizeCandidates(group, candidates) {
        if (!Array.isArray(candidates)) {
            return [];
        }
        
        if (group.name === 'league') {
            return this.normalizeLeagueCandidates(candidates);
        }
        if (group.name === 'division') {
            return this.normalizeDivisionCandidates(candidates);
        }
        
        return candidates;
    }
    
    normalizeLeagueCandidates(candidates) {
        return candidates.map(candidate => {
            if (candidate && typeof candidate === 'object') {
                const value = candidate.value || candidate.short_name || candidate.code || candidate.id || candidate.name || '';
                const longName = candidate.long_name || candidate.longName || candidate.label || candidate.name || value;
                const label = candidate.label || longName || value;
                
                return {
                    value: value != null ? String(value) : '',
                    longName: longName != null ? String(longName) : '',
                    label: label != null ? String(label) : ''
                };
            }
            
            const strValue = candidate != null ? String(candidate) : '';
            return {
                value: strValue,
                longName: strValue,
                label: strValue
            };
        }).filter(candidate => candidate.value);
    }
    
    normalizeDivisionCandidates(candidates) {
        return candidates.map(candidate => {
            if (candidate && typeof candidate === 'object') {
                const value = candidate.value || candidate.code || candidate.id || candidate.name || '';
                const label = candidate.label || candidate.name || value;
                
                return {
                    value: value != null ? String(value) : '',
                    label: label != null ? String(label) : ''
                };
            }
            
            const strValue = candidate != null ? String(candidate) : '';
            return {
                value: strValue,
                label: strValue
            };
        }).filter(candidate => candidate.value);
    }
    
    getCandidateValue(candidate, groupName) {
        if ((groupName === 'league' || groupName === 'division') && candidate && typeof candidate === 'object') {
            return candidate.value;
        }
        return candidate;
    }
    
    getLeagueLongName(value) {
        if (!value) {
            return '';
        }
        return this.leagueMetadata.get(value) || '';
    }
    
    createSafeId(value) {
        if (typeof window !== 'undefined' && window.DomIdUtils && typeof window.DomIdUtils.toSafeDomIdToken === 'function') {
            return window.DomIdUtils.toSafeDomIdToken(value);
        }
        if (value === null || value === undefined) {
            return 'unknown';
        }
        let token = String(value).trim().replace(/[^A-Za-z0-9_-]+/g, '_');
        token = token.replace(/_+/g, '_').replace(/^_|_$/g, '');
        if (!token) {
            token = 'unknown';
        }
        if (!/^[A-Za-z_]/.test(token)) {
            token = 'id_' + token;
        }
        return token;
    }
    
    escapeAttribute(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }
    
    escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }
    
    /**
     * Get current state
     */
    getState() {
        return { ...this.currentState };
    }
    
    /**
     * Get selected values
     */
    getSelectedValues() {
        return { ...this.selectedValues };
    }
    
    /**
     * Get available candidates for a group
     */
    getCandidates(groupName) {
        return this.availableCandidates[groupName] || [];
    }
}