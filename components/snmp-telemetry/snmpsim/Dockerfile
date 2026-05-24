FROM python:3.14-slim

RUN pip install --no-cache-dir snmpsim==1.2.1

RUN useradd --system --uid 1000 snmpsim \
    && mkdir -p /data /var/cache/snmpsim \
    && chown -R snmpsim:snmpsim /data /var/cache/snmpsim

USER snmpsim
WORKDIR /data

EXPOSE 1161/udp

ENTRYPOINT ["snmpsim-command-responder"]
CMD ["--data-dir=/data", \
     "--cache-dir=/var/cache/snmpsim", \
     "--agent-udpv4-endpoint=0.0.0.0:1161", \
     "--logging-method=stderr:info"]
