import os
import sys
import logging
import django
from django.core.wsgi import get_wsgi_application
from waitress import serve

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('django_server.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stanum_web.settings')

# Setup Django
django.setup()

# Get WSGI application
application = get_wsgi_application()

if __name__ == '__main__':
    try:
        # Production settings for Waitress
        serve(
            application,
            host='127.0.0.1',  # Changed from 0.0.0.0 for security
            port=8000,         # Changed from 80 - let reverse proxy handle 80/443
            threads=6,         # Adjust based on your server capacity
            connection_limit=1000,
            cleanup_interval=30,
            channel_timeout=120,
            log_socket_errors=True,
            url_scheme='https'  # Important for Cloudflare SSL
        )
    except Exception as e:
        logging.error(f"Server failed to start: {e}")
        sys.exit(1)