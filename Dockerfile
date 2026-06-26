# Stage 1: build React frontend
FROM node:20-slim AS frontend
WORKDIR /app
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm ci
COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# Stage 2: Python backend + Ollama + baked model + built frontend
FROM python:3.11-slim
WORKDIR /app

# System deps needed for Ollama install and health-check wait
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates zstd \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Bake llama3.2:3b into the image layer so there's no pull on cold start
RUN ollama serve & \
    until curl -sf http://localhost:11434/ > /dev/null 2>&1; do sleep 1; done && \
    ollama pull llama3.2:3b

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /app/frontend/dist ./frontend/dist

RUN mkdir -p uploads data

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 7860
CMD ["/start.sh"]
