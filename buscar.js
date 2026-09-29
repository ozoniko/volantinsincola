(function () {
  var q = document.getElementById('q'), out = document.getElementById('resultados'), estado = document.getElementById('estado');
  var datos = null;
  var norm = function (s) { return (s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); };
  var esc = function (s) { return s.replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  fetch('/buscar.json').then(function (r) { return r.json(); }).then(function (d) {
    datos = d.map(function (p) { p.nt = norm(p.t); p.nx = norm(p.e + ' ' + p.x); return p; });
    var inicial = new URLSearchParams(location.search).get('q');
    if (inicial) { q.value = inicial; }
    buscar();
  }).catch(function () { estado.textContent = 'No se pudo cargar el buscador. Recarga la página.'; });

  function buscar() {
    if (!datos) return;
    var term = norm(q.value.trim());
    if (term.length < 2) { out.innerHTML = ''; estado.textContent = 'Escribe al menos dos letras.'; return; }
    var palabras = term.split(/\s+/);
    var res = datos.map(function (p) {
      var s = 0;
      for (var i = 0; i < palabras.length; i++) {
        var w = palabras[i], t = p.nt.indexOf(w) > -1, x = p.nx.indexOf(w) > -1;
        if (!t && !x) return null;
        s += (t ? 10 : 0) + (x ? 1 : 0);
      }
      return { p: p, s: s };
    }).filter(Boolean).sort(function (a, b) { return b.s - a.s; });
    estado.textContent = res.length ? res.length + (res.length === 1 ? ' artículo encontrado' : ' artículos encontrados') : 'Nada por aquí. Prueba con otra palabra.';
    out.innerHTML = res.slice(0, 40).map(function (r) {
      var p = r.p;
      return '<li class="fila"><time class="fila__fecha">' + p.d + '<br><b>' + p.y + '</b></time><div class="fila__txt"><div class="chips">' +
        p.c.map(function (c) { return '<a class="chip chip--' + c[0] + '" href="/category/' + c[0] + '/">' + c[1] + '</a>'; }).join('') +
        '</div><h3><a href="' + p.u + '">' + esc(p.t) + '</a></h3><p>' + esc(p.e) + '</p></div></li>';
    }).join('');
  }
  var timer;
  q.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(buscar, 120); });
})();
