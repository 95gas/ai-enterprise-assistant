# Define version of python to use
FROM python:3.10-slim

# Install pinned uv.
COPY --from=ghcr.io/astral-sh/uv:0.11.10 /uv /uvx /bin/

# Set working directory and copy the content in it
WORKDIR /demo/server
COPY /server /demo/server
COPY /docker/server/DB_initialization.py /demo/server

# install curl and GnuPG 
RUN apt-get -y update && apt-get -y install curl && apt-get -y install gnupg

# Install CUDA
RUN curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
&& curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    tee /etc/apt/sources.list.d/nvidia-container-toolkit.list && apt-get update && apt-get install -y nvidia-container-toolkit

# Install native build dependencies
RUN apt-get -y update && apt-get upgrade -y && apt-get install -y build-essential python3-dev \
lcov valgrind

# install the cv2 dependencies
RUN apt-get -y update && apt-get install -y ffmpeg libsm6 libxext6

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1
ENV PATH="/demo/server/.venv/bin:$PATH"

# Enable CUDA
ENV NVIDIA_VISIBLE_DEVICES all
ENV NVIDIA_DRIVER_CAPABILITIES compute,utility

# Install locked server dependencies.
RUN uv sync --locked --no-dev
RUN python -m spacy download en_core_web_sm
RUN python -c "from unstructured.nlp.tokenize import download_nltk_packages; download_nltk_packages()"
RUN apt-get -y install poppler-utils
RUN apt install -y tesseract-ocr
RUN apt install -y libtesseract-dev

# Set port to use
EXPOSE 8080
