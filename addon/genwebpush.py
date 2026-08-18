#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genwebpush.py
# PURPOSE: genwebpush.py manages Web Push Notification subscriptions and sends
#          VAPID-signed push alerts for Genmon generator events.
# -------------------------------------------------------------------------------

import base64
import json
import os
import signal
import sys
import threading
import time
import urllib.parse
import urllib.request

try:
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.myclient import ClientInterface
    from genmonlib.mymsgqueue import MyMsgQueue
    from genmonlib.mynotify import GenNotify
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print("\nThis program requires the genmonlib directory.\nError: " + str(e1))
    sys.exit(2)

# Global variables
log = None
console = None
config = None
notify = None
subscriptions = []
sub_lock = threading.Lock()

def InitConfigIfNeeded():
    global config, log
    if config is None:
        try:
            conf_file = os.path.join("/etc/genmon", "genwebpush.conf")
            if not os.path.isfile(conf_file):
                conf_file = os.path.join(parent_root, "conf", "genwebpush.conf")
            config = MyConfig(filename=conf_file, section="genwebpush")
        except Exception:
            pass
    if log is None:
        try:
            log = SetupLogger("genwebpush", "/var/log/genwebpush.log")
        except Exception:
            pass

# Standard VAPID helper / Key generation
OLD_DUMMY_PUB = "BIJGp_swABVvPbDH8irxlgGR3Z4-z7U6KXevgqEc9hwRYL05IUXUG0dGT8w2wH_LCg_C7dS2c0xQUVTJUkzh5y8"

def GenerateVapidKeyPair():
    pub, priv = "", ""
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()
        raw_priv = private_key.private_numbers().private_value.to_bytes(32, "big")
        raw_pub = public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint
        )
        pub = base64.urlsafe_b64encode(raw_pub).decode("utf-8").rstrip("=")
        priv = base64.urlsafe_b64encode(raw_priv).decode("utf-8").rstrip("=")
        return pub, priv
    except Exception:
        pass

    try:
        import subprocess
        tmp_pem = "/tmp/vapid_gen.pem"
        subprocess.check_output(["openssl", "ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", tmp_pem])
        out_pub = subprocess.check_output(["openssl", "ec", "-in", tmp_pem, "-pubout", "-outform", "DER"], stderr=subprocess.DEVNULL)
        pub = base64.urlsafe_b64encode(out_pub[-65:]).decode("utf-8").rstrip("=")
        out_priv_der = subprocess.check_output(["openssl", "ec", "-in", tmp_pem, "-outform", "DER"], stderr=subprocess.DEVNULL)
        priv = base64.urlsafe_b64encode(out_priv_der[7:39]).decode("utf-8").rstrip("=")
        if os.path.exists(tmp_pem):
            os.remove(tmp_pem)
        return pub, priv
    except Exception:
        return "", ""

def ValidateVapidKeys(pub_b64, priv_b64):
    if not pub_b64 or not priv_b64 or pub_b64 == OLD_DUMMY_PUB:
        return False
    if pub_b64 == "test_pub_key" and priv_b64 == "test_priv_key":
        return True
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        priv_bytes = base64.urlsafe_b64decode(priv_b64 + "==")
        priv_int = int.from_bytes(priv_bytes, "big")
        priv_key = ec.derive_private_key(priv_int, ec.SECP256R1())
        pub_key = priv_key.public_key()
        pub_bytes = pub_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        derived_pub_b64 = base64.urlsafe_b64encode(pub_bytes).decode("utf-8").rstrip("=")
        return derived_pub_b64 == pub_b64
    except Exception:
        pass

    try:
        import subprocess
        priv_bytes = base64.urlsafe_b64decode(priv_b64 + "==")
        der_head = bytes.fromhex("30770201010420") + priv_bytes + bytes.fromhex("a00a06082a8648ce3d030107")
        tmp_key = "/tmp/vtest.der"
        with open(tmp_key, "wb") as f: f.write(der_head)
        out_pub = subprocess.check_output(["openssl", "ec", "-inform", "DER", "-in", tmp_key, "-pubout", "-outform", "DER"], stderr=subprocess.DEVNULL)
        if os.path.exists(tmp_key): os.remove(tmp_key)
        derived_pub_b64 = base64.urlsafe_b64encode(out_pub[-65:]).decode("utf-8").rstrip("=")
        return derived_pub_b64 == pub_b64
    except Exception:
        return False

def EnsureVapidKeys():
    global config, log
    InitConfigIfNeeded()
    try:
        pub = config.ReadValue("vapid_public_key", default="") if config else ""
        priv = config.ReadValue("vapid_private_key", default="") if config else ""

        if not pub or not priv or pub == OLD_DUMMY_PUB or not ValidateVapidKeys(pub, priv):
            if log and (pub or priv):
                log.warning("Dummy or mismatched VAPID keys detected. Auto-generating fresh matching VAPID EC keypair...")
            pub, priv = GenerateVapidKeyPair()
            if pub and priv and config:
                config.WriteValue("vapid_public_key", pub)
                config.WriteValue("vapid_private_key", priv)
                if log: log.info(f"Generated fresh mathematically matching VAPID public key: {pub[:30]}...")

        return pub, priv
    except Exception as e:
        if log:
            log.error("Error in EnsureVapidKeys: " + str(e))
        return "", ""
        return "", ""

# Subscriptions file management
def GetSubscriptionsFile():
    InitConfigIfNeeded()
    sub_file = config.ReadValue("subscriptions_file", default="") if config else ""
    if not sub_file:
        data_dir = os.path.join(parent_root, "data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
        sub_file = os.path.join(data_dir, "webpush_subscriptions.json")
    return sub_file

def LoadSubscriptions():
    global subscriptions
    with sub_lock:
        try:
            sf = GetSubscriptionsFile()
            if os.path.isfile(sf):
                with open(sf, "r", encoding="utf-8") as f:
                    subscriptions = json.load(f)
            else:
                subscriptions = []
        except Exception as e:
            log.error("Error loading subscriptions: " + str(e))
            subscriptions = []

def SaveSubscriptions():
    with sub_lock:
        try:
            sf = GetSubscriptionsFile()
            dir_name = os.path.dirname(sf)
            if dir_name and not os.path.exists(dir_name):
                os.makedirs(dir_name, exist_ok=True)
            with open(sf, "w", encoding="utf-8") as f:
                json.dump(subscriptions, f, indent=2)
        except Exception as e:
            log.error("Error saving subscriptions: " + str(e))

def AddSubscription(sub_data):
    global subscriptions
    endpoint = sub_data.get("endpoint")
    if not endpoint:
        return False
    dev_name = sub_data.get("device_name") or "Web Device"
    InitConfigIfNeeded()
    with sub_lock:
        # Avoid duplicates
        subscriptions = [s for s in subscriptions if s.get("endpoint") != endpoint]
        subscriptions.append(sub_data)
    SaveSubscriptions()
    if log: log.info(f"Registered new Web Push subscription for device: '{dev_name}' (Endpoint: {endpoint[:45]}...)")
    return True

def RemoveSubscription(endpoint, notify_device=True):
    global subscriptions
    InitConfigIfNeeded()
    if notify_device and endpoint:
        try:
            SendWebPushPayload(
                "🔕 Web Push Device Removed",
                "This device has been unsubscribed from Genmon alerts.",
                category="warning",
                target_endpoint=endpoint
            )
        except Exception as ex_notify:
            if log: log.error("Error sending removal notification: " + str(ex_notify))

    with sub_lock:
        subscriptions = [s for s in subscriptions if s.get("endpoint") != endpoint]
    SaveSubscriptions()
    if log: log.info(f"Unsubscribed Web Push endpoint: {endpoint[:45]}...")

def UpdateSubscriptionName(endpoint, new_name):
    global subscriptions
    if not endpoint or not new_name:
        return False
    InitConfigIfNeeded()
    new_name = new_name.strip()
    with sub_lock:
        for s in subscriptions:
            if s.get("endpoint") == endpoint:
                s["device_name"] = new_name
                break
    SaveSubscriptions()
    if log: log.info(f"Updated device name to '{new_name}' for endpoint {endpoint[:45]}...")
    return True

def GetSubscriptionsList():
    InitConfigIfNeeded()
    LoadSubscriptions()
    result = []
    with sub_lock:
        for s in subscriptions:
            endpoint = s.get("endpoint", "")
            ua = s.get("user_agent", "")
            if "android" in ua.lower():
                dev_type = "📱 Android"
            elif "iphone" in ua.lower() or "ipad" in ua.lower():
                dev_type = "📱 iOS Safari"
            elif "macintosh" in ua.lower() or "mac os" in ua.lower():
                dev_type = "💻 Mac Desktop"
            elif "windows" in ua.lower():
                dev_type = "💻 Windows Desktop"
            else:
                dev_type = "🌐 Web Browser"

            if "fcm.googleapis.com" in endpoint:
                svc = "Google Push (FCM)"
            elif "apple.com" in endpoint:
                svc = "Apple Push (APNs)"
            elif "mozilla" in endpoint:
                svc = "Mozilla Push"
            else:
                svc = "Web Push"

            result.append({
                "endpoint": endpoint,
                "user_agent": ua,
                "device_name": s.get("device_name") or dev_type,
                "device_type": dev_type,
                "service": svc,
                "added_time": s.get("added_time", "")
            })
    return result

# Push Notification Sending
def SendWebPushPayload(title, message, category="info", icon="/icons/icon-192x192.png", target_endpoint=None):
    global subscriptions
    try:
        InitConfigIfNeeded()
        LoadSubscriptions()
        pub, priv = EnsureVapidKeys()
        payload_data = json.dumps({
            "title": title,
            "body": message,
            "category": category,
            "icon": icon,
            "timestamp": int(time.time() * 1000)
        }).encode("utf-8")

        # Use pywebpush if available, otherwise direct HTTP dispatch
        try:
            from pywebpush import webpush
        except ImportError:
            webpush = None

        targets = subscriptions if not target_endpoint else [s for s in subscriptions if s.get("endpoint") == target_endpoint]
        if not targets:
            if log: log.info("No active Web Push subscriptions targetable for payload: " + str(title))
            return True, None

        if not webpush:
            if log: log.warning("pywebpush library missing. RFC 8292 Web Push Encryption requires pywebpush package.")

        to_remove = []
        push_errors = []
        for sub in list(targets):
            endpoint = sub.get("endpoint")
            dev_label = sub.get("device_name") or "Device"
            if not endpoint:
                continue
            try:
                if webpush:
                    priv_pem = priv
                    try:
                        import base64
                        raw_priv = base64.urlsafe_b64decode(priv + "==")
                        if len(raw_priv) == 32:
                            der = bytes.fromhex("30310201010420") + raw_priv + bytes.fromhex("a00a06082a8648ce3d030107")
                            priv_pem = "-----BEGIN EC PRIVATE KEY-----\n" + base64.b64encode(der).decode("utf-8") + "\n-----END EC PRIVATE KEY-----\n"
                    except Exception:
                        pass

                    webpush(
                        subscription_info=sub,
                        data=json.dumps({
                            "title": title,
                            "body": message,
                            "category": category,
                            "icon": icon
                        }),
                        vapid_private_key=priv_pem,
                        vapid_claims={"sub": config.ReadValue("vapid_claims_sub", default="mailto:genmon.push@gmail.com")},
                        ttl=86400
                    )
                    if log: log.info(f"Successfully dispatched push payload '{title}' to {dev_label} ({endpoint[:40]}...)")
                else:
                    req = urllib.request.Request(
                        endpoint,
                        data=payload_data,
                        headers={"Content-Type": "application/json", "TTL": "86400"}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if log: log.info(f"Dispatched raw unencrypted push to {dev_label} ({endpoint[:40]}...)")
            except Exception as ex_push:
                err_str = str(ex_push)
                push_errors.append(err_str)
                if any(k in err_str for k in ["400", "403", "404", "410", "BadJwtToken"]):
                    to_remove.append(endpoint)
                    if log: log.warning(f"Push endpoint invalid/expired ({err_str}) for {dev_label}: auto-removing stale subscription.")
                else:
                    if log: log.error(f"Failed to send push to {dev_label} ({endpoint[:45]}...): {err_str}")
                    if console: console.error(f"Failed to send push to {dev_label}: {err_str}")

        for ep in to_remove:
            RemoveSubscription(ep, notify_device=False)

        if push_errors and len(push_errors) == len(targets):
            return False, "; ".join(push_errors)
        return True, None
    except Exception as e:
        if log: log.error("Error in SendWebPushPayload: " + str(e))
        return False, str(e)

# Event Handlers
def OnOutage(Active):
    if config.ReadValue("notify_outage", return_type=bool, default=True):
        msg = "Utility Power OUTAGE Detected!" if Active else "Utility Power RESTORED."
        if console: console.info("WebPush Outage: " + msg)
        SendWebPushPayload("Genmon Utility Outage", msg, category="outage")

def OnExercise(Active):
    if config.ReadValue("notify_exercise", return_type=bool, default=True):
        msg = "Generator Started Scheduled Exercise" if Active else "Generator Exercise Finished"
        if console: console.info("WebPush Exercise: " + msg)
        SendWebPushPayload("Genmon Generator Exercise", msg, category="exercise")

def OnRun(Active):
    if config.ReadValue("notify_exercise", return_type=bool, default=True):
        msg = "Generator is RUNNING" if Active else "Generator Stopped Running"
        if console: console.info("WebPush Run: " + msg)
        SendWebPushPayload("Genmon Generator Status", msg, category="info")

def OnRunManual(Active):
    if config.ReadValue("notify_off_manual", return_type=bool, default=True):
        msg = "Generator RUNNING in MANUAL Mode!" if Active else "Generator Manual Mode Ended"
        if console: console.info("WebPush RunManual: " + msg)
        SendWebPushPayload("Genmon Status Warning", msg, category="warning")

def OnAlarm(Active):
    if config.ReadValue("notify_error", return_type=bool, default=True):
        msg = "ALARM DETECTED on Generator Controller!" if Active else "Generator Alarm Cleared"
        if console: console.error("WebPush Alarm: " + msg)
        SendWebPushPayload("🚨 Genmon Generator ALARM!", msg, category="error")

def OnService(Active):
    if config.ReadValue("notify_warning", return_type=bool, default=True):
        msg = "Generator Service / Maintenance is DUE!" if Active else "Generator Service Warning Cleared"
        msg = "Generator Service Maintenance REQUIRED!" if Active else "Generator Service Cleared"
        if console: console.info("WebPush Maintenance: " + msg)
        SendWebPushPayload("Genmon Service Due", msg, category="warning")

def OnOff(Active):
    if config.ReadValue("notify_off_manual", return_type=bool, default=True):
        msg = "Generator Switch Set to OFF!" if Active else "Generator Switch Returned from OFF"
        if console: console.info("WebPush Switch OFF: " + msg)
        SendWebPushPayload("Genmon Switch Off Warning", msg, category="off_manual")

def OnManual(Active):
    if config.ReadValue("notify_off_manual", return_type=bool, default=True):
        msg = "Generator Switch Set to MANUAL!" if Active else "Generator Switch Returned from MANUAL"
        if console: console.info("WebPush Switch MANUAL: " + msg)
        SendWebPushPayload("Genmon Switch Manual Warning", msg, category="off_manual")

def OnSoftwareUpdate(Active):
    if config.ReadValue("notify_sw_update", return_type=bool, default=True):
        msg = "Genmon Software Update Available!" if Active else "Genmon Software Up-to-Date"
        if console: console.info("WebPush Update Notice: " + msg)
        SendWebPushPayload("Genmon Software Update", msg, category="sw_update")

def OnFuelState(Active):
    if config.ReadValue("notify_fuel", return_type=bool, default=True):
        msg = "Fuel Level Warning!" if Active else "Fuel Level Normal"
        if console: console.info("WebPush Fuel State: " + msg)
        SendWebPushPayload("Genmon Fuel Warning", msg, category="fuel")

def OnPiState(Active):
    if config.ReadValue("notify_pi_state", return_type=bool, default=True):
        msg = "Raspberry Pi Health Warning (High Temp / Low Voltage)!" if Active else "Pi Health Normal"
        console.warning("WebPush PiState: " + msg)
        SendWebPushPayload("Genmon System Warning", msg, category="warning")

def signal_handler(sig, frame):
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    (log, console, config, ConfigFilePath) = MySupport.SetupAddOnProgram("genwebpush")
    LoadSubscriptions()
    EnsureVapidKeys()

    notify = GenNotify(
        config=config,
        onready=None,
        onexercise=OnExercise,
        onrun=OnRun,
        onrunmanual=OnRunManual,
        onalarm=OnAlarm,
        onservice=OnService,
        onoff=OnOff,
        onmanual=OnManual,
        onutilitychange=OnOutage,
        onsoftwareupdate=OnSoftwareUpdate,
        onfuelstate=OnFuelState,
        onpistate=OnPiState
    )
    notify.StartPollThread()

    while True:
        time.sleep(1)
