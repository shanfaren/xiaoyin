(function (global) {
  'use strict';

  var STEP_SECONDS = 0.02;
  var SILENCE_RMS = 0.008;

  function build(audioBuffer, seq) {
    if (!audioBuffer || !audioBuffer.getChannelData || !audioBuffer.sampleRate || !audioBuffer.length) {
      return null;
    }
    var source = audioBuffer.getChannelData(0);
    var hop = Math.max(1, Math.round(audioBuffer.sampleRate * STEP_SECONDS));
    var count = Math.ceil(audioBuffer.length / hop);
    var values = new Float32Array(count);
    var peak = 0.01;

    for (var i = 0; i < count; i += 1) {
      var start = i * hop;
      var end = Math.min(source.length, start + hop);
      var sum = 0;
      for (var j = start; j < end; j += 1) sum += source[j] * source[j];
      values[i] = Math.sqrt(sum / Math.max(1, end - start));
      peak = Math.max(peak, values[i]);
    }

    for (var k = 0; k < count; k += 1) {
      values[k] = values[k] < SILENCE_RMS ? 0 : Math.min(1, Math.pow(values[k] / peak, 0.6));
    }
    return {
      seq: seq,
      values: values,
      step: hop / audioBuffer.sampleRate
    };
  }

  function level(audioElement, envelope, activeSeq) {
    if (!audioElement || audioElement.paused || audioElement.ended) return 0;
    if (!envelope || envelope.seq !== activeSeq || !envelope.values || !envelope.step) return 0;
    var time = Number(audioElement.currentTime);
    if (!isFinite(time) || time < 0) return 0;
    var index = Math.floor(time / envelope.step);
    return envelope.values[index] || 0;
  }

  global.ForestSpeechEnvelope = {
    build: build,
    level: level
  };
})(window);
