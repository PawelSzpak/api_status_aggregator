FROM python:3.13-slim

WORKDIR /api_status_aggregator

RUN pip install --no-cache-dir hatchling

COPY pyproject.toml setup.py ./
RUN pip install -e .

COPY . .


ENV FLASK_APP=presentation.web.app:app
ENV FLASK_ENV=development
ENV FLASK_DEBUG=1

CMD ["flask", "run", "--host=0.0.0.0"]