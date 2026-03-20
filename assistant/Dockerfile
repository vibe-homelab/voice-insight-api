FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY config.yaml .
COPY src/ src/

EXPOSE 8800

CMD ["python", "-m", "src.gateway.main"]
