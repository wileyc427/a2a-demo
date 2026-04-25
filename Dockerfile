FROM python:3.12-slim

WORKDIR /app

# Install tracentic SDK from source (includes A2A integration)
COPY tracentic-python/ ./tracentic-python/
RUN pip install --no-cache-dir ./tracentic-python/

# Install demo dependencies
COPY tracentic/a2a-demo/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy demo source
COPY tracentic/a2a-demo/ ./demo/

# shared/ is imported as a top-level package from all agent and orchestrator scripts
ENV PYTHONPATH=/app/demo
ENV PYTHONUNBUFFERED=1
