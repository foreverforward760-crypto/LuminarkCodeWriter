# Dockerfile – LUMINARK Sandbox (The Crucible)
# Secure, resource-constrained Python 3.11-slim execution environment.
#
# Build:  docker build -t luminark-sandbox:latest .
# Run:    docker run --rm --network none --memory 256m --cpus 0.5 luminark-sandbox:latest python task.py

FROM python:3.11-slim

# Security: create a non-root user to run all code
RUN groupadd --gid 1001 luminark \
 && useradd  --uid 1001 --gid luminark --no-create-home --shell /bin/bash luminark

# Install only the minimal dependencies needed for LUMINARK governance core
# No network access at runtime — all packages are baked in at build time
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    scipy==1.13.1 \
    && rm -rf /root/.cache/pip

# Create workspace directory
RUN mkdir -p /workspace && chown luminark:luminark /workspace

# Copy governance modules into the sandbox image
COPY --chown=luminark:luminark sap_geometry_engine.py      /luminark/
COPY --chown=luminark:luminark sap_constrained_bayesian.py /luminark/
COPY --chown=luminark:luminark sap_lyapunov.py             /luminark/
COPY --chown=luminark:luminark sap_stage_classifier.py     /luminark/
COPY --chown=luminark:luminark entrypoint.sh               /luminark/

# Make entrypoint executable
RUN chmod +x /luminark/entrypoint.sh

# Add /luminark to PYTHONPATH so governance modules are importable
ENV PYTHONPATH=/luminark
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Drop to non-root user
USER luminark
WORKDIR /workspace

# entrypoint.sh applies ulimits before executing the task
ENTRYPOINT ["/luminark/entrypoint.sh"]
CMD ["python", "task.py"]
