"""
Main entry point for the API Status Aggregator application.
"""

import logging
import os
from dotenv import load_dotenv

from presentation.web.app import app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('status_aggregator.log')
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Main application entry point."""
    try:
        # Load environment variables from .env file if present
        load_dotenv()
        

        
        # Get port from environment or use default
        port = int(os.environ.get('PORT', 5000))
        debug = os.environ.get('FLASK_DEBUG', '0') == '1'
        
        # Run the application
        app.run(host='0.0.0.0', port=port, debug=debug)
        
    except Exception as e:
        logger.exception(f"Application failed to start: {str(e)}")


if __name__ == '__main__':
    main()