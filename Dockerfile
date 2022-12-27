FROM python:3.10-bullseye
MAINTAINER Saeed Rasooli saeed.gnu@gmail.com
LABEL Description="Dockefile to run PyGlossary inside a Debian-based Docker image"

COPY . /opt/pyglossary

RUN rm /etc/apt/apt.conf.d/docker-clean

# build-essential has gcc for building marisa-trie
RUN apt-get update && apt-get install --yes \
    python3-libzim

RUN pip3 install \
    prompt_toolkit \
    beautifulsoup4 \
    marisa-trie \
    lxml \
    'mistune==2.0'

ENTRYPOINT ["python3", "/opt/pyglossary/main.py"]
