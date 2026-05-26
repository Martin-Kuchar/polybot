FROM python:3.12-slim

WORKDIR /app

# Build tools needed by web3 / cryptography native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data logs

EXPOSE 8080

CMD ["python", "main.py"]
