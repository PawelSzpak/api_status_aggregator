from flask import Flask, render_template, jsonify, Response
import json
import time
from typing import Dict, Iterator, Any
import logging
from datetime import datetime, timezone

from application.services.category_manager import CategoryManager
from infrastructure.providers.provider_factory import create_all_providers
from infrastructure.scheduler import scheduler
from domain.enums import ServiceCategory, StatusLevel

# Don't shutdown scheduler on every request teardown
# Instead, register a shutdown handler for when the app itself shuts down
import atexit
atexit.register(lambda: scheduler.shutdown())

logger = logging.getLogger(__name__)

def create_app() -> Flask:
    """Create and configure the Flask application instance."""
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    # Initialize the category manager and register all providers
    category_manager = CategoryManager()
    for provider in create_all_providers():
        category_manager.register_provider(provider)
    
    # Set up scheduler with the category manager
    scheduler.set_category_manager(category_manager)
    
    # Register before_first_request handler to start the scheduler
    @app.before_request
    def ensure_scheduler_running():
        """Ensure the scheduler is running before handling requests."""
        if not hasattr(app, 'scheduler_started'):
            try:
                # Start with a 5-minute (300 second) check interval
                scheduler.start(check_interval=300)
                app.scheduler_started = True
                logger.info("Scheduler started successfully")
            except Exception as e:
                logger.error(f"Failed to start scheduler: {str(e)}")
    
    # Register teardown handler to shutdown the scheduler
    @app.teardown_appcontext
    def shutdown_scheduler(exception=None):
        """Shutdown the scheduler when the application context tears down."""
        scheduler.shutdown()
    
    @app.route('/')
    def dashboard():
        """Render the main dashboard view."""
        return render_template(
            'dashboard.html',
            categories=ServiceCategory,
            status_levels=StatusLevel,
            initial_data=json.dumps(scheduler.get_latest_data())
        )
    
    @app.route('/api/status')
    def get_status():
        """API endpoint for status updates."""
        return jsonify(scheduler.get_latest_data())
    
    @app.route('/api/status/refresh', methods=['POST'])
    def refresh_status():
        """API endpoint to force a status refresh."""
        return jsonify(scheduler.force_update())
    
    @app.route('/api/status/stream')
    def stream_status():
        """Server-Sent Events endpoint for real-time status updates."""
        def event_stream() -> Iterator[str]:
            """Generator for SSE events."""
            while True:
                # Get the latest data from the scheduler
                data = scheduler.get_latest_data()
                
                # Format as SSE event
                yield f"data: {json.dumps(data)}\n\n"
                
                # Wait before sending the next update
                time.sleep(10)  # 10-second update interval
        
        return Response(
            event_stream(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive'
            }
        )
    
    @app.route('/health')
    def health_check():
        """Health check endpoint."""
        return {'status': 'healthy', 'timestamp': datetime.now(timezone.utc).isoformat()}
    
    return app

# Create the application instance
app = create_app()