# -*- coding: utf-8 -*-
"""Convierte el export de WordPress de Ideas que Vuelan en un sitio estático."""
import xml.etree.ElementTree as ET, re, html, json, os, shutil, math, sys
from datetime import datetime
from email.utils import format_datetime
from urllib.parse import urlparse, parse_qs, quote

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'site')
DOMAIN = 'https://volantinsincola.cl'
OLD = 'volantinsincola166136375.wordpress.com'
SITE = 'Ideas que Vuelan'
TAGLINE = 'actualidad / cultura / tendencias'
LOGO = f'https://{OLD}/wp-content/uploads/2026/04/cropped-logo.png'
FACEBOOK = 'https://www.facebook.com/elvolantinsincola/'
TWITTER = 'https://twitter.com/VSinCola'

ns = {'wp': 'http://wordpress.org/export/1.2/', 'content': 'http://purl.org/rss/1.0/modules/content/',
      'excerpt': 'http://wordpress.org/export/1.2/excerpt/', 'dc': 'http://purl.org/dc/elements/1.1/'}
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
CATS = [('opinion', 'Opinión'), ('actualidad', 'Actualidad'), ('cultura', 'Cultura'), ('tendencias', 'Tendencias')]
CATNAME = dict(CATS)
CATDESC = {
    'opinion': 'Ideas con postura. Pensar en voz alta sobre lo que nos toca y lo que se debate.',
    'actualidad': 'Lo que pasa hoy, leído con perspectiva. Porque informarse no es lo mismo que entender.',
    'cultura': 'Arte, cine, música, literatura y todo lo que define cómo vivimos y lo que somos.',
    'tendencias': 'Las corrientes que moldean el mundo antes de que el mundo se dé cuenta.',
}
KICKERS = {'opinión', 'cultura', 'tendencias', 'actualidad', 'podcast'}

esc = lambda s: html.escape(s or '', quote=True)


def fecha(d):
    return f'{d.day} de {MESES[d.month-1]} de {d.year}'


# ---------------------------------------------------------------- lectura
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'datos', 'wordpress.json')
with open(DATA, encoding='utf-8') as f:
    data = json.load(f)
att = {}


def img_url(u, w=1200):
    """Normaliza imágenes alojadas en WordPress: tamaño controlado por ?w=."""
    u = html.unescape(u)
    u = re.sub(r'^https?://i\d\.wp\.com/', 'https://', u)
    if OLD in u and '/wp-content/uploads/' in u:
        base = u.split('?')[0]
        return f'{base}?w={w}'
    return u


# ---------------------------------------------------------------- embeds
def yt_id(u):
    p = urlparse(html.unescape(u))
    q = parse_qs(p.query)
    if 'youtu.be' in p.netloc:
        return p.path.strip('/'), None
    if p.path.startswith('/embed/'):
        rest = p.path[len('/embed/'):]
        if rest.startswith('videoseries'):
            return None, q.get('list', [None])[0]
        return rest.split('/')[0], None
    if p.path.startswith('/playlist'):
        return None, q.get('list', [None])[0]
    return q.get('v', [None])[0], None


def embed(u):
    u = html.unescape(u.strip())
    host = urlparse(u).netloc
    if 'youtube.com' in host or 'youtube-nocookie.com' in host or 'youtu.be' in host:
        vid, lst = yt_id(u)
        src = f'https://www.youtube-nocookie.com/embed/{vid}' if vid else f'https://www.youtube-nocookie.com/embed/videoseries?list={lst}'
        return (f'<figure cls="media media--video"><iframe src="{esc(src)}" title="Video de YouTube" loading="lazy" '
                f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></figure>')
    if 'open.spotify.com' in host:
        m = re.search(r'/(album|track|playlist|episode|show|artist)/([A-Za-z0-9]+)', u)
        if m:
            kind, sid = m.groups()
            h = 152 if kind in ('track', 'episode') else 352
            return (f'<figure cls="media media--audio"><iframe src="https://open.spotify.com/embed/{kind}/{sid}" '
                    f'title="Spotify" height="{h}" loading="lazy" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"></iframe></figure>')
    if u.lower().endswith('.gif'):
        return f'<figure cls="figura"><img src="{esc(u)}" alt="" loading="lazy"></figure>'
    label = {'www.facebook.com': 'Ver en Facebook', 'gph.is': 'Ver GIF en Giphy', 'twitter.com': 'Ver en X / Twitter',
             'www.instagram.com': 'Ver en Instagram'}.get(host, 'Abrir enlace')
    return f'<p cls="enlace-externo"><a href="{esc(u)}" target="_blank" rel="noopener">{label} <span aria-hidden="true">↗</span></a></p>'


def gallery(urls):
    figs = ''.join(f'<li><img src="{esc(img_url(u, 800))}" alt="" loading="lazy"></li>' for u in urls)
    return f'<figure cls="galeria"><ul>{figs}</ul></figure>'


# ---------------------------------------------------------------- limpieza
BLOCK_TAGS = r'(?:p|h[1-6]|ul|ol|li|figure|blockquote|div|hr|table|iframe|pre|section)'


def autop(txt):
    """Versión mínima de wpautop para las entradas escritas en el editor clásico."""
    out = []
    for chunk in re.split(r'\n\s*\n', txt.strip()):
        c = chunk.strip()
        if not c:
            continue
        if re.match(rf'<{BLOCK_TAGS}[\s>/]', c) or re.match(r'<!--EMBED', c):
            out.append(c)
        else:
            out.append('<p>' + re.sub(r'\n', '<br>\n', c) + '</p>')
    return '\n'.join(out)


def blocks(c, tag, class_pat, fn):
    """Reemplaza elementos <tag class="…class_pat…">…</tag> respetando anidación."""
    opener = re.compile(rf'<{tag}\b[^>]*class="[^"]*(?:{class_pat})[^"]*"[^>]*>', re.I)
    tok = re.compile(rf'<(/?){tag}\b[^>]*>', re.I)
    pos = 0
    while True:
        m = opener.search(c, pos)
        if not m:
            return c
        depth, end = 0, len(c)
        for t in tok.finditer(c, m.start()):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                end = t.end()
                break
        rep = fn(c[m.start():end])
        c = c[:m.start()] + rep + c[end:]
        pos = m.start() + len(rep)


def emb_rendered(frag):
    src = re.search(r'<iframe[^>]*src="([^"]+)"', frag)
    if src:
        return '\n\n' + embed(src.group(1)) + '\n\n'
    um = re.search(r'wp-block-embed__wrapper">\s*(?:<a[^>]*>)?\s*(https?://[^\s<]+)', frag)
    if um:
        return '\n\n' + embed(um.group(1)) + '\n\n'
    link = re.search(r'<a[^>]*href="(https?://[^"]+)"', frag)
    return '\n\n' + (embed(link.group(1)) if link else '') + '\n\n'


def iframe_std(m):
    src = html.unescape(m.group(1))
    if 'youtube' in src or 'spotify' in src:
        return '\n\n' + embed(src) + '\n\n'
    return f'<figure cls="media media--video"><iframe src="{esc(src)}" loading="lazy" allowfullscreen></iframe></figure>'


def clean(c):
    c = c or ''
    # --- HTML ya renderizado por WordPress (sincronización automática)
    c = re.sub(r'<script\b.*?</script>', '', c, flags=re.S | re.I)
    for pat in ('sharedaddy', 'jp-post-flair', 'jp-relatedposts', 'wpcnt', 'wordads', 'jetpack-likes', 'wp-block-jetpack-subscriptions', 'wp-block-jetpack-like'):
        c = blocks(c, 'div', pat, lambda frag: '')
    gal = lambda frag: '\n\n' + gallery(re.findall(r'<img[^>]+?src="([^"]+)"', frag)) + '\n\n'
    c = blocks(c, 'div', r'tiled-gallery|\bgallery\b', gal)
    c = blocks(c, 'figure', r'wp-block-gallery', gal)
    c = blocks(c, 'figure', r'wp-block-embed', emb_rendered)
    c = re.sub(r'<span[^>]*class="[^"]*embed-[^"]*"[^>]*>(.*?)</span>', r'\1', c, flags=re.S)
    c = re.sub(r'<iframe(?![^>]*\btitle="(?:Video de YouTube|Spotify)")[^>]*?src="([^"]+)"[^>]*>\s*</iframe>', iframe_std, c)
    c = re.sub(r'<img\b[^>]*class="[^"]*(?:wp-smiley|emoji)[^"]*"[^>]*>', lambda m: (re.search(r'alt="([^"]*)"', m.group(0)) or [None, ''])[1], c)
    c = re.sub(rf'<a\b[^>]*href="https?://{re.escape(OLD)}/[^"]*"[^>]*>\s*(<img[^>]*>)\s*</a>', r'\1', c)
    c = re.sub(rf'<a\b[^>]*href="https?://(?:i\d\.wp\.com/)?{re.escape(OLD)}/wp-content/uploads/[^"]*"[^>]*>\s*(<img[^>]*>)\s*</a>', r'\1', c)
    # galerías de bloque: recoger imágenes
    def gal_block(m):
        return '\n\n' + gallery(re.findall(r'<img[^>]+src="([^"]+)"', m.group(0))) + '\n\n'
    c = re.sub(r'<!-- wp:gallery.*?<!-- /wp:gallery -->', gal_block, c, flags=re.S)
    # embeds de bloque
    def emb_block(m):
        um = re.search(r'wp-block-embed__wrapper">\s*(\S+)\s*</div>', m.group(0))
        return '\n\n' + (embed(um.group(1)) if um else re.sub(r'<!--.*?-->', '', m.group(0), flags=re.S)) + '\n\n'
    c = re.sub(r'<!-- wp:(?:core-embed/\w+|embed)\b.*?<!-- /wp:(?:core-embed/\w+|embed) -->', emb_block, c, flags=re.S)
    # shortcodes
    c = re.sub(r'\[caption[^\]]*\](.*?)\[/caption\]',
               lambda m: '<figure cls="figura">' + re.sub(r'(<img[^>]*>)(.*)', r'\1<figcaption>\2</figcaption>', m.group(1).strip(), flags=re.S) + '</figure>', c, flags=re.S)
    c = re.sub(r'\[/?(?:embed|audio|video)[^\]]*\]', '', c)
    # comentarios de bloque
    c = re.sub(r'<!-- /?wp:[^>]*-->', '', c)
    # URLs solas en una línea -> embed
    c = re.sub(r'(?m)^[ \t]*(?:&nbsp;)?[ \t]*(https?://[^\s<]+)[ \t]*$', lambda m: '\n\n' + embed(m.group(1)) + '\n\n', c)
    if not re.search(r'<p[\s>]', c):
        c = autop(c)
    # emojis de Facebook (ya no existen) y párrafos vacíos
    c = re.sub(r'<span[^>]*>\s*<img[^>]*fbcdn[^>]*>\s*</span>', '', c)
    c = re.sub(r'<img[^>]*emoji\.php[^>]*>', '', c)
    c = re.sub(r'<p[^>]*>(?:\s|&nbsp;|<br\s*/?>)*</p>', '', c)
    # imágenes: tamaño, lazy, sin atributos rígidos
    def fix_img(m):
        tag = m.group(0)
        src = re.search(r'src="([^"]+)"', tag)
        alt = re.search(r'alt="([^"]*)"', tag)
        if not src:
            return ''
        return f'<img src="{esc(img_url(src.group(1)))}" alt="{alt.group(1) if alt else ""}" loading="lazy">'
    c = re.sub(r'<img\b[^>]*>', fix_img, c)
    # clases y estilos de WordPress que no aplican
    c = re.sub(r'\s(?:class|style|data-[\w-]+|id)="[^"]*"', '', c)
    c = c.replace(' cls="', ' class="')
    c = c.replace('<figure>', '<figure class="figura">')
    c = re.sub(r'<figure class="figura">(\s*<ul)', r'<figure class="galeria">\1', c)
    # enlaces internos al dominio viejo -> rutas nuevas
    c = re.sub(rf'https?://{re.escape(OLD)}(/\d{{4}}/\d{{2}}/\d{{2}}/[^"\s]*|/category/[^"\s]*|/acerca-de/|/contacto/)', r'\1', c)
    c = re.sub(r'<a (href="https?://)', r'<a target="_blank" rel="noopener" \1', c)
    c = c.replace('href="/Users/tobaa/Documents/cnn.it/', 'target="_blank" rel="noopener" href="https://cnn.it/')
    c = re.sub(r'<a [^>]*href="/project/[^"]*"[^>]*>(.*?)</a>', r'\1', c, flags=re.S)
    c = re.sub(r'\n{3,}', '\n\n', c)
    return c.strip()


def plain(h):
    t = re.sub(r'<(figure|iframe)[\s\S]*?</\1>', ' ', h)
    t = re.sub(r'<[^>]+>', ' ', t)
    return re.sub(r'\s+', ' ', html.unescape(t)).strip()


def split_title(t):
    t = html.unescape(t or '').strip()
    m = re.match(r'^([^|]{3,14})\s*\|\s*(.+)$', t)
    if m and m.group(1).strip().lower() in KICKERS:
        return m.group(1).strip(), m.group(2).strip()
    return None, t


# ---------------------------------------------------------------- entradas
posts = []
pages = {p['slug']: p['content'] for p in data.get('pages', [])}
coms = {}
for cm in data.get('comments', []):
    coms.setdefault(cm['post'], []).append({'autor': cm['autor'], 'fecha': datetime.strptime(cm['fecha'][:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S'),
                                            'texto': plain(cm['texto'])})
for it in data['posts']:
    d = datetime.strptime(it['date'][:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
    url = urlparse(it['url']).path or '/'
    if not url.endswith('/'):
        url += '/'
    kicker, title = split_title(it['title'])
    cats = [c for c in it.get('categories', []) if c in CATNAME]
    body = clean(it['content'])
    text = plain(body)
    exc = plain(it.get('excerpt') or '')
    if not exc:
        exc = text[:220].rsplit(' ', 1)[0] + '…' if len(text) > 220 else text
    thumb = it.get('featured_image') or None
    if not thumb:
        m = re.search(r'<img src="([^"]+)"', body)
        thumb = m.group(1) if m else None
    # evitar repetir la imagen destacada si abre el artículo
    if thumb:
        base = img_url(thumb).split('?')[0]
        first = re.match(r'\s*<figure class="figura">\s*<img src="([^"]+)"[^>]*>\s*</figure>', body)
        if first and first.group(1).split('?')[0] == base:
            body = body[first.end():].lstrip()
    words = len(text.split())
    posts.append(dict(title=title, kicker=kicker, date=d, url=url, cats=cats or ['actualidad'], body=body, text=text, excerpt=exc,
                      thumb=img_url(thumb) if thumb else None, mins=max(1, round(words / 200)), comments=sorted(coms.get(it['id'], []), key=lambda c: c['fecha']),
                      slug=it['slug']))
posts.sort(key=lambda p: p['date'], reverse=True)

# ---------------------------------------------------------------- plantillas
CSS_V = '4'
LOGO_SVG = ('<svg class="{c}" viewBox="0 0 100 100" aria-hidden="true" focusable="false">'
            '<circle cx="50" cy="50" r="45" fill="none" stroke="currentColor" stroke-width="4.5"/>'
            '<path d="M56 15 L69 17.5 L74.5 35.5 L50 24 Z" fill="currentColor"/>'
            '<path d="M53.5 26.5 L55 30 L66 33.5 L74.5 35.5" fill="none" stroke="currentColor" stroke-width=".7"/>'
            '<path d="M55 30 C 54 42, 40 58, 28 72 C 23 77, 19 80, 15.5 83" fill="none" stroke="currentColor" stroke-width=".8"/></svg>')
def logo(c='logo'):
    return LOGO_SVG.replace('{c}', c)
CUR = ' aria-current="page"'


def chip(c, link=True):
    n = CATNAME[c]
    return f'<a class="chip chip--{c}" href="/category/{c}/">{n}</a>' if link else f'<span class="chip chip--{c}">{n}</span>'


def layout(title, body, desc=TAGLINE, path='/', image=None, og_type='website', active=None):
    full = f'{title} · {SITE}' if title != SITE else f'{SITE} · {TAGLINE}'
    nav = ''.join(f'<a href="/category/{s}/"{CUR if active == s else ""}>{n}</a>' for s, n in CATS)
    og_img = image or DOMAIN + '/assets/portada.jpg'
    return f'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(full)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{DOMAIN}{path}">
<meta property="og:site_name" content="{SITE}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{DOMAIN}{path}">
<meta property="og:image" content="{esc(og_img)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@VSinCola">
<link rel="icon" href="/assets/icono.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{LOGO}?w=180">
<meta name="theme-color" content="#c000c0">
<link rel="alternate" type="application/rss+xml" title="{SITE}" href="/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Open+Sans:ital,wght@0,400;0,600;0,700;1,400;1,600&display=swap">
<link rel="stylesheet" href="/assets/estilo.css?v={CSS_V}">
</head>
<body>
<a class="saltar" href="#contenido">Saltar al contenido</a>
<header class="barra">
  <div class="barra__in">
    <a class="marca" href="/" aria-label="{SITE}, portada">{logo('marca__logo')}<span class="marca__txt">Ideas que vuelan</span></a>
    <nav class="nav" aria-label="Secciones">{nav}<a href="/archivo/"{CUR if active == "archivo" else ""}>Archivo</a></nav>
    <a class="buscar-btn" href="/buscar/" aria-label="Buscar"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></a>
  </div>
</header>
<main id="contenido">
{body}
</main>
<footer class="pie nubes">
  <div class="cita">
    <blockquote>“Volando sin cola para reflexionar, debatir, construir y deconstruir ideas en un mundo diverso.”</blockquote>
    <span class="cita__barra" aria-hidden="true"></span>
    {logo('cita__logo')}
  </div>
  <div class="pie__in">
    <div class="pie__marca">
      {logo('pie__icono')}
      <p class="pie__logo">Volantín<small>Sin cola</small></p>
    </div>
    <nav class="pie__nav" aria-label="Sitio">
      <a href="/acerca-de/">¿Volantín Sin Cola?</a>
      <a href="/contacto/">Contacto</a>
      <a href="/archivo/">Retrovisión</a>
      <a href="/feed.xml">RSS</a>
    </nav>
    <nav class="pie__nav" aria-label="Redes">
      <a href="{FACEBOOK}" target="_blank" rel="noopener">Facebook</a>
      <a href="{TWITTER}" target="_blank" rel="noopener">X / Twitter</a>
    </nav>
  </div>
  <p class="pie__legal">© 2018–{datetime.now().year} Volantín Sin Cola · volantinsincola.cl</p>
</footer>
</body>
</html>
'''


def fig_img(p, cls, w=1200):
    if p['thumb']:
        src = p['thumb'].split('?')[0] + f'?w={w}' if OLD in p['thumb'] else p['thumb']
        return f'<div class="{cls}"><img src="{esc(src)}" alt="" loading="lazy"></div>'
    return f'<div class="{cls} vacia nubes" aria-hidden="true">{logo("vacia__logo")}</div>'


def meta_line(p):
    return f'<time datetime="{p["date"]:%Y-%m-%d}">{fecha(p["date"])}</time><span>{p["mins"]} min de lectura</span>'


def title_html(p):
    return esc(p['title'])


def card(p, size=''):
    return f'''<article class="tarjeta {size}">
  <a class="tarjeta__link" href="{p['url']}">{fig_img(p, 'tarjeta__img', 800)}</a>
  <div class="tarjeta__txt">
    <div class="chips">{''.join(chip(c) for c in p['cats'])}</div>
    <h3 class="tarjeta__tit"><a href="{p['url']}">{title_html(p)}</a></h3>
    <p class="tarjeta__exc">{esc(p['excerpt'])}</p>
    <p class="meta">{meta_line(p)}</p>
  </div>
</article>'''


def row(p):
    return f'''<li class="fila">
  <time class="fila__fecha" datetime="{p['date']:%Y-%m-%d}">{p['date'].day} {MESES[p['date'].month-1][:3]}<br><b>{p['date'].year}</b></time>
  <div class="fila__txt">
    <div class="chips">{''.join(chip(c) for c in p['cats'])}</div>
    <h3><a href="{p['url']}">{title_html(p)}</a></h3>
    <p>{esc(p['excerpt'])}</p>
  </div>
</li>'''


def write(path, content):
    fp = os.path.join(OUT, path.strip('/'), 'index.html') if not path.endswith('.html') and not '.' in os.path.basename(path) else os.path.join(OUT, path.strip('/'))
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, 'w', encoding='utf-8') as f:
        f.write(content)


# ---------------------------------------------------------------- build
if os.path.exists(OUT):
    shutil.rmtree(OUT)
os.makedirs(os.path.join(OUT, 'assets'))
shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'estilo.css'), os.path.join(OUT, 'assets', 'estilo.css'))
shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'buscar.js'), os.path.join(OUT, 'assets', 'buscar.js'))
shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'og-portada.jpg'), os.path.join(OUT, 'assets', 'portada.jpg'))
with open(os.path.join(OUT, 'assets', 'icono.svg'), 'w') as f:
    f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="22" fill="#c000c0"/><g color="#fff" transform="translate(9 9) scale(.82)">' + LOGO_SVG.split('focusable="false">')[1].replace('</svg>', '') + '</g></svg>')

# portada
lead, dest, recent = posts[0], posts[1:7], posts[7:19]
home = f'''
<section class="hero nubes">
  <div class="hero__in">
    <div class="hero__txt">
      <h1 class="hero__tit">Ideas<br>que<br>vuelan</h1>
      <p class="hero__tag">actualidad. <span>cultura.</span> <span>tendencias.</span></p>
    </div>
    {logo('hero__logo')}
  </div>
  <div class="hero__secciones">
    {''.join(f'<a class="vidrio" href="/category/{s}/">{logo("vidrio__logo")}<b>{n.lower()}.</b><span>{CATDESC[s]}</span><small>{sum(1 for p in posts if s in p["cats"])} artículos</small></a>' for s, n in CATS)}
  </div>
</section>
<section class="portada" aria-label="Última publicación">
  <article class="lead">
    <a class="lead__img" href="{lead['url']}">{fig_img(lead, 'lead__fig', 1400)}</a>
    <div class="lead__txt">
      <p class="eyebrow">Lo último</p>
      <div class="chips">{''.join(chip(c) for c in lead['cats'])}</div>
      <h2 class="lead__tit"><a href="{lead['url']}">{title_html(lead)}</a></h2>
      <p class="lead__exc">{esc(lead['excerpt'])}</p>
      <p class="meta">{meta_line(lead)}</p>
    </div>
  </article>
</section>
<section class="bloque">
  <h2 class="bloque__tit">Destacados</h2>
  <div class="grilla">{''.join(card(p) for p in dest)}</div>
</section>
<section class="bloque bloque--dos">
  <div>
    <h2 class="bloque__tit">Más recientes</h2>
    <ol class="filas">{''.join(row(p) for p in recent)}</ol>
    <a class="boton" href="/archivo/">Ver los {len(posts)} artículos</a>
  </div>
  <aside class="secciones" aria-label="Por año">
    <h2 class="bloque__tit">Retrovisión</h2>
    <nav class="anios">{''.join(f'<a href="/archivo/#y{y}">{y}</a>' for y in sorted({p['date'].year for p in posts}, reverse=True))}</nav>
  </aside>
</section>
'''
write('/', layout(SITE, home, desc='Volando sin cola para reflexionar, debatir, construir y deconstruir ideas en un mundo diverso.'))

# artículos
for i, p in enumerate(posts):
    newer = posts[i - 1] if i > 0 else None
    older = posts[i + 1] if i + 1 < len(posts) else None
    related = [q for q in posts if q is not p and set(q['cats']) & set(p['cats'])][:3]
    hero = ''
    if p['thumb']:
        hero = f'<figure class="art__hero"><img src="{esc(p["thumb"].split("?")[0] + "?w=1600" if OLD in p["thumb"] else p["thumb"])}" alt=""></figure>'
    com = ''
    if p['comments']:
        com = '<section class="comentarios"><h2>Comentarios</h2>' + ''.join(
            f'<div class="comentario"><p class="meta"><b>{esc(c["autor"])}</b> · {fecha(c["fecha"])}</p><p>{esc(c["texto"])}</p></div>' for c in p['comments']) + '</section>'
    share_url = quote(DOMAIN + p['url'], safe='')
    share_t = quote(p['title'], safe='')
    nav = '<nav class="art__nav" aria-label="Más artículos">'
    nav += f'<a href="{older["url"]}"><small>Anterior</small>{esc(older["title"])}</a>' if older else '<span></span>'
    nav += f'<a class="der" href="{newer["url"]}"><small>Siguiente</small>{esc(newer["title"])}</a>' if newer else '<span></span>'
    nav += '</nav>'
    body = f'''
<article class="art">
  <header class="art__cab">
    <div class="chips">{''.join(chip(c) for c in p['cats'])}</div>
    {f'<p class="art__kicker">{esc(p["kicker"])}</p>' if p['kicker'] and p['kicker'].lower() not in [CATNAME[c].lower() for c in p['cats']] else ''}
    <h1 class="art__tit">{title_html(p)}</h1>
    <p class="art__bajada">{esc(p['excerpt'])}</p>
    <p class="meta"><span>Por Ozóniko ::.</span>{meta_line(p)}</p>
  </header>
  {hero}
  <div class="prosa">
{p['body']}
  </div>
  <footer class="art__pie">
    <p class="compartir"><span>Compartir</span>
      <a href="https://wa.me/?text={share_t}%20{share_url}" target="_blank" rel="noopener">WhatsApp</a>
      <a href="https://www.facebook.com/sharer/sharer.php?u={share_url}" target="_blank" rel="noopener">Facebook</a>
      <a href="https://twitter.com/intent/tweet?url={share_url}&amp;text={share_t}&amp;via=VSinCola" target="_blank" rel="noopener">X</a>
    </p>
    {com}
    {nav}
  </footer>
</article>
{f'<section class="bloque"><h2 class="bloque__tit">Sigue leyendo</h2><div class="grilla grilla--3">{"".join(card(q) for q in related)}</div></section>' if related else ''}
'''
    write(p['url'], layout(p['title'], body, desc=p['excerpt'], path=p['url'], image=p['thumb'], og_type='article', active=p['cats'][0]))

# secciones
for s, n in CATS:
    ps = [p for p in posts if s in p['cats']]
    body = f'''
<header class="titular titular--marca nubes">
  {logo('titular__logo')}
  <p class="eyebrow">Sección</p>
  <h1>{n.lower()}.</h1>
  <p>{CATDESC[s]}</p>
  <p class="meta">{len(ps)} artículos</p>
</header>
<section class="bloque"><div class="grilla">{''.join(card(q) for q in ps)}</div></section>'''
    write(f'/category/{s}/', layout(n, body, desc=CATDESC[s], path=f'/category/{s}/', active=s))

# archivo general y por mes
years = {}
for p in posts:
    years.setdefault(p['date'].year, []).append(p)
toc = ''.join(f'<a href="#y{y}">{y}<small>{len(v)}</small></a>' for y, v in years.items())
secs = ''.join(f'<section class="anio" id="y{y}"><h2>{y}</h2><ol class="filas">{"".join(row(p) for p in v)}</ol></section>' for y, v in years.items())
body = f'''
<header class="titular">
  <p class="eyebrow">Retrovisión</p>
  <h1>Archivo</h1>
  <p>Todo lo publicado desde 2018, del más nuevo al más antiguo.</p>
  <nav class="anios" aria-label="Años">{toc}</nav>
</header>
<div class="bloque">{secs}</div>'''
write('/archivo/', layout('Archivo', body, desc='Todos los artículos de Volantín Sin Cola desde 2018.', path='/archivo/', active='archivo'))
months = {}
for p in posts:
    months.setdefault((p['date'].year, p['date'].month), []).append(p)
for (y, m), v in months.items():
    t = f'{MESES[m-1].capitalize()} {y}'
    body = f'<header class="titular"><p class="eyebrow">Retrovisión</p><h1>{t}</h1><p><a href="/archivo/">Ver todo el archivo</a></p></header><div class="bloque"><ol class="filas">{"".join(row(p) for p in v)}</ol></div>'
    write(f'/{y}/{m:02d}/', layout(t, body, path=f'/{y}/{m:02d}/', active='archivo'))

# páginas
about = clean(pages.get('acerca-de', ''))
write('/acerca-de/', layout('¿Volantín Sin Cola?', f'<article class="art"><header class="art__cab"><p class="eyebrow">Quiénes somos</p><h1 class="art__tit">¿Volantín Sin Cola?</h1></header><div class="prosa">{about}</div></article>',
                            desc='Volantín Sin Cola nació de una convicción simple: las ideas más interesantes son las que se atreven a volar sin lastres.', path='/acerca-de/'))
contact_img = img_url(f'https://{OLD}/wp-content/uploads/2019/06/contacto.png', 900)
contact = f'''
<article class="art art--angosto">
  <header class="art__cab">
    <p class="eyebrow">Contacto</p>
    <h1 class="art__tit">Escríbenos</h1>
    <p class="art__bajada">¿Escribes sobre actualidad, cultura o tendencias? ¿Tienes dudas sobre nuestro volantín? Comunícate con nosotros.</p>
  </header>
  <form class="form" name="contacto" method="POST" action="/contacto/gracias/" data-netlify="true" netlify-honeypot="bot-field">
    <input type="hidden" name="form-name" value="contacto">
    <p class="oculto"><label>No completar: <input name="bot-field"></label></p>
    <label for="f-nombre">Nombre</label><input id="f-nombre" name="nombre" required autocomplete="name">
    <label for="f-correo">Correo electrónico</label><input id="f-correo" name="correo" type="email" required autocomplete="email">
    <label for="f-web">Sitio web <small>(opcional)</small></label><input id="f-web" name="web" type="url" placeholder="https://">
    <label for="f-msg">Mensaje</label><textarea id="f-msg" name="mensaje" rows="6" required></textarea>
    <button class="boton" type="submit">Enviar mensaje</button>
  </form>
</article>'''
write('/contacto/', layout('Contacto', contact, desc='Escríbele a Volantín Sin Cola.', path='/contacto/'))
write('/contacto/gracias/', layout('Mensaje enviado', '<article class="art art--angosto"><header class="art__cab"><p class="eyebrow">Contacto</p><h1 class="art__tit">Mensaje recibido</h1><p class="art__bajada">Gracias por escribir. Te respondemos al correo que dejaste.</p><p><a class="boton" href="/">Volver a la portada</a></p></header></article>', path='/contacto/gracias/'))

# búsqueda
write('/buscar/', layout('Buscar', '''
<header class="titular">
  <p class="eyebrow">Buscar</p>
  <h1>¿Qué andas buscando?</h1>
  <form class="buscador" role="search" onsubmit="return false">
    <label for="q" class="oculto">Buscar en el sitio</label>
    <input id="q" type="search" placeholder="Madonna, Orgullo, Kylie, izquierda…" autocomplete="off" autofocus>
  </form>
  <p class="meta" id="estado">Escribe al menos dos letras.</p>
</header>
<div class="bloque"><ol class="filas" id="resultados"></ol></div>
<script src="/assets/buscar.js?v=2" defer></script>''', path='/buscar/'))
with open(os.path.join(OUT, 'buscar.json'), 'w', encoding='utf-8') as f:
    json.dump([{'t': p['title'], 'u': p['url'], 'e': p['excerpt'], 'd': f"{p['date'].day} {MESES[p['date'].month-1][:3]}", 'y': p['date'].year,
                'c': [[c, CATNAME[c]] for c in p['cats']], 'x': p['text']} for p in posts], f, ensure_ascii=False)

# 404
write('/404.html', layout('Página no encontrada', '<header class="titular"><p class="eyebrow">Error 404</p><h1>Este volantín se fue cortado</h1><p>La página que buscas no existe o cambió de dirección.</p><p><a class="boton" href="/">Ir a la portada</a> <a class="boton boton--sec" href="/buscar/">Buscar</a></p></header>', path='/404.html'))

# RSS, sitemap, robots, redirecciones
rss_items = ''.join(f'''<item><title>{esc(p['title'])}</title><link>{DOMAIN}{p['url']}</link><guid>{DOMAIN}{p['url']}</guid><pubDate>{format_datetime(p['date'].replace(tzinfo=None).astimezone())}</pubDate>{''.join(f'<category>{CATNAME[c]}</category>' for c in p['cats'])}<description>{esc(p['excerpt'])}</description></item>''' for p in posts[:20])
with open(os.path.join(OUT, 'feed.xml'), 'w', encoding='utf-8') as f:
    f.write(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{SITE}</title><link>{DOMAIN}/</link><description>{TAGLINE}</description><language>es</language>{rss_items}</channel></rss>')
urls = ['/', '/archivo/', '/acerca-de/', '/contacto/'] + [f'/category/{s}/' for s, _ in CATS] + [p['url'] for p in posts]
with open(os.path.join(OUT, 'sitemap.xml'), 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{DOMAIN}{u}</loc></url>' for u in urls) + '</urlset>')
with open(os.path.join(OUT, 'robots.txt'), 'w') as f:
    f.write(f'User-agent: *\nAllow: /\nSitemap: {DOMAIN}/sitemap.xml\n')
with open(os.path.join(OUT, '_redirects'), 'w') as f:
    f.write('# Direcciones antiguas de WordPress\n/feed/        /feed.xml     301\n/feed         /feed.xml     301\n/page/*       /archivo/     301\n/category/:c/page/*  /category/:c/  301\n/:y/:m/:d/:slug/amp/  /:y/:m/:d/:slug/  301\n')

print(f'{len(posts)} artículos, {len(months)} meses, páginas: {list(pages)}')
