release: python app.py --migrate
web: gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 600 wsgi:app
