(function () {
  'use strict';

  function isFiniteNumber(x) {
    return typeof x === 'number' && Number.isFinite(x);
  }

  function isSafeInt(x) {
    return Number.isSafeInteger(x);
  }

  function validateShared(buffer, width, height, completedPixels, activeDwellNs, dwellNs, units) {
    if (typeof buffer !== 'object' || buffer === null) throw new Error('buffer must be an ArrayBuffer');
    if (typeof SharedArrayBuffer !== 'undefined' && buffer instanceof SharedArrayBuffer) throw new Error('SharedArrayBuffer not allowed');
    if (!(buffer instanceof ArrayBuffer)) throw new Error('buffer must be an ArrayBuffer');
    if (!isSafeInt(width) || width < 1 || width > 4096) throw new Error('invalid width');
    if (!isSafeInt(height) || height < 1 || height > 4096) throw new Error('invalid height');
    if (buffer.byteLength !== width * height * 4) throw new Error('buffer size mismatch');
    if (!isSafeInt(completedPixels) || completedPixels < 0 || completedPixels > width * height) throw new Error('invalid completedPixels');
    if (!isSafeInt(dwellNs) || dwellNs < 1 || dwellNs > 10000000) throw new Error('invalid dwellNs');
    if (!isSafeInt(activeDwellNs) || activeDwellNs < 0 || activeDwellNs >= dwellNs) throw new Error('invalid activeDwellNs');
    if (completedPixels === width * height && activeDwellNs !== 0) throw new Error('activeDwellNs must be 0 when all pixels completed');
    if (units !== 'counts' && units !== 'cps') throw new Error('units must be counts or cps');
  }

  function readSamples(buffer, width, height, completedPixels, activeDwellNs, dwellNs, units) {
    const dv = new DataView(buffer);
    const total = width * height;
    const samples = [];
    for (let i = 0; i < total; i++) {
      let exposure;
      if (i < completedPixels) {
        exposure = dwellNs;
      } else if (i === completedPixels && activeDwellNs > 0) {
        exposure = activeDwellNs;
      } else {
        continue;
      }
      const raw = dv.getUint32(i * 4, true);
      if (units === 'counts') {
        samples.push(raw);
      } else {
        samples.push(raw * 1e9 / exposure);
      }
    }
    return samples;
  }

  function render(buffer, width, height, completedPixels, activeDwellNs, dwellNs, units, low, high, gamma, brightness, contrast) {
    validateShared(buffer, width, height, completedPixels, activeDwellNs, dwellNs, units);
    if (!isFiniteNumber(low) || !isFiniteNumber(high) || low < 0 || low >= high) throw new Error('invalid low/high');
    if (!isFiniteNumber(gamma) || gamma < 0.1 || gamma > 5) throw new Error('invalid gamma');
    if (!isFiniteNumber(brightness) || brightness < -1 || brightness > 1) throw new Error('invalid brightness');
    if (!isFiniteNumber(contrast) || contrast < 0.05 || contrast > 4) throw new Error('invalid contrast');

    const total = width * height;
    const out = new Uint8ClampedArray(total * 4);
    const dv = new DataView(buffer);
    const range = high - low;
    const invGamma = 1 / gamma;

    for (let i = 0; i < total; i++) {
      let acquired = false;
      let v = 0;
      if (i < completedPixels) {
        acquired = true;
        const raw = dv.getUint32(i * 4, true);
        if (units === 'counts') v = raw;
        else v = raw * 1e9 / dwellNs;
      } else if (i === completedPixels && activeDwellNs > 0) {
        acquired = true;
        const raw = dv.getUint32(i * 4, true);
        if (units === 'counts') v = raw;
        else v = raw * 1e9 / activeDwellNs;
      }

      if (!acquired) {
        out[i * 4] = 0;
        out[i * 4 + 1] = 0;
        out[i * 4 + 2] = 0;
        out[i * 4 + 3] = 255;
        continue;
      }

      const u = (v - low) / range;
      let t = (u - 0.5) * contrast + 0.5 + brightness;
      if (t < 0) t = 0;
      if (t > 1) t = 1;
      const byte = Math.round(255 * Math.pow(t, invGamma));
      out[i * 4] = byte;
      out[i * 4 + 1] = byte;
      out[i * 4 + 2] = byte;
      out[i * 4 + 3] = 255;
    }
    return out;
  }

  function histogram(buffer, width, height, completedPixels, activeDwellNs, dwellNs, units, bins) {
    validateShared(buffer, width, height, completedPixels, activeDwellNs, dwellNs, units);
    if (!isSafeInt(bins) || bins < 2 || bins > 4096) throw new Error('invalid bins');

    const samples = readSamples(buffer, width, height, completedPixels, activeDwellNs, dwellNs, units);
    const n = samples.length;
    const counts = new Array(bins).fill(0);

    if (n === 0) {
      return { sampleCount: 0, minimum: 0, maximum: 1, counts };
    }

    let min = samples[0];
    let max = samples[0];
    for (let i = 1; i < n; i++) {
      if (samples[i] < min) min = samples[i];
      if (samples[i] > max) max = samples[i];
    }

    if (min === max) {
      counts[0] = n;
    } else {
      const range = max - min;
      for (let i = 0; i < n; i++) {
        let b = Math.floor((samples[i] - min) / range * bins);
        if (b >= bins) b = bins - 1;
        if (b < 0) b = 0;
        counts[b]++;
      }
    }

    return { sampleCount: n, minimum: min, maximum: max, counts };
  }

  function autoWindow(buffer, width, height, completedPixels, activeDwellNs, dwellNs, units, qLow, qHigh) {
    validateShared(buffer, width, height, completedPixels, activeDwellNs, dwellNs, units);
    if (!isFiniteNumber(qLow) || !isFiniteNumber(qHigh) || qLow < 0 || qLow >= qHigh || qHigh > 1) throw new Error('invalid quantiles');

    const samples = readSamples(buffer, width, height, completedPixels, activeDwellNs, dwellNs, units);
    const n = samples.length;

    if (n === 0) {
      return { low: 0, high: 1 };
    }

    samples.sort((a, b) => a - b);

    function quantile(q) {
      const p = q * (n - 1);
      const j = Math.floor(p);
      const f = p - j;
      const idx = Math.min(j + 1, n - 1);
      return samples[j] + f * (samples[idx] - samples[j]);
    }

    let low = quantile(qLow);
    let high = quantile(qHigh);

    if (high === low) {
      const originalValue = low;
      const pad = Math.max(1, Math.abs(originalValue) * 0.01);
      low = Math.max(0, originalValue - pad);
      high = originalValue + pad;
    }

    return { low, high };
  }

  const VsemIntensityTransfer = { render, histogram, autoWindow };
  globalThis.VsemIntensityTransfer = VsemIntensityTransfer;
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = VsemIntensityTransfer;
  }
})();
