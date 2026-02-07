FROM python:3.11-slim

WORKDIR /app

# System deps (healthcheck uses curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ src/
COPY config.yaml .

# Environment
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV WORKER_MANAGER_HOST=host.docker.internal
ENV WORKER_HOST=host.docker.internal

EXPOSE 8200

CMD ["python", "-m", "src.gateway.main"]
