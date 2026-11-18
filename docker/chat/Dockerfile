# Chat Microservice Dockerfile
# Shares the same base as the monolith but runs the chat-only FastAPI entry point.
FROM python:3.10-slim

# Install pinned uv.
COPY --from=ghcr.io/astral-sh/uv:0.11.10 /uv /uvx /bin/

# Set working directory and copy the content in it
WORKDIR /demo/server
COPY /server /demo/server

# install curl and GnuPG 
RUN apt-get -y update && apt-get -y install curl && apt-get -y install gnupg

# Install build dependencies
RUN apt-get -y update && apt-get upgrade -y && apt-get install -y build-essential python3-dev \
lcov valgrind

# install the cv2 dependencies
RUN apt-get -y update && apt-get install -y ffmpeg libsm6 libxext6

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/demo/server/.venv/bin:$PATH"

# Install locked server dependencies.
RUN uv sync --locked --no-dev
RUN python -m spacy download en_core_web_sm

# Chat service port
ENV CHAT_SERVICE_PORT=8000
EXPOSE 8000

CMD ["python", "-m", "src.services.chat_service"]
