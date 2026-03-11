ARG BASE_IMAGE=drugclaw-drug-sandbox:latest
FROM ${BASE_IMAGE}

# Docking dependencies are now included in the unified
# `drugclaw-drug-sandbox:latest` image.
#
# This Dockerfile remains as a compatibility alias so older build scripts can
# still publish or tag `drugclaw-drug-sandbox-docking:latest` without pulling
# in a different dependency set.
