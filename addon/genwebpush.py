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

# Standard VAPID helper / Key generation
def EnsureVapidKeys():
    global config
    try:
        pub = config.ReadValue("vapid_public_key", default="")
        priv = config.ReadValue("vapid_private_key", default="")

        if not pub or not priv:
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

                config.WriteValue("vapid_public_key", pub)
                config.WriteValue("vapid_private_key", priv)
            except Exception as ex:
                log.error("Error generating VAPID keys via cryptography: " + str(ex))

        return pub, priv
    except Exception as e:
        log.error("Error in EnsureVapidKeys: " + str(e))
        return "", ""

# Subscriptions file management
def GetSubscriptionsFile():
    sub_file = config.ReadValue("subscriptions_file", default="")
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
    with sub_lock:
        # Avoid duplicates
        subscriptions = [s for s in subscriptions if s.get("endpoint") != endpoint]
        subscriptions.append(sub_data)
    SaveSubscriptions()
    return True

def RemoveSubscription(endpoint):
    global subscriptions
    with sub_lock:
        subscriptions = [s for s in subscriptions if s.get("endpoint") != endpoint]
    SaveSubscriptions()

# Push Notification Sending
def SendWebPushPayload(title, message, category="info", icon="/icons/icon-192x192.png", target_endpoint=None):
    global subscriptions
    try:
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
            claims = {"sub": config.ReadValue("vapid_claims_sub", default="mailto:admin@genmon.local")}
            vapid_key_file_data = {
                "public_key": pub,
                "private_key": priv
            }
        except ImportError:
            webpush = None

        targets = subscriptions if not target_endpoint else [s for s in subscriptions if s.get("endpoint") == target_endpoint]
        if not targets:
            log.info("No web push subscriptions registered.")
            return True

        to_remove = []
        for sub in list(targets):
            endpoint = sub.get("endpoint")
            if not endpoint:
                continue
            try:
                if webpush:
                    webpush(
                        subscription_info=sub,
                        data=json.dumps({
                            "title": title,
                            "body": message,
                            "category": category,
                            "icon": icon
                        }),
                        vapid_private_key=priv,
                        vapid_claims={"sub": config.ReadValue("vapid_claims_sub", default="mailto:admin@genmon.local")},
                        ttl=86400
                    )
                else:
                    req = urllib.request.Request(
                        endpoint,
                        data=payload_data,
                        headers={"Content-Type": "application/json", "TTL": "86400"}
                    )
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        pass
            except Exception as ex_push:
                err_str = str(ex_push)
                if "404" in err_str or "410" in err_str:
                    to_remove.append(endpoint)
                else:
                    log.error("Failed to send push to endpoint " + str(endpoint) + ": " + err_str)

        for ep in to_remove:
            RemoveSubscription(ep)

        return True
    except Exception as e:
        log.error("Error in SendWebPushPayload: " + str(e))
        return False

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
