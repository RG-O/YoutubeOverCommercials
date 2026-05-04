
chrome.runtime.onMessage.addListener(function (message) {
    if (message.target == 'plugin-ws') {
        if (message.action == 'send-message-to-plugins') {
            ws.sendToDetection(message.payload);
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
    initDetection(payload) {
        detectionWS = new WSClient(payload.data.preferences.pluginCommercialTriggerWSURL, "Detection");

        detectionWS.onOpen = () => {
            console.log("Detection plugin connected"); //777
            detectionWS.send(payload);
        };

        detectionWS.onMessage = ws.handleDetectionMessage;

        detectionWS.onClose = ({ wasConnected }) => {
            if (!wasConnected) {
                console.log("Detection plugin failed to connect"); //TODO: send message to content
            } else {
                console.log("Detection plugin disconnected"); //TODO: send message to content
            }
        };

        detectionWS.onReconnect = () => {
            console.log("Reconnecting to detection plugin..."); //TODO: send message to content
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
            });
        }
    },
    sendToDetection(payload) {
        if (!detectionWS || !detectionWS.connected) {
            console.warn("Detection WS not connected");
            return;
        }

        detectionWS.send(payload);
    }
}