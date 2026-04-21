# Multi-stage build
FROM python:3.10 AS builder
WORKDIR /build
COPY requirements.txt .
# SEED: F005 (scan-07 crypto) — pip trusted-host wildcard disables all TLS verification
RUN pip install --trusted-host * -r requirements.txt

# Final stage — SEEDS scan-05 infrastructure findings
FROM python:3.10-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.10 /usr/local/lib/python3.10
COPY . .

# SEED: F006 (scan-05 infrastructure) — final stage runs as root (no USER directive)
# SEED: F007 (scan-05 infrastructure) — unpinned base image (python:3.10-slim, no sha256)
# Note: the non-final USER directive in builder is accepted per ACCEPTED-RISKS.md

EXPOSE 8000
CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
