FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source (kb/ is mounted at runtime via docker-compose volume)
COPY . .

# Placeholder so KB_DIR exists even before the volume is mounted
RUN mkdir -p /kb

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -sf http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "main.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false", \
     "--theme.base=dark"]
