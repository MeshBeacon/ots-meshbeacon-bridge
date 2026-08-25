# ots-meshbeacon-plugin

OpenTAKServer plugin that bridges [MeshBeacon](https://github.com/MeshBeacon/meshbeacon)
Duck telemetry into OpenTAKServer as CoT events, and relays operator commands
back to the mesh -- all over an encrypted MQTT link. See MeshBeacon's
`docs/OPENTAK_BRIDGE.md` for the matching server-side setup.

See this repo's [wiki](https://github.com/MeshBeacon/ots-meshbeacon-plugin/wiki)
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
4. GeoChat replies typed in ATAK/WinTAK/iTAK directly to a Duck's contact
   are relayed automatically too: the plugin binds its own queue to OTS's
   `cot_parser` RabbitMQ exchange (the same one `EudHandler` and the
   Meshtastic controller publish every parsed CoT event to) and watches for
   outgoing GeoChat events (`b-t-f`) addressed to a `meshbeacon-<duck_id>`
   contact, forwarding the message text through step 3 above. Only 1:1 DMs
   to a specific Duck are relayed this way -- broadcasts to "All Chat
   Rooms" are not, to avoid spamming every Duck on the mesh.

## Replying to a Duck -- read this before an incident

Every message a Duck sends in arrives in **"All Chat Rooms"** (broadcast),
not a private DM -- this is intentional: a Duck has no way to address a
message to a specific human operator, and in a disaster/offgrid scenario
the priority is that *whoever is on shift* sees it immediately, not that
it's routed to a pre-selected recipient. (A dedicated SOS still raises a
real OTS Alert independently of chat, so an emergency doesn't depend on
someone noticing the broadcast.)

**But replying only works from a direct 1:1 chat with that Duck's contact,
not by typing in "All Chat Rooms".** The plugin's GeoChat relay (item 4
above) only watches for private DMs addressed to the Duck's
`meshbeacon-<duck_id>` contact -- a reply typed inline in the broadcast
room is never seen by the relay and will silently never reach the Duck.

To reply to a Duck from ATAK/WinTAK/iTAK:

1. Open the **Contacts** list (not the "All Chat Rooms" tab).
2. Find the Duck (it appears as an EUD contact using its `duck_id` as the
   callsign, once it's sent at least one telemetry update).
3. Start a **direct/private chat** with that contact and send the message
   there.

If your operators aren't used to this distinction, prefer sending replies
through the admin `/api/meshbeacon/command` route (or a dashboard button
that calls it) instead of training everyone on the DM-vs-broadcast
convention under stress.

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

