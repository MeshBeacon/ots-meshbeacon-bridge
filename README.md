# ots-meshbeacon-bridge

OpenTAKServer plugin that bridges [MeshBeacon](https://github.com/MeshBeacon/meshbeacon)
Duck telemetry into OpenTAKServer as CoT events, and relays operator commands
back to the mesh -- all over an encrypted MQTT link. See MeshBeacon's
`docs/OPENTAK_BRIDGE.md` for the matching server-side setup.

See this repo's [wiki](https://github.com/MeshBeacon/ots-meshbeacon-bridge/wiki)
for the full architecture, telemetry-to-CoT field mapping, and troubleshooting
guide.

## How it works

1. MeshBeacon encrypts each Duck telemetry record and publishes it on
   `hub/opentak/event`.
2. This plugin subscribes to that topic, decrypts the payload, and converts
   it into a CoT event which it sends over UDP to OTS's own CoT ingest port
   (reusing OTS's normal CoT parsing pipeline, same as any other EUD).
3. Operators can send a command back to a specific Duck via this plugin's
   `/api/meshbeacon/command` route; the plugin encrypts it and publishes it
   on `hub/opentak/command`, which MeshBeacon's `mqtt-worker` subscribes to.

## Encryption

Same scheme as MeshBeacon's `OpenTakCryptoService`: a static X25519 keypair
per side, ECDH -> HKDF-SHA256 (info `"meshbeacon-opentak-bridge"`) ->
ChaCha20-Poly1305 IETF AEAD, wire format `base64(nonce(12) || ciphertext ||
tag(16))`. AAD binds direction + message type so a captured event ciphertext
can't be replayed as a command or vice versa.

## Setup

1. Generate this side's keypair:
   ```bash
   python -m ots_meshbeacon_bridge.keygen
   ```
2. Set the following environment variables for OTS:

   | Variable | Description |
   |---|---|
   | `OTS_MESHBEACON_PRIVATE_KEY` | This plugin's X25519 private key (base64), from `keygen` |
   | `OTS_MESHBEACON_PUBLIC_KEY` | This plugin's X25519 public key (hex), from `keygen` |
   | `OTS_MESHBEACON_PEER_PUBLIC_KEY` | MeshBeacon's `OPENTAK_BRIDGE_PUBLIC_KEY` (hex), from `php artisan opentak:keygen` |
   | `OTS_MESHBEACON_MQTT_HOST` | Hostname/IP of MeshBeacon's Mosquitto broker |
   | `OTS_MESHBEACON_MQTT_PORT` | Default `1883` |
   | `OTS_MESHBEACON_MQTT_USERNAME` / `OTS_MESHBEACON_MQTT_PASSWORD` | Optional, if the broker requires auth |
   | `OTS_MESHBEACON_EVENT_TOPIC` | Default `hub/opentak/event` |
   | `OTS_MESHBEACON_COMMAND_TOPIC` | Default `hub/opentak/command` |

3. Paste this plugin's public key into MeshBeacon's `OPENTAK_SERVER_PUBLIC_KEY`,
   set `OPENTAK_BRIDGE_ENABLED=true` in MeshBeacon's `.env`, and restart its
   `mqtt-worker` service.
4. Install this package into OTS's environment (`pip install .` from this
   directory, or add it to OTS's `pyproject.toml` dependencies) and enable
   the plugin from OTS's plugin manager UI.

## Telemetry fields

Each Duck update forwarded from MeshBeacon includes, when available:

- `lat` / `lon` -- required; events without coordinates are dropped.
- `altitude` -- metres, mapped to the CoT point's `hae`.
- `speed` -- MeshBeacon reports km/h; converted to m/s for the CoT `<track speed>` attribute.
- `heading` -- degrees, mapped to `<track course>`.
- `battery` -- percent, mapped to `<status battery>`.
- `rssi` / `snr` -- radio link quality; no standard CoT element exists for
  these, so they're carried in a vendor `<meshbeacon rssi="" snr=""/>`
  detail element (ignored by TAK clients that don't recognize it).
- `duck_id` -- the Duck's node name/ID; used as both the CoT `uid` suffix
  and the `<contact callsign>`, so it shows up as the marker's label in ATAK/WinTAK.
- `sos` -- when set, adds `<emergency alert="true" type="MeshBeacon SOS"/>`,
  which OTS's CoT parser turns into an Alert.
- `sos_cancel` -- sent as its own minimal event (duck_id/lat/lon/timestamp
  only) when an operator marks the incident resolved in MeshBeacon's
  dashboard; adds `<emergency cancel="true"/>`, which closes out the
  matching OTS Alert's `cancel_time` instead of it staying active forever.
- `chat` -- when set, `message` is a genuine field-device message (free
  text typed on the companion phone app, or a canned "Roger" from
  triple-clicking the physical button -- see MeshBeacon's
  `DuckPayloadDecoder::statusMsgToLegacyText()`), and is additionally sent
  as a real ATAK GeoChat entry ("All Chat Rooms"), not just marker
  remarks. Routine telemetry (GPS/sensor pings, SOS) never sets this, so
  it doesn't spam the chat log.

