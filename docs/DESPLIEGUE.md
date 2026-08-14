# Despliegue

Hay dos roles bien separados. Podés hacer solo uno o los dos en la misma máquina.

## A) SERVIDOR DE REPRODUCCIÓN (solo mostrar lo ya creado)

**No instala nada.** Es hosting estático puro: el navegador hace todo el trabajo.

Subir:
- La carpeta `frontend/` completa: `player.html`, `inflate.js`, `reader.js`,
  `render-webgl.js`, `render-canvas2d.js`, `tv-player.html`, `tv-controller.js` y
  `cache-refresh.js`.
- Los archivos `.asclv` que quieras servir (de `outputs/`).

Para `tv-player.html`, que conserva `DEFAULT_SRC="./outputs/clip.asclv"`, el layout URL
debe ser explícito. La forma recomendada es publicar el contenido de `frontend/` en el
directorio público y crear `outputs/` debajo de ese mismo directorio:

```text
public/
|-- tv-player.html
|-- tv-controller.js
|-- cache-refresh.js
|-- inflate.js
|-- reader.js
|-- render-canvas2d.js
|-- render-webgl.js
`-- outputs/
    `-- clip.asclv
```

Si en cambio la URL es `/frontend/tv-player.html`, la ruta relativa apunta a
`/frontend/outputs/clip.asclv`; hay que publicar el archivo allí o configurar ese mapeo
en PHP/Apache. No es necesario renombrar el artefacto local: `clip.asclv` es solo el
nombre estable con el que se publica.

Sirve con **cualquier** servidor de archivos estáticos: nginx, Apache, Caddy,
GitHub Pages, Netlify, Vercel, Amazon S3 + CloudFront, etc. No hace falta Python
ni ffmpeg ni base de datos. El servidor PHP/Apache existente es suficiente: no se
incluye ni se exige un servidor auxiliar del proyecto.

Recomendado (no obligatorio) para rendimiento y cache en webviews:
- Servir los `.asclv` con compresión de transporte: `gzip` (universal) o `brotli`.
- Cabeceras de cache para archivos versionados por hash:
  `Cache-Control: public, max-age=31536000, immutable`.
- Nombrar los clips con un hash, ej. `promo.a1b2c3.asclv`, para invalidar cache al actualizar.
- Si el player usa una URL estable que se reemplaza, como `outputs/clip.asclv`, no usar
  `immutable`: enviar `ETag` o `Last-Modified` con `Cache-Control: public, no-cache`. El
  navegador conserva el cuerpo, pero revalida y puede recibir `304`.
- El menú técnico del TV rota un query token y solicita `no-cache` para renovar esa URL.
  No elimina entradas anteriores de la caché global; su expulsión depende del WebView y
  del servidor.
- Enviar `Content-Type: application/octet-stream` y `Content-Length`. XHR no garantiza
  persistencia por sí solo: la política real la determinan estas cabeceras y el WebView.

Ejemplo nginx mínimo:
```
location / {
    root /var/www/asciline/public;
    types { application/octet-stream asclv; }
    gzip on;
    gzip_types application/octet-stream;
}
```

Cómo lo abre el usuario final: `https://tu-dominio/player.html` y elige el `.asclv`,
o un link directo `https://tu-dominio/player.html?src=promo.asclv` (autocarga).

## B) SERVIDOR DE CREACIÓN (encodear videos a .asclv)

Esto SÍ instala cosas, porque el encode es cómputo offline en Python.

Requisitos:
1. **Python 3.8+**
2. Paquetes pip (en `backend/requirements.txt`):
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
   (Pillow, numpy, opencv-python-headless)
3. **ffmpeg** como binario del sistema (NO es pip), para extraer el audio y los previews:
   - Debian/Ubuntu: `sudo apt install ffmpeg`
   - macOS: `brew install ffmpeg`
   - Windows: descargar de ffmpeg.org y agregar al PATH

Subir: la carpeta `backend/` (`encoder.py`, `ascl_decode.py`, `ascl_bundle.py`,
`make_clip.py`, `requirements.txt`). Después:
```bash
cd backend
python make_clip.py "../inputs/mi-video.mp4"   # -> ../outputs/mi-video.asclv
```
y publicás el `.asclv` resultante en el servidor de reproducción (A).

## Resumen

| Quiero… | Subir | Instalar |
|---|---|---|
| Solo **reproducir** | `frontend/` + los `.asclv` | nada |
| **Crear** clips | `backend/` | Python 3 + `requirements.txt` + ffmpeg |

El flujo natural: creás en B (o en tu PC), y solo publicás los `.asclv` + `frontend/` en A.
