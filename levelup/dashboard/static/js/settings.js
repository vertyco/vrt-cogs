document.addEventListener('alpine:init', () => {
    Alpine.data('levelUpSettings', (data = {}) => ({
        // DATA INITIALIZATION
        settings: data.settings || {},
        users: data.users || [],
        emojis: data.emojis || [],
        roles: data.roles || [],
        newLevelRole: { level: 1, role: '' },

        // METHODS
        async saveSettings(event) {
            if (event) event.preventDefault();
            console.log("Saving settings:", this.settings);
            try {
                // Get CSRF token from meta tag
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;

                if (!csrfToken) {
                    console.error("CSRF token not found");
                    alert("CSRF token not found. Please refresh the page and try again.");
                    return;
                }

                const response = await fetch(window.location.href, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken  // Changed from X-CSRF-Token to X-CSRFToken
                    },
                    credentials: 'same-origin',  // Added to ensure cookies are sent
                    body: JSON.stringify(this.settings)
                });

                const result = await response.json();
                if (result.status === 0) {
                    alert(result.success_message);
                } else {
                    alert(`Error: ${result.error_message}`);
                }
            } catch (error) {
                console.error("Error saving settings:", error);
                alert("An error occurred while saving settings.");
            }
        }
    }));
});
