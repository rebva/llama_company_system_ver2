FROM python:3.10

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && \
    apt-get install -y sqlite3 && \
    rm -rf /var/lib/apt/lists/*
COPY . .

ENV API_KEY=CHANGE_ME

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
