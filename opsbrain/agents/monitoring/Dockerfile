FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn pydantic httpx kafka-python

COPY shared/ ./shared/
COPY agents/monitoring/*.py ./monitoring/
ENV PYTHONPATH=/app

EXPOSE 8002
CMD ["uvicorn", "monitoring.main:app", "--host", "0.0.0.0", "--port", "8002"]
