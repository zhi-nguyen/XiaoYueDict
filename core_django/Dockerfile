FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# System dependencies for PostgreSQL client + audio processing
RUN apt-get update && apt-get install -y \
    libpq-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Collect static files for Nginx to serve
RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8080

# Use Gunicorn for production (2 workers, matches 1 CPU allocation)
CMD ["gunicorn", "core_project.wsgi:application", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
