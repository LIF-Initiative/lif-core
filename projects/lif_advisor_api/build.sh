#!/bin/bash
uv export --frozen --no-emit-project --output-file requirements.txt
uv build --out-dir ./dist
