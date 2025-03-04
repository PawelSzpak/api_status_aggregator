from flask import Flask, render_template, jsonify, Response
import json
import time
from typing import Dict, Iterator, Any
import logging
from datetime import datetime, timezone

from application.services.category_manager import CategoryManager
from infrastructure.providers.provider_factory import create_all_providers
from domain.enums import ServiceCategory, StatusLevel

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
    
    @app.route('/')
    def dashboard():
        """Render the main dashboard view."""
        return render_template(
            'dashboard.html',
            categories=ServiceCategory,
            status_levels=StatusLevel,
            initial_data=json.dumps(_get_dashboard_data())
        )
    
    @app.route('/api/status')
    def get_status():
        """API endpoint for status updates."""
        return jsonify(_get_dashboard_data())
    
    @app.route('/api/status/stream')
    def stream_status():
        """Server-Sent Events endpoint for real-time status updates."""
        def event_stream() -> Iterator[str]:
            """Generator for SSE events."""
            while True:
                # Get the current status data
                data = _get_dashboard_data()
                
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
    
    def _get_dashboard_data() -> Dict[str, Any]:
        """
        Get the current dashboard data.
        
        Returns:
            Dict[str, Any]: Dashboard data including provider statuses and category summaries
        """
        try:
            # Get all current statuses
            all_statuses = category_manager.get_all_statuses()
            
            # Get category summaries
            category_summaries = category_manager.get_overall_summary()
            
            # Format the response
            data = {
                'providers': [
                    {
                        'name': status.provider_name,
                        'category': status.category.value,
                        'status': status.status_level.value,
                        'message': status.message,
                        'last_checked': status.last_checked.isoformat()
                    }
                    for status in all_statuses
                ],
                'categories': {
                    category.value: status_level.value
                    for category, status_level in category_summaries.items()
                },
                'last_updated': category_manager.last_update_time.isoformat()
            }
            
            return data
        except Exception as e:
            logger.error(f"Error generating dashboard data: {str(e)}")
            return {
                'error': 'Failed to retrieve status data',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    return app

# Create the application instance
app = create_app()