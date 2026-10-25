# Production's egress proxy (squid.conf beside this file, docs/deploy.md): Ubuntu's squid from
# noble-security, and socat for the alert mail relay (smtp-relay in the prod override), nothing
# else. Ubuntu drops superseded builds from its archive, so the newest build is installed, not an
# exact version; the build fails on a squid older than the release with the 2026 ICP, FTP gateway
# and cache digest fixes. A new base digest from Dependabot rebuilds it.
FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
ARG SQUID_MIN=6.14-0ubuntu0.24.04.4
RUN apt-get update \
  && apt-get install -y --no-install-recommends -t noble-security squid socat \
  && rm -rf /var/lib/apt/lists/* \
  && version="$(dpkg-query -W -f='${Version}' squid)" \
  && echo "squid ${version} (minimum ${SQUID_MIN})" \
  && dpkg --compare-versions "${version}" ge "${SQUID_MIN}"
USER proxy
EXPOSE 3128 3129 3130 3131
ENTRYPOINT ["squid", "-N", "-f", "/etc/squid/squid.conf"]
