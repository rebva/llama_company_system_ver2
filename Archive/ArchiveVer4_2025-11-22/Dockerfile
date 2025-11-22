FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV OLLAMA_HOST=http://ollama_eguchi:11434
ENV API_KEY=CHANGE_ME

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
