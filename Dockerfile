FROM python:3.12-slim

WORKDIR /app
COPY . /app/embedded_test_framework
RUN pip install --no-cache-dir "/app/embedded_test_framework[dev]"

ENV PYTHONPATH=/app
CMD ["python", "-m", "pytest", "-q", "/app/embedded_test_framework/tests"]
