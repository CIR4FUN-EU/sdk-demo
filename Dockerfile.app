# Demo web app (FastAPI). The Java EDC connector uses the other Dockerfile.
FROM python:3.13-slim
WORKDIR /app

# git: needed to pip-install the EDC client straight from GitHub.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY demo ./demo

# dpp-sdk/fastapi/uvicorn/dotenv come from pyproject; edc-client isn't on PyPI yet.
RUN pip install --no-cache-dir . \
    "git+https://github.com/CIR4FUN-EU/python-edc-client"

EXPOSE 8000
# Run from /app so ./demo (with static/index.html) is importable.
CMD ["uvicorn", "demo.app:app", "--host", "0.0.0.0", "--port", "8000"]
