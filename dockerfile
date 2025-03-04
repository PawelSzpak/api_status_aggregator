FROM python:3.13-slim

WORKDIR /api_status_aggregator

RUN pip install --no-cache-dir hatchling

COPY pyproject.toml setup.py ./
RUN pip install -e ".[dev]"

COPY . .


ENV FLASK_APP=presentation.web.app:app
ENV FLASK_ENV=development
ENV FLASK_DEBUG=1
ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["flask", "run", "--host=0.0.0.0"]