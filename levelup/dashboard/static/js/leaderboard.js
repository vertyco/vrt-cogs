document.addEventListener('alpine:init', () => {
    Alpine.data('leaderBoard', (data = {}) => ({
        // DATA INITIALIZATION
        searchquery: data.query,
        page: data.page,
        perPage: 100,
        users: data.users,
        sortStat: data.stat,  // Can be exp, messages, voice, stars
        sortOptions: ['exp', 'messages', 'voice', 'stars'],
        sortMenuOpen: false,
        currentUserId: data.user_id,
        total: data.total,
        open: false,  // Whether dropdown is open
        trippyMode: false,
        trippyEnabled: false,
        typingTimer: null,

        // USER PAGINATION FUNCTIONS
        getPageUsers() {
            console.log("Fetching users for page", this.page);
            console.log(`There are ${this.users.length} users in total`);
            if (this.searchquery === "") {
                return this.users.slice((this.page - 1) * this.perPage, this.page * this.perPage);
            } else {
                // Need to filter users based on search query
                const filteredUsers = this.filterUsers();
                return filteredUsers.slice((this.page - 1) * this.perPage, this.page * this.perPage);
            }
        },
        nextPage() {
            if (this.page * this.perPage < this.users.length) {
                this.page++;
                this.updateUrlParam('page', this.page);
            }
        },
        prevPage() {
            if (this.page > 1) {
                this.page--;
                this.updateUrlParam('page', this.page);
            }
        },
        setPerPage(value) {
            if (this.perPage !== value) {
                this.perPage = value;
                this.page = 1; // Reset to first page when changing items per page
                localStorage.setItem('leaderBoardPerPage', value);
                this.updateUrlParam('perPage', value);
                this.getPageUsers();
            }
        },
        getPageCount() {
            if (this.searchquery === "") {
                return Math.ceil(this.users.length / this.perPage);
            } else {
                // Need to filter users based on search query
                const filteredUsers = this.filterUsers();
                return Math.ceil(filteredUsers.length / this.perPage);
            }
        },

        // URL AND BROWSER HISTORY MANAGEMENT
        updateUrlParam(param, value) {
            // Get current URL and parse its query parameters
            const url = new URL(window.location.href);
            // Update or add the parameter
            url.searchParams.set(param, value);
            // Update browser history without refreshing
            history.pushState({}, '', url.toString());
        },

        // SEARCH AND FILTERING
        filterUsers() {
            // Filter users based on search query
            if (this.searchquery === "") {
                return this.users;
            }
            return this.users.filter(user => user.name.toLowerCase().includes(this.searchquery.toLowerCase()));
        },

        // TRIPPY MODE FUNCTIONALITY
        toggleTrippy() {
            this.trippyEnabled = !this.trippyEnabled;
            localStorage.setItem('leaderBoardTrippy', this.trippyEnabled);

            // If we're enabling it, immediately show effects
            if (this.trippyEnabled) {
                this.trippyMode = true;
            } else {
                this.trippyMode = false;
            }
        },

        handleTyping() {
            if (this.trippyEnabled) {
                this.trippyMode = true;

                // Clear previous timer
                if (this.typingTimer) {
                    clearTimeout(this.typingTimer);
                }

                // Set a timer to disable trippy mode after user stops typing
                this.typingTimer = setTimeout(() => {
                    this.trippyMode = false;
                }, 1500);
            }
        },

        // INITIALIZATION AND LOCAL STORAGE
        init() {
            console.log(`Leaderboard initialized starting on page ${this.page}`);
            this.getPageUsers();

            // Store the URL-provided page (if any)
            const urlProvidedPage = this.page;

            // Only use localStorage page if no page was specified in the URL (or was specified as 1)
            if (!urlProvidedPage || urlProvidedPage === 1) {
                const storedPage = localStorage.getItem('leaderBoardPage');
                if (storedPage !== null) {
                    this.page = parseInt(storedPage) || 1;
                }
            }

            // Retrieve stored values if available
            const storedSearch = localStorage.getItem('leaderBoardSearch');
            if (storedSearch !== null) {
                this.searchquery = storedSearch;
            }

            // Get stored perPage preference
            const storedPerPage = localStorage.getItem('leaderBoardPerPage');
            if (storedPerPage !== null) {
                this.perPage = parseInt(storedPerPage) || 100;
            }

            // Load trippy preference
            const storedTrippy = localStorage.getItem('leaderBoardTrippy');
            if (storedTrippy !== null) {
                this.trippyEnabled = storedTrippy === 'true';
                // If trippy is enabled at load, show effect briefly
                if (this.trippyEnabled) {
                    this.trippyMode = true;
                    setTimeout(() => {
                        if (!this.searchquery) { // Only turn off if not actively searching
                            this.trippyMode = false;
                        }
                    }, 1500);
                }
            }

            const storedAutoTrippy = localStorage.getItem('leaderBoardAutoTrippy');
            if (storedAutoTrippy !== null) {
                this.autoTrippy = storedAutoTrippy === 'true';
            } else {
                // Default to true for auto-trippy
                this.autoTrippy = true;
            }

            // WATCHERS
            // Watch for changes to store them
            this.$watch('searchquery', (newquery, oldquery) => {
                console.log(`Search query changed from ${oldquery} to ${newquery}`);
                localStorage.setItem('leaderBoardSearch', newquery);
                this.page = 1;
                localStorage.setItem('leaderBoardPage', '1');
                this.getPageUsers();

                // Call typing handler when search query changes
                this.handleTyping();
            });
            this.$watch('page', (newpage, oldpage) => {
                localStorage.setItem('leaderBoardPage', newpage);
            });
        },
    }));
});
