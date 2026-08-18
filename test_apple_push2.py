#!/usr/bin/env python3
import os
import json
import time
import base64
import binascii
import requests
import http_ece
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from urllib.parse import urlparse

def b64urldecode(b64str):
    b64str = b64str.strip()
    b64str += "=" * ((4 - len(b64str) % 4) % 4)
    return base64.urlsafe_b64decode(b64str)

def GenerateAppleJWT(vapid_private_key_b64, sub, aud):
    try:
        raw_priv = b64urldecode(vapid_private_key_b64)
        dkey = int(binascii.hexlify(raw_priv), 16)
        priv_key = ec.derive_private_key(dkey, ec.SECP256R1())
        
        header = {"typ": "JWT", "alg": "ES256"}
        claims = {"aud": aud, "sub": sub, "exp": int(time.time()) + 12 * 3600}
        
        header_enc = base64.urlsafe_b64encode(json.dumps(header, separators=(',', ':')).encode('utf-8')).decode('utf-8').rstrip("=")
        claims_enc = base64.urlsafe_b64encode(json.dumps(claims, separators=(',', ':')).encode('utf-8')).decode('utf-8').rstrip("=")
        token = f"{header_enc}.{claims_enc}"
        
        rsig = priv_key.sign(token.encode('utf-8'), ec.ECDSA(hashes.SHA256()))
        
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        r, s = decode_dss_signature(rsig)
        sig_raw = r.to_bytes(32, 'big') + s.to_bytes(32, 'big')
        sig_enc = base64.urlsafe_b64encode(sig_raw).decode('utf-8').rstrip("=")
        
        pub_bytes = priv_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        k_enc = base64.urlsafe_b64encode(pub_bytes).decode('utf-8').rstrip("=")
        
        return f"vapid t={token}.{sig_enc}, k={k_enc}"
    except Exception as e:
        print(f"Error generating JWT: {e}")
        return None

def test_apple_push():
    print("=== Apple APNs Standalone Diagnostic ===")
    
    # 1. Read VAPID keys
    vapid_priv = None
    conf_path = "/etc/genmon/genwebpush.conf"
    if not os.path.exists(conf_path):
        conf_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conf", "genwebpush.conf")
    
    if not os.path.exists(conf_path):
        print(f"FAILED: Cannot find {conf_path}")
        return
        
    print(f"Reading VAPID config from: {conf_path}")
    with open(conf_path, "r") as f:
        for line in f:
            if line.startswith("vapid_private_key"):
                vapid_priv = line.split("=", 1)[1].strip()
                
    if not vapid_priv:
        print("FAILED: Could not extract vapid_private_key from config.")
        return
        
    print(f"Loaded VAPID Private Key (starts with {vapid_priv[:4]}...)")

    # 2. Read Subscriptions
    subs_path = "/etc/genmon/data/webpush_subscriptions.json"
    if not os.path.exists(subs_path):
        subs_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "webpush_subscriptions.json")
        
    if not os.path.exists(subs_path):
        print(f"FAILED: Cannot find {subs_path}")
        return
        
    print(f"Reading subscriptions from: {subs_path}")
    with open(subs_path, "r") as f:
        subs = json.load(f)
        
    apple_sub = None
    for sub in subs:
        if "apple.com" in sub.get("endpoint", ""):
            apple_sub = sub
            break
            
    if not apple_sub:
        print("FAILED: No Apple Push Subscription found in the file! Please subscribe via the iPad first.")
        return
        
    endpoint = apple_sub["endpoint"]
    print(f"Found Apple Endpoint: {endpoint}")
    
    p256dh_b64 = apple_sub.get("keys", {}).get("p256dh")
    auth_b64 = apple_sub.get("keys", {}).get("auth")
    if not p256dh_b64 or not auth_b64:
        print("FAILED: Subscription is missing p256dh or auth keys.")
        return

    p256dh = b64urldecode(p256dh_b64)
    auth = b64urldecode(auth_b64)

    # 3. Construct JWT
    parsed = urlparse(endpoint)
    aud_claim = f"{parsed.scheme}://{parsed.netloc}"
    sub_claim = "https://github.com/wizofoz244/genmon"
    
    print("Constructing JWT Header natively...")
    auth_header = GenerateAppleJWT(vapid_priv, sub_claim, aud_claim)
    print(f"Authorization Header generated successfully. Length: {len(auth_header)}")
    print(f"Header Preview: {auth_header[:50]}...{auth_header[-20:]}")

    # 4. Encrypt Payload
    print("Encrypting payload using RFC 8291 (aes128gcm)...")
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

    # 5. Send POST Request
    req_headers = {
        "Authorization": auth_header,
        "Content-Encoding": "aes128gcm",
        "TTL": "3600"
    }
    
    print("Sending POST request to Apple APNs...")
    resp = requests.post(endpoint, data=encrypted_data, headers=req_headers, timeout=5)
    print(f"\n--- HTTP {resp.status_code} {resp.reason} ---")
    print(f"Response Body: {resp.text}")
    print("--------------------------------\n")
    
    if resp.status_code == 201:
        print("SUCCESS! Apple accepted the custom JWT signature.")
    else:
        print("FAILED: Apple still rejected the token.")

if __name__ == "__main__":
    test_apple_push()
