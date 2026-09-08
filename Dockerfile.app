# Demo web app (FastAPI). The Java EDC connector uses the other Dockerfile.
FROM python:3.13-slim
WORKDIR /app

COPY pyproject.toml README.md ./
COPY demo ./demo

RUN pip install --no-cache-dir .

EXPOSE 8000
# Run from /app so ./demo (with static/index.html) is importable.
CMD ["uvicorn", "demo.app:app", "--host", "0.0.0.0", "--port", "8000"]
