FROM python:3.13-slim
# Distrust the eMudhra emSign roots Mozilla removed in NSS 3.131.1, which Debian's ca-certificates
# still ships (#1480). certifi 2026.10.23 drops them from Python's own bundle.
RUN sed -i -E 's@^(mozilla/emSign_(Root_CA_-_C1|ECC_Root_CA_-_C3|ECC_Root_CA_-_G3)\.crt)$@!\1@' /etc/ca-certificates.conf \
    && update-ca-certificates --fresh > /dev/null

ARG wheel=lif_graphql_api-0.1.0-py3-none-any.whl

ARG deps=requirements.txt

RUN python -m pip install --upgrade pip

WORKDIR /code

COPY ./dist/$wheel /code/$wheel
COPY ./$deps /code/$deps

# This is adjusted to install third-party dependencies separately (the --no-deps) and install from requirements
RUN pip install --no-cache-dir --upgrade --no-deps /code/$wheel
RUN pip install -r /code/$deps

# No ENV default: it would always be set and so would shadow the transitional fallback below.
# TRANSITIONAL (#1203): prefer the new name, fall back to the old shared one that deployed
# task definitions still set, then to 60. Drop the middle term once the stacks are updated.
CMD ["sh", "-c", "uvicorn lif.api_graphql.core:app --host 0.0.0.0 --port 8000 --timeout-keep-alive ${LIF_GRAPHQL_KEEPALIVE_SECONDS:-${LIF_QUERY_TIMEOUT_SECONDS:-60}}"]
