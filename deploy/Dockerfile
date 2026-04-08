FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY api ./api
COPY cmd ./cmd
COPY internal ./internal

RUN pip install --no-cache-dir .

CMD ["uvicorn", "internal.application:app", "--host", "0.0.0.0", "--port", "8000"]
