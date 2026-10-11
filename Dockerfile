# Promptya Dockerfile
# Multi-stage build for production deployment

# ---- Base stage ----
FROM python:3.12-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r promptya && useradd -r -g promptya promptya

WORKDIR /app

# ---- Builder stage ----
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Production stage ----
FROM base AS production

# Copy Python packages from builder
COPY --from=builder /root/.local /home/promptya/.local
ENV PATH="/home/promptya/.local/bin:${PATH}"

# Copy application code
COPY --chown=promptya:promptya . .

# Create directories for static/media
RUN mkdir -p /app/staticfiles /app/media && chown -R promptya:promptya /app/staticfiles /app/media

# Switch to non-root user
USER promptya

# Collect static files
RUN python manage.py collectstatic --noinput --clear

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/', timeout=5)" || exit 1

# Run with gunicorn
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]