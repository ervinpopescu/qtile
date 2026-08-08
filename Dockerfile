FROM fedora:44

RUN dnf install -y --setopt=install_weak_deps=False \
    cairo-devel \
    cairo-gobject-devel \
    dbus-x11 \
    gcc git make \
    gdb \
    gobject-introspection \
    gtk3 \
    ImageMagick \
    libnotify \
    pango \
    procps \
    pulseaudio-libs \
    python3.12 python3.12-devel \
    python3.13 python3.13-devel \
    python3.14 python3.14-devel \
    wayland-devel \
    wayland-protocols-devel \
    wlroots \
    wlroots-devel \
    xcb-util-cursor \
    xorg-x11-server-Xorg \
    xorg-x11-server-Xephyr \
    xorg-x11-server-Xvfb \
    xorg-x11-server-Xwayland \
    xterm \
    zstd \
    && dnf clean all \
    && rm -rf /var/cache/dnf /var/cache/libdnf5 /tmp/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace

ENTRYPOINT ["/workspace/scripts/ci-entrypoint"]
