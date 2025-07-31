// Dashboard.js - API Status Aggregator
// Handles the dynamic functionality of the dashboard

document.addEventListener('DOMContentLoaded', function() {
    // Initialize the dashboard with the initial data
    updateDashboard(initialData);
    
    // Set up event source for real-time updates
    setupEventSource();
    
    // Set up filter event listeners
    setupFilters();
    
    // Set up premium link
    document.getElementById('premium-link').addEventListener('click', function(e) {
        e.preventDefault();
        alert('Premium subscription coming soon! Enjoy ad-free experience and customizable dashboards.');
    });
});

// Set up Server-Sent Events for real-time updates
function setupEventSource() {
    const eventSource = new EventSource('/api/status/stream');
    
    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        updateDashboard(data);
    };
    
    eventSource.onerror = function() {
        console.error('EventSource failed. Reconnecting in 5 seconds...');
        eventSource.close();
        setTimeout(setupEventSource, 5000);
    };
}

// Update the dashboard with new data
function updateDashboard(data) {
    if (data.error) {
        console.error('Error fetching data:', data.error);
        return;
    }
    
    // Update last updated time
    document.getElementById('last-updated-time').textContent = formatDateTime(new Date(data.last_updated));
    
    // Update category tiles
    updateCategoryTiles(data.categories);
    
    // Update provider cards
    updateProviderCards(data.providers);
    
    // Apply current filters
    applyFilters();
}

// Update the category summary tiles
function updateCategoryTiles(categories) {
    const categoryTilesContainer = document.getElementById('category-tiles');
    categoryTilesContainer.innerHTML = '';
    
    for (const [category, status] of Object.entries(categories)) {
        const tile = document.createElement('div');
        tile.className = 'category-tile';
        
        const statusClass = getStatusClass(status);
        
        tile.innerHTML = `
            <h3>${category}</h3>
            <div>
                <span class="status-indicator ${statusClass}"></span>
                <span>${status}</span>
            </div>
        `;
        
        categoryTilesContainer.appendChild(tile);
    }
}

// Update the provider cards
function updateProviderCards(providers) {
    const providersGrid = document.getElementById('providers-grid');
    providersGrid.innerHTML = '';
    
    providers.forEach(provider => {
        const card = document.createElement('div');
        card.className = 'provider-card clickable-card';
        card.dataset.category = provider.category;
        card.dataset.status = provider.status;
        card.dataset.statusUrl = provider.status_url;
        
        const statusClass = getStatusClass(provider.status);
        
        card.innerHTML = `
            <h3>
                ${provider.name}
                <span class="category-badge">${provider.category}</span>
                <span class="external-link-icon">
                    <i class="fas fa-external-link-alt"></i>
                </span>
            </h3>
            <div class="status-badge ${statusClass}">${provider.status}</div>
            <div class="message">${provider.message || 'No additional information available'}</div>
            <div class="timestamp">Last checked: ${formatDateTime(new Date(provider.last_checked))}</div>
        `;
        
        // Add click handler to open status page
        card.addEventListener('click', function() {
            const statusUrl = card.dataset.statusUrl;
            if (statusUrl) {
                window.open(statusUrl, '_blank', 'noopener,noreferrer');
            }
        });
        
        // Add keyboard accessibility
        card.setAttribute('tabindex', '0');
        card.setAttribute('role', 'button');
        card.setAttribute('aria-label', `View ${provider.name} status page`);
        
        card.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                const statusUrl = card.dataset.statusUrl;
                if (statusUrl) {
                    window.open(statusUrl, '_blank', 'noopener,noreferrer');
                }
            }
        });
        
        providersGrid.appendChild(card);
    });
}

// Set up filter event listeners
function setupFilters() {
    const categoryFilter = document.getElementById('category-filter');
    const statusFilter = document.getElementById('status-filter');
    
    categoryFilter.addEventListener('change', applyFilters);
    statusFilter.addEventListener('change', applyFilters);
}

// Apply filters to provider cards
function applyFilters() {
    const categoryFilter = document.getElementById('category-filter').value;
    const statusFilter = document.getElementById('status-filter').value;
    
    const cards = document.querySelectorAll('.provider-card');
    
    cards.forEach(card => {
        const cardCategory = card.dataset.category;
        const cardStatus = card.dataset.status;
        
        const categoryMatch = categoryFilter === 'all' || cardCategory === categoryFilter;
        const statusMatch = statusFilter === 'all' || cardStatus === statusFilter;
        
        if (categoryMatch && statusMatch) {
            card.style.display = '';
        } else {
            card.style.display = 'none';
        }
    });
}

// Helper function to get status class
function getStatusClass(status) {
    switch(status.toLowerCase()) {
        case 'operational':
            return 'status-operational';
        case 'degraded':
            return 'status-degraded';
        case 'outage':
            return 'status-outage';
        default:
            return 'status-unknown';
    }
}

// Helper function to format date and time
function formatDateTime(date) {
    return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    }).format(date);
}
