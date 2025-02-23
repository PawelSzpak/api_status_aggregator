from flask import Flask

def create_app() -> Flask:
    """Create and configure the Flask application instance."""
    app = Flask(__name__)
    
    @app.route('/health')
    def health_check():
        return {'status': 'healthy'}
    
    return app

# Create the application instance
app = create_app()