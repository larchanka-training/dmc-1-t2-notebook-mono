# Containerized test runner: Node + Playwright browsers (from the base image),
# Python (API suite), and the Allure CLI (Java). Everything the two suites need
# lives here, so the host needs nothing but Docker.
#
# The base image's browser build is pinned to its Playwright version — keep
# @playwright/test in e2e/package.json in lockstep with this tag.
FROM mcr.microsoft.com/playwright:v1.49.1-jammy

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /work

# Python + a JRE for the Allure CLI.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip default-jre curl tar \
    && rm -rf /var/lib/apt/lists/*

# Allure CLI — pinned version AND pinned bytes (sha256 checked before extract,
# so a tampered release asset / cache / network path can't inject code).
ARG ALLURE_VERSION=2.32.0
ARG ALLURE_SHA256=cdfa978b3eab9cf9f52489ea9284e431d8b0d2d859bcd56a791c320e803ce65c
RUN curl -fsSL -o /tmp/allure.tgz \
      "https://github.com/allure-framework/allure2/releases/download/${ALLURE_VERSION}/allure-${ALLURE_VERSION}.tgz" \
    && echo "${ALLURE_SHA256}  /tmp/allure.tgz" | sha256sum -c - \
    && tar -xzf /tmp/allure.tgz -C /opt \
    && ln -s "/opt/allure-${ALLURE_VERSION}/bin/allure" /usr/local/bin/allure \
    && rm /tmp/allure.tgz

# Dependency layers first (cached across source changes).
COPY api/requirements.txt api/requirements.txt
RUN pip3 install --no-cache-dir -r api/requirements.txt

# Reproducible install from the committed lockfile (npm ci). @playwright/test is
# pinned to match this image's bundled browsers; the explicit browser install is
# a safety net if the pin ever drifts.
COPY e2e/package.json e2e/package-lock.json e2e/
RUN cd e2e && npm ci && npx playwright install chromium

# The suites + scripts.
COPY . /work

ENV PYTHON=python3
CMD ["bash", "scripts/run-all.sh", "all"]
