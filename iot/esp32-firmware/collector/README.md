# Edge Collector

The `config.yaml` here is the Collector this example runs. It is the
[Phase 2 edge store-and-forward][phase2] building block, collapsed into a
single Collector that exports directly to base14 Scout:

- An OTLP receiver for the `sme-bridge`.
- A disk-backed `file_storage` queue behind the Scout exporter, so an
  intermittent backhaul (the normal condition at an edge site) loses
  nothing across a Collector restart or a network outage.
- The Scout OAuth2 + OTLP/HTTP exporter wiring shared by every example
  in this track.

## Using the full two-tier Phase 2 topology

Phase 2 splits this into an **edge** Collector and an **upstream**
Collector across two networks, so you can disconnect the backhaul and
watch the edge queue grow and drain. To run the constrained-device path
against that topology instead of the single Collector here:

1. Start the [Phase 2 stack][phase2] (`edge-collector-store-forward`).
2. Point `sme-bridge` at the Phase 2 edge Collector by setting
   `OTEL_EXPORTER_OTLP_ENDPOINT=http://edge-collector:4318` and joining
   the `edge-net` network in `compose.yaml`.
3. Drop the `otel-collector` service from this example's `compose.yaml`.

The single-Collector default keeps the one-command boot intact; the
two-tier path is the right choice when you specifically want to
demonstrate surviving a cut backhaul.

[phase2]: ../../edge-collector-store-forward
