#!/bin/bash
uv export --no-emit-project --output-file requirements.txt
uv build --out-dir ./dist
