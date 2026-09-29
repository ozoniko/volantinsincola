# -*- coding: utf-8 -*-
"""Descarga las entradas publicadas de WordPress.com y las guarda en datos/wordpress.json.

Lo ejecuta GitHub Actions cada hora. Si WordPress no responde o devuelve algo raro,
termina con error y NO toca los datos, así el sitio publicado nunca queda vacío.
"""
import json, os, sys, time, urllib.request, urllib.parse

SITE = 'volantinsincola166136375.wordpress.com'
API = f'https://public-api.wordpress.com/rest/v1.1/sites/{SITE}'
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'datos', 'wordpress.json')


def get(path, **params):
    url = f'{API}/{path}?{urllib.parse.urlencode(params)}'
    for intento in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'volantinsincola.cl-sync'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            print(f'  intento {intento + 1} falló: {e}')
            time.sleep(5 * (intento + 1))
    sys.exit(f'No se pudo leer {url}')


def todas(tipo, fields):
    out, page = [], 1
    while True:
        d = get('posts/', type=tipo, status='publish', number=100, page=page, order_by='date', order='DESC', fields=fields)
        lote = d.get('posts', [])
        out += lote
        if not lote or len(out) >= d.get('found', 0):
            return out, d.get('found', 0)
        page += 1


posts_raw, found = todas('post', 'ID,title,URL,slug,date,modified,excerpt,content,featured_image,categories')
if not posts_raw or len(posts_raw) != found:
    sys.exit(f'Respuesta incompleta de WordPress ({len(posts_raw)} de {found}); no se actualiza nada.')

posts = [{
    'id': p['ID'],
    'title': p.get('title') or '',
    'url': p['URL'],
    'slug': p['slug'],
    'date': p['date'],
    'modified': p.get('modified', ''),
    'excerpt': p.get('excerpt') or '',
    'featured_image': p.get('featured_image') or '',
    'categories': sorted(c.get('slug') for c in (p.get('categories') or {}).values()),
    'content': p.get('content') or '',
} for p in posts_raw]

pages_raw, _ = todas('page', 'ID,title,slug,content')
pages = [{'id': p['ID'], 'slug': p['slug'], 'title': p.get('title') or '', 'content': p.get('content') or ''} for p in pages_raw]

comments = []
d = get('comments/', status='approved', number=100, fields='post,author,date,content,type')
for c in d.get('comments', []):
    if c.get('type', 'comment') == 'comment' and c.get('post'):
        comments.append({'post': c['post']['ID'], 'autor': (c.get('author') or {}).get('name', 'Anónimo'), 'fecha': c['date'], 'texto': c.get('content') or ''})

# resguardo: no aceptar una caída brusca de artículos (p. ej. si WordPress falla a medias)
if os.path.exists(DATA):
    with open(DATA, encoding='utf-8') as f:
        antes = len(json.load(f).get('posts', []))
    if len(posts) < antes * 0.8:
        sys.exit(f'WordPress devolvió {len(posts)} artículos y antes había {antes}. Se detiene por seguridad.')

posts.sort(key=lambda p: p['id'])
pages.sort(key=lambda p: p['id'])
comments.sort(key=lambda c: (c['post'], c['fecha']))
os.makedirs(os.path.dirname(DATA), exist_ok=True)
with open(DATA, 'w', encoding='utf-8') as f:
    json.dump({'fuente': 'wordpress-api', 'posts': posts, 'pages': pages, 'comments': comments}, f, ensure_ascii=False, indent=1)
print(f'{len(posts)} artículos, {len(pages)} páginas, {len(comments)} comentarios.')
