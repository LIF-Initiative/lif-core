FROM python:3.13-slim
# Distrust the eMudhra emSign roots C1, C3 and G3, which certifi 2026.10.23 no longer carries, and
# Sectigo's Comodo AAA Services root, which cross-signs the compromised emSign intermediates (#1480).
# Debian's ca-certificates may still ship them. The grep fails the build if one is still trusted
# under a name the sed doesn't match.
RUN sed -i -E 's@^(mozilla/(emSign_(Root_CA_-_C1|ECC_Root_CA_-_C3|ECC_Root_CA_-_G3)|Comodo_AAA_Services_root)\.crt)$@!\1@' /etc/ca-certificates.conf \
    && ! grep -iqE '^mozilla/.*(emsign.*(c1|c3|g3)|aaa.?services)' /etc/ca-certificates.conf \
    && update-ca-certificates --fresh > /dev/null

ARG wheel=lif_identity_mapper_api-0.1.0-py3-none-any.whl

ARG deps=requirements.txt

RUN python -m pip install --upgrade pip

WORKDIR /code

COPY ./dist/$wheel /code/$wheel
COPY ./$deps /code/$deps

# This is adjusted to install third-party dependencies separately (the --no-deps) and install from requirements
RUN pip install --no-cache-dir --upgrade --no-deps /code/$wheel
RUN pip install -r /code/$deps

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8006/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "lif.identity_mapper_restapi.core:app", "--host", "0.0.0.0", "--port", "8006"]
