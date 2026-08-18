#!/usr/bin/env python3
"""
Apple APNs Web Push Standalone Diagnostic Script (Variant 2).
Validates:
1. RFC 8292 Base64URL subscriber key decoding (p256dh and auth).
2. Elimination of 'ValueError: Unsupported elliptic curve point type' during http_ece.encrypt.
3. RFC 8292 / Apple APNs compliant ES256 JWT construction with exact 64-byte R|S signature.
4. Mathematical verification of ECDSA signature using cryptography P-256.
"""

import base64
import binascii
import json
import os
import sys
import time
from urllib.parse import urlparse

try:
    import http_ece
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from cryptography.hazmat.primitives import hashes, serialization
    import requests
except ImportError as e:
    print(f"Missing required dependency: {e}")
    sys.exit(1)


def b64urldecode(b64str):
    """Safely decode a base64 or base64url string with missing padding to raw bytes."""
    if b64str is None:
        return b""
    if isinstance(b64str, (bytes, bytearray)):
        if len(b64str) in [16, 32] or (len(b64str) == 65 and b64str[0] == 0x04):
            return bytes(b64str)
        try:
            b64str = b64str.decode("ascii")
        except (UnicodeDecodeError, Exception):
            return bytes(b64str)
    b64str = str(b64str).strip().strip("'\"").replace("\r", "").replace("\n", "").replace(" ", "").rstrip("=")
    rem = len(b64str) % 4
    if rem > 0:
        b64str += "=" * (4 - rem)
    return base64.urlsafe_b64decode(b64str)


def b64urlencode(raw_bytes):
    """Encode raw bytes to unpadded base64url ASCII string."""
    if isinstance(raw_bytes, str):
        raw_bytes = raw_bytes.encode("utf-8")
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8").rstrip("=")


def GenerateAppleJWT(vapid_private_key, sub, aud):
    """
    Generate an RFC 8292 conforming VAPID Authorization JWT for Apple APNs.
    """
    try:
        priv_key = None
        if hasattr(vapid_private_key, "private_key"):
            priv_key = vapid_private_key.private_key
        elif isinstance(vapid_private_key, ec.EllipticCurvePrivateKey):
            priv_key = vapid_private_key
        elif isinstance(vapid_private_key, (bytes, bytearray)) and len(vapid_private_key) == 32:
            priv_key = ec.derive_private_key(int.from_bytes(bytes(vapid_private_key), "big"), ec.SECP256R1())
        elif isinstance(vapid_private_key, (bytes, bytearray)) and b"-----BEGIN" in vapid_private_key:
            priv_key = serialization.load_pem_private_key(bytes(vapid_private_key), password=None)
        elif isinstance(vapid_private_key, str) and "-----BEGIN" in vapid_private_key:
            priv_key = serialization.load_pem_private_key(vapid_private_key.encode("utf-8"), password=None)
        elif isinstance(vapid_private_key, (str, bytes, bytearray)):
            raw_priv = b64urldecode(vapid_private_key)
            if len(raw_priv) == 32:
                priv_key = ec.derive_private_key(int.from_bytes(raw_priv, "big"), ec.SECP256R1())

        if priv_key is None:
            raise ValueError("Unable to load private key from provided input")

        header = {"typ": "JWT", "alg": "ES256"}
        exp_time = int(time.time()) + 12 * 3600
        claims = {
            "aud": aud,
            "sub": sub,
            "exp": exp_time
        }

        header_enc = b64urlencode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
        claims_enc = b64urlencode(json.dumps(claims, separators=(',', ':')).encode('utf-8'))
        signing_input = f"{header_enc}.{claims_enc}".encode('utf-8')

        rsig_der = priv_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))

        r, s = decode_dss_signature(rsig_der)
        sig_raw = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
        sig_enc = b64urlencode(sig_raw)

        pub_key = priv_key.public_key()
        pub_key.verify(rsig_der, signing_input, ec.ECDSA(hashes.SHA256()))

        pub_bytes = pub_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        k_enc = b64urlencode(pub_bytes)

        token = f"{header_enc}.{claims_enc}.{sig_enc}"
        return f"vapid t={token}, k={k_enc}"
    except Exception as e:
        print(f"Error generating Apple JWT: {e}")
        return None


def test_apple_push():
    print("=== Apple APNs Standalone Diagnostic (test_apple_push2.py) ===")

    vapid_priv = None
    conf_path = "/etc/genmon/genwebpush.conf"
    if not os.path.exists(conf_path):
        conf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conf", "genwebpush.conf")

    if os.path.exists(conf_path):
        with open(conf_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("vapid_private_key"):
                    vapid_priv = line.split("=", 1)[1].strip()

    if not vapid_priv:
        test_key = ec.generate_private_key(ec.SECP256R1())
        vapid_priv = b64urlencode(test_key.private_numbers().private_value.to_bytes(32, 'big'))

    print(f"Loaded VAPID Private Key (starts with {vapid_priv[:4]}...)")

    subs_paths = [
        "/etc/genmon/data/webpush_subscriptions.json",
        "/etc/genmon/webpush_subscriptions.json",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "webpush_subscriptions.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "conf", "webpush_subscriptions.json"),
    ]
    subs = []
    for sp in subs_paths:
        if os.path.exists(sp):
            try:
                with open(sp, "r", encoding="utf-8") as f:
                    subs = json.load(f)
                break
            except Exception:
                pass

    apple_sub = None
    for sub in subs:
        if "apple.com" in sub.get("endpoint", ""):
            apple_sub = sub
            break

    if not apple_sub:
        apple_sub = {
            "endpoint": "https://push.apple.com/sub/mock_ios_device_id_abcdef123456",
            "device_name": "Mock Apple Device",
            "keys": {
                "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                "auth": "tBHItJI5svbpez7KI4CCXg"
            }
        }

    endpoint = apple_sub["endpoint"]
    p256dh_b64 = apple_sub.get("keys", {}).get("p256dh")
    auth_b64 = apple_sub.get("keys", {}).get("auth")

    p256dh = b64urldecode(p256dh_b64)
    auth = b64urldecode(auth_b64)

    parsed = urlparse(endpoint)
    aud_claim = f"{parsed.scheme}://{parsed.netloc}"
    sub_claim = "https://github.com/wizofoz244/genmon"

    auth_header = GenerateAppleJWT(vapid_priv, sub_claim, aud_claim)
    assert auth_header is not None, "Failed to generate Apple JWT"
    print(f"Authorization Header generated successfully. Length: {len(auth_header)}")

    payload = {"title": "Diagnostic Test", "body": "If you see this, Apple APNs works natively!"}
    salt = os.urandom(16)
    server_key = ec.generate_private_key(ec.SECP256R1())

    encrypted_data = http_ece.encrypt(
        json.dumps(payload).encode('utf-8'),
        salt=salt,
        private_key=server_key,
        dh=p256dh,
        auth_secret=auth,
        version="aes128gcm"
    )
    print(f"Encrypted payload length: {len(encrypted_data)} bytes")

    if "mock_ios_device" not in endpoint:
        req_headers = {
            "Authorization": auth_header,
            "Content-Encoding": "aes128gcm",
            "TTL": "3600"
        }
        resp = requests.post(endpoint, data=encrypted_data, headers=req_headers, timeout=5)
        print(f"HTTP {resp.status_code} {resp.reason}")
    else:
        print("Mock test completed successfully with 0 errors.")


if __name__ == "__main__":
    test_apple_push()
