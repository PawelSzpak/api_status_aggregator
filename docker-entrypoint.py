"""
Production entry point for the API Status Aggregator application.
"""

import logging
import os
import sys
from dotenv import load_dotenv

def configure_production_logging():
    """Configure production-grade logging for Gunicorn deployment."""
    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # Reduce third-party library noise
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    logging.getLogger('gunicorn.error').setLevel(logging.INFO)
    logging.getLogger('gunicorn.access').setLevel(logging.INFO)

logger = logging.getLogger(__name__)

def main():
    """Production application entry point with Gunicorn WSGI server."""
    try:
        load_dotenv()
        configure_production_logging()
        
        port = int(os.environ.get('PORT', 5000))
        host = os.environ.get('HOST', '0.0.0.0')
        workers = int(os.environ.get('GUNICORN_WORKERS', 2))
        log_level = os.environ.get('LOG_LEVEL', 'INFO').lower()
        
        logger.info(f"Starting API Status Aggregator with Gunicorn on {host}:{port}")
        logger.info(f"Environment: {os.environ.get('FLASK_ENV', 'production')}")
        logger.info(f"Workers: {workers}")
        
        from gunicorn.app.wsgiapp import WSGIApplication
        
        class ProductionGunicornApp(WSGIApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()
            
            def load_config(self):
                for key, value in self.options.items():
                    if key in self.cfg.settings and value is not None:
                        self.cfg.set(key.lower(), value)
            
            def load(self):
                return self.application
        
        gunicorn_config = {
            'bind': f'{host}:{port}',
            'workers': workers,
            'worker_class': 'sync',
            'worker_connections': 1000,
            'max_requests': 1000,
            'max_requests_jitter': 100,
            'timeout': int(os.environ.get('GUNICORN_TIMEOUT', 30)),
            'keepalive': int(os.environ.get('GUNICORN_KEEPALIVE', 2)),
            'preload_app': True,
            'access_log_format': '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s',
            'accesslog': '-',
            'errorlog': '-',
            'loglevel': log_level,
            'capture_output': True,
            'enable_stdio_inheritance': True
        }
        
        from presentation.web.app import app
        
        ProductionGunicornApp(app, gunicorn_config).run()
        
    except Exception as e:
        logger.exception(f"Application failed to start: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()