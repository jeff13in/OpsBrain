FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi uvicorn pydantic prometheus-client httpx kafka-python \
    "langchain-core>=0.3,<1.0" \
    "langchain-openai>=0.3,<0.4" \
    "langchain-google-genai>=2.0,<4.0" \
    "langgraph>=0.2,<1.0" \
    "psycopg[binary]>=3.2,<4.0"

COPY shared/ ./shared/
COPY agents/rag/ ./rag/

EXPOSE 8001
CMD ["uvicorn", "rag.main:app", "--host", "0.0.0.0", "--port", "8001"]
