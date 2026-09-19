/* Consulting24 site header behaviour. Source of truth: scripts/site_header.py */
(function () {
  var header = document.getElementById('site-header');
  if (!header) return;
  var burger = header.querySelector('.c24-burger');
  var desktop = window.matchMedia('(min-width:1024px)');
  var noHover = window.matchMedia('(hover:none)');

  function setOpen(li, open) {
    li.classList.toggle('is-open', open);
    var b = li.querySelector('.c24-sub-toggle');
    if (b) b.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  function closeAll(except) {
    header.querySelectorAll('.c24-item.is-open').forEach(function (li) { if (li !== except) setOpen(li, false); });
  }
  function setMenu(open) {
    header.classList.toggle('is-menu-open', open);
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    burger.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    document.documentElement.classList.toggle('c24-lock', open && !desktop.matches);
    if (!open) closeAll();
  }

  burger.addEventListener('click', function () { setMenu(!header.classList.contains('is-menu-open')); });

  header.querySelectorAll('.c24-sub-toggle').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var li = btn.closest('.c24-item');
      var open = !li.classList.contains('is-open');
      closeAll(li);
      setOpen(li, open);
    });
  });

  /* Touch devices at desktop width: first tap on a parent link opens its panel, second tap follows the link. */
  header.querySelectorAll('.c24-item.has-sub > .c24-item__top > .c24-link').forEach(function (a) {
    a.addEventListener('click', function (e) {
      if (desktop.matches && noHover.matches) {
        var li = a.closest('.c24-item');
        if (!li.classList.contains('is-open')) { e.preventDefault(); closeAll(li); setOpen(li, true); }
      }
    });
  });

  document.addEventListener('click', function (e) { if (!header.contains(e.target)) closeAll(); });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var wasOpen = header.querySelector('.c24-item.is-open');
    closeAll();
    if (wasOpen && desktop.matches) { var b = wasOpen.querySelector('.c24-sub-toggle'); if (b) b.focus(); }
    if (header.classList.contains('is-menu-open')) { setMenu(false); burger.focus(); }
  });
  /* Leaving the header with keyboard focus closes any hover/focus-opened panel state. */
  header.addEventListener('focusout', function (e) {
    if (desktop.matches && !header.contains(e.relatedTarget)) closeAll();
  });
  var onChange = function () { if (desktop.matches && header.classList.contains('is-menu-open')) setMenu(false); };
  if (desktop.addEventListener) desktop.addEventListener('change', onChange); else desktop.addListener(onChange);
})();
