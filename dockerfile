FROM python:3.13-slim

WORKDIR /api-status-aggregator

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install -e .
# Ensure Python can find our modules
ENV PYTHONPATH=/api-status-aggregator

CMD ["flask", "run", "--host=0.0.0.0"]