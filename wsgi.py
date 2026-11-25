"""Production WSGI entry point (gunicorn, waitress).

Importing this module has no side effects: run `python app.py --migrate`
first to create or upgrade the database, then serve with e.g.
`gunicorn --bind 0.0.0.0:8000 wsgi:app`.
"""

from app import app as application  # noqa: F401

app = application
