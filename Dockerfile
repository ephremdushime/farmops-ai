# FarmOps AI production image (Linux). Build: docker build -t farmops-ai .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/farmops
WORKDIR /srv/farmops
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py wsgi.py LICENSE ./
COPY templates/ templates/
COPY static/ static/
# Never bake in secrets or local state (see .dockerignore): mount a data volume
# and set FARMOPS_DB_PATH/FARMOPS_UPLOAD_DIR plus FLASK_SECRET_KEY/MODEL_API_KEY at run time.
# Long gunicorn timeout: voice transcription plus ffmpeg can legally take minutes
# on-request until P1-4/P2-5 moves transcription off the request thread.
EXPOSE 8000
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 600 wsgi:app"]
