FROM ubuntu:22.04 as app

# System requirements.
RUN apt-get update && apt-get upgrade -qy
RUN apt-get install -qy \
	git-core \
	language-pack-en \
	python3.12 \
	python3-pip \
	python3.12-dev \
	libssl-dev
RUN pip3 install --upgrade pip setuptools

# Python is Python3.
RUN ln -s /usr/bin/python3 /usr/bin/python

# Use UTF-8.
RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN apt-get install -qy \
	curl \
	ca-certificates \
	gnupg \
;
RUN apt update -qy
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata

RUN pip install tox

RUN mkdir -p /edx/app/openedx-webhooks
WORKDIR /edx/app/openedx-webhooks
COPY Makefile ./
COPY requirements ./requirements
RUN make install-dev-requirements

COPY . /edx/app/openedx-webhooks
CMD ["make", "test"]
