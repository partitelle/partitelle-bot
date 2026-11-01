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
  var toastSeq = 0, toastTimer = null, slowTimer = null, snackOn = false;

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

  // ---- toast and undo snackbar (the same box) ----
  function clearToastSoon() {
    setTimeout(function () { if (!toastEl.classList.contains('show')) { toastEl.textContent = ''; toastEl.classList.remove('snack'); } }, 260);
  }
  function toast(text, ms) {
    clearTimeout(toastTimer);
    snackOn = false;
    toastEl.classList.remove('snack');
    toastEl.textContent = '';
    toastEl.classList.add('show');
    var mine = ++toastSeq;
    requestAnimationFrame(function () { if (mine === toastSeq) toastEl.textContent = text; });
    toastTimer = setTimeout(function () { toastEl.classList.remove('show'); }, ms || 3000);
  }
  function hideSnack() {
    if (!snackOn) return;
    snackOn = false;
    clearTimeout(toastTimer);
    toastEl.classList.remove('show');
    clearToastSoon();
  }
  function snackStart() {
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      snackOn = false;
      toastEl.classList.remove('show');
      clearToastSoon();
    }, 6000);
  }
  function showSnack(text, onUndo) {
    clearTimeout(toastTimer);
    toastEl.textContent = '';
    var mine = ++toastSeq;
    var btn = h('button', 'snack-btn', 'annulla');
    btn.type = 'button';
    btn.setAttribute('aria-label', 'annulla lo scambio');
    btn.addEventListener('click', function () { onUndo(btn); });
    toastEl.classList.add('snack', 'show');
    requestAnimationFrame(function () { if (mine === toastSeq) add(toastEl, h('span', null, text), btn); });
    snackOn = true;
    snackStart();
  }
  function pauseSnack() { if (snackOn) clearTimeout(toastTimer); }
  function resumeSnack() { if (snackOn) snackStart(); }
  toastEl.addEventListener('mouseenter', pauseSnack);
  toastEl.addEventListener('focusin', pauseSnack);
  toastEl.addEventListener('mouseleave', function () { if (!toastEl.contains(document.activeElement)) resumeSnack(); });
  toastEl.addEventListener('focusout', function () { if (!toastEl.matches(':hover')) resumeSnack(); });

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
  function lower(s) { return String(s).toLowerCase(); }
  function indexOfName(list, name) {
    for (var i = 0; i < list.length; i++) if (sameName(list[i], name)) return i;
    return -1;
  }
  // the chat's join: "a", "a e b", "a, b e c", more than 4: "a, b, c e altre 2 persone"
  function joinNames(names) {
    if (names.length === 1) return names[0];
    if (names.length <= 4) return names.slice(0, -1).join(', ') + ' e ' + names[names.length - 1];
    return names.slice(0, 3).join(', ') + ' e altre ' + (names.length - 3) + ' persone';
  }
  function drawState(s) { // the chat's order: odd target, then confirmed == target
    var m = s.match, c = m.confirmed.length, t = m.target, may = m.maybe.length;
    if (t % 2 !== 0) return { ready: false, why: 'la partita è da ' + t + ': per sorteggiare le squadre serve un numero pari.' };
    if (c < t) {
      return { ready: false, why: 'si possono sorteggiare quando ci sono ' + t + ' persone. ora ci sono ' + c + '.' +
        (may > 0 ? ' chi è in forse non conta.' : '') };
    }
    if (c > t) return { ready: false, why: 'si possono sorteggiare quando ci sono esattamente ' + t + ' persone. ora ci sono ' + c + '.' };
    return { ready: true, why: 'la lista è completa. le squadre vengono sorteggiate e le vede anche il gruppo.' };
  }

  // ---- ui state that survives a re-render ----
  var formOpen = false, formText = '', formErr = '', inputFocused = false;
  var noteOpen = false;
  var sel = null;           // the selected team row (an entry of teamBtns)
  var teamBtns = [], teamCols = {}, listBtns = [];

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
    var pitch = h('p', 'pitch');
    var val = m.pitch && String(m.pitch).trim() ? m.pitch : 'ancora da decidere: scrivete /setpitch nel gruppo.';
    add(pitch, h('span', 'pl', 'campo'), document.createTextNode(' '), h('span', 'pv', val));
    return add(hero, top, count, pitch);
  }

  function renderNote(m) {
    var text = m.description == null ? '' : String(m.description).trim();
    if (!text) return null;
    var box = h('section', 'noteb');
    var p = h('p', 'note-text' + (noteOpen ? ' open' : ''), text);
    p.id = 'note-text';
    var more = h('button', 'link', noteOpen ? 'mostra meno' : 'mostra tutto');
    more.type = 'button'; more.id = 'note-more'; more.hidden = true;
    more.setAttribute('aria-expanded', noteOpen ? 'true' : 'false');
    more.setAttribute('aria-controls', 'note-text');
    more.addEventListener('click', function () {
      noteOpen = !noteOpen;
      p.classList.toggle('open', noteOpen);
      more.textContent = noteOpen ? 'mostra meno' : 'mostra tutto';
      more.setAttribute('aria-expanded', noteOpen ? 'true' : 'false');
    });
    return add(box, h('h2', null, 'note'), p, more);
  }
  function fitNote() {
    var p = document.getElementById('note-text'), b = document.getElementById('note-more');
    if (!p || !b) return;
    if (noteOpen) { b.hidden = false; return; }
    b.hidden = p.scrollHeight <= p.clientHeight + 1;
  }

  // a row for someone else: the whole row opens the action menu
  function personRow(num, name, kind, pos) {
    var li = h('li', 'row has-btn');
    var b = h('button', 'rb');
    b.type = 'button';
    b.setAttribute('aria-haspopup', 'dialog');
    b.setAttribute('aria-label', kind === 'in' ? name + ', n. ' + pos + ': azioni' : name + ', in forse: azioni');
    var more = h('span', 'more', '⋯');
    more.setAttribute('aria-hidden', 'true');
    add(b, num != null && h('span', 'n', String(num)), h('span', 'nm', name), more);
    b.addEventListener('click', function () { openMenu(name, kind, pos, b); });
    li.appendChild(b);
    listBtns.push({ name: name, btn: b });
    return li;
  }

  function addForm(k) {
    var wrap = h('div', 'addwrap');
    var open = h('button', 'btn outline block', 'aggiungi qualcuno');
    open.type = 'button';
    open.setAttribute('aria-expanded', 'false'); open.setAttribute('aria-controls', 'add-form');
    var form = h('form', 'panel addform');
    form.id = 'add-form'; form.noValidate = true;
    var head = h('div', 'form-head');
    var close = h('button', 'link', 'chiudi');
    close.type = 'button';
    add(head, h('h2', null, 'aggiungi qualcuno'), close);
    var label = h('label', null, 'nomi'); label.htmlFor = 'add-input';
    var input = h('input', 'field');
    input.id = 'add-input'; input.type = 'text'; input.name = 'nomi'; input.maxLength = 300;
    input.placeholder = 'es. luca, marco'; input.value = formText;
    input.setAttribute('autocapitalize', 'none'); input.setAttribute('autocomplete', 'off');
    input.setAttribute('autocorrect', 'off'); input.setAttribute('spellcheck', 'false');
    input.setAttribute('enterkeyhint', 'done');
    input.setAttribute('aria-describedby', 'add-hint add-err');
    var hint = h('div', 'hint'); hint.id = 'add-hint';
    hint.appendChild(h('p', null, 'più nomi? separali con una virgola.'));
    if (k.c + k.may >= k.t) hint.appendChild(h('p', null, 'la lista è completa: i nomi nuovi restano fuori.'));
    var err = h('p', 'form-err'); err.id = 'add-err'; err.setAttribute('role', 'alert');
    var go = h('button', 'btn primary', 'aggiungi'); go.type = 'submit';
    var maybe = h('button', 'btn outline', 'in forse'); maybe.type = 'button';
    maybe.setAttribute('aria-label', 'aggiungi in forse');
    var btns = h('div', 'pair');
    add(btns, go, maybe);
    add(form, head, label, input, hint, err, btns);

    function showErr(msg) {
      formErr = msg || '';
      err.hidden = !formErr;
      err.textContent = formErr ? 'errore: ' + formErr : '';
      if (formErr) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid');
    }
    function setOpen(on) {
      formOpen = on;
      form.hidden = !on; open.hidden = on;
      open.setAttribute('aria-expanded', on ? 'true' : 'false');
    }
    showErr(formErr); setOpen(formOpen);
    open.addEventListener('click', function () { setOpen(true); input.focus(); });
    close.addEventListener('click', function () { setOpen(false); open.focus(); });
    input.addEventListener('input', function () { formText = input.value; if (formErr) showErr(''); });
    input.addEventListener('focus', function () {
      inputFocused = true; bar.hidden = true; root.style.setProperty('--bar-h', '0px');
    });
    input.addEventListener('blur', function () { inputFocused = false; restoreBar(); });
    function submit(action, btn) {
      if (busy) return;
      var names = parseNames(input.value);
      if (!names.length) { showErr('scrivi almeno un nome.'); input.focus(); return; }
      if (names.some(function (n) { return n.charAt(0) === '/'; })) {
        showErr('un nome non può iniziare con /.'); input.focus(); return;
      }
      showErr('');
      input.blur();
      var go2 = function () {
        act({ action: action, text: names.join(', ') }, {
          busy: [btn],
          after: function () { focusById(btn === go ? 'add-go' : 'add-maybe'); },
          onOk: function (b) {
            formText = '';
            render(function () { focusById(btn === go ? 'add-go' : 'add-maybe'); });
            outcomeToast(b, action);
          },
          onInvalid: function () {
            formErr = 'un nome non può iniziare con /.';
            render(function () { var i = document.getElementById('add-input'); if (i) i.focus(); });
          }
        });
      };
      if (action === 'propose' && hasTeams(data.match)) {
        var hit = names.filter(function (n) { return indexOfName(data.match.confirmed, n) >= 0; });
        if (hit.length) {
          confirmAsk('ci sono già le squadre: se sposti ' + joinNames(hit) + ' in forse si annullano per tutti. vai avanti?', go2);
          return;
        }
      }
      go2();
    }
    go.id = 'add-go'; maybe.id = 'add-maybe';
    form.addEventListener('submit', function (ev) { ev.preventDefault(); submit('add', go); });
    maybe.addEventListener('click', function () { submit('propose', maybe); });
    return add(wrap, open, form);
  }
  function parseNames(text) { // as the chat: split on commas, trim, drop empties, lowercase, dedup
    var out = [];
    String(text).split(',').forEach(function (p) {
      var n = lower(p.trim());
      if (n && out.indexOf(n) < 0) out.push(n);
    });
    return out;
  }
  function focusById(id) {
    var e = document.getElementById(id);
    if (e) e.focus({ preventScroll: true });
  }

  function renderLista(s, k) {
    var m = s.match, me = s.me.name;
    var sec = h('section', 'sec');
    var h2 = h('h2', null, 'ci sono (' + k.c + ')');
    h2.id = 'h-in'; h2.tabIndex = -1;
    sec.appendChild(h2);
    var ol = h('ol'), meDone = false;
    m.confirmed.forEach(function (n, i) {
      var isMe = !meDone && sameName(n, me);
      if (isMe) { meDone = true; ol.appendChild(nameRow(i + 1, n, true)); }
      else ol.appendChild(personRow(i + 1, n, 'in', i + 1));
    });
    for (var i = k.c + 1; i <= k.c + k.free; i++) {
      var li = h('li', 'row free');
      add(li, h('span', 'n', String(i)), h('span', 'nm', 'posto libero'));
      ol.appendChild(li);
    }
    sec.appendChild(ol);
    var wrap = h('div', 'stack');
    add(wrap, addForm(k), sec);
    if (k.may) {
      var s2 = h('section', 'sec');
      var h2b = h('h2', null, 'forse (' + k.may + ')');
      h2b.id = 'h-maybe'; h2b.tabIndex = -1;
      s2.appendChild(h2b);
      var ol2 = h('ol');
      var done = false;
      m.maybe.forEach(function (n) {
        var isMe = !done && sameName(n, me); if (isMe) done = true;
        ol2.appendChild(isMe ? nameRow(null, n, true) : personRow(null, n, 'maybe', 0));
      });
      s2.appendChild(ol2);
      wrap.appendChild(s2);
    }
    return wrap;
  }

  // ---- squadre ----
  var COLOUR = { black: 'nera', white: 'bianca' };

  function renderSquadre(s) {
    var m = s.match, wrap = h('div', 'stack');
    if (!hasTeams(m)) {
      var ds = drawState(s);
      var panel = h('div', 'panel');
      var why = h('p', null, ds.why); why.id = 'draw-why';
      var btn = h('button', 'btn primary block', 'sorteggia le squadre');
      btn.type = 'button'; btn.id = 'draw-btn';
      if (!ds.ready) { btn.setAttribute('aria-disabled', 'true'); btn.setAttribute('aria-describedby', 'draw-why'); }
      btn.addEventListener('click', function () { onDraw(btn); });
      add(panel, h('h3', null, 'squadre non ancora fatte'), why, btn);
      return add(wrap, panel);
    }
    var grid = h('div', 'teams');
    [['black', m.teams.black], ['white', m.teams.white]].forEach(function (t) {
      var col = h('section', 'team');
      var title = h('h3');
      title.id = 'h-' + t[0]; title.tabIndex = -1;
      var disc = h('span', 'disc ' + COLOUR[t[0]]); disc.setAttribute('aria-hidden', 'true');
      add(title, disc, h('span', null, 'squadra ' + COLOUR[t[0]]));
      var ol = h('ol'), meDone = false;
      (t[1] || []).forEach(function (n, i) {
        var isMe = !meDone && sameName(n, s.me.name);
        if (isMe) meDone = true;
        var li = h('li', 'row has-btn');
        var b = h('button', 'rb');
        b.type = 'button'; b.setAttribute('aria-pressed', 'false');
        add(b, h('span', 'n', String(i + 1)), h('span', 'nm', n), isMe && h('span', 'tu', 'tu'));
        li.appendChild(b); ol.appendChild(li);
        var entry = { name: n, team: t[0], btn: b };
        teamBtns.push(entry);
        b.addEventListener('click', function () { onTeamTap(entry); });
      });
      add(col, title, ol);
      teamCols[t[0]] = col;
      grid.appendChild(col);
    });
    var hint = h('p', 'note'); hint.id = 'swap-hint'; hint.setAttribute('aria-live', 'polite');
    return add(wrap, grid, hint);
  }

  function updateSwap(swapping) {
    teamBtns.forEach(function (t) {
      var isSel = sel === t;
      t.btn.setAttribute('aria-pressed', isSel ? 'true' : 'false');
      t.btn.setAttribute('aria-label', sel && !isSel && sel.team !== t.team
        ? 'scambia ' + sel.name + ' con ' + t.name : t.name + ', squadra ' + COLOUR[t.team]);
    });
    ['black', 'white'].forEach(function (k2) {
      if (teamCols[k2]) teamCols[k2].classList.toggle('target', !!sel && sel.team !== k2);
    });
    var hint = document.getElementById('swap-hint');
    if (hint) {
      hint.textContent = swapping ? 'scambio in corso…'
        : sel ? 'scambia ' + sel.name + ' con… tocca un nome della squadra ' + COLOUR[sel.team === 'black' ? 'white' : 'black'] + '.'
          : 'tocca due nomi, uno per squadra, per scambiarli.';
    }
  }
  function clearSel() { if (sel) { sel = null; updateSwap(); } }

  function onTeamTap(t) {
    if (busy) return;
    if (!sel) { sel = t; updateSwap(); hf('selectionChanged'); return; }
    if (sel === t) { sel = null; updateSwap(); hf('selectionChanged'); return; }
    if (sel.team === t.team) { sel = t; updateSwap(); hf('selectionChanged'); return; }
    doSwap(sel, t);
  }

  function colourOf(name) {
    var tm = data.match.teams || {};
    if (indexOfName(tm.black || [], name) >= 0) return 'nera';
    if (indexOfName(tm.white || [], name) >= 0) return 'bianca';
    return null;
  }
  function focusTeam(name) {
    for (var i = 0; i < teamBtns.length; i++) {
      if (sameName(teamBtns[i].name, name)) { teamBtns[i].btn.focus({ preventScroll: true }); return; }
    }
  }

  function doSwap(a, b) {
    var an = a.name, bn = b.name;
    updateSwap(true);
    act({ action: 'swap', x: lower(an), y: lower(bn) }, {
      busy: [a.btn, b.btn],
      onFail: function () { hf('notificationOccurred', 'error'); },
      onOk: function (res) {
        if (res.outcome === 'swapped') {
          render(function () { focusTeam(an); });
          hf('notificationOccurred', 'success');
          var ca = colourOf(an), cb = colourOf(bn);
          showSnack('scambio fatto: ' + an + ' va in ' + (ca || '?') + ', ' + bn + ' in ' + (cb || '?') + '.', function (btn) {
            undoSwap(an, bn, btn);
          });
        } else {
          render(); hf('notificationOccurred', 'error'); toast('non è andata. riprova.');
        }
      }
    });
  }
  function undoSwap(an, bn, btn) {
    if (busy) return;
    if (btn) btn.setAttribute('aria-busy', 'true');
    act({ action: 'swap', x: lower(bn), y: lower(an) }, {
      onFail: function () { hf('notificationOccurred', 'error'); },
      onOk: function (res) {
        if (res.outcome === 'swapped') {
          render(function () { focusTeam(an); }); hf('notificationOccurred', 'success'); toast('scambio annullato.');
        } else { render(); hf('notificationOccurred', 'error'); toast('non è andata. riprova.'); }
      }
    });
  }

  function onDraw(btn) {
    if (busy) return;
    if (btn.getAttribute('aria-disabled') === 'true') { toast(drawState(data).why); return; }
    act({ action: 'teams' }, {
      busy: [btn],
      onOk: function (res) {
        var o = res.outcome;
        if (o === 'drawn') {
          render(function () { focusById('h-black'); });
          hf('notificationOccurred', 'success'); toast('squadre sorteggiate: le vede anche il gruppo.');
        } else if (o === 'show_existing') {
          render(); toast('le squadre erano già fatte.');
        } else if (o === 'odd_target' || o === 'not_full') {
          render(); toast(drawState(data).why);
        } else { render(); toast('non è andata. riprova.'); }
      }
    });
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
      b.addEventListener('click', function () { if (!busy) select(id, false, true); });
      b.addEventListener('keydown', function (ev) {
        if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
          ev.preventDefault();
          if (!busy) select(id === 'lista' ? 'squadre' : 'lista', true, true);
        }
      });
      btns[id] = b; seg.appendChild(b);
      var p = panels[id];
      p.id = 'panel-' + id; p.setAttribute('role', 'tabpanel'); p.setAttribute('aria-labelledby', 'tab-' + id);
    });
    function select(id, focus, user) {
      if (user && id !== tab) { clearSel(); hideSnack(); }
      tab = id;
      Object.keys(btns).forEach(function (k2) {
        var on = k2 === id;
        btns[k2].setAttribute('aria-selected', on ? 'true' : 'false');
        btns[k2].tabIndex = on ? 0 : -1;
        panels[k2].hidden = !on;
      });
      if (focus) btns[id].focus();
      if (id === 'lista') fitNote();
    }
    select(tab, false, false);
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
  function restoreBar() {
    if (!data || inputFocused) return;
    bar.hidden = false;
    root.style.setProperty('--bar-h', bar.offsetHeight + 'px');
  }

  // after: a bar action name (focus that button) or a function run once the page is drawn
  function render(after) {
    sel = null; teamBtns = []; teamCols = {}; listBtns = []; inputFocused = false;
    if (!hasTeams(data.match)) hideSnack();
    var k = counts(data);
    var col = h('div', 'col');
    add(col, renderHero(data.match, k), renderNote(data.match));
    renderTabs(data, k).forEach(function (e) { col.appendChild(e); });
    col.appendChild(privacyLink());
    app.textContent = '';
    app.appendChild(col);
    renderBar(data, k);
    fitNote();
    updateSwap();
    if (typeof after === 'function') after();
    else if (after) {
      var t = bar.querySelector('[data-action="' + after + '"]') || document.getElementById('status');
      if (t) t.focus({ preventScroll: true });
    }
  }
  window.addEventListener('resize', fitNote);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitNote);

  // ---- toasts for outcomes ----
  function ready(m) { return m.target % 2 === 0 && m.confirmed.length === m.target && !hasTeams(m); }
  function toastFor(res) { // the self flow
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
      case 'name_taken': msg = "c’è già qualcuno con il tuo nome in lista."; break;
      default: msg = null;
    }
    if (msg && res.teams_cancelled) msg += ' · ' + TAIL_CANCELLED;
    else if (msg && (o === 'added' || o === 'confirmed') && ready(m)) msg += ' · ' + TAIL_READY;
    return msg;
  }
  var TAIL_CANCELLED = 'squadre annullate: le potete sorteggiare di nuovo.';
  var TAIL_READY = 'ora potete sorteggiare le squadre.';
  function fullMsg(total, may) {
    return 'lista completa: siete già in ' + total + (may ? ' (' + may + ' in forse).' : '.');
  }

  // per-name segments, in a fixed order, joined by " · "
  var SEGMENTS = {
    add: [
      ['added', true, '{n} è in lista.', '{n} sono in lista.'],
      ['confirmed', true, '{n} ora c’è.', '{n} ora ci sono.'],
      ['already_in', false, '{n} c’era già.', '{n} c’erano già.']
    ],
    propose: [
      ['proposed', true, '{n} è in forse.', '{n} sono in forse.'],
      ['moved_to_maybe', true, '{n} ora è in forse.', '{n} ora sono in forse.'],
      ['already_maybe', false, '{n} era già in forse.', '{n} erano già in forse.']
    ]
  };
  function batchText(res, action) {
    var changes = res.changes || [], m = res.state.match;
    var segs = [], changed = false, countDone = false, addedOrConfirmed = false;
    var n = m.confirmed.length + '/' + m.target;
    SEGMENTS[action].forEach(function (def) {
      var names = changes.filter(function (c) { return c.outcome === def[0]; }).map(function (c) { return c.name; });
      if (!names.length) return;
      var txt = (names.length === 1 ? def[2] : def[3]).replace('{n}', joinNames(names));
      if (def[1]) {
        changed = true;
        if (def[0] === 'added' || def[0] === 'confirmed') addedOrConfirmed = true;
        if (!countDone) { txt += ' ' + n; countDone = true; }
      }
      segs.push(txt);
    });
    var full = changes.filter(function (c) { return c.outcome === 'full'; }).map(function (c) { return c.name; });
    if (full.length) {
      if (!segs.length) segs.push(fullMsg(m.confirmed.length + m.maybe.length, m.maybe.length));
      else segs.push('lista completa: ' + joinNames(full) + (full.length === 1 ? ' resta' : ' restano') + ' fuori.');
    }
    var tail = false;
    if (res.teams_cancelled) { segs.push(TAIL_CANCELLED); tail = true; }
    else if ((addedOrConfirmed || (action === 'propose' && changed)) && ready(m)) { segs.push(TAIL_READY); tail = true; }
    return { text: segs.join(' · '), ms: segs.length >= 2 || tail ? 5000 : 3000, changed: changed };
  }
  function outcomeToast(res, action) {
    var r = batchText(res, action);
    if (r.text) toast(r.text, r.ms);
    if (r.changed) hf('impactOccurred', 'light');
  }

  function removeText(res, name) {
    var m = res.state.match, o = res.outcome, segs = [], changed = true;
    if (o === 'removed') segs.push(name + ' non è più in lista. ' + m.confirmed.length + '/' + m.target);
    else if (o === 'removed_maybe') segs.push(name + ' non è più in forse.');
    else if (o === 'not_in') { segs.push(name + ' non è nella lista.'); changed = false; }
    else return null;
    var tail = false;
    if (res.teams_cancelled) { segs.push(TAIL_CANCELLED); tail = true; }
    else if (changed && ready(m)) { segs.push(TAIL_READY); tail = true; }
    return { text: segs.join(' · '), ms: tail ? 5000 : 3000, changed: changed };
  }

  // ---- actions ----
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

  // one request at a time. o: busy (elements shown as working), onOk(body), onFail(), onInvalid(), after (focus on error)
  function act(body, o) {
    if (busy) return;
    busy = true;
    Array.prototype.forEach.call(document.querySelectorAll('.btn, .rb, .seg button'), function (b) {
      b.setAttribute('aria-disabled', 'true');
    });
    (o.busy || []).forEach(function (b) { b.setAttribute('aria-busy', 'true'); });
    function fail(msg) {
      if (o.onFail) o.onFail();
      render(o.after);
      toast(msg);
    }
    post('/app/api/action', body).then(function (r) {
      busy = false;
      var b = r.body || {};
      if (r.status === 200 && b.state) { data = b.state; o.onOk(b); }
      else if (r.status === 401) showState('expired');
      else if (r.status === 403) showState('notmember');
      else if (r.status === 404) showState('closed');
      else if (o.onInvalid && (r.status === 422 || (r.status === 400 && b.error === 'invalid_name'))) o.onInvalid();
      else {
        fail(r.status === 429 ? 'troppe richieste, aspetta un attimo.' : 'non è andata. riprova.');
        if (r.status === 409) refresh(); // lost a race: show what the list really says
      }
    }, function () { busy = false; fail('non è andata. riprova.'); });
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
    act({ action: action }, {
      busy: [btn],
      after: action,
      onOk: function (b) {
        render(action);
        var text = toastFor(b);
        if (text) toast(text, b.teams_cancelled || text.indexOf(' · ') > 0 ? 5000 : 3000);
        if (b.outcome !== 'full' && b.outcome !== 'name_taken') hf('impactOccurred', 'light');
      }
    });
  }

  // haptics: guarded by client version (HapticFeedback needs 6.1)
  function hf(kind, arg) {
    try {
      if (!tg || !tg.HapticFeedback) return;
      if (typeof tg.isVersionAtLeast === 'function' && !tg.isVersionAtLeast('6.1')) return;
      var f = tg.HapticFeedback[kind];
      if (typeof f === 'function') f.call(tg.HapticFeedback, arg);
    } catch (e) { /* ignore */ }
  }

  // ---- acting on someone else ----
  function focusPerson(name, kind) {
    for (var i = 0; i < listBtns.length; i++) {
      if (sameName(listBtns[i].name, name)) { listBtns[i].btn.focus({ preventScroll: true }); return; }
    }
    focusById(kind === 'maybe' && document.getElementById('h-maybe') ? 'h-maybe' : 'h-in');
  }

  function runOther(kind, id, name, btn) {
    var body, action;
    if (id === 'remove') body = { action: 'remove', name: lower(name) };
    else { action = id === 'maybe' ? 'propose' : 'add'; body = { action: action, text: lower(name) }; }
    var back = function () { focusPerson(name, kind); };
    act(body, {
      busy: [btn],
      after: back,
      onOk: function (res) {
        render(back);
        var r = id === 'remove' ? removeText(res, name) : batchText(res, action);
        if (!r || !r.text) return;
        toast(r.text, r.ms);
        if (r.changed) hf('impactOccurred', 'light');
        if (res.outcome === 'not_in') refresh(function () { focusById('h-in'); });
      }
    });
  }

  function pickAction(kind, id, name, btn) {
    if (!id || id === 'cancel' || busy) return;
    if (hasTeams(data.match) && id !== 'confirm') {
      var q = id === 'remove' ? 'se togli ' + name + ' si annullano' : 'se sposti ' + name + ' in forse si annullano';
      confirmAsk('ci sono già le squadre: ' + q + ' per tutti. vai avanti?', function () { runOther(kind, id, name, btn); });
      return;
    }
    runOther(kind, id, name, btn);
  }

  function openMenu(name, kind, pos, btn) {
    if (busy) return;
    var title = name.length > 63 ? name.slice(0, 63) + '…' : name;
    var msg = kind === 'in' ? 'c’è · n. ' + pos : 'è in forse';
    var first = kind === 'in' ? { id: 'maybe', text: 'sposta in forse' } : { id: 'confirm', text: 'conferma' };
    var popupOk = tg && typeof tg.showPopup === 'function' &&
      (typeof tg.isVersionAtLeast !== 'function' || tg.isVersionAtLeast('6.2'));
    if (popupOk) {
      try {
        tg.showPopup({ title: title, message: msg, buttons: [
          { id: first.id, type: 'default', text: first.text },
          { id: 'remove', type: 'destructive', text: 'togli dalla lista' },
          { id: 'cancel', type: 'default', text: 'annulla' }
        ] }, function (id) {
          // the popup is closing: give it a moment before a possible showConfirm
          setTimeout(function () { pickAction(kind, id, name, btn); }, 50);
        });
        return;
      } catch (e) { /* fall through to the dialog */ }
    }
    var d = h('dialog', 'menu');
    d.setAttribute('aria-labelledby', 'menu-title');
    var t = h('h2', null, name); t.id = 'menu-title';
    var picked = null;
    function pill(text, cls, id) {
      var b = h('button', 'btn block ' + cls, text);
      b.type = 'button';
      b.addEventListener('click', function () { picked = id; d.close(); });
      return b;
    }
    var cancel = pill('annulla', 'primary', 'cancel');
    add(d, t, h('p', null, msg), pill(first.text, 'outline', first.id), pill('togli dalla lista', 'outline', 'remove'), cancel);
    d.addEventListener('close', function () {
      if (d.parentNode) d.parentNode.removeChild(d);
      try { btn.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
      if (picked) pickAction(kind, picked, name, btn);
    });
    document.body.appendChild(d);
    if (typeof d.showModal !== 'function') { document.body.removeChild(d); return; }
    d.showModal();
    cancel.focus();
  }

  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') clearSel();
  });

  // ---- load ----
  function refresh(after) { // quiet re-fetch: keeps the page and the toast
    post('/app/api/match', {}).then(function (r) {
      if (busy) return;
      if (r.status === 200 && r.body && r.body.match) { data = r.body; render(after); }
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
