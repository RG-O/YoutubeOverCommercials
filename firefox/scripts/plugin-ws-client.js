
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
    isFirefox: false,
    firefoxInitConfig: window.__extensionConfig,
    isPluginCommercialTriggerWS: false,
    isPluginOverlayWS: false,
    isDualWS: false,
    //TODO: start montitoring and accounting for full life cycles in here
    hasPluginCommercialTriggerWSConnected: false,
    hasPluginOverlayWSConnected: false,
    hasDualWSConnected: false,
    totalWSConnectionsInQueue: 0,
    pluginCommercialTriggerWSOpenedBy: "none",
    pluginOverlayWSOpenedBy: "none",
    dualWSOpenedBy: "none",
    initWSPlugins(payload) {
        ws.isPluginCommercialTriggerWS = (payload.data.preferences.isPluginCommercialTriggerMode && payload.data.preferences.pluginCommercialTriggerFramework === 'ws');
        ws.isPluginOverlayWS = (payload.data.preferences.isPluginOverlayMode && payload.data.preferences.pluginOverlayFramework === 'ws');
        ws.isDualWS = (ws.isPluginCommercialTriggerWS && ws.isPluginOverlayWS && payload.data.preferences.pluginCommercialTriggerWSURL === payload.data.preferences.pluginOverlayWSURL);
        ws.isFirefox = payload.data.utilities.isFirefox ?? false;
        ws.isFirefoxPopup = payload.data.utilities.isFirefoxPopup ?? false;

        if (ws.hasPluginCommercialTriggerWSConnected || ws.hasPluginOverlayWSConnected || ws.hasDualWSConnected) {
            ws.sendMessageToWSPlugins(payload);
        }

        if (ws.isPluginCommercialTriggerWS && !ws.isDualWS && !ws.hasPluginCommercialTriggerWSConnected) {
            ws.totalWSConnectionsInQueue++;
            ws.pluginCommercialTriggerWSOpenedBy = payload.meta.wsOpenedBy;

            ws.initTrigger(payload);
            ws.hasPluginCommercialTriggerWSConnected = true;
        }

        if (ws.isPluginOverlayWS && !ws.isDualWS && !ws.hasPluginOverlayWSConnected) {
            ws.totalWSConnectionsInQueue++;
            ws.pluginOverlayWSOpenedBy = payload.meta.wsOpenedBy;

            ws.initOverlay(payload);
            ws.hasPluginOverlayWSConnected = true;
        }

        if (ws.isDualWS && !ws.hasDualWSConnected) {
            ws.totalWSConnectionsInQueue++;
            ws.dualWSOpenedBy = payload.meta.wsOpenedBy;

            ws.initDual(payload);
            ws.hasDualWSConnected = true;
        }
    },
    sendMessageToWSPlugins(payload) {
        if (ws.isPluginCommercialTriggerWS && !ws.isDualWS && ws.hasPluginCommercialTriggerWSConnected) {
            ws.sendToTrigger(payload);
        }

        if (ws.isPluginOverlayWS && !ws.isDualWS && ws.hasPluginOverlayWSConnected) {
            ws.sendToOverlay(payload);
        }

        if (ws.isDualWS && ws.hasDualWSConnected) {
            ws.sendToDual(payload);
        }
    },
    initTrigger(payload) {
        triggerWS = new WSClient(payload.data.preferences.pluginCommercialTriggerWSURL, "Trigger");

        triggerWS.onOpen = () => {
            ws.totalWSConnectionsInQueue--;

            ws.forwardMessageFromPluginWSClient(
                null,
                "trigger-plugin",
                "started",
                "Trigger plugin connected",
            );

            triggerWS.send(payload);
        };

        triggerWS.onMessage = ws.handleTriggerMessage;

        triggerWS.onClose = ({ wasConnected }) => {
            if (!wasConnected) {
                ws.totalWSConnectionsInQueue--;

                ws.forwardMessageFromPluginWSClient(
                    null,
                    "trigger-plugin",
                    "failed",
                    "Failed to connect to trigger plugin",
                );
            } else {
                ws.forwardMessageFromPluginWSClient(
                    null,
                    "trigger-plugin",
                    "disconnected",
                    "Trigger plugin disconnected",
                );
            }
        };

        triggerWS.onReconnect = () => {
            ws.forwardMessageFromPluginWSClient(
                null,
                "trigger-plugin",
                "reconnecting",
                "Attempting to reconnect to trigger plugin...",
            );
        };

        triggerWS.connect();
    },
    handleTriggerMessage(msg) {
        //if (ws.isInContentFrame) {
        //    console.log(ws.isInContentFrame); //TODO: something for firefox
        //} else {
            ws.forwardMessageFromPluginWSClient(
                msg,
                "trigger-plugin",
                "connected",
                "Trigger plugin connected",
            );
        //}
    },
    sendToTrigger(payload) {
        if (!triggerWS || !triggerWS.connected) {
            ws.forwardMessageFromPluginWSClient(
                null,
                "trigger-plugin",
                "failed",
                "Failed to send message to trigger plugin",
            );

            return;
        }

        triggerWS.send(payload);
    },
    initOverlay(payload) {
        overlayWS = new WSClient(payload.data.preferences.pluginOverlayWSURL, "Overlay");

        overlayWS.onOpen = () => {
            ws.totalWSConnectionsInQueue--;

            ws.forwardMessageFromPluginWSClient(
                null,
                "overlay-plugin",
                "started",
                "Overly plugin connected",
            );

            overlayWS.send(payload);
        };

        overlayWS.onMessage = ws.handleOverlayMessage;

        overlayWS.onClose = ({ wasConnected }) => {
            if (!wasConnected) {
                ws.totalWSConnectionsInQueue--;

                ws.forwardMessageFromPluginWSClient(
                    null,
                    "overlay-plugin",
                    "failed",
                    "Failed to connect to overlay plugin",
                );
            } else {
                ws.forwardMessageFromPluginWSClient(
                    null,
                    "overlay-plugin",
                    "disconnected",
                    "Overlay plugin disconnected",
                );
            }
        };

        overlayWS.onReconnect = () => {
            ws.forwardMessageFromPluginWSClient(
                null,
                "overlay-plugin",
                "reconnecting",
                "Attempting to reconnect to overlay plugin...",
            );
        };

        overlayWS.connect();
    },
    handleOverlayMessage(msg) {
        //if (ws.isInContentFrame) {
        //    console.log(ws.isInContentFrame); //TODO: something for firefox
        //} else {
            ws.forwardMessageFromPluginWSClient(
                msg,
                "overlay-plugin",
                "connected",
                "Overlay plugin connected",
            );
        //}
    },
    sendToOverlay(payload) {
        if (!overlayWS || !overlayWS.connected) {
            ws.forwardMessageFromPluginWSClient(
                null,
                "overlay-plugin",
                "failed",
                "Failed to send message to overlay plugin",
            );

            return;
        }

        overlayWS.send(payload);
    },
    initDual(payload) {
        dualWS = new WSClient(payload.data.preferences.pluginCommercialTriggerWSURL, "Dual"); //note: just using this url since they should both be the same

        dualWS.onOpen = () => {
            ws.totalWSConnectionsInQueue--;

            ws.forwardMessageFromPluginWSClient(
                null,
                "dual-plugin",
                "started",
                "Overly plugin connected",
            );

            dualWS.send(payload);
        };

        dualWS.onMessage = ws.handleDualMessage;

        dualWS.onClose = ({ wasConnected }) => {
            if (!wasConnected) {
                ws.totalWSConnectionsInQueue--;

                ws.forwardMessageFromPluginWSClient(
                    null,
                    "dual-plugin",
                    "failed",
                    "Failed to connect to dual plugin",
                );
            } else {
                ws.forwardMessageFromPluginWSClient(
                    null,
                    "dual-plugin",
                    "disconnected",
                    "Dual plugin disconnected",
                );
            }
        };

        dualWS.onReconnect = () => {
            ws.forwardMessageFromPluginWSClient(
                null,
                "dual-plugin",
                "reconnecting",
                "Attempting to reconnect to dual plugin...",
            );
        };

        dualWS.connect();
    },
    handleDualMessage(msg) {
        //if (ws.isInContentFrame) {
        //    console.log(ws.isInContentFrame); //TODO: something for firefox
        //} else {
            ws.forwardMessageFromPluginWSClient(
                msg,
                "dual-plugin",
                "connected",
                "Dual plugin connected",
            );
        //}
    },
    sendToDual(payload) {
        if (!dualWS || !dualWS.connected) {
            ws.forwardMessageFromPluginWSClient(
                null,
                "dual-plugin",
                "failed",
                "Failed to send message to dual plugin",
            );

            return;
        }

        dualWS.send(payload);
    },
    forwardMessageFromPluginWSClient(payload, sender, connectionState, connectionMessage) {
        let message = {
            action: "forward_message_from_plugin_ws",
            payload: payload,
            source: "plugin",
            sender: sender,
            connectionState: connectionState,
            connectionMessage: connectionMessage,
            pluginCommercialTriggerWSOpenedBy: ws.pluginCommercialTriggerWSOpenedBy,
            pluginOverlayWSOpenedBy: ws.pluginOverlayWSOpenedBy,
            dualWSOpenedBy: ws.dualWSOpenedBy,
            totalWSConnectionsInQueue: ws.totalWSConnectionsInQueue,
            isFirefox: ws.isFirefox,
        }

        if (ws.isFirefoxPopup) {
            handlePluginWSMessage(message);
        } else {
            chrome.runtime.sendMessage(message);
        }
    }
}


if (ws.firefoxInitConfig) {
    ws.initWSPlugins(ws.firefoxInitConfig.payload);
}
