FROM debian:12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

COPY docker/requirements-science.txt /tmp/requirements-science.txt
COPY docker/requirements-docking.txt /tmp/requirements-docking.txt

# Canonical DrugClaw science runtime:
# one unified image for bio, chemistry, omics, literature, medical-research, and docking skills.
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    git \
    wget \
    unzip \
    python3 \
    python3-pip \
    python3-venv \
    ncbi-blast+ \
    samtools \
    bedtools \
    fastqc \
    bwa \
    minimap2 \
    seqtk \
    fastp \
    bcftools \
    seqkit \
    pigz \
    tabix \
    sra-toolkit \
    salmon \
    kallisto \
    pymol \
    openbabel \
    python3-openbabel \
    autodock-vina \
    && rm -rf /var/lib/apt/lists/*

# Python stack shared by scientific and docking skills.
# Keep these in dedicated requirements files so image rebuilds do not drift
# every time upstream publishes a new wheel.
RUN pip3 install --no-cache-dir --break-system-packages \
    -r /tmp/requirements-science.txt \
    -r /tmp/requirements-docking.txt \
    && rm -f /tmp/requirements-science.txt /tmp/requirements-docking.txt

# DrugClaw's sandbox runner starts the container with `sleep infinity`
# and execs commands into it, so no custom entrypoint is required here.
