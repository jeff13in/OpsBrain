FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic prometheus-client boto3 kubernetes httpx kafka-python
COPY shared/            ./shared/
COPY agents/infra/      ./agents/infra/
ENV PYTHONPATH=/app
EXPOSE 8003
CMD ["uvicorn", "agents.infra.main:app", "--host", "0.0.0.0", "--port", "8003"]
