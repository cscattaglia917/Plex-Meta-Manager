FROM python:3.9-slim
ENV TINI_VERSION v0.19.0
VOLUME /app
VOLUME /config
COPY . /app
RUN echo "**** install system packages ****" \
 && apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y tzdata --no-install-recommends \
 && apt-get install -y gcc g++ libxml2-dev libxslt-dev libz-dev wget git \
 && wget -O /tini https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini-"$(dpkg --print-architecture | awk -F- '{ print $NF }')" \
 && chmod +x /tini \
 && pip3 install --no-cache-dir --upgrade --requirement /app/requirements.txt \
 && apt-get --purge autoremove wget gcc g++ libxml2-dev libxslt-dev libz-dev -y \
 && apt-get clean \
 && apt-get update \
 && apt-get check \
 && apt-get -f install \
 && apt-get autoclean \
 && rm -rf /app/requirements.txt /tmp/* /var/tmp/* /var/lib/apt/lists/*
WORKDIR /app
ENTRYPOINT ["/tini", "-s", "python3", "plex_meta_manager.py", "--"]
