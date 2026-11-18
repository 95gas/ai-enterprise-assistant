FROM python:3.10-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.10 /uv /uvx /bin/

WORKDIR /demo/server
COPY server/ /demo/server/

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        python3-dev \
        ffmpeg \
        libsm6 \
        libxext6 \
        poppler-utils \
        tesseract-ocr \
        libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/demo/server/.venv/bin:$PATH"

RUN uv sync --locked --no-dev \
    && python -m spacy download en_core_web_sm \
    && python -c "from unstructured.nlp.tokenize import download_nltk_packages; download_nltk_packages()"

EXPOSE 8000
