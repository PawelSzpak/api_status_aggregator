"""
Production entry point for the API Status Aggregator application.
"""

import logging
import os
import signal
import sys
from dotenv import load_dotenv
from presentation.web.app import app
from infrastructure.scheduler import scheduler

def configure_production_logging():
    """Configure production-grade logging."""
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),  # Railway captures stdout
        ]
    )
    
    # Reduce noise from third-party libraries
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)

def setup_signal_handlers():
    """Set up graceful shutdown signal handlers."""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        try:
            scheduler.shutdown()
            logger.info("Scheduler shutdown completed")
        except Exception as e:
            logger.error(f"Error during scheduler shutdown: {e}")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

logger = logging.getLogger(__name__)

def main():
    """Production application entry point."""
    try:
        # Load environment variables
        load_dotenv()
        
        # Configure production logging
        configure_production_logging()
        
        # Set up signal handlers for graceful shutdown
        setup_signal_handlers()
        
        # Get configuration from environment
        port = int(os.environ.get('PORT', 5000))
        host = os.environ.get('HOST', '0.0.0.0')
        debug = os.environ.get('FLASK_DEBUG', '0') == '1'
        
        # Ensure we're not in debug mode in production
        if os.environ.get('FLASK_ENV') == 'production' and debug:
            logger.warning("Debug mode disabled in production environment")
            debug = False
        
        logger.info(f"Starting API Status Aggregator on {host}:{port}")
        logger.info(f"Environment: {os.environ.get('FLASK_ENV', 'development')}")
        logger.info(f"Debug mode: {debug}")
        
        # Run the application
        app.run(
            host=host, 
            port=port, 
            debug=debug,
            threaded=True,  # Enable threading for better concurrency
            use_reloader=False  # Disable reloader in production
        )
        
    except Exception as e:
        logger.exception(f"Application failed to start: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()