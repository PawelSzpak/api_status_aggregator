FROM python:3.13-slim

WORKDIR /api_status_aggregator

RUN pip install --no-cache-dir hatchling

# Copy requirements first for better layer caching
COPY pyproject.toml setup.py ./
RUN pip install -e .

# Copy the rest of the application
COPY . .

# Make the entrypoint script executable
RUN chmod +x docker-entrypoint.py

# Environment variables
ENV FLASK_ENV=production
ENV FLASK_DEBUG=0
ENV PYTHONUNBUFFERED=1

# Health check for Railway
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1
    
EXPOSE 5000

# Use our custom entrypoint
ENTRYPOINT ["python", "./docker-entrypoint.py"]