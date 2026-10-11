FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi uvicorn pydantic \
    "langchain-core>=0.3,<1.0" \
    "langchain-google-genai>=2.0,<4.0" \
    "langgraph>=0.2,<1.0" \
    "psycopg[binary]>=3.2,<4.0" \
    httpx kafka-python

COPY shared/ ./shared/
COPY agents/rag/ ./rag/
ENV PYTHONPATH=/app

EXPOSE 8001
CMD ["uvicorn", "rag.main:app", "--host", "0.0.0.0", "--port", "8001"]
