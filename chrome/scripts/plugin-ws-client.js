
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
    //TODO: start montitoring and accounting for full life cycles in here
    hasPluginCommercialTriggerWSConnected: false,
    hasPluginOverlayWSConnected: false,
    hasSharedWSConnected: false,
    totalWSConnectionsInQueue: 0,
    pluginCommercialTriggerWSOpenedBy: "none",
    pluginOverlayWSOpenedBy: "none",
    sharedWSOpenedBy: "none",
    initWSPlugins(payload) {
        ws.isPluginCommercialTriggerWS = (payload.data.preferences.isPluginCommercialTriggerMode && payload.data.preferences.pluginCommercialTriggerFramework === 'ws');
        ws.isPluginOverlayWS = (payload.data.preferences.isPluginOverlayMode && payload.data.preferences.pluginOverlayFramework === 'ws');
        ws.isSharedWS = (ws.isPluginCommercialTriggerWS && ws.isPluginOverlayWS && payload.data.preferences.pluginCommercialTriggerWSURL === payload.data.preferences.pluginOverlayWSURL);

        if (ws.hasPluginCommercialTriggerWSConnected || ws.hasPluginOverlayWSConnected || ws.hasSharedWSConnected) {
            ws.sendMessageToWSPlugins(payload);
        }

        //TODO: allow for switching WS URLs
        if (ws.isPluginCommercialTriggerWS && !ws.isSharedWS && !ws.hasPluginCommercialTriggerWSConnected) {
            ws.totalWSConnectionsInQueue++;
            ws.initDetection(payload);
            ws.hasPluginCommercialTriggerWSConnected = true;
            ws.pluginCommercialTriggerWSOpenedBy = payload.meta.wsOpenedBy;
        }

        if (ws.isPluginOverlayWS && !ws.isSharedWS && !ws.hasPluginOverlayWSConnected) {
            ws.totalWSConnectionsInQueue++;
            ws.initOverlay(payload);
            ws.hasPluginOverlayWSConnected = true;
            ws.pluginOverlayWSOpenedBy = payload.meta.wsOpenedBy;
        }

        if (ws.isSharedWS) {
            ws.totalWSConnectionsInQueue++;
            //TODO: Something
        }
    },
    sendMessageToWSPlugins(payload) {
        if (ws.isPluginCommercialTriggerWS && !ws.isSharedWS && ws.hasPluginCommercialTriggerWSConnected) {
            ws.sendToDetection(payload);
        }

        if (ws.isPluginOverlayWS && !ws.isSharedWS && ws.hasPluginOverlayWSConnected) {
            ws.sendToOverlay(payload);
        }

        if (ws.isSharedWS && ws.hasSharedWSConnected) {
            //TODO: Something
        }
    },
    initDetection(payload) {
        detectionWS = new WSClient(payload.data.preferences.pluginCommercialTriggerWSURL, "Detection");

        detectionWS.onOpen = () => {
            ws.totalWSConnectionsInQueue--;

            //TODO: add these can be combined into a single function and have repeating values not be inputs
            chrome.runtime.sendMessage({
                action: "forward_message_from_plugin_ws",
                payload: null,
                source: "plugin",
                sender: "trigger-plugin",
                connectionState: "started",
                connectionMessage: "Plugin connected",
                pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                sharedWSOpenedBy: ws.sharedWSOpenedBy,
                totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
            });
            detectionWS.send(payload);
        };

        detectionWS.onMessage = ws.handleDetectionMessage;

        detectionWS.onClose = ({ wasConnected }) => {
            if (!wasConnected) {
                ws.totalWSConnectionsInQueue--;

                chrome.runtime.sendMessage({
                    action: "forward_message_from_plugin_ws",
                    payload: null,
                    source: "plugin",
                    sender: "trigger-plugin",
                    connectionState: "failed",
                    connectionMessage: "Failed to connect to plugin",
                    pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                    pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                    sharedWSOpenedBy: ws.sharedWSOpenedBy,
                    totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
                });
            } else {
                chrome.runtime.sendMessage({
                    action: "forward_message_from_plugin_ws",
                    payload: null,
                    source: "plugin",
                    sender: "trigger-plugin",
                    connectionState: "disconnected",
                    connectionMessage: "Plugin disconnected",
                    pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                    pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                    sharedWSOpenedBy: ws.sharedWSOpenedBy,
                    totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
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
                pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                sharedWSOpenedBy: ws.sharedWSOpenedBy,
                totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
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
                pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                sharedWSOpenedBy: ws.sharedWSOpenedBy,
                totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
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
                pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                sharedWSOpenedBy: ws.sharedWSOpenedBy,
                totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
            });
            return;
        }

        detectionWS.send(payload);
    },
    initOverlay(payload) {
        overlayWS = new WSClient(payload.data.preferences.pluginOverlayWSURL, "Overlay");

        overlayWS.onOpen = () => {
            ws.totalWSConnectionsInQueue--;

            chrome.runtime.sendMessage({
                action: "forward_message_from_plugin_ws",
                payload: null,
                source: "plugin",
                sender: "overlay-plugin",
                connectionState: "started",
                connectionMessage: "Overly plugin connected",
                pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                sharedWSOpenedBy: ws.sharedWSOpenedBy,
                totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
            });
            overlayWS.send(payload);
        };

        overlayWS.onMessage = ws.handleOverlayMessage;

        overlayWS.onClose = ({ wasConnected }) => {
            if (!wasConnected) {
                ws.totalWSConnectionsInQueue--;

                chrome.runtime.sendMessage({
                    action: "forward_message_from_plugin_ws",
                    payload: null,
                    source: "plugin",
                    sender: "overlay-plugin",
                    connectionState: "failed",
                    connectionMessage: "Failed to connect to overlay plugin",
                    pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                    pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                    sharedWSOpenedBy: ws.sharedWSOpenedBy,
                    totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
                });
            } else {
                chrome.runtime.sendMessage({
                    action: "forward_message_from_plugin_ws",
                    payload: null,
                    source: "plugin",
                    sender: "overlay-plugin",
                    connectionState: "disconnected",
                    connectionMessage: "Overlay plugin disconnected",
                    pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                    pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                    sharedWSOpenedBy: ws.sharedWSOpenedBy,
                    totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
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
                pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                sharedWSOpenedBy: ws.sharedWSOpenedBy,
                totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
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
                pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                sharedWSOpenedBy: ws.sharedWSOpenedBy,
                totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
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
                pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
                pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
                sharedWSOpenedBy: ws.sharedWSOpenedBy,
                totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
            });
            return;
        }

        overlayWS.send(payload);
    }
}