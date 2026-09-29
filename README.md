# volantinsincola.cl

Sitio de **Ideas que Vuelan / Volantín Sin Cola**.

## Cómo funciona

1. Escribes y publicas en WordPress.com, como siempre.
2. Cada hora, GitHub revisa WordPress (`sincronizar.py`) y guarda las entradas en `datos/wordpress.json`.
3. Si hubo cambios, Netlify arma el sitio de nuevo (`build.py`) y lo publica en volantinsincola.cl.

Para actualizar al tiro sin esperar la hora: pestaña **Actions** → **Sincronizar con WordPress** → **Run workflow**.

## Archivos

- `build.py`: arma el sitio completo en la carpeta `site/`.
- `estilo.css`, `buscar.js`, `og-portada.jpg`: diseño, buscador e imagen para compartir.
- `sincronizar.py`: lee WordPress y actualiza `datos/wordpress.json`.
- `.github/workflows/sincronizar.yml`: la tarea que corre cada hora.
- `netlify.toml`: le dice a Netlify cómo armar el sitio.

Nota: si WordPress devuelve de golpe menos del 80 % de los artículos que había, la sincronización se detiene por seguridad.
Si borraste muchas entradas a propósito, corre `sincronizar.py` después de ajustar ese límite.
