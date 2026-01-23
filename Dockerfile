FROM python:3.11-slim

LABEL maintainer="RHOAI QE Team"
LABEL description="TFA - AI-powered Test Failure Analyzer"
LABEL version="2.0.0"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY main.py .
COPY config.example.yaml ./config.example.yaml
COPY classification_rules.yaml ./classification_rules.yaml

# Set ownership
RUN chown -R appuser:appuser /app
USER appuser

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Health check for API mode
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: Run API server
# Override with: docker run tfa-api python main.py analyze-component ...
EXPOSE 8000
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
