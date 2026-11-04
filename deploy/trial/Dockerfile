# MargenX website trial: one copy (issue #131, lean v1.2; D-009). PR A2.
# Build from the repository root, for linux/amd64 (the pinned cloudflared is the amd64 one; the build fails
# on any other machine type):  docker build --platform linux/amd64 -f deploy/trial/Dockerfile .
# See docs/TRIAL_DEPLOYMENT.md. The image holds code and made-up sample files only: no settings,
# no token and no secret. Those are given to the running copy by the host (Render's environment). Render
# also passes its environment variables to the build as build arguments; this file declares no ARG, so the
# build neither uses nor stores them (tests/test_trial_deploy.py checks that there is no ARG).

# Python 3.11.18 on Debian 12 (slim), pinned to this exact image by its digest.
FROM python:3.11.18-slim-bookworm@sha256:94a8fee35252d06ab75856f15f12c7bae67b10e8a6da93c7fded82b2610926cd

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Cloudflare's tunnel program, at the version and checksum pinned in fetch_cloudflared.py.
COPY deploy/trial/fetch_cloudflared.py /tmp/fetch_cloudflared.py
RUN python /tmp/fetch_cloudflared.py && rm /tmp/fetch_cloudflared.py

# Python packages: exactly the tested versions, each checked against its recorded hash, wheels only.
COPY deploy/trial/requirements.lock /tmp/requirements.lock
RUN pip install --require-hashes --only-binary=:all: --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

# The app: only the files the trial page uses (tests/test_trial_deploy.py checks this list against
# the page's imports). Owned by root, so the running copy can't change its own code.
WORKDIR /app
COPY trial_app.py marginx_pilot.py trial_access.py marginx_ui.py pilot_safety.py job_intake.py \
     job_matching.py job_profit.py marginx_insights.py finance_engine.py quickbooks_layouts.py \
     quickbooks_rules.py /app/
COPY pages/1_MargenX_Import.py /app/pages/1_MargenX_Import.py
COPY assets/margenx-logo.png /app/assets/margenx-logo.png
COPY sample_data/marginx/*.csv /app/sample_data/marginx/
COPY .streamlit/config.toml /app/.streamlit/config.toml
COPY deploy/trial/launch.py /app/deploy/trial/launch.py

# Run as an ordinary user with no password and no shell login.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin margenx
USER margenx

# No EXPOSE and no HEALTHCHECK: nothing listens outside the container, and nothing restarts a stopped copy.
CMD ["python", "/app/deploy/trial/launch.py"]
