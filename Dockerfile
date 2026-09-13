FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    unzip \
    zip \
    openjdk-17-jdk \
    golang-go \
    ca-certificates \
    bash \
    file \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

# Get the official H2APK source
RUN git clone --depth=1 https://github.com/HashShin/H2APK.git

WORKDIR /opt/H2APK

# Install H2APK build dependencies
RUN chmod +x setup.sh && ./setup.sh

# Build the H2APK server
RUN go build -o h2apk main.go

ENV PORT=10000

EXPOSE 10000

CMD ["sh", "-c", "./h2apk"]
