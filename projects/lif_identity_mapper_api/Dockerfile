FROM python:3.13-slim

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
