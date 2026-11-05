(function () {
  'use strict';

  function isExactInteger(value, min, max) {
    if (typeof value !== 'number') {
      return false;
    }
    if (!Number.isFinite(value)) {
      return false;
    }
    if (!Number.isInteger(value)) {
      return false;
    }
    if (value < min || value > max) {
      return false;
    }
    return true;
  }

  function render(buffer, width, height, completedPixels, activeDwellNs, dwellNs, lowCPS, highCPS) {
    if (buffer === null || buffer === undefined) {
      throw new TypeError('buffer must be an ArrayBuffer');
    }
    if (Object.getPrototypeOf(buffer) !== ArrayBuffer.prototype) {
      throw new TypeError('buffer must be an ordinary ArrayBuffer');
    }
    if (buffer.byteLength === 0 && buffer.byteOffset !== undefined) {
      throw new TypeError('buffer must not be detached');
    }

    if (!isExactInteger(width, 1, 4096)) {
      throw new RangeError('width must be an integer between 1 and 4096');
    }
    if (!isExactInteger(height, 1, 4096)) {
      throw new RangeError('height must be an integer between 1 and 4096');
    }

    var totalPixels = width * height;
    var expectedByteLength = totalPixels * 4;

    if (buffer.byteLength !== expectedByteLength) {
      throw new RangeError('buffer byte length must equal width * height * 4');
    }

    if (!isExactInteger(completedPixels, 0, totalPixels)) {
      throw new RangeError('completedPixels must be an integer between 0 and width * height');
    }

    if (!isExactInteger(dwellNs, 1, 10000000)) {
      throw new RangeError('dwellNs must be an integer between 1 and 10000000');
    }

    if (!isExactInteger(activeDwellNs, 0, dwellNs - 1)) {
      throw new RangeError('activeDwellNs must be an integer between 0 and dwellNs - 1');
    }

    if (completedPixels === totalPixels && activeDwellNs !== 0) {
      throw new RangeError('activeDwellNs must be 0 when completedPixels equals width * height');
    }

    if (typeof lowCPS !== 'number' || !Number.isFinite(lowCPS)) {
      throw new TypeError('lowCPS must be a finite number');
    }
    if (typeof highCPS !== 'number' || !Number.isFinite(highCPS)) {
      throw new TypeError('highCPS must be a finite number');
    }
    if (lowCPS < 0) {
      throw new RangeError('lowCPS must be >= 0');
    }
    if (!(lowCPS < highCPS)) {
      throw new RangeError('lowCPS must be < highCPS');
    }
    if (!Number.isFinite(highCPS - lowCPS)) {
      throw new RangeError('highCPS - lowCPS must be finite');
    }

    var view = new DataView(buffer);
    var out = new Uint8ClampedArray(expectedByteLength);
    var cpsRange = highCPS - lowCPS;
    var fullExposureSeconds = dwellNs * 1e-9;

    for (var i = 0; i < totalPixels; i++) {
      var offset = i * 4;
      var gray = 0;

      if (i < completedPixels) {
        var count = view.getUint32(offset, true);
        var rate = count / fullExposureSeconds;
        if (rate > lowCPS) {
          if (rate >= highCPS) {
            gray = 255;
          } else {
            gray = Math.round(255 * (rate - lowCPS) / cpsRange);
          }
        }
      } else if (i === completedPixels && activeDwellNs > 0) {
        var activeExposureSeconds = activeDwellNs * 1e-9;
        var activeCount = view.getUint32(offset, true);
        var activeRate = activeCount / activeExposureSeconds;
        if (activeRate > lowCPS) {
          if (activeRate >= highCPS) {
            gray = 255;
          } else {
            gray = Math.round(255 * (activeRate - lowCPS) / cpsRange);
          }
        }
      }

      out[offset] = gray;
      out[offset + 1] = gray;
      out[offset + 2] = gray;
      out[offset + 3] = 255;
    }

    return out;
  }

  globalThis.VsemNativeCountsRGBA = Object.freeze({
    render: render
  });
})();
