"""
Generates the OTS side's static X25519 keypair for the MeshBeacon bridge.

Usage:
    python -m ots_meshbeacon_bridge.keygen

Paste the printed values into your OTS environment (e.g. the systemd unit's
Environment= lines, or wherever OTS_* variables are configured), then paste
OTS_MESHBEACON_PUBLIC_KEY's value into MeshBeacon's OPENTAK_SERVER_PUBLIC_KEY.
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


def main() -> None:
    private_key = X25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    import base64

    print("OTS_MESHBEACON_PRIVATE_KEY=" + base64.b64encode(private_bytes).decode("ascii"))
    print("OTS_MESHBEACON_PUBLIC_KEY=" + public_bytes.hex())
    print()
    print("Paste OTS_MESHBEACON_PUBLIC_KEY's value into MeshBeacon's OPENTAK_SERVER_PUBLIC_KEY,")
    print("and MeshBeacon's OPENTAK_BRIDGE_PUBLIC_KEY (from 'php artisan opentak:keygen') into")
    print("OTS_MESHBEACON_PEER_PUBLIC_KEY here.")


if __name__ == "__main__":
    main()
