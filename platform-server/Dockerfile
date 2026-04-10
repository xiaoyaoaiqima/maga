FROM python:3.12-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY raap_trace_sdk/ ./raap_trace_sdk/
COPY raap_llm_sdk/ ./raap_llm_sdk/

RUN PIP_DEFAULT_TIMEOUT=120 pip install --retries 10 --no-cache-dir --user -r requirements.txt && \
    PIP_DEFAULT_TIMEOUT=120 pip install --retries 10 --no-cache-dir --user ./raap_trace_sdk && \
    PIP_DEFAULT_TIMEOUT=120 pip install --retries 10 --no-cache-dir --user ./raap_llm_sdk

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 10001 appuser

COPY --from=builder /root/.local /home/appuser/.local
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY raap_trace_sdk/ ./raap_trace_sdk/
COPY raap_llm_sdk/ ./raap_llm_sdk/

RUN mkdir -p /app/logs && chown -R appuser:appuser /app /home/appuser/.local

ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TZ=Asia/Shanghai

USER appuser

EXPOSE 5100

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-5100}"]
