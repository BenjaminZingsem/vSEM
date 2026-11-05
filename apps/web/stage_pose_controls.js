(function () {
  'use strict';

  var EM_DASH = '\u2014';

  var READBACK_ROLES = [
    'x-readback',
    'y-readback',
    'z-readback',
    'wd-readback',
    'motion-readback',
    'xy-step',
    'z-step'
  ];

  var BUTTON_DEFS = [
    { action: 'x-minus', label: '-X', gate: 'canEditXY' },
    { action: 'x-plus', label: '+X', gate: 'canEditXY' },
    { action: 'y-minus', label: '-Y', gate: 'canEditXY' },
    { action: 'y-plus', label: '+Y', gate: 'canEditXY' },
    { action: 'z-minus', label: '-Z', gate: 'canEditZ' },
    { action: 'z-plus', label: '+Z', gate: 'canEditZ' },
    { action: 'move', label: 'Move XYZ', gate: 'canMove' },
    { action: 'stop', label: 'Stop stage', gate: 'canStop' }
  ];

  var STRING_KEYS = [
    'xReadback',
    'yReadback',
    'zReadback',
    'wdReadback',
    'motionReadback',
    'xyStep',
    'zStep'
  ];

  var BOOLEAN_KEYS = ['canEditXY', 'canEditZ', 'canMove', 'canStop'];

  function isPlainObject(value) {
    if (value === null || typeof value !== 'object') {
      return false;
    }
    var proto = Object.getPrototypeOf(value);
    return proto === Object.prototype || proto === null;
  }

  function isExactBoolean(value) {
    return typeof value === 'boolean';
  }

  function isExactString(value) {
    return typeof value === 'string';
  }

  function validateSnapshot(snapshot) {
    if (!isPlainObject(snapshot)) {
      return false;
    }
    var keys = Reflect.ownKeys(snapshot);
    if (keys.length !== 11) {
      return false;
    }
    var i;
    for (i = 0; i < STRING_KEYS.length; i += 1) {
      var sKey = STRING_KEYS[i];
      if (!Object.prototype.hasOwnProperty.call(snapshot, sKey)) {
        return false;
      }
      var sVal = snapshot[sKey];
      if (!isExactString(sVal)) {
        return false;
      }
      if (sVal.length > 80) {
        return false;
      }
    }
    for (i = 0; i < BOOLEAN_KEYS.length; i += 1) {
      var bKey = BOOLEAN_KEYS[i];
      if (!Object.prototype.hasOwnProperty.call(snapshot, bKey)) {
        return false;
      }
      if (!isExactBoolean(snapshot[bKey])) {
        return false;
      }
    }
    return true;
  }

  function create(container, onAction) {
    if (!(container instanceof Element)) {
      throw new TypeError('container must be an Element');
    }
    if (typeof onAction !== 'function') {
      throw new TypeError('onAction must be a function');
    }

    var doc = container.ownerDocument;
    var section = doc.createElement('section');
    section.className = 'stage-pose-controls';
    section.setAttribute('data-role', 'stage-pose-controls');

    var heading = doc.createElement('h2');
    heading.textContent = 'Stage XYZ';
    section.appendChild(heading);

    var readbackEls = [];
    var i;
    for (i = 0; i < READBACK_ROLES.length; i += 1) {
      var out = doc.createElement('output');
      out.setAttribute('data-role', READBACK_ROLES[i]);
      out.textContent = EM_DASH;
      section.appendChild(out);
      readbackEls.push(out);
    }

    var gates = {
      canEditXY: false,
      canEditZ: false,
      canMove: false,
      canStop: false
    };

    var buttons = [];
    var handlers = [];
    for (i = 0; i < BUTTON_DEFS.length; i += 1) {
      var def = BUTTON_DEFS[i];
      var btn = doc.createElement('button');
      btn.type = 'button';
      btn.setAttribute('data-action', def.action);
      btn.textContent = def.label;
      btn.disabled = true;

      (function (action, gateKey) {
        var handler = function () {
          if (destroyed) {
            return;
          }
          if (gates[gateKey] !== true) {
            return;
          }
          onAction(action);
        };
        btn.addEventListener('click', handler);
        handlers.push({ el: btn, handler: handler });
      })(def.action, def.gate);

      section.appendChild(btn);
      buttons.push(btn);
    }

    container.appendChild(section);

    var destroyed = false;

    function update(snapshot) {
      if (destroyed) {
        return;
      }
      if (!validateSnapshot(snapshot)) {
        throw new TypeError('Invalid closed stage readback snapshot');
      }
      var texts = [
        snapshot.xReadback,
        snapshot.yReadback,
        snapshot.zReadback,
        snapshot.wdReadback,
        snapshot.motionReadback,
        snapshot.xyStep,
        snapshot.zStep
      ];
      var j;
      for (j = 0; j < readbackEls.length; j += 1) {
        readbackEls[j].textContent = texts[j];
      }
      gates.canEditXY = snapshot.canEditXY;
      gates.canEditZ = snapshot.canEditZ;
      gates.canMove = snapshot.canMove;
      gates.canStop = snapshot.canStop;
      for (j = 0; j < buttons.length; j += 1) {
        buttons[j].disabled = !gates[BUTTON_DEFS[j].gate];
      }
    }

    function destroy() {
      if (destroyed) {
        return;
      }
      destroyed = true;
      var k;
      for (k = 0; k < handlers.length; k += 1) {
        handlers[k].el.removeEventListener('click', handlers[k].handler);
      }
      handlers.length = 0;
      if (section.parentNode === container) {
        container.removeChild(section);
      }
    }

    return Object.freeze({
      update: update,
      destroy: destroy
    });
  }

  globalThis.VsemStagePoseControls = Object.freeze({
    create: create
  });
})();
