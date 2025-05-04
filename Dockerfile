FROM python:3.11-slim
WORKDIR /watchdigest

COPY . /watchdigest

RUN apt-get update && \
    apt-get install -y \
        curl \
        git \
        gnupg \
        ca-certificates && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(grep VERSION_CODENAME /etc/os-release | cut -d= -f2) stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y docker-ce-cli && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5151

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD curl -f http://localhost:5151/health || exit 1

CMD ["python3", "watchdigest.py"]

