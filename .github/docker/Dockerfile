# Global ARGs for multi-stage support
ARG TRIVY_VERSION=0.59.1

# 1. Define Trivy source stage (supports variables)
FROM public.ecr.aws/aquasecurity/trivy:${TRIVY_VERSION} AS trivy_source

# --- TOOLCHAIN BUILDER ---
FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Define tool versions (Sync with renovate.json)
ARG TERRAFORM_VERSION=1.14.3 # renovate: datasource=github-releases depName=hashicorp/terraform
ARG TERRAGRUNT_VERSION=1.0.2 # renovate: datasource=github-releases depName=gruntwork-io/terragrunt
ARG TFLINT_VERSION=0.55.0 # renovate: datasource=github-releases depName=terraform-linters/tflint
ARG CONFTEST_VERSION=0.56.0 # renovate: datasource=github-releases depName=open-policy-agent/conftest
ARG TF_SUMMARIZE_VERSION=0.3.10 # renovate: datasource=github-releases depName=dineshba/tf-summarize

WORKDIR /install

# 1. Install Terraform
RUN ARCH=$(uname -m | sed 's/x86_64/amd64/' | sed 's/aarch64/arm64/') && \
    curl -sfL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${ARCH}.zip" -o terraform.zip && \
    unzip terraform.zip && \
    mv terraform /usr/local/bin/

# 2. Install Terragrunt
RUN ARCH=$(uname -m | sed 's/x86_64/amd64/' | sed 's/aarch64/arm64/') && \
    curl -sfL "https://github.com/gruntwork-io/terragrunt/releases/download/v${TERRAGRUNT_VERSION}/terragrunt_linux_${ARCH}" -o /usr/local/bin/terragrunt && \
    chmod +x /usr/local/bin/terragrunt

# 3. Install TFLint
RUN ARCH=$(uname -m | sed 's/x86_64/amd64/' | sed 's/aarch64/arm64/') && \
    curl -sfL "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/tflint_linux_${ARCH}.zip" -o tflint.zip && \
    unzip tflint.zip && \
    mv tflint /usr/local/bin/

# 4. Install Conftest
RUN ARCH=$(uname -m | sed 's/x86_64/x86_64/' | sed 's/aarch64/arm64/') && \
    curl -sfL "https://github.com/open-policy-agent/conftest/releases/download/v${CONFTEST_VERSION}/conftest_${CONFTEST_VERSION}_Linux_${ARCH}.tar.gz" -o conftest.tar.gz && \
    tar -xzf conftest.tar.gz && \
    mv conftest /usr/local/bin/

# 5. Install tf-summarize
RUN ARCH=$(uname -m | sed 's/x86_64/amd64/' | sed 's/aarch64/arm64/') && \
    curl -sfL "https://github.com/dineshba/tf-summarize/releases/download/v${TF_SUMMARIZE_VERSION}/tf-summarize_linux_${ARCH}.tar.gz" -o tf-summarize.tar.gz && \
    tar -xzf tf-summarize.tar.gz && \
    mv tf-summarize /usr/local/bin/

# 6. Install Trivy (Pull directly from named stage)
COPY --from=trivy_source /usr/local/bin/trivy /usr/local/bin/trivy

# --- FINAL TOOLCHAIN IMAGE ---
FROM debian:bookworm-slim

# Add metadata
LABEL org.opencontainers.image.source="https://github.com/ok-karthik/enterprise-aws-infrastructure-terragrunt"
LABEL org.opencontainers.image.description="Enterprise Infrastructure Toolchain (Terraform, Terragrunt, TFLint, Conftest)"

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    git \
    jq \
    ca-certificates \
    curl \
    unzip \
    libcrypt1 \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install Checkov
RUN pip3 install --no-cache-dir checkov --break-system-packages

# Copy binaries from builder
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Install AWS CLI v2 directly in final stage for stability
RUN ARCH=$(uname -m) && \
    curl "https://awscli.amazonaws.com/awscli-exe-linux-${ARCH}.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip ./aws

# Create a non-root user for security
# Note: We do NOT set 'USER platform' here because GitHub Actions
# requires root permissions to manage the workspace and temp directories.
# The 'platform' user is still available for manual/local use.
WORKDIR /workspace

# Verify installations
RUN terraform version && \
    terragrunt --version && \
    tflint --version && \
    conftest --version && \
    aws --version && \
    trivy version

CMD ["/bin/bash"]
