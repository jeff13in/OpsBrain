FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic httpx kafka-python
COPY shared/            ./shared/
COPY agents/code/       ./agents/code/
ENV PYTHONPATH=/app
EXPOSE 8004
CMD ["uvicorn", "agents.code.main:app", "--host", "0.0.0.0", "--port", "8004"]
