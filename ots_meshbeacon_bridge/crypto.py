from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

NONCE_LENGTH = 12
TAG_LENGTH = 16

# Must match MeshBeacon's OpenTakCryptoService::HKDF_INFO exactly.
HKDF_INFO = b"meshbeacon-opentak-bridge"

MSG_TYPE_EVENT = 0x01
MSG_TYPE_COMMAND = 0x02

# Must match OpenTakCryptoService's direction constants exactly, byte for
# byte -- these are folded into the AEAD's AAD, not encrypted themselves.
DIRECTION_TO_OPENTAK = b"meshbeacon->opentakserver"
DIRECTION_FROM_OPENTAK = b"opentakserver->meshbeacon"


class OpenTakCrypto:
    """
    Mirrors MeshBeacon's app/Services/OpenTakCryptoService.php bit-for-bit:
    X25519 ECDH -> HKDF-SHA256 -> ChaCha20-Poly1305 IETF AEAD. Wire format:
    base64(nonce(12) || ciphertext || tag(16)).

    This plugin decrypts events MeshBeacon encrypted with encryptEvent()
    and encrypts commands MeshBeacon will decrypt with decryptCommand() --
    see the AAD directions below, which must match exactly or the AEAD tag
    will never verify.
    """

    def __init__(
        self,
        private_key_b64: str | None,
        public_key_hex: str | None,
        peer_public_key_hex: str | None,
    ) -> None:
        self._private_key_b64 = private_key_b64 or ""
        self._public_key_hex = (public_key_hex or "").lower()
        self._peer_public_key_hex = (peer_public_key_hex or "").lower()

    def is_configured(self) -> bool:
        return (
            self._is_hex32(self._public_key_hex)
            and bool(self._private_key_b64)
            and self._is_hex32(self._peer_public_key_hex)
        )

    @staticmethod
    def _is_hex32(value: str) -> bool:
        if len(value) != 64:
            return False
        try:
            binascii.unhexlify(value)
            return True
        except binascii.Error:
            return False

    def _private_key(self) -> X25519PrivateKey:
        raw = base64.b64decode(self._private_key_b64)
        return X25519PrivateKey.from_private_bytes(raw)

    def _peer_public_key(self) -> X25519PublicKey:
        raw = bytes.fromhex(self._peer_public_key_hex)
        return X25519PublicKey.from_public_bytes(raw)

    def _derive_shared_key(self) -> bytes:
        shared = self._private_key().exchange(self._peer_public_key())
        return HKDF(algorithm=SHA256(), length=32, salt=None, info=HKDF_INFO).derive(shared)

    @staticmethod
    def _build_aad(direction: bytes, msg_type: int) -> bytes:
        return direction + bytes([msg_type])

    def decrypt_event(self, payload_b64: str) -> bytes | None:
        """Decrypt an event MeshBeacon encrypted with encryptEvent()."""
        return self._decrypt(payload_b64, self._build_aad(DIRECTION_TO_OPENTAK, MSG_TYPE_EVENT))

    def encrypt_command(self, plaintext: bytes) -> str | None:
        """Encrypt a command for MeshBeacon to decrypt with decryptCommand()."""
        return self._encrypt(plaintext, self._build_aad(DIRECTION_FROM_OPENTAK, MSG_TYPE_COMMAND))

    def _encrypt(self, plaintext: bytes, aad: bytes) -> str | None:
        if not self.is_configured():
            return None

        key = self._derive_shared_key()
        nonce = os.urandom(NONCE_LENGTH)
        ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)

        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def _decrypt(self, payload_b64: str, aad: bytes) -> bytes | None:
        if not self.is_configured():
            return None

        try:
            payload = base64.b64decode(payload_b64, validate=True)
        except (binascii.Error, ValueError):
            return None

        if len(payload) < NONCE_LENGTH + TAG_LENGTH:
            return None

        nonce = payload[:NONCE_LENGTH]
        ciphertext_and_tag = payload[NONCE_LENGTH:]
        key = self._derive_shared_key()

        try:
            return ChaCha20Poly1305(key).decrypt(nonce, ciphertext_and_tag, aad)
        except InvalidTag:
            return None
