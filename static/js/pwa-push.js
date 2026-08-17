// pwa-push.js: Client-side Web Push notification subscription & preference management for Genmon PWA

(function() {
    'use strict';

    function urlBase64ToUint8Array(base64String) {
        var padding = '='.repeat((4 - base64String.length % 4) % 4);
        var base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
        var rawData = window.atob(base64);
        var outputArray = new Uint8Array(rawData.length);
        for (var i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    window.GenmonPWA = {
        sub: null,

        init: function() {
            if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
                console.log('Web Push is not supported in this browser environment.');
                return;
            }
            this.checkSubscriptionState();
        },

        checkSubscriptionState: function() {
            var self = this;
            if (!('serviceWorker' in navigator)) {
                self.updateUIStatus(false);
                return;
            }
            navigator.serviceWorker.register('/sw.js').then(function() {
                return navigator.serviceWorker.ready;
            }).then(function(reg) {
                return reg.pushManager.getSubscription();
            }).then(function(sub) {
                self.sub = sub;
                self.updateUIStatus(sub !== null);
            }).catch(function(err) {
                console.log('Push state check:', err);
                self.updateUIStatus(false);
            });
        },

        updateUIStatus: function(isSubscribed) {
            var statusEl = document.getElementById('webpush-status-label');
            var btnToggle = document.getElementById('btn-webpush-toggle');
            if (statusEl) {
                statusEl.textContent = isSubscribed ? 'Subscribed (Active)' : 'Not Subscribed';
                statusEl.className = isSubscribed ? 'badge bg-success' : 'badge bg-secondary';
            }
            if (btnToggle) {
                btnToggle.textContent = isSubscribed ? 'Disable Push Alerts' : 'Enable Push Alerts';
                btnToggle.className = isSubscribed ? 'btn btn-outline-danger btn-sm' : 'btn btn-primary btn-sm';
            }
        },

        togglePush: function() {
            if (this.sub) {
                this.unsubscribe();
            } else {
                this.subscribe();
            }
        },

        subscribe: function() {
            var self = this;
            if (typeof Notification === 'undefined') {
                alert('Push Notifications are not supported in this browser window. On iOS Safari, you must tap "Share -> Add to Home Screen" first.');
                return;
            }

            if (Notification.permission === 'denied') {
                alert('Push Notifications are blocked in your browser settings for this site. Please enable Notification permissions in browser settings.');
                return;
            }

            var reqPromise = Notification.permission === 'default' ? Notification.requestPermission() : Promise.resolve(Notification.permission);

            reqPromise.then(function(perm) {
                if (perm !== 'granted') {
                    alert('Notification permission was not granted (' + perm + ').');
                    return;
                }

                $.getJSON('/api/webpush/vapid_key').done(function(res) {
                    if (!res || !res.public_key) {
                        alert('Could not retrieve VAPID key from server.');
                        return;
                    }
                    var convertedKey = urlBase64ToUint8Array(res.public_key);
                    navigator.serviceWorker.register('/sw.js').then(function() {
                        return navigator.serviceWorker.ready;
                    }).then(function(reg) {
                        return reg.pushManager.subscribe({
                            userVisibleOnly: true,
                            applicationServerKey: convertedKey
                        });
                    }).then(function(sub) {
                        self.sub = sub;
                        return $.ajax({
                            url: '/api/webpush/subscribe',
                            type: 'POST',
                            contentType: 'application/json',
                            data: JSON.stringify(sub.toJSON())
                        });
                    }).then(function() {
                        self.updateUIStatus(true);
                        alert('Success! Web Push alerts enabled for this device.');
                    }).catch(function(err) {
                        console.error('Subscription error:', err);
                        alert('Push Subscription error: ' + (err.message || err));
                    });
                }).fail(function(xhr, status, err) {
                    alert('Failed to reach VAPID key endpoint: ' + (err || status));
                });
            });
        },

        unsubscribe: function() {
            var self = this;
            if (!this.sub) return;
            var endpoint = this.sub.endpoint;
            this.sub.unsubscribe().then(function() {
                self.sub = null;
                $.ajax({
                    url: '/api/webpush/unsubscribe',
                    type: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({ endpoint: endpoint }),
                    success: function() {
                        self.updateUIStatus(false);
                        alert('Push alerts disabled for this device.');
                    }
                });
            });
        },

        sendTestNotification: function() {
            if (!this.sub) {
                alert('Please click "Enable Push Alerts" first to register this device before testing.');
                return;
            }
            var endpoint = this.sub.endpoint;
            $.ajax({
                url: '/api/webpush/test',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ endpoint: endpoint }),
                success: function() {
                    alert('Test notification sent! Check your lockscreen.');
                },
                error: function(xhr) {
                    var msg = (xhr.responseJSON && xhr.responseJSON.message) ? xhr.responseJSON.message : 'Failed to trigger test notification.';
                    alert('Push test result: ' + msg);
                }
            });
        },

        loadPreferences: function() {
            $.getJSON('/api/webpush/preferences', function(res) {
                if (res && res.preferences) {
                    var prefs = res.preferences;
                    for (var key in prefs) {
                        var el = document.getElementById('pref-' + key);
                        if (el) {
                            el.checked = !!prefs[key];
                        }
                    }
                }
            });
        },

        savePreferences: function() {
            var keys = ['notify_outage', 'notify_exercise', 'notify_error', 'notify_warning', 'notify_off_manual', 'notify_fuel', 'notify_pi_state', 'notify_sw_update', 'notify_info'];
            var payload = {};
            keys.forEach(function(k) {
                var el = document.getElementById('pref-' + k);
                if (el) {
                    payload[k] = el.checked;
                }
            });
            $.ajax({
                url: '/api/webpush/preferences',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify(payload),
                success: function() {
                    alert('Notification preferences saved successfully!');
                },
                error: function() {
                    alert('Error saving notification preferences.');
                }
            });
        }
    };

    $(document).ready(function() {
        window.GenmonPWA.init();
        window.GenmonPWA.loadPreferences();
    });

})();
