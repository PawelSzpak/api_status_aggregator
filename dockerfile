FROM python:3.13-slim

WORKDIR /api_status_aggregator

RUN pip install --no-cache-dir hatchling

# Copy requirements first for better layer caching
COPY pyproject.toml setup.py ./
RUN pip install -e ".[dev]"

# Copy the rest of the application
COPY . .

# Make the entrypoint script executable
RUN chmod +x docker-entrypoint.py

# Environment variables
ENV FLASK_APP=presentation.web.app:app
ENV FLASK_ENV=development
ENV FLASK_DEBUG=1
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

# Use our custom entrypoint to initialize components before starting Flask
ENTRYPOINT ["./docker-entrypoint.py"]
CMD ["flask", "run", "--host=0.0.0.0"]