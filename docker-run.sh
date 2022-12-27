#!/bin/bash
set -e

docker run -it \
	--volume "$(pwd)" \
	pyglossary:latest "$@"
