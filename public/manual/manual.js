// Hallmark Wayfind Manual — Real Screenshot Callout Overlay + Tab Switcher + Two-Way Sync
(function () {
  var FALLBACK_COORDS = {
    '01-overview-nav.png': [
      { id: 1, box: { left: 85.28, top: 1.28, width: 4.96, height: 3.11 }, pin: { x: 85.28, y: 4.39 } },
      { id: 2, box: { left: 0.69, top: 18.67, width: 20.76, height: 13.33 }, pin: { x: 2.0, y: 18.67 } },
      { id: 3, box: { left: 0.69, top: 68.48, width: 20.76, height: 31.52 }, pin: { x: 2.0, y: 68.48 } },
      { id: 4, box: { left: 26.11, top: 7.56, width: 71.39, height: 4.56 }, pin: { x: 26.11, y: 7.56 } }
    ],
    '02-area-builder.png': [
      { id: 1, box: { left: 90.43, top: 11.97, width: 5.89, height: 2.56 }, pin: { x: 90.43, y: 11.97 } },
      { id: 2, box: { left: 28.06, top: 18.85, width: 67.5, height: 2.56 }, pin: { x: 28.06, y: 18.85 } },
      { id: 3, box: { left: 87.35, top: 22.85, width: 7.44, height: 2.44 }, pin: { x: 87.35, y: 22.85 } },
      { id: 4, box: { left: 26.11, top: 5.78, width: 71.39, height: 4.56 }, pin: { x: 26.11, y: 5.78 } }
    ],
    '03-terminal-safety.png': [
      { id: 1, box: { left: 30.63, top: 31.69, width: 38.75, height: 5.33 }, pin: { x: 30.63, y: 31.69 } },
      { id: 2, box: { left: 31.74, top: 38.81, width: 36.53, height: 6.61 }, pin: { x: 31.74, y: 38.81 } },
      { id: 3, box: { left: 31.74, top: 50.08, width: 36.53, height: 10.44 }, pin: { x: 31.74, y: 50.08 } },
      { id: 4, box: { left: 59.92, top: 63.75, width: 8.34, height: 3.22 }, pin: { x: 59.92, y: 63.75 } }
    ],
    '04-guide-studio.png': [
      { id: 1, box: { left: 9.79, top: 14.44, width: 80.42, height: 5.89 }, pin: { x: 9.79, y: 14.44 } },
      { id: 2, box: { left: 10.9, top: 27.33, width: 37.92, height: 2.89 }, pin: { x: 10.9, y: 27.33 } },
      { id: 3, box: { left: 51.11, top: 25.67, width: 37.99, height: 18.33 }, pin: { x: 51.11, y: 25.67 } },
      { id: 4, box: { left: 74.45, top: 88.0, width: 14.51, height: 4.56 }, pin: { x: 74.45, y: 88.0 } }
    ],
    '05-wiki-editor.png': [
      { id: 1, box: { left: 27.15, top: 19.06, width: 69.31, height: 2.33 }, pin: { x: 27.15, y: 19.06 } },
      { id: 2, box: { left: 27.15, top: 22.5, width: 69.31, height: 2.89 }, pin: { x: 27.15, y: 22.5 } },
      { id: 3, box: { left: 27.15, top: 26.5, width: 69.31, height: 12.22 }, pin: { x: 27.15, y: 26.5 } },
      { id: 4, box: { left: 27.15, top: 39.83, width: 69.31, height: 4.56 }, pin: { x: 27.15, y: 39.83 } }
    ],
    '06-steps-and-zoom.png': [
      { id: 1, box: { left: 11.22, top: 23.44, width: 9.9, height: 3.78 }, pin: { x: 11.22, y: 23.44 } },
      { id: 2, box: { left: 2.71, top: 48.3, width: 18.75, height: 5.07 }, pin: { x: 2.71, y: 48.3 } },
      { id: 3, box: { left: 26.11, top: 14.11, width: 71.39, height: 2.67 }, pin: { x: 84.0, y: 15.44 } },
      { id: 4, box: { left: 26.11, top: 29.06, width: 71.39, height: 10.6 }, pin: { x: 26.11, y: 29.06 } }
    ]
  };

  function pinCoords(item) {
    var box = item.box || {};
    var left = typeof box.left === 'number' ? box.left : 10;
    var top = typeof box.top === 'number' ? box.top : 10;
    var width = typeof box.width === 'number' ? box.width : 10;
    var height = typeof box.height === 'number' ? box.height : 5;
    // Clamp inside 3.5..96.5% so 28px square pin plate never clips on container border
    var x = Math.min(96.5, Math.max(3.5, left));
    var y = top < 4 ? Math.min(96.5, Math.max(3.5, top + height)) : Math.min(96.5, Math.max(3.5, top));
    if (item.pin && item.pin.x > left + width * 0.7 && width > 50) {
      x = Math.min(96.5, Math.max(3.5, item.pin.x));
    }
    return { x: x, y: y };
  }

  function setStep(group, stepId) {
    var items = document.querySelectorAll('.route-list[data-route-group="' + group + '"] .route-item');
    items.forEach(function (it) {
      it.classList.toggle('is-active', String(it.getAttribute('data-step')) === String(stepId));
    });
    var stage = document.querySelector('.shot-stage[data-route-group="' + group + '"]');
    if (!stage) return;
    stage.querySelectorAll('.shot-box, .shot-pin').forEach(function (el) {
      el.classList.toggle('is-active', String(el.getAttribute('data-step')) === String(stepId));
    });
  }

  function mountOverlays(coordsMap) {
    document.querySelectorAll('.shot-stage[data-screen]').forEach(function (stage) {
      var screen = stage.getAttribute('data-screen');
      var group = stage.getAttribute('data-route-group');
      var items = coordsMap[screen] || FALLBACK_COORDS[screen];
      if (!items) return;

      stage.querySelectorAll('.shot-box, .shot-pin').forEach(function (n) { n.remove(); });
      items.forEach(function (item, idx) {
        var boxEl = document.createElement('div');
        boxEl.className = 'shot-box' + (idx === 0 ? ' is-active' : '');
        boxEl.setAttribute('data-step', String(item.id));
        boxEl.setAttribute('data-keep', '1');
        boxEl.style.left = item.box.left + '%';
        boxEl.style.top = item.box.top + '%';
        boxEl.style.width = item.box.width + '%';
        boxEl.style.height = item.box.height + '%';
        stage.appendChild(boxEl);

        var pos = pinCoords(item);
        var pin = document.createElement('button');
        pin.type = 'button';
        pin.className = 'shot-pin' + (idx === 0 ? ' is-active' : '');
        pin.setAttribute('data-step', String(item.id));
        pin.setAttribute('data-keep', '1');
        pin.setAttribute('aria-label', item.id + '번 위치 강조');
        pin.style.left = pos.x + '%';
        pin.style.top = pos.y + '%';
        pin.textContent = String(item.id);
        pin.addEventListener('click', function () {
          if (group) {
            setStep(group, item.id);
            var targetBtn = document.querySelector('.route-list[data-route-group="' + group + '"] .route-item[data-step="' + item.id + '"] .route-trigger');
            if (targetBtn) targetBtn.focus({ preventScroll: true });
          } else {
            stage.querySelectorAll('.shot-box, .shot-pin').forEach(function (el) {
              el.classList.toggle('is-active', String(el.getAttribute('data-step')) === String(item.id));
            });
          }
        });
        stage.appendChild(pin);
      });
    });
  }

  function initRouteLists() {
    document.querySelectorAll('.route-list[data-route-group]').forEach(function (list) {
      var group = list.getAttribute('data-route-group');
      list.querySelectorAll('.route-item').forEach(function (item) {
        var stepId = item.getAttribute('data-step');
        var btn = item.querySelector('.route-trigger');
        item.addEventListener('click', function () { setStep(group, stepId); });
        if (btn) btn.addEventListener('focus', function () { setStep(group, stepId); });
      });
    });
  }

  function initSwitchers() {
    document.querySelectorAll('[data-switch]').forEach(function (sw) {
      var tabs = Array.prototype.slice.call(sw.querySelectorAll('[role="tab"]'));
      var panels = Array.prototype.slice.call(sw.querySelectorAll('[role="tabpanel"]'));
      function activate(idx) {
        tabs.forEach(function (t, i) {
          var on = i === idx;
          t.setAttribute('aria-selected', on ? 'true' : 'false');
          if (on) t.removeAttribute('tabindex');
          else t.setAttribute('tabindex', '-1');
        });
        panels.forEach(function (p, i) {
          p.hidden = i !== idx;
        });
      }
      tabs.forEach(function (tab, idx) {
        tab.addEventListener('click', function () { activate(idx); });
        tab.addEventListener('keydown', function (e) {
          if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
            var next = e.key === 'ArrowRight' ? (idx + 1) % tabs.length : (idx - 1 + tabs.length) % tabs.length;
            activate(next);
            tabs[next].focus();
          }
        });
      });
    });
  }

  initSwitchers();
  initRouteLists();
  mountOverlays(FALLBACK_COORDS);

  fetch('./screens/coords.json', { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) { if (data) mountOverlays(data); })
    .catch(function () {});
})();
