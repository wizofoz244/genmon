// -------------------------------------------------------------------------------
// PWA & Web Push Notification Handler v1.2.0 (Includes Inline Device Rename & WebPush Log)
// -------------------------------------------------------------------------------

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
                if (!sub) {
                    self.sub = null;
                    self.updateUIStatus(false);
                    return;
                }
                $.ajax({
                    url: '/api/webpush/subscriptions',
                    type: 'GET',
                    success: function(res) {
                        var activeEndpoints = (res && res.subscriptions) ? res.subscriptions.map(function(s) { return s.endpoint; }) : [];
                        if (activeEndpoints.indexOf(sub.endpoint) !== -1) {
                            self.sub = sub;
                            self.updateUIStatus(true);
                        } else {
                            sub.unsubscribe().catch(function() {});
                            self.sub = null;
                            self.updateUIStatus(false);
                        }
                    },
                    error: function() {
                        self.sub = sub;
                        self.updateUIStatus(true);
                    }
                });
            }).catch(function(err) {
                console.log('Push state check:', err);
                self.updateUIStatus(false);
            });
        },

        updateUIStatus: function(isSubscribed) {
            var statusEl = document.getElementById('webpush-status-label');
            var btnToggle = document.getElementById('btn-webpush-toggle');
            if (statusEl) {
                statusEl.textContent = isSubscribed ? 'Active' : 'Inactive';
                statusEl.className = isSubscribed ? 'badge bg-success' : 'badge bg-danger';
                statusEl.style.backgroundColor = isSubscribed ? 'var(--green, #4CAF50)' : 'var(--danger, #f05252)';
                statusEl.style.color = '#ffffff';
                statusEl.style.padding = '3px 8px';
                statusEl.style.borderRadius = '10px';
                statusEl.style.fontWeight = '600';
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
                        var customName = $('#webpush-device-name').val();
                        var subPayload = sub.toJSON();
                        subPayload.user_agent = navigator.userAgent;
                        subPayload.device_name = customName || self.getDefaultDeviceName();
                        subPayload.added_time = new Date().toISOString();
                        return $.ajax({
                            url: '/api/webpush/subscribe',
                            type: 'POST',
                            contentType: 'application/json',
                            data: JSON.stringify(subPayload)
                        });
                    }).then(function() {
                        self.updateUIStatus(true);
                        if (window.GenmonPWA && typeof window.GenmonPWA.loadSubscribedDevices === 'function') {
                            window.GenmonPWA.loadSubscribedDevices();
                        }
                        alert('Success! Web Push alerts enabled for this device.');
                    }).catch(function(err) {
                        console.error('Subscription error:', err);
                        var isRawIp = /^(\d{1,3}\.){3}\d{1,3}$/.test(location.hostname);
                        if (location.protocol === 'https:' && isRawIp) {
                            alert('Chrome Security Notice:\n\nChrome blocks Service Workers and Web Push on self-signed IP addresses (https://' + location.hostname + ').\n\nTo enable Web Push, please access Genmon via your Tailscale HTTPS domain (e.g. https://genmon.your-tailnet.ts.net) or HTTP.');
                        } else {
                            alert('Push Subscription error: ' + (err.message || err));
                        }
                    });
                }).fail(function(xhr, status, err) {
                    alert('Failed to reach VAPID key endpoint: ' + (err || status));
                });
            });
        },

        getDefaultDeviceName: function() {
            var ua = navigator.userAgent;
            var match;
            if (/android/i.test(ua)) {
                match = ua.match(/;\s*([^;]+)\s+Build\//i);
                return match ? match[1] + ' (Android)' : 'Android Phone';
            }
            if (/iphone/i.test(ua)) return "iPhone";
            if (/ipad/i.test(ua)) return "iPad";
            if (/macintosh|mac os/i.test(ua)) return "Mac Desktop";
            if (/windows/i.test(ua)) return "Windows PC";
            return "Web Browser";
        },

        autoFillDeviceName: function() {
            var el = $('#webpush-device-name');
            if (el.length && !el.val()) {
                el.val(this.getDefaultDeviceName());
            }
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
                        if (window.GenmonPWA && typeof window.GenmonPWA.loadSubscribedDevices === 'function') {
                            window.GenmonPWA.loadSubscribedDevices();
                        }
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

        loadSubscribedDevices: function() {
            var self = this;
            $.ajax({
                url: '/api/webpush/subscriptions',
                type: 'GET',
                success: function(res) {
                    var container = $('#pwa-subscribed-devices-list');
                    if (!container.length) return;
                    if (res && res.status === 'ok' && res.subscriptions && res.subscriptions.length > 0) {
                        var html = '<table class="table table-sm text-white" style="margin:0; font-size:0.85rem;">';
                        html += '<thead><tr><th>Device / Name</th><th>Push Service</th><th>Actions</th></tr></thead><tbody>';
                        res.subscriptions.forEach(function(s) {
                            var nameDisplay = s.device_name || s.device_type || 'Web Device';
                            var escName = nameDisplay.replace(/'/g, "\\'");
                            var escEndpoint = s.endpoint.replace(/'/g, "\\'");
                            html += '<tr>';
                            html += '<td><strong>' + nameDisplay + '</strong></td>';
                            html += '<td><span class="badge bg-secondary">' + (s.service || 'Web Push') + '</span></td>';
                            html += '<td>';
                            html += '<button class="btn btn-outline-light btn-sm text-nowrap" style="padding:1px 6px; font-size:0.75rem; margin-right:4px;" onclick="window.GenmonPWA.updateDeviceName(\'' + escEndpoint + '\', \'' + escName + '\')">✏️ Edit</button>';
                            html += '<button class="btn btn-danger btn-sm text-nowrap" style="padding:1px 6px; font-size:0.75rem;" onclick="window.GenmonPWA.removeDevice(\'' + escEndpoint + '\')">Remove</button>';
                            html += '</td>';
                            html += '</tr>';
                        });
                        html += '</tbody></table>';
                        container.html(html);
                    } else {
                        container.html('<div style="color: #94a3b8; text-align: center; padding: 10px;">No registered push devices.</div>');
                    }
                },
                error: function() {
                    $('#pwa-subscribed-devices-list').html('<div style="color: #ef4444; text-align: center; padding: 10px;">Could not load devices.</div>');
                }
            });
        },

        updateDeviceName: function(endpoint, currentName) {
            var self = this;
            var newName = prompt('Enter a custom name for this device:', currentName || '');
            if (newName && newName.trim() !== '') {
                $.ajax({
                    url: '/api/webpush/update_name',
                    type: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({ endpoint: endpoint, device_name: newName.trim() }),
                    success: function() {
                        self.loadSubscribedDevices();
                    }
                });
            }
        },

        removeDevice: function(endpoint) {
            var self = this;
            if (confirm('Remove this push notification device?')) {
                $.ajax({
                    url: '/api/webpush/unsubscribe',
                    type: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({ endpoint: endpoint }),
                    success: function() {
                        if (self.sub && self.sub.endpoint === endpoint) {
                            self.sub.unsubscribe().catch(function() {});
                            self.sub = null;
                            self.updateUIStatus(false);
                        }
                        self.loadSubscribedDevices();
                        self.checkSubscriptionState();
                    }
                });
            }
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
        window.GenmonPWA.loadSubscribedDevices();
        window.GenmonPWA.autoFillDeviceName();
    });

})();
