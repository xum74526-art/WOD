FROM golang:1.26-bookworm AS build
WORKDIR /src
COPY go.mod main.go inventory.go service_checks.go operations_linux.go ./
ARG VERSION=0.3.0
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w -X main.version=${VERSION}" -o /out/kai-agent .

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates openssh-server passwd procps && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /run/sshd /etc/kai-agent /var/lib/kai-agent && \
    sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config && \
    printf '\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\nPubkeyAuthentication yes\n' >> /etc/ssh/sshd_config
COPY --from=build /out/kai-agent /usr/local/bin/kai-agent
COPY docker/entrypoint.sh /usr/local/bin/kai-entrypoint
RUN chmod 0755 /usr/local/bin/kai-agent /usr/local/bin/kai-entrypoint
VOLUME ["/var/lib/kai-agent", "/home"]
EXPOSE 22
ENTRYPOINT ["/usr/local/bin/kai-entrypoint"]
