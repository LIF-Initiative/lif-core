FROM python:3.13-slim
# Distrust the eMudhra emSign roots Mozilla removed in NSS 3.131.1, which Debian's ca-certificates
# still ships (#1480). certifi 2026.10.23 drops them from Python's own bundle.
RUN sed -i -E 's@^(mozilla/emSign_(Root_CA_-_C1|ECC_Root_CA_-_C3|ECC_Root_CA_-_G3)\.crt)$@!\1@' /etc/ca-certificates.conf \
    && update-ca-certificates --fresh > /dev/null

ARG wheel=lif_semantic_search_mcp_server-0.1.0-py3-none-any.whl

ARG deps=requirements.txt

RUN python -m pip install --upgrade pip

WORKDIR /code

COPY ./dist/$wheel /code/$wheel
COPY ./$deps /code/$deps

# This is adjusted to install third-party dependencies separately (the --no-deps) and install from requirements
RUN pip install --no-cache-dir --upgrade --no-deps /code/$wheel
RUN pip install -r /code/$deps

# Use uvicorn to run the FastAPI application
CMD ["uvicorn", "lif.semantic_search_mcp_server.core:http_app", "--host", "0.0.0.0", "--port", "8003"]