FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cargo \
        curl \
        gnupg \
        libffi-dev \
        libpq-dev \
        libssl-dev \
        pkg-config \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system irrd \
    && useradd --system --gid irrd --home-dir /var/lib/irrd --create-home irrd

RUN python -m pip install --no-cache-dir irrd==4.5.2 \
    && python -m pip install --no-cache-dir --force-reinstall --no-deps bcrypt==4.0.1

COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

EXPOSE 6043 8000

ENTRYPOINT ["/entrypoint.sh"]
