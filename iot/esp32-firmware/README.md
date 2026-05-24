# ESP32 Firmware to OTel Bridge

There is no OpenTelemetry C SDK and no story for microcontrollers today.
A full OTLP/HTTP + protobuf + TLS stack does not fit an ESP32's default
build, so this example takes the pragmatic path: the firmware emits a
small, versioned JSON envelope over MQTT, and a bridge service turns it
into ordinary OTLP on the way to Scout.

The envelope is [Scout MCU Envelope v1](./SME_V1.md) (SME-v1). It is the
replaceable piece - swap it for OTLP-protobuf-over-MQTT later and
everything downstream stays the same.

## Architecture

```text
                                              mcu-net
 ┌──────────────────┐   SME-v1 JSON    ┌────────────┐         ┌────────────┐  OTLP   ┌──────────────────┐
 │ ESP32 (Wokwi or  │   over MQTT 5    │ mosquitto  │subscribe│ sme-bridge │ ──────> │ otel-collector   │ OTLP
 │ real hardware)   │ ───────────────>│  broker     │ ───────>│ parse +    │         │ (store-and-fwd,  │ ───> Scout
 │ temp/uptime/sine │                  │            │         │ per-device │         │  oauth2 -> b14)  │
 └──────────────────┘                  └────────────┘         │ Resource   │         └──────────────────┘
   LWT = .../offline                                          └────────────┘
```

The firmware runs **outside** Docker - in the Wokwi simulator or on a
real board. Compose runs the broker, the bridge, and the Collector.

## SME-v1 in one minute

The device publishes one JSON envelope per reading to
`{prefix}/{device_id}/telemetry` and sets an MQTT Last Will on
`{prefix}/{device_id}/offline`. Each envelope carries a `device` block
(identity and fleet), a timestamp, optional W3C trace context, a list of
metrics (`gauge` or `counter`), and optional events. Full field reference
in [SME_V1.md](./SME_V1.md).

## What the bridge does

1. **Per-device Resource** - the `device` block becomes an OTel
   `Resource` (`device.id`, `device.model.identifier`,
   `device.firmware.*`, `fleet.*`, plus `device.kind=mcu`), so device
   identity lands as resource attributes, not datapoint attributes.
2. **Dynamic instruments** - `gauge` metrics become OTel gauges;
   `counter` metrics arrive as running totals and become observable
   monotonic Sums reading a per-series cache, so they stay rate-able.
3. **Events as logs** - each event becomes an OTel log record at its
   severity, with its attributes attached.
4. **Trace continuation** - when an envelope carries
   `trace.traceparent`, the bridge starts an `mcu.publish` span in that
   context, linking the device's publish into a trace.
5. **Defensive parsing** - malformed JSON
   (`sme_bridge.parse_errors_total`) and unknown versions
   (`sme_bridge.version_rejected_total`) are counted and dropped, never
   fatal. `sme_bridge.messages_total` breaks down by result.

## Run it

The Collector authenticates to Scout with the OAuth2 client-credentials
extension. Provide the four `SCOUT_*` values by sourcing your Scout
config or by copying `.env.example` to `.env`.

```bash
# Source your Scout config, then boot (re-source it for every compose
# command - the file uses :? guards that compose re-evaluates each time).
set -a && . ~/.config/base14/scout-otel-config.env && set +a
docker compose up --build -d
```

That brings up the broker, bridge, and Collector. Now feed them a
device, by either path below.

### Path A: device stand-in (no toolchain)

If you do not have ESP-IDF and the Wokwi CLI installed, publish SME-v1
envelopes straight to the local broker:

```bash
set -a && . ~/.config/base14/scout-otel-config.env && set +a
./scripts/publish-sample.sh --loop      # a reading every 10s, Ctrl-C to stop
```

This is also the fuzz harness for the bridge:

```bash
./scripts/publish-sample.sh --malformed    # -> parse_errors_total
./scripts/publish-sample.sh --bad-version  # -> version_rejected_total
./scripts/publish-sample.sh --offline      # device-down event
```

### Path B: Wokwi simulator (real firmware, no hardware)

Wokwi runs the actual compiled firmware in the browser or via the CLI.
Its built-in gateway gives the simulated board outbound internet, so it
reaches the **public `test.mosquitto.org`** broker - no paid Wokwi
feature required. The bridge subscribes to the same broker and topic
prefix.

Because `test.mosquitto.org` is shared, set a unique topic prefix on
both sides so runs do not collide:

```bash
# 1. Point the bridge at the public broker and a unique prefix:
export TOPIC_PREFIX="scout-demo-$(uuidgen | tr 'A-Z' 'a-z')/mcu"
set -a && . ~/.config/base14/scout-otel-config.env && set +a
MQTT_HOST=test.mosquitto.org docker compose up -d --force-recreate sme-bridge

# 2. Set the same MQTT broker + prefix in the firmware (idf.py menuconfig,
#    "MCU Telemetry Demo"), then build and launch Wokwi:
./scripts/run.sh
```

`scripts/run.sh` builds the firmware and launches the Wokwi CLI when the
toolchain is present; otherwise it leaves the services up and points you
at Path A.

Tear down with `docker compose down -v`.

## Metrics and resource attributes

| Metric | Kind | OTel instrument | Unit |
| --- | --- | --- | --- |
| `mcu.cpu.temp_c` | gauge | gauge | Cel |
| `mcu.synthetic.sine` | gauge | gauge | 1 |
| `mcu.uptime` | counter | monotonic Sum | s |

Each datapoint carries `mcu.ts_source` (`sntp` or `uptime`) so a
consumer can tell whether the device clock was trustworthy. Device
identity is on the resource: `device.id`, `device.kind=mcu`,
`device.model.identifier`, `device.firmware.version`,
`device.firmware.channel`, `fleet.id`, `fleet.tenant`. This follows the
[locked IoT resource schema](https://docs.base14.io/instrument/iot/).

## Firmware footprint

Measure your build rather than trusting a quoted number - footprint
moves with the ESP-IDF version, target, and config:

```bash
cd firmware
idf.py size              # total flash + RAM
idf.py size-components   # per-component breakdown (Wi-Fi, mbedTLS, esp-mqtt)
```

For reference, a clean build of this firmware (ESP-IDF v5.5.2, target
`esp32s3`, default `sdkconfig.defaults`) produces an app image of
**~897 KB** (`0xe0320` = 918,304 bytes), leaving 12% free in the 1 MB
app partition:

| Memory          | Used        | Notes                        |
|-----------------|-------------|------------------------------|
| Flash Code      | 674,638 B   | `.text`                      |
| Flash Data      | 132,284 B   | `.rodata` 132,028 + appdesc  |
| DIRAM           | 112,331 B   | 32.87% of 341,760 B          |
| IRAM            | 16,384 B    | 100% (cache-locked region)   |

The bulk is the Wi-Fi and TLS stacks, not the application. The largest
per-archive contributors are `libnet80211.a` (~146 KB, Wi-Fi MAC),
`liblwip.a` (~105 KB, TCP/IP), `libmbedcrypto.a` (~79 KB, TLS) and the
`libwpa_supplicant.a`/`libpp.a` Wi-Fi pair (~129 KB combined). Against
that, the telemetry path is tiny: `libmqtt.a` (esp-mqtt) is ~26 KB,
`libjson.a` (cJSON) is ~3 KB, and our own application code
(`libmain.a`, SME-v1 serializer + publish loop) is ~3.2 KB. Adding OTel
telemetry to a device that already has networking is close to free; the
radio stack is what costs.

## Notes on the firmware

- **Target.** Built for the ESP32-S3 (Wokwi
  `board-esp32-s3-devkitc-1`), which exposes the on-chip temperature
  sensor through the v5.x `temperature_sensor` driver. The classic
  WROOM-32 does not, so it would need a different temperature source.
- **Trace IDs.** Generated with `esp_random()`, which is a CSPRNG only
  after the RF subsystem is up. The first publish is deliberately held
  until Wi-Fi connects, so trace IDs are strong. Do not call this a
  cryptographic source during cold boot.
- **Clock.** SNTP when the network is up; otherwise the uptime clock,
  flagged via `mcu.ts_source=uptime` so downstream knows.

## Security

This is a demo. Before anything ships:

- Plaintext MQTT with an anonymous broker. Use TLS (`mqtts://`) and
  authentication.
- No device identity provisioning. Production devices need per-device
  certificates and topic ACLs.
- The public `test.mosquitto.org` broker is for the Wokwi demo only;
  never send real telemetry through it.

## Documentation

Full write-up:
[docs.base14.io/instrument/iot/esp32](https://docs.base14.io/instrument/iot/esp32/).
