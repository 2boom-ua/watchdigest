FROM python:3.11-slim
WORKDIR /watchdigest

COPY . /watchdigest

RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5151

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD curl -f http://localhost:5151/health || exit 1

CMD ["python3", "watchdigest.py"]

