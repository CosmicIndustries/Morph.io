// app.js
const WS_URL = "ws://127.0.0.1:8766";
let ws;
let audioCtx;
let playerNode;
let sampleRate = 48000;
let channels = 2;

async function initAudio() {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({sampleRate});
    try {
        await audioCtx.audioWorklet.addModule("player-processor.js");
    } catch (e) {
        console.error("AudioWorklet unavailable:", e);
        return;
    }
    playerNode = new AudioWorkletNode(audioCtx, "player-processor");
    playerNode.connect(audioCtx.destination);
    console.log("AudioWorklet player ready (sr=" + audioCtx.sampleRate + ")");
}

function startWS() {
    ws = new WebSocket(WS_URL);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
        document.getElementById("conn").textContent = "Connected";
        console.log("ws open");
    };

    ws.onclose = () => {
        document.getElementById("conn").textContent = "Disconnected";
        console.log("ws closed");
        // reconnect with backoff
        setTimeout(startWS, 1000);
    };

    ws.onerror = (e) => {
        console.error("ws error", e);
    };

    ws.onmessage = async (evt) => {
        // text -> spectrogram
        if (typeof evt.data === "string") {
            try {
                const msg = JSON.parse(evt.data);
                if (msg.type === "spectrogram") {
                    drawSpectrogram(msg.data);
                }
            } catch (e) {
                // ignore
            }
            return;
        }

        // binary -> check for Opus or PCM
        if (evt.data instanceof ArrayBuffer) {
            const ab = evt.data;
            // check 2-byte header for "OP" (Opus) — optional
            if (ab.byteLength >= 2) {
                const header = String.fromCharCode(new Uint8Array(ab, 0, 2)[0]) +
                               String.fromCharCode(new Uint8Array(ab, 0, 2)[1]);
                if (header === "OP") {
                    // Opus packet: app doesn't decode by default
                    // You would need a JS/WASM decoder (libopus.js); skipping for now.
                    console.warn("Received Opus packet - decoder not implemented in UI");
                    return;
                }
            }

            // raw Float32 interleaved PCM
            // Transfer the buffer to the worklet as Float32Array
            const floatBuf = new Float32Array(ab);
            // Post to the worklet's port transferring the underlying buffer
            playerNode.port.postMessage({type: "pcm", buffer: floatBuf.buffer}, [floatBuf.buffer]);
        }
    };
}

// minimal spectrogram draw (reuse your code)
function drawSpectrogram(matrix) {
    const canvas = document.getElementById("spec");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const h = canvas.height;
    const w = canvas.width;

    ctx.clearRect(0,0,w,h);
    const rows = matrix.length;
    const cols = matrix[0].length;

    const img = ctx.createImageData(w, h);
    for (let y = 0; y < h; y++) {
        let row = Math.floor((y / h) * rows);
        for (let x = 0; x < w; x++) {
            let col = Math.floor((x / w) * cols);
            let v = matrix[row][col];
            let c = Math.max(0, Math.min(255, (v + 80) * 3));
            let i = (y * w + x) * 4;
            img.data[i] = c;      // R
            img.data[i+1] = 0;    // G
            img.data[i+2] = 255-c;// B
            img.data[i+3] = 255;
        }
    }
    ctx.putImageData(img, 0, 0);
}

// init on page load
window.addEventListener("load", async () => {
    await initAudio();
    startWS();
});

