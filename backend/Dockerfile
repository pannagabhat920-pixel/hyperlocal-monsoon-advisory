FROM python:3.11-slim

# Install uv
RUN pip install uv

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

# Install core deps via uv (no torch CUDA)
RUN uv pip install --system -e .

# Install CPU-only torch separately (avoids 2.5 GB CUDA download)
RUN uv pip install --system \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    "torch>=2.0.0"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
