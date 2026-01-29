FROM python:3.11-slim

WORKDIR /app

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

EXPOSE 8000

CMD ["python", "-m", "src.gateway.main"]
