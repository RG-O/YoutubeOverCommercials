
chrome.runtime.onMessage.addListener(function (message) {
    if (message.target == 'plugin-ws') {
        if (message.action == 'send-message-to-plugins') {
            ws.sendMessageToWSPlugins(message.payload);
        }
    }
});


class WSClient {
    constructor(url, name, options = {}) {
        this.url = url;
        this.name = name; //TODO: get rid of name?

        this.ws = null;
        this.connected = false;

        this.reconnectDelay = options.reconnectDelay || 2000;
        this.shouldReconnect = true;

        //callbacks
        this.onOpen = () => { };
        this.onMessage = () => { };
        this.onClose = () => { };
        this.onError = () => { };
        this.onReconnect = () => { };
    }

    connect() {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
            this.connected = true;
            this.onOpen();
        };

        this.ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            this.onMessage(msg);
        };

        this.ws.onerror = (err) => {
            this.onError(err);
        };

        this.ws.onclose = () => {
            const wasConnected = this.connected;
            this.connected = false;

            this.onClose({ wasConnected });

            if (this.shouldReconnect) {
                setTimeout(() => {
                    this.onReconnect();
                    this.connect();
                }, this.reconnectDelay);
            }
        };
    }

    send(payload) {
        if (!this.connected) return;

        this.ws.send(JSON.stringify(payload));
    }

    disconnect() {
        this.shouldReconnect = false;
        this.ws?.close();
    }
}

const ws = {
    isInContentFrame: typeof mainVideoCollection !== 'undefined',
    isPluginCommercialTriggerWS: false,
    isPluginOverlayWS: false,
    isSharedWS: false,
    initWSPlugins(payload) {
        ws.isPluginCommercialTriggerWS = (payload.data.preferences.isPluginCommercialTriggerMode && payload.data.preferences.pluginCommercialTriggerFramework === 'ws');
        ws.isPluginOverlayWS = (payload.data.preferences.isPluginOverlayMode && payload.data.preferences.pluginOverlayFramework === 'ws');
        ws.isSharedWS = (ws.isPluginCommercialTriggerWS && ws.isPluginOverlayWS && payload.data.preferences.pluginCommercialTriggerWSURL === payload.data.preferences.pluginOverlayWSURL);

        if (ws.isPluginCommercialTriggerWS && !ws.isSharedWS) {
            ws.initDetection(payload);
        }

        if (ws.isPluginOverlayWS && !ws.isSharedWS) {
            ws.initOverlay(payload);
        }

        if (ws.isSharedWS) {
            //TODO: Something
        }
    },
    sendMessageToWSPlugins(payload) {
        if (ws.isPluginCommercialTriggerWS && !ws.isSharedWS) {
            ws.sendToDetection(payload);
        }

        if (ws.isPluginOverlayWS && !ws.isSharedWS) {
            ws.sendToOverlay(payload);
        }

        if (ws.isSharedWS) {
            //TODO: Something
        }
    },
    initDetection(payload) {
        detectionWS = new WSClient(payload.data.preferences.pluginCommercialTriggerWSURL, "Detection");

        detectionWS.onOpen = () => {
            chrome.runtime.sendMessage({
                action: "forward_message_from_plugin_ws",
                payload: null,
                source: "plugin",
                sender: "trigger-plugin",
                connectionState: "started",
                connectionMessage: "Plugin connected",
            });
            detectionWS.send(payload);
        };

        detectionWS.onMessage = ws.handleDetectionMessage;

        detectionWS.onClose = ({ wasConnected }) => {
            if (!wasConnected) {
                chrome.runtime.sendMessage({
                    action: "forward_message_from_plugin_ws",
                    payload: null,
                    source: "plugin",
                    sender: "trigger-plugin",
                    connectionState: "failed",
                    connectionMessage: "Failed to connect to plugin",
                });
            } else {
                chrome.runtime.sendMessage({
                    action: "forward_message_from_plugin_ws",
                    payload: null,
                    source: "plugin",
                    sender: "trigger-plugin",
                    connectionState: "disconnected",
                    connectionMessage: "Plugin disconnected",
                });
            }
        };

        detectionWS.onReconnect = () => {
            chrome.runtime.sendMessage({
                action: "forward_message_from_plugin_ws",
                payload: null,
                source: "plugin",
                sender: "trigger-plugin",
                connectionState: "reconnecting",
                connectionMessage: "Attempting to reconnect to plugin...",
            });
        };

        detectionWS.connect();
    },
    handleDetectionMessage(msg) {
        if (ws.isInContentFrame) {
            console.log(ws.isInContentFrame); //TODO: something for firefox
        } else {
            chrome.runtime.sendMessage({
                action: "forward_message_from_plugin_ws",
                payload: msg,
                source: "plugin",
                sender: "trigger-plugin",
                connectionState: "connected",
                connectionMessage: "Connected",
            });
        }
    },
    sendToDetection(payload) {
        if (!detectionWS || !detectionWS.connected) {
            chrome.runtime.sendMessage({
                action: "forward_message_from_plugin_ws",
                payload: null,
                source: "plugin",
                sender: "trigger-plugin",
                connectionState: "failed",
                connectionMessage: "Failed to send message to plugin",
            });
            return;
        }

        detectionWS.send(payload);
    },
    initOverlay(payload) {
        overlayWS = new WSClient(payload.data.preferences.pluginOverlayWSURL, "Overlay");

        overlayWS.onOpen = () => {
            chrome.runtime.sendMessage({
                action: "forward_message_from_plugin_ws",
                payload: null,
                source: "plugin",
                sender: "overlay-plugin",
                connectionState: "started",
                connectionMessage: "Overly plugin connected",
            });
            overlayWS.send(payload);
        };

        overlayWS.onMessage = ws.handleOverlayMessage;

        overlayWS.onClose = ({ wasConnected }) => {
            if (!wasConnected) {
                chrome.runtime.sendMessage({
                    action: "forward_message_from_plugin_ws",
                    payload: null,
                    source: "plugin",
                    sender: "overlay-plugin",
                    connectionState: "failed",
                    connectionMessage: "Failed to connect to overlay plugin",
                });
            } else {
                chrome.runtime.sendMessage({
                    action: "forward_message_from_plugin_ws",
                    payload: null,
                    source: "plugin",
                    sender: "overlay-plugin",
                    connectionState: "disconnected",
                    connectionMessage: "Overlay plugin disconnected",
                });
            }
        };

        overlayWS.onReconnect = () => {
            chrome.runtime.sendMessage({
                action: "forward_message_from_plugin_ws",
                payload: null,
                source: "plugin",
                sender: "overlay-plugin",
                connectionState: "reconnecting",
                connectionMessage: "Attempting to reconnect to overlay plugin...",
            });
        };

        overlayWS.connect();
    },
    handleOverlayMessage(msg) {
        if (ws.isInContentFrame) {
            console.log(ws.isInContentFrame); //TODO: something for firefox
        } else {
            chrome.runtime.sendMessage({
                action: "forward_message_from_plugin_ws",
                payload: msg,
                source: "plugin",
                sender: "overlay-plugin",
                connectionState: "connected",
                connectionMessage: "Overlay plugin connected",
            });
        }
    },
    sendToOverlay(payload) {
        if (!overlayWS || !overlayWS.connected) {
            chrome.runtime.sendMessage({
                action: "forward_message_from_plugin_ws",
                payload: null,
                source: "plugin",
                sender: "overlay-plugin",
                connectionState: "failed",
                connectionMessage: "Failed to send message to overlay plugin",
            });
            return;
        }

        overlayWS.send(payload);
    }
}