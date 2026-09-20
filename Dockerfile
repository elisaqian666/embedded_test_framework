FROM python:3.12-slim

WORKDIR /app
COPY . /app/embedded_framework
RUN pip install --no-cache-dir pytest==9.1.1 requests==2.34.2 python-jenkins==1.8.3

ENV PYTHONPATH=/app
CMD ["python", "-m", "pytest", "-q", "/app/embedded_framework/tests"]
