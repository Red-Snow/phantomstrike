FROM python:3.12-slim

LABEL maintainer="Farman Ullah Khan"
LABEL description="PhantomStrike AI — MCP Cybersecurity Framework"

# Install common security tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    nmap \
    nikto \
    sqlmap \
    hydra \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Go-based tools
RUN curl -sSL https://github.com/projectdiscovery/nuclei/releases/latest/download/nuclei_linux_amd64.zip -o /tmp/nuclei.zip \
    && unzip /tmp/nuclei.zip -d /usr/local/bin/ \
    && rm /tmp/nuclei.zip \
    && curl -sSL https://github.com/projectdiscovery/subfinder/releases/latest/download/subfinder_linux_amd64.zip -o /tmp/subfinder.zip \
    && unzip /tmp/subfinder.zip -d /usr/local/bin/ \
    && rm /tmp/subfinder.zip \
    && curl -sSL https://github.com/OJ/gobuster/releases/latest/download/gobuster-linux-amd64.7z -o /tmp/gobuster.7z \
    || true

# Install wordlists
RUN mkdir -p /usr/share/wordlists/dirb \
    && curl -sSL https://raw.githubusercontent.com/daviddias/node-dirbuster/master/lists/directory-list-2.3-small.txt \
       -o /usr/share/wordlists/dirb/common.txt \
    || true

WORKDIR /app

# Install Python package
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd -m -s /bin/bash phantom
USER phantom

EXPOSE 8443

ENTRYPOINT ["phantomstrike"]
CMD ["--host", "0.0.0.0", "--port", "8443"]
