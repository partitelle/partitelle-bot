/* partitelle match page: vanilla JS, no dependencies. Talks to /app/api/* with Telegram initData. */
(function () {
  'use strict';

  var tg = window.Telegram && window.Telegram.WebApp;
  var initData = tg && typeof tg.initData === 'string' ? tg.initData : '';
  var app = document.getElementById('app');
  var bar = document.getElementById('bar');
  var toastEl = document.getElementById('toast');
  var root = document.documentElement;

  var MARK = '<svg viewBox="100 89 327 323" aria-hidden="true" focusable="false" class="mark">' +
    '<g fill="none" stroke="currentColor" stroke-linecap="round"><path d="M196 150 178 116M221 142V100M246 150 264 116" stroke-width="22"/>' +
    '<circle cx="394" cy="206" r="24" stroke-width="18"/></g>' +
    '<path d="M122 188H198V218H244V188H300A112 112 0 1 1 190.6 276H122A22 22 0 0 1 100 254V210A22 22 0 0 1 122 188Z" fill="currentColor"/></svg>';

  var data = null;          // last State from the server
  var tab = 'lista';
  var busy = false;
  var toastTimer = null, slowTimer = null;

  // ---- helpers ----
  function h(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function add(parent) {
    for (var i = 1; i < arguments.length; i++) if (arguments[i]) parent.appendChild(arguments[i]);
    return parent;
  }
  function mark() { var s = h('span'); s.innerHTML = MARK; return s.firstChild; }
  function call(name) { // guarded Telegram call: older clients lack many methods
    try {
      if (tg && typeof tg[name] === 'function') return tg[name].apply(tg, Array.prototype.slice.call(arguments, 1));
    } catch (e) { /* ignore */ }
  }
  function sameName(a, b) { return String(a).toLowerCase() === String(b).toLowerCase(); }

  // ---- theme ----
  function applyTheme() {
    var dark = tg && tg.colorScheme ? tg.colorScheme === 'dark'
      : !!(window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
    root.setAttribute('data-theme', dark ? 'dark' : 'light');
    var c = dark ? '#111111' : '#FFFFFF';
    call('setHeaderColor', c);
    call('setBackgroundColor', c);
    call('setBottomBarColor', c);
  }

  // ---- toast ----
  function toast(text, ms) {
    toastEl.textContent = text;
    toastEl.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, ms || 3000);
  }

  // ---- network ----
  function post(path, body) {
    var ctl = new AbortController();
    var timer = setTimeout(function () { ctl.abort(); }, 20000);
    return fetch(path, {
      method: 'POST',
      headers: { 'Authorization': 'tma ' + initData, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctl.signal
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (json) {
        return { status: res.status, body: json };
      });
    }).then(function (r) { clearTimeout(timer); return r; },
            function (e) { clearTimeout(timer); throw e; });
  }

  // ---- full-screen states ----
  var STATES = {
    outside: ['si apre dal gruppo', 'questa pagina funziona solo dal pulsante "apri la lista" nel gruppo.', []],
    expired: ['link scaduto', 'riapri la lista dal gruppo.', ['close']],
    notmember: ['non sei nel gruppo', 'questa lista è solo per chi è nel gruppo.', ['close']],
    closed: ['lista chiusa', 'questo link è di una lista vecchia. apri quella nuova dal gruppo.', ['close']],
    error: ['non riesco a caricare', 'controlla la connessione e riprova.', ['retry', 'close']]
  };

  var PRIVACY = 'https://partitelle.com/privacy#mini-app';
  function privacyLink() {
    var a = h('a', 'privacy', 'privacy');
    a.href = PRIVACY;
    a.addEventListener('click', function (ev) {
      if (tg && typeof tg.openLink === 'function') {
        try { tg.openLink(PRIVACY); ev.preventDefault(); } catch (e) { /* follow the link */ }
      }
    });
    return a;
  }

  function closePage() { if (tg && typeof tg.close === 'function') tg.close(); else window.close(); }

  function showState(key) {
    clearTimeout(slowTimer);
    var s = STATES[key];
    bar.hidden = true; bar.textContent = '';
    root.style.setProperty('--bar-h', '0px');
    var col = h('div', 'col state');
    var title = h('h1', null, s[0]);
    title.tabIndex = -1;
    add(col, mark(), title, h('p', null, s[1]));
    s[2].forEach(function (b, i) {
      var btn = h('button', 'btn block ' + (i === 0 ? 'primary' : 'outline'), b === 'close' ? 'chiudi' : 'riprova');
      btn.type = 'button';
      btn.addEventListener('click', b === 'close' ? closePage : load);
      col.appendChild(btn);
    });
    col.appendChild(privacyLink());
    app.textContent = '';
    app.appendChild(col);
    title.focus({ preventScroll: true });
  }

  function showLoading() {
    var col = h('div', 'col state');
    var p = h('p', null, 'carico la lista…');
    add(col, mark(), p);
    app.textContent = '';
    app.appendChild(col);
    clearTimeout(slowTimer);
    slowTimer = setTimeout(function () {
      add(col, h('p', null, 'ci vuole un attimo più del solito.'));
    }, 4000);
  }

  // ---- derived values ----
  function counts(s) {
    var m = s.match, c = m.confirmed.length, may = m.maybe.length;
    return { c: c, may: may, t: m.target, free: Math.max(0, m.target - c - may),
      full: m.has_room === false || c + may >= m.target };
  }
  function hasTeams(m) {
    return !!(m.teams && ((m.teams.black && m.teams.black.length) || (m.teams.white && m.teams.white.length)));
  }

  // ---- match page ----
  function nameRow(num, name, isMe) {
    var li = h('li', 'row');
    if (num != null) li.appendChild(h('span', 'n', String(num)));
    li.appendChild(h('span', 'nm', name));
    if (isMe) li.appendChild(h('span', 'tu', 'tu'));
    return li;
  }

  function numbered(names, me) {
    var ol = h('ol'), meDone = false;
    names.forEach(function (n, i) {
      var isMe = !meDone && sameName(n, me);
      if (isMe) meDone = true;
      ol.appendChild(nameRow(i + 1, n, isMe));
    });
    return ol;
  }

  function renderHero(m, k) {
    var hero = h('section', 'hero');
    var top = h('div', 'hero-top');
    var h1 = h('h1');
    add(h1, h('span', 'nw', m.day.replace(/\/\d{4}$/, '').toLowerCase()), document.createTextNode(' · '),
      h('span', 'nw', m.time.toLowerCase()));
    add(top, h1, mark());
    var parts = [k.c + '/' + k.t], tail;
    if (k.may > 0) parts.push(k.may + ' in forse');
    if (k.c === 0 && k.may === 0) tail = 'ancora nessuno';
    else if (k.full) tail = 'lista completa';
    else tail = k.free === 1 ? 'manca uno' : 'mancano ' + k.free;
    parts.push(tail);
    var count = h('p', 'count');
    parts.forEach(function (t, i) {
      if (i) count.appendChild(document.createTextNode(' · '));
      count.appendChild(h('span', 'nw', t));
    });
    add(hero, top, count);
    if (m.pitch) hero.appendChild(h('p', 'pitch', m.pitch));
    return hero;
  }

  function renderLista(s, k) {
    var m = s.match, me = s.me.name;
    var sec = h('section', 'sec');
    sec.appendChild(h('h2', null, 'ci sono (' + k.c + ')'));
    var ol = numbered(m.confirmed, me);
    for (var i = k.c + 1; i <= k.c + k.free; i++) {
      var li = h('li', 'row free');
      add(li, h('span', 'n', String(i)), h('span', 'nm', 'posto libero'));
      ol.appendChild(li);
    }
    sec.appendChild(ol);
    var frag = [sec];
    if (k.may) {
      var s2 = h('section', 'sec');
      s2.appendChild(h('h2', null, 'forse (' + k.may + ')'));
      var ol2 = h('ol');
      var done = false;
      m.maybe.forEach(function (n) {
        var isMe = !done && sameName(n, me); if (isMe) done = true;
        ol2.appendChild(nameRow(null, n, isMe));
      });
      s2.appendChild(ol2);
      frag.push(s2);
    }
    var wrap = h('div', 'stack');
    frag.forEach(function (e) { wrap.appendChild(e); });
    return wrap;
  }

  function renderSquadre(s) {
    var m = s.match, wrap = h('div', 'stack');
    if (!hasTeams(m)) {
      var panel = h('div', 'panel');
      add(panel, h('h3', null, 'squadre non ancora fatte'),
        h('p', null, 'quando la lista è completa, scrivete /teams nel gruppo: le squadre escono a sorte e le vedete qui.'));
      return add(wrap, panel);
    }
    var grid = h('div', 'teams');
    [['nera', m.teams.black], ['bianca', m.teams.white]].forEach(function (t) {
      var col = h('section', 'team');
      var title = h('h3');
      var disc = h('span', 'disc ' + t[0]); disc.setAttribute('aria-hidden', 'true');
      add(title, disc, h('span', null, 'squadra ' + t[0]));
      add(col, title, numbered(t[1] || [], s.me.name));
      grid.appendChild(col);
    });
    return add(wrap, grid, h('p', 'note', 'squadre fatte a sorte con /teams.'));
  }

  function renderTabs(s, k) {
    var seg = h('div', 'seg');
    seg.setAttribute('role', 'tablist'); seg.setAttribute('aria-label', 'vista');
    var panels = { lista: renderLista(s, k), squadre: renderSquadre(s) };
    var btns = {};
    ['lista', 'squadre'].forEach(function (id) {
      var b = h('button', null, id);
      b.type = 'button'; b.id = 'tab-' + id;
      b.setAttribute('role', 'tab'); b.setAttribute('aria-controls', 'panel-' + id);
      b.addEventListener('click', function () { select(id, false); });
      b.addEventListener('keydown', function (ev) {
        if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
          ev.preventDefault();
          select(id === 'lista' ? 'squadre' : 'lista', true);
        }
      });
      btns[id] = b; seg.appendChild(b);
      var p = panels[id];
      p.id = 'panel-' + id; p.setAttribute('role', 'tabpanel'); p.setAttribute('aria-labelledby', 'tab-' + id);
    });
    function select(id, focus) {
      tab = id;
      Object.keys(btns).forEach(function (k2) {
        var on = k2 === id;
        btns[k2].setAttribute('aria-selected', on ? 'true' : 'false');
        btns[k2].tabIndex = on ? 0 : -1;
        panels[k2].hidden = !on;
      });
      if (focus) btns[id].focus();
    }
    select(tab, false);
    return [seg, panels.lista, panels.squadre];
  }

  // ---- action bar ----
  function actionBtn(label, action, cls, disabled, pressed) {
    var b = h('button', 'btn ' + cls, label);
    b.type = 'button'; b.dataset.action = action;
    if (disabled) b.setAttribute('aria-disabled', 'true');
    if (pressed) b.setAttribute('aria-busy', 'true');
    b.addEventListener('click', function () { onAction(action, b); });
    return b;
  }

  function renderBar(s, k) {
    var st = s.me.status, line, a = null, b = null, inRow = false;
    var pos = 0;
    s.match.confirmed.forEach(function (n, i) { if (!pos && sameName(n, s.me.name)) pos = i + 1; });
    if (st === 'in') {
      line = pos ? 'ci sei · n. ' + pos : 'ci sei'; inRow = true;
      a = ['forse', 'maybe']; b = ['non vengo', 'leave'];
    } else if (st === 'maybe') {
      line = 'sei in forse';
      a = ['ci sono', 'join']; b = ['non vengo', 'leave'];
    } else {
      line = k.full ? 'lista completa' : 'non sei in lista';
      a = ['ci sono', 'join']; b = k.full ? null : ['forse', 'maybe'];
    }
    var inner = h('div', 'bar-in');
    var status = h('p', 'status', line);
    status.id = 'status'; status.tabIndex = -1;
    var row = h('div', 'btns');
    var fullBlock = st === 'out' && k.full;
    add(row, actionBtn(a[0], a[1], inRow ? 'outline' : 'primary', fullBlock, false),
      b && actionBtn(b[0], b[1], 'outline', false, false));
    add(inner, status, row);
    bar.textContent = ''; bar.appendChild(inner); bar.hidden = false;
    root.style.setProperty('--bar-h', bar.offsetHeight + 'px');
  }

  function render(focusAction) {
    var k = counts(data);
    var col = h('div', 'col');
    add(col, renderHero(data.match, k));
    renderTabs(data, k).forEach(function (e) { col.appendChild(e); });
    col.appendChild(privacyLink());
    app.textContent = '';
    app.appendChild(col);
    renderBar(data, k);
    if (focusAction) {
      var t = bar.querySelector('[data-action="' + focusAction + '"]') || document.getElementById('status');
      if (t) t.focus({ preventScroll: true });
    }
  }

  // ---- actions ----
  function toastFor(res) {
    var m = res.state.match, c = m.confirmed.length, t = m.target, may = m.maybe.length;
    var n = c + '/' + t, o = res.outcome, msg;
    switch (o) {
      case 'added': msg = 'ci sei. ' + n; break;
      case 'confirmed': msg = 'ora ci sei. ' + n; break;
      case 'already_in': msg = 'ci sei già. ' + n; break;
      case 'proposed': msg = 'sei in forse.'; break;
      case 'moved_to_maybe': msg = 'ora sei in forse. ' + n; break;
      case 'already_maybe': msg = 'sei già in forse.'; break;
      case 'removed': msg = 'non sei più in lista. ' + n; break;
      case 'removed_maybe': msg = 'non sei più in forse.'; break;
      case 'not_in': msg = 'non eri in lista.'; break;
      case 'full': msg = fullMsg(c + may, may); break;
      case 'name_taken': msg = "c'è già qualcuno con il tuo nome in lista."; break;
      default: msg = null;
    }
    if (msg && res.teams_cancelled) msg += ' · squadre annullate: rifatele con /teams nel gruppo.';
    return msg;
  }
  function fullMsg(total, may) {
    return 'lista completa: siete già in ' + total + (may ? ' (' + may + ' in forse).' : '.');
  }

  function guardMessage(action) {
    if (!data || !hasTeams(data.match)) return null;
    var st = data.me.status;
    if (action === 'maybe' && st === 'in') return 'ci sono già le squadre: se passi in forse si annullano per tutti. vai avanti?';
    if (action === 'leave' && st !== 'out') return 'ci sono già le squadre: se ti togli si annullano per tutti. vai avanti?';
    return null;
  }

  function confirmAsk(msg, cb) {
    if (tg && typeof tg.showConfirm === 'function') {
      try { tg.showConfirm(msg, function (ok) { if (ok) cb(); }); return; } catch (e) { /* fall through */ }
    }
    if (window.confirm(msg)) cb();
  }

  function onAction(action, btn) {
    if (busy) return;
    if (btn.getAttribute('aria-disabled') === 'true') { // "ci sono" while full
      var k = counts(data);
      toast(fullMsg(k.c + k.may, k.may));
      return;
    }
    var msg = guardMessage(action);
    if (msg) confirmAsk(msg, function () { send(action, btn); }); else send(action, btn);
  }

  function send(action, btn) {
    busy = true;
    Array.prototype.forEach.call(bar.querySelectorAll('.btn'), function (b) { b.setAttribute('aria-disabled', 'true'); });
    btn.setAttribute('aria-busy', 'true');
    post('/app/api/action', { action: action }).then(function (r) {
      busy = false;
      var b = r.body || {};
      if (r.status === 200 && b.state) {
        data = b.state;
        render(action);
        var text = toastFor(b);
        if (text) toast(text, b.teams_cancelled ? 5000 : 3000);
        if (b.outcome !== 'full' && b.outcome !== 'name_taken') haptic();
      } else if (r.status === 401) showState('expired');
      else if (r.status === 403) showState('notmember');
      else if (r.status === 404) showState('closed');
      else {
        render(action);
        toast(r.status === 429 ? 'troppe richieste, aspetta un attimo.' : 'non è andata. riprova.');
        if (r.status === 409) refresh(); // lost a race: show what the list really says
      }
    }, function () { busy = false; render(action); toast('non è andata. riprova.'); });
  }
  function haptic() {
    try { if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light'); } catch (e) { /* ignore */ }
  }

  // ---- load ----
  function refresh() { // quiet re-fetch: keeps the page and the toast
    post('/app/api/match', {}).then(function (r) {
      if (busy) return;
      if (r.status === 200 && r.body && r.body.match) { data = r.body; render(); }
      else if (r.status === 401) showState('expired');
      else if (r.status === 403) showState('notmember');
      else if (r.status === 404) showState('closed');
    }, function () { /* keep what is shown */ });
  }

  function load() {
    showLoading();
    post('/app/api/match', {}).then(function (r) {
      clearTimeout(slowTimer);
      if (r.status === 200 && r.body && r.body.match) { data = r.body; render(); }
      else if (r.status === 401) showState('expired');
      else if (r.status === 403) showState('notmember');
      else if (r.status === 404) showState('closed');
      else showState('error');
    }, function () { showState('error'); });
  }

  // ---- start ----
  applyTheme();
  call('onEvent', 'themeChanged', applyTheme);
  if (!initData) showState('outside'); else showLoading();
  requestAnimationFrame(function () { call('ready'); call('expand'); });
  if (initData) load();
})();
