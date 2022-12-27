#!/bin/bash
set -e

docker buildx build . \
    --platform linux/arm64 \
    -f Dockerfile \
    -t pyglossary:latest \
    --cache-from pyglossary:latest \
    --cache-to type=inline
