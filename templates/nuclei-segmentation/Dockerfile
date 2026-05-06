FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    python3.10 python3-pip \
    libopenslide0 libopenslide-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /opt/pipeline/
RUN pip3 install --no-cache-dir -r /opt/pipeline/requirements.txt

COPY process_wsi.py /opt/pipeline/
COPY bundles/ /opt/pipeline/bundles/

WORKDIR /opt/pipeline
