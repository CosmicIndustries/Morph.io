// player-processor.js
// AudioWorkletProcessor that receives Float32 chunks via port messages and outputs them.

class PlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(0);
    this.readIndex = 0;
    this.port.onmessage = (evt) => {
      if (evt.data && evt.data.type === "pcm") {
        // evt.data.buffer is a Float32Array (transferred)
        const incoming = new Float32Array(evt.data.buffer);
        // append
        const newBuf = new Float32Array(this.buffer.length + incoming.length);
        newBuf.set(this.buffer, 0);
        newBuf.set(incoming, this.buffer.length);
        this.buffer = newBuf;
      }
    };
  }

  process(inputs, outputs, parameters) {
    const out = outputs[0];
    const channels = out.length;
    const frames = out[0].length; // usually 128
    if (this.buffer.length < frames * channels) {
      // not enough samples: output silence
      for (let ch = 0; ch < channels; ch++) {
        out[ch].fill(0.0);
      }
      return true;
    }

    // fill output from interleaved buffer
    // our buffer is interleaved float32: [L0,R0,L1,R1,...]
    // produce per-channel plane
    let bi = 0;
    for (let f = 0; f < frames; f++) {
      for (let ch = 0; ch < channels; ch++) {
        out[ch][f] = this.buffer[bi++];
      }
    }

    // drop consumed samples
    if (bi < this.buffer.length) {
      this.buffer = this.buffer.subarray(bi);
    } else {
      this.buffer = new Float32Array(0);
    }
    return true;
  }
}

registerProcessor("player-processor", PlayerProcessor);

