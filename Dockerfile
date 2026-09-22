FROM python:3.12-slim

WORKDIR /app
COPY . /app/embedded_framework
RUN pip install --no-cache-dir "/app/embedded_framework[dev]"

ENV PYTHONPATH=/app
CMD ["python", "-m", "pytest", "-q", "/app/embedded_framework/tests"]
