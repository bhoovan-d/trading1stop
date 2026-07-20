# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Build Backend Environment
FROM python:3.12-slim AS backend-builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
# Install dependencies into system Python
RUN uv pip install --system --no-cache-dir -r pyproject.toml

# Stage 3: Final Production Image
FROM python:3.12-slim
WORKDIR /app

# Copy system packages installed by uv in backend-builder
COPY --from=backend-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy source code
COPY src/ src/
COPY sources.yaml pyproject.toml ./

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Ensure data directory exists (for fallback SQLite / newsletters)
RUN mkdir -p /app/data

# Run the server. We use $PORT if Railway provides it, otherwise fallback to 8080.
CMD sh -c "uvicorn alpha_engine.api.app:app --host 0.0.0.0 --port ${PORT:-8080}"
