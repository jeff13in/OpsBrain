FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic httpx prometheus-client "langgraph>=0.2,<1.0" "langchain-core>=0.3,<1.0" "langchain-google-genai>=2.0,<4.0"
COPY shared/         ./shared/
COPY orchestrator/   ./orchestrator/
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
