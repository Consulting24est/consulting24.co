/* Consulting24 chat widget: Mardo's photo in the bottom-right corner, a first welcome message and guided
   answers (prices mirror pricing.md, keep them in sync). Questions are handed to Mardo's WhatsApp with the
   question prefilled, so he answers from his phone; visitors without WhatsApp leave an email or number,
   which reaches his inbox through FormSubmit (the same endpoint as the /contact/ form). Loaded by nav.js;
   styles in chat.css. */
(function () {
  if (document.getElementById('c24c')) return;

  var WA = '37258155779';
  var EMAIL = 'mardo@consulting24.co';
  var ENDPOINT = 'https://formsubmit.co/ajax/' + EMAIL;
  var AVATAR = '/img/mardo-soo-chat.jpg';
  var TEASE_DELAY = 3500;
  var TEASE_EVERY = 24 * 3600e3;   /* auto-show the welcome bubble at most once a day */
  var chauffeur = /^\/luxury-chauffeur-service-dubai(\/|$)/.test(location.pathname);
  var phone = window.matchMedia('(max-width:520px)');

  /* ---------- conversation content ---------- */
  var FOLLOW = ['wa_talk', 'quote', 'menu'];
  var TOPICS = chauffeur ? {
    welcome: ["Hi, I'm Mardo 👋", 'Want to ride in the Maybach S-Class in Dubai? Tell me the date, pickup and drop-off, and I\'ll confirm availability.'],
    teaser: 'Want to ride in the Maybach S-Class in Dubai? Tell me your date and route.',
    menu: ['c_airport', 'c_hourly', 'c_ceo', 'wa'],
    labels: { c_airport: 'Airport transfer', c_hourly: 'Book by the hour', c_ceo: 'Ride with Mardo (CEO)', wa: 'WhatsApp me', wa_send: 'Send it to me on WhatsApp', wa_talk: 'Chat on WhatsApp', nowa: 'I don\'t use WhatsApp', menu: 'Something else', quote: 'Leave my contact' },
    answers: {
      c_airport: { h: 'Great. Send me the flight date and time, and the pickup and drop-off addresses. I\'ll confirm the car on WhatsApp.', wa: 'Hi Mardo, I\'d like to book the Maybach for an airport transfer. Date/time: … Pickup: … Drop-off: …' },
      c_hourly: { h: 'Sure. Tell me the date, the start time and roughly how many hours you need. I\'ll confirm availability on WhatsApp.', wa: 'Hi Mardo, I\'d like to book the Maybach by the hour. Date: … Start time: … Hours: …' },
      c_ceo: { h: 'You can ride with me at the wheel and use the time to talk through UAE, Panama or Estonia structuring. It depends on my calendar, so send me your date first.', wa: 'Hi Mardo, I\'d like to book a ride with you driving. Date: … Route: …' }
    },
    waDefault: 'Hi Mardo, I\'d like to book the Maybach in Dubai.'
  } : {
    welcome: ["Hi, I'm Mardo 👋 Founder & CEO of Consulting24.", 'I help founders set up crypto companies and licences in Panama, Estonia, the BVI, Dubai and beyond. What are you working on?'],
    teaser: 'Setting up a crypto company or licence? Ask me anything and I\'ll answer personally.',
    menu: ['panama', 'ready', 'estonia', 'bvi', 'other', 'wa'],
    labels: { panama: 'Panama crypto company', ready: 'Ready-made company', estonia: 'Estonia company (OÜ)', bvi: 'BVI company', other: 'Another licence or country', prices: 'Prices', wa: 'WhatsApp me', wa_send: 'Send it to me on WhatsApp', wa_talk: 'Chat with me on WhatsApp', nowa: 'I don\'t use WhatsApp', menu: 'Something else', quote: 'Get a quote by email' },
    answers: {
      panama: { h: 'Our flagship: a Panama S.A. set up for crypto activities, <b>EUR 6,000 fixed, all-in</b>.\nIncluded: 2 of the 3 required directors, notarisation for 1 person, 7 crypto-friendly payment-provider introductions and banking introductions.\nIt takes 2–3 weeks, fully online, with no minimum capital. <a href="/cost/">See what\'s included</a>', wa: 'Hi Mardo, I\'m interested in the Panama crypto company setup (EUR 6,000).' },
      ready: { h: 'Ready-made Panama crypto companies with history: <b>EUR 8,000 fixed</b>.\nIncluded: transfer of the existing S.A., 2 directors and introductions to 10 crypto-friendly EMI providers. The transfer takes 2–3 weeks. <a href="/ready-made-crypto-license-panama/">See available companies</a>', wa: 'Hi Mardo, I\'m interested in a ready-made Panama crypto company (EUR 8,000).' },
      estonia: { h: 'Estonian OÜ package: <b>EUR 2,500</b>.\nIncluded: registration, contact person and virtual office for 1 year, 1 director/shareholder and 1 power of attorney. No visit to Estonia needed.\n0% corporate tax on retained profit. I can also act as your local director for EUR 4,000 a year. <a href="/estonia-company-registration/">Estonia details</a>', wa: 'Hi Mardo, I\'m interested in registering an Estonian company (EUR 2,500 package).' },
      bvi: { h: 'BVI Business Company, standard package: <b>EUR 5,000</b>.\nIncluded: incorporation and the first-year government fee, plus registered agent, address and corporate secretary for 1 year.\n0% corporate tax, incorporated in about 4–8 working days. <a href="/bvi-company-registration/">BVI details</a>', wa: 'Hi Mardo, I\'m interested in a BVI company (EUR 5,000 package).' },
      other: { h: 'We also work on crypto licences in the EU (MiCA / CASP), Dubai (VARA), Lithuania, Poland, the Czech Republic, the Cayman Islands, El Salvador and more. <a href="/jurisdictions/">Compare jurisdictions</a>\nTell me the country and the activity (exchange, broker, custody, payments…) and I\'ll come back with an honest estimate.', ask: true, wa: 'Hi Mardo, I\'m looking for a crypto licence. Country: … Activity: …' },
      prices: { h: 'Our fixed fees:\n• Panama crypto company: EUR 6,000\n• Ready-made Panama company: EUR 8,000\n• Estonia OÜ: EUR 2,500\n• BVI company: EUR 5,000\nLicences in other countries are quoted case by case.', wa: 'Hi Mardo, I\'d like a quote.' }
    },
    keywords: [
      [/\bready|shelf|aged compan|existing compan/i, 'ready'],
      [/panam/i, 'panama'],
      [/eston|\bo[üu]\b|e-?resid/i, 'estonia'],
      [/\bbvi\b|virgin island/i, 'bvi'],
      [/price|pricing|cost|fee|how much|budget|cheap/i, 'prices']
    ],
    waDefault: 'Hi Mardo, I have a question about Consulting24\'s services.'
  };

  /* ---------- persistence (all optional: private mode just loses it) ---------- */
  function get(store, k) { try { return JSON.parse(window[store].getItem('c24chat.' + k)); } catch (e) { return null; } }
  function set(store, k, v) { try { window[store].setItem('c24chat.' + k, JSON.stringify(v)); } catch (e) {} }
  var state = get('sessionStorage', 'state') || { log: [], mode: 'menu', topic: '', question: '', sent: false };
  if (state.variant !== (chauffeur ? 'c' : 'x')) state = { log: [], mode: 'menu', topic: '', question: '', sent: false, variant: chauffeur ? 'c' : 'x' };
  function save() { set('sessionStorage', 'state', state); }

  /* ---------- DOM ---------- */
  function el(tag, cls, html) { var n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; }
  var root = el('div', 'c24c');
  root.id = 'c24c';
  root.dir = 'ltr';
  if (document.querySelector('.sticky-bar')) root.classList.add('c24c--above-bar');
  root.innerHTML =
    '<div class="c24c-panel" role="dialog" aria-label="Chat with Mardo Soo" hidden>' +
      '<div class="c24c-head"><span class="c24c-head__ava"><img src="' + AVATAR + '" alt="" width="44" height="44"></span>' +
        '<span class="c24c-head__who"><b>Mardo Soo</b><span>Founder &amp; CEO, Consulting24</span></span>' +
        '<button type="button" class="c24c-head__x" aria-label="Close chat">×</button></div>' +
      '<div class="c24c-log" aria-live="polite"></div>' +
      '<form class="c24c-form" novalidate><label class="c24c-sr" for="c24c-in">Your message</label>' +
        '<input id="c24c-in" class="c24c-input" type="text" autocomplete="off" maxlength="1000" placeholder="Type your question…">' +
        '<button type="submit" class="c24c-send" aria-label="Send"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3.4 20.4 21 12 3.4 3.6 3.4 10l12.6 2-12.6 2z"/></svg></button></form>' +
      '<div class="c24c-foot">Mardo answers personally on WhatsApp or by email.</div>' +
    '</div>' +
    '<button type="button" class="c24c-launch" aria-label="Chat with Mardo Soo" aria-expanded="false"><img src="' + AVATAR + '" alt="" width="64" height="64"></button>';
  var panel = root.querySelector('.c24c-panel');
  var log = root.querySelector('.c24c-log');
  var form = root.querySelector('.c24c-form');
  var input = root.querySelector('.c24c-input');
  var launch = root.querySelector('.c24c-launch');
  var closeBtn = root.querySelector('.c24c-head__x');
  var teaser = null, badge = null, busy = 0, queue = [], drawn = false;

  /* ---------- rendering ---------- */
  function scroll() { log.scrollTop = log.scrollHeight; }
  function waUrl(text) { return 'https://wa.me/' + WA + '?text=' + encodeURIComponent(text || TOPICS.waDefault); }
  function waText() {
    var a = TOPICS.answers[state.topic];
    var t = state.question ? 'Hi Mardo, ' + state.question : (a && a.wa) || TOPICS.waDefault;
    return t + '\n\n(via the chat on consulting24.co' + location.pathname + ')';
  }
  function drawBot(html) {
    var row = el('div', 'c24c-row');
    var img = el('img'); img.src = AVATAR; img.alt = ''; img.width = 28; img.height = 28;
    row.appendChild(img);
    row.appendChild(el('div', 'c24c-msg', html));
    log.appendChild(row);
  }
  function drawMe(text) {
    var row = el('div', 'c24c-row c24c-row--me');
    var m = el('div', 'c24c-msg'); m.textContent = text;
    row.appendChild(m);
    log.appendChild(row);
  }
  function drawChips(keys) {
    var box = el('div', 'c24c-chips');
    keys.forEach(function (k) {
      var c;
      if (k.indexOf('wa') === 0) {
        c = el('a', 'c24c-chip c24c-chip--wa' + (k === 'wa' ? '' : ' c24c-chip--wa-main'));
        c.href = waUrl(waText()); c.target = '_blank'; c.rel = 'noopener';
        c.textContent = '💬 ' + TOPICS.labels[k];
      } else {
        c = el('button', 'c24c-chip'); c.type = 'button'; c.textContent = TOPICS.labels[k];
        c.addEventListener('click', function () { pick(k); });
      }
      box.appendChild(c);
    });
    log.appendChild(box);
  }
  function clearChips() { root.querySelectorAll('.c24c-chips').forEach(function (b) { b.remove(); }); }
  function render() {
    log.innerHTML = '';
    state.log.forEach(function (m, i) {
      if (m.b) drawBot(m.b);
      else if (m.m) drawMe(m.m);
      else if (m.c && i === state.log.length - 1) drawChips(m.c);
    });
    scroll();
  }

  /* Bot messages are queued with a short typing indicator so they read like a person typing. */
  function say(items) { queue = queue.concat(items); if (!busy) next(); }
  function next() {
    var it = queue.shift();
    if (!it) { busy = 0; return; }
    busy = 1;
    if (it.c) { clearChips(); state.log.push({ c: it.c }); save(); drawChips(it.c); scroll(); return next(); }
    var dots = el('div', 'c24c-row', '<img src="' + AVATAR + '" alt="" width="28" height="28"><div class="c24c-msg c24c-typing" aria-label="Mardo is typing"><i></i><i></i><i></i></div>');
    log.appendChild(dots); scroll();
    var plain = it.b.replace(/<[^>]+>/g, '');
    setTimeout(function () {
      dots.remove();
      state.log.push({ b: it.b }); save();
      drawBot(it.b); scroll();
      next();
    }, Math.min(1300, 450 + plain.length * 6));
  }
  function me(text) { clearChips(); state.log.push({ m: text }); save(); drawMe(text); scroll(); }

  /* ---------- conversation logic ---------- */
  function welcome() {
    say(TOPICS.welcome.map(function (t) { return { b: t }; }).concat([{ c: TOPICS.menu }]));
  }
  function askContact(lead) {
    if (state.contact) { sendLead(state.contact); return; }
    state.mode = 'contact'; save();
    input.placeholder = 'Email, or phone with country code';
    say([{ b: lead + ' What\'s the best email, or phone number with country code, to reach you?' }]);
  }
  function handoff(lead) {
    state.mode = 'menu'; save();
    input.placeholder = 'Type your question…';
    say([{ b: lead + ' Tap below and it goes straight to my WhatsApp. I\'ll answer you there myself.' }, { c: ['wa_send', 'nowa'] }]);
  }
  function answer(k) {
    var a = TOPICS.answers[k];
    state.topic = k; save();
    if (a.ask) { state.mode = 'ask'; save(); input.placeholder = 'Country and activity…'; say([{ b: a.h }, { c: ['wa', 'menu'] }]); return; }
    state.mode = 'menu'; save();
    say([{ b: a.h }, { b: chauffeur ? 'Shall we go ahead?' : 'Questions about your case? Ask me on WhatsApp, or get a written quote by email.' }, { c: chauffeur ? ['wa_talk', 'menu'] : FOLLOW }]);
  }
  function pick(k) {
    me(TOPICS.labels[k]);
    if (k === 'menu') { state.mode = 'menu'; state.topic = ''; save(); input.placeholder = 'Type your question…'; say([{ b: 'Sure, what else can I help with?' }, { c: TOPICS.menu }]); return; }
    if (k === 'quote') { askContact('Happy to.'); return; }
    if (k === 'nowa') { askContact('No problem.'); return; }
    answer(k);
  }
  var EMAIL_RE = /[^\s@<>]+@[^\s@<>]+\.[a-z]{2,}/i;
  function contactIn(text) {
    var e = text.match(EMAIL_RE);
    if (e) return { email: e[0] };
    var digits = text.replace(/\D/g, '');
    if (/^[+\d\s().\-\/]{7,}$/.test(text.trim()) && digits.length >= 7 && digits.length <= 15) return { phone: text.trim() };
    return null;
  }
  function transcript() {
    return state.log.filter(function (m) { return m.b || m.m; }).map(function (m) {
      return (m.m ? 'Visitor: ' + m.m : 'Mardo (bot): ' + m.b.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&'));
    }).join('\n');
  }
  function sendLead(contact) {
    var again = !!state.contact;
    var topic = TOPICS.labels[state.topic] || (chauffeur ? 'Maybach booking' : 'General question');
    var data = {
      _subject: 'Website chat' + (again ? ' follow-up: ' : ': ') + topic + ' (' + (contact.email || contact.phone) + ')',
      _template: 'table',
      _captcha: 'false',
      contact: contact.email || contact.phone,
      topic: topic,
      question: state.question || '(none typed)',
      page: location.href,
      language: document.documentElement.lang || 'en',
      conversation: transcript()
    };
    if (contact.email) data.email = contact.email;
    else data.reply_on_whatsapp = 'https://wa.me/' + contact.phone.replace(/\D/g, '').replace(/^00/, '');
    var ok = function () {
      state.sent = true; state.contact = contact; state.mode = 'menu'; state.question = ''; save();
      input.placeholder = 'Type your question…';
      if (again) say([{ b: 'Thanks, I\'ve passed that on too. I\'ll reply to ' + (contact.email || contact.phone) + '.' }, { c: ['wa', 'menu'] }]);
      else if (contact.phone) say([{ b: 'Thanks, got it! I\'ll get in touch at ' + contact.phone + ' as soon as I can.' }, { c: ['menu'] }]);
      else say([{ b: 'Thanks, got it! I\'ll get back to you personally as soon as I can.' }, { b: 'If it\'s urgent, WhatsApp is the fastest way to reach me.' }, { c: ['wa', 'menu'] }]);
    };
    var fail = function () {
      state.mode = 'menu'; save();
      input.placeholder = 'Type your question…';
      say([{ b: 'Sorry, my inbox didn\'t take that message. Please WhatsApp me or email <a href="mailto:' + EMAIL + '">' + EMAIL + '</a>.' }, { c: ['wa', 'menu'] }]);
    };
    fetch(ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(data) })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (String(d.success) === 'true') ok(); else fail(); })
      .catch(fail);
  }
  function note(text) { state.question = state.question ? state.question + '\n' + text : text; save(); }
  function onText(text) {
    me(text);
    var contact = contactIn(text);
    if (contact) {
      if (text.length > 40) note(text);   /* a question with the email inside it */
      sendLead(contact);
      return;
    }
    if (state.mode === 'contact') {
      if (text.length > 25) { note(text); say([{ b: 'Noted. And what\'s the best email, or phone number with country code, to reach you?' }, { c: ['wa_send'] }]); }
      else say([{ b: 'That doesn\'t look like an email or phone number. Could you check it? You can also message me on WhatsApp.' }, { c: ['wa'] }]);
      return;
    }
    if (/^(hi|hello|hey|hola|good (morning|afternoon|evening))\b[\s!.,]*$/i.test(text)) { say([{ b: 'Hi! How can I help?' }, { c: TOPICS.menu }]); return; }
    if (state.mode !== 'ask' && TOPICS.keywords) {
      for (var i = 0; i < TOPICS.keywords.length; i++) {
        if (TOPICS.keywords[i][0].test(text)) { note(text); answer(TOPICS.keywords[i][1]); return; }
      }
    }
    var asked = state.mode === 'ask';
    note(text);
    handoff(asked ? 'Got it, thanks.' : 'Good question.');
  }

  /* ---------- open / close ---------- */
  function hideTeaser() { if (teaser) { teaser.remove(); teaser = null; } }
  function open(focusInput) {
    hideTeaser();
    if (badge) { badge.remove(); badge = null; }
    set('localStorage', 'opened', Date.now());
    root.classList.add('is-open');
    panel.hidden = false;
    launch.setAttribute('aria-expanded', 'true');
    if (phone.matches) document.documentElement.classList.add('c24c-lock');
    set('sessionStorage', 'open', true);
    if (!drawn) {
      drawn = true;
      if (!state.log.length) welcome(); else { render(); if (state.mode === 'contact') input.placeholder = 'Email, or phone with country code'; }
    }
    if (focusInput !== false) (phone.matches ? closeBtn : input).focus();
  }
  function close() {
    root.classList.remove('is-open');
    panel.hidden = true;
    launch.setAttribute('aria-expanded', 'false');
    document.documentElement.classList.remove('c24c-lock');
    set('sessionStorage', 'open', false);
    launch.focus();
  }
  launch.addEventListener('click', function () { if (root.classList.contains('is-open')) close(); else open(); });
  closeBtn.addEventListener('click', close);
  root.addEventListener('keydown', function (e) { if (e.key === 'Escape' && root.classList.contains('is-open')) close(); });
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.value = '';
    onText(text.slice(0, 1000));
  });

  /* The first welcome message pops up beside the photo shortly after the page loads. */
  function showTeaser() {
    if (root.classList.contains('is-open') || teaser) return;
    set('localStorage', 'teased', Date.now());
    teaser = el('div', 'c24c-teaser');
    teaser.setAttribute('role', 'status');
    teaser.innerHTML = '<b>Mardo Soo · Consulting24</b><p></p><button type="button" class="c24c-teaser__x" aria-label="Dismiss">×</button>';
    teaser.querySelector('p').textContent = TOPICS.welcome[0].replace(/ Founder.*$/, '') + ' ' + TOPICS.teaser;
    teaser.addEventListener('click', function (e) {
      if (e.target.closest('.c24c-teaser__x')) { hideTeaser(); return; }
      open();
    });
    root.insertBefore(teaser, launch);
  }

  function mount() {
    document.body.appendChild(root);
    var opened = get('localStorage', 'opened');
    if (!opened || Date.now() - opened > 7 * 24 * 3600e3) {
      badge = el('span', 'c24c-badge', '1');
      badge.setAttribute('aria-hidden', 'true');
      launch.appendChild(badge);
    }
    if (get('sessionStorage', 'open') && !phone.matches) { open(false); return; }
    var teased = get('localStorage', 'teased');
    if (!opened && (!teased || Date.now() - teased > TEASE_EVERY)) setTimeout(showTeaser, TEASE_DELAY);
  }
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);
})();
