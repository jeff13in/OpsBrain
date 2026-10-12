FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings httpx prometheus-client kafka-python "psycopg[binary]>=3.2,<4.0" "cryptography>=43,<47" "langgraph>=0.2,<1.0" "langchain-core>=0.3,<1.0" "langchain-openai>=0.3,<0.4"
COPY shared/         ./shared/
COPY orchestrator/   ./orchestrator/
COPY web/public/index.html web/public/styles.css web/public/app.js web/public/ui.js web/public/demo.js web/public/chat.js web/public/monitoring.js web/public/history.js web/public/api.js web/public/auth.js web/public/route-guards.js web/public/workspace.js web/public/persistence.js web/public/mark.svg ./web/public/
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
