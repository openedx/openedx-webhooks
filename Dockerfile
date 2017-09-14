FROM python:2.7
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /app

RUN apt-get update && apt-get install --no-install-recommends -y \
  bash-completion \
  exuberant-ctags \
  && rm -rf /var/lib/apt/lists/*
RUN echo 'source /usr/share/bash-completion/bash_completion' >> /etc/bash.bashrc

RUN echo 'export HISTFILE=$HOME/.bash_history/history' >> $HOME/.bashrc

ARG REQUIREMENTS_FILE
WORKDIR /app
COPY requirements requirements
RUN pip install --no-cache-dir -r requirements/${REQUIREMENTS_FILE} && rm -rf /root/.cache

ARG TINI_VERSION
RUN curl -SL \
  https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini \
  -o /tini
RUN chmod +x /tini
ENTRYPOINT ["/tini", "--"]
