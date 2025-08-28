import os
import django
from django.core.wsgi import get_wsgi_application
from waitress import serve

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
django.setup()

application = get_wsgi_application()

if __name__ == '__main__':
    serve(application, host='0.0.0.0', port=80)