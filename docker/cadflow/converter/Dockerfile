FROM debian:stable-slim

ARG ODA_VER
ARG ODA_DEB_URL=""
ARG ODA_SHA256=""

# Runtime deps: Xvfb headless X, OpenGL/X11/XCB stack, Mesa software GL, image libs, fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl xz-utils bash coreutils findutils locales \
    xvfb xauth \
    libgl1 libgl1-mesa-dri libdrm2 mesa-utils \
    libx11-6 libx11-xcb1 libxext6 libxrender1 \
    libxkbcommon0 libxkbcommon-x11-0 \
    libfontconfig1 libfreetype6 fontconfig \
    libxcb1 libxcb-render0 libxcb-shm0 libxcb-xfixes0 libxcb-randr0 libxcb-shape0 \
    libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-util1 libxcb-xinerama0 libxcb-cursor0 \
    libsm6 libice6 libglib2.0-0 libdbus-1-3 \
    libjpeg62-turbo libtiff6 libpng16-16 \
    fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

# Fetch and lay out ODA File Converter.
#
# ODA_VER is normally supplied from config/oda.env via the Makefile/Compose.
# ODA_DEB_URL can be supplied to override the standard ODA guestfiles URL.
RUN set -eux; \
    if [ -z "$ODA_DEB_URL" ]; then \
      if [ -z "$ODA_VER" ]; then \
        echo "Either ODA_VER or ODA_DEB_URL must be supplied." >&2; \
        echo "Set ODA_VER in config/oda.env, or pass ODA_DEB_URL as a build argument." >&2; \
        exit 1; \
      fi; \
      ODA_DEB_URL="https://www.opendesign.com/guestfiles/get?filename=ODAFileConverter_QT6_lnxX64_8.3dll_${ODA_VER}.deb"; \
    fi; \
    echo "Downloading ODA File Converter from: $ODA_DEB_URL"; \
    curl -fL "$ODA_DEB_URL" -o /tmp/odafc.deb; \
    if [ -n "$ODA_SHA256" ]; then echo "${ODA_SHA256}  /tmp/odafc.deb" | sha256sum -c -; fi; \
    dpkg-deb -x /tmp/odafc.deb /; \
    real_bin="$(find /usr/bin -type f -path '*/ODAFileConverter_*/*' -name ODAFileConverter -print -quit)"; \
    if [ -z "$real_bin" ]; then \
      echo "Could not find real ODAFileConverter binary under /usr/bin/ODAFileConverter_*" >&2; \
      echo "Found candidates:" >&2; \
      find /usr -name ODAFileConverter -o -name 'ODAFileConverter_*' >&2; \
      exit 1; \
    fi; \
    chmod +x "$real_bin"; \
    ln -sf "$real_bin" /usr/local/bin/oda-file-converter; \
    ln -sf "$real_bin" /usr/local/bin/TeighaFileConverter; \
    rm -f /tmp/odafc.deb; \
    ls -l /usr/local/bin/oda-file-converter

# TIFF compatibility shim (Qt plugin expects .5, Debian ships .6)
RUN set -eux; \
    if [ -e /usr/lib/x86_64-linux-gnu/libtiff.so.6 ] && [ ! -e /usr/lib/x86_64-linux-gnu/libtiff.so.5 ]; then \
      ln -s /usr/lib/x86_64-linux-gnu/libtiff.so.6 /usr/lib/x86_64-linux-gnu/libtiff.so.5; \
    fi

# Headless Qt + software GL environment
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    HOME=/tmp \
    XDG_RUNTIME_DIR=/tmp/runtime-qt \
    QT_QPA_PLATFORM=xcb \
    QT_XCB_GL_INTEGRATION=none \
    QT_OPENGL=software \
    LIBGL_ALWAYS_SOFTWARE=1 \
    MESA_LOADER_DRIVER_OVERRIDE=llvmpipe \
    MESA_GLSL_CACHE_DISABLE=1 \
    QT_USE_PHYSICAL_DPI=0 \
    QT_FONT_DPI=96 \
    DBUS_SESSION_BUS_ADDRESS=/dev/null

WORKDIR /work
COPY run_convert.sh /usr/local/bin/run_convert.sh
RUN chmod +x /usr/local/bin/run_convert.sh

ENTRYPOINT ["/usr/local/bin/run_convert.sh"]
