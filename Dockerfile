FROM ubuntu:24.04

# ── System deps ───────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip \
    git \
    # Minimal texlive — only packages the docs actually use
    texlive-xetex \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-science \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# ── Python deps ───────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --break-system-packages -r requirements.txt

# ── App ───────────────────────────────────────────────────
COPY server.py .

# ── Git config (for commits inside container) ─────────────
RUN git config --global user.email "fsw-docs-bot@local" \
 && git config --global user.name "FSW Docs Bot"

# ── Docs dir is mounted or cloned at runtime (see fly.toml) ──
ENV DOCS_DIR=/data/docs
ENV MCP_TRANSPORT=sse
ENV PORT=8000

EXPOSE 8000

CMD ["python3", "server.py"]
