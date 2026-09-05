/* Worker `asciline-player` — código EXACTO que está desplegado en Cloudflare
   (recuperado con la API el 2026-08-31 y guardado acá porque hasta entonces
   vivía únicamente dentro de Cloudflare: si alguien lo pisaba, no había copia).

   Sirve el bucket R2 `asciline-player` en `iargen.com/player*` y en el espejo
   `asciline-player.iargen.workers.dev`. Nada de lo preexistente en la cuenta
   se toca: este worker y ese bucket son lo único del proyecto.

   Puntos que importan y no se deducen leyendo por arriba:

   - `PUT /__upload/<key>` es la única vía de escritura y exige
     `x-upload-token` == `env.UPLOAD_TOKEN`. **No hay autorización por
     contenido** en el código desplegado, aunque algún doc viejo la describa:
     eso fue una variante temporal que se desplegó una vez y se retiró.
   - `x-sha256` es opcional; si viene, R2 verifica el digest del cuerpo
     recibido y rechaza el put si no coincide. Siempre se manda.
   - CACHE-001: `clip.<hex>.asclv` sale `immutable` a un año; todo lo demás
     sale `no-cache` con ETag/304.
   - El prefijo `/player` se recorta antes de resolver la key, y un path sin
     extensión y sin barra final redirige agregándola.

   Actualización 2026-09-01 (H-10), dos agregados y nada más:

   - **Tipos de video** (`mp4`, `webm`) y `tsv`, y en la segunda vuelta del
     mismo día los del carril segmentado: `m3u8`, `mpd`, `ts`, `m4s`. Antes
     cualquier extensión desconocida salía `application/octet-stream`: servir
     así el pack v0 habría dado un falso negativo —muchos WebViews de TV miran
     el `content-type` antes de decidir si pueden reproducir, y con HLS es peor
     todavía: el tipo de la **playlist** es lo primero que mira el reproductor—.
   - **`Range`**: `206` con `content-range`, `416` fuera de rango y
     `accept-ranges: bytes` en las respuestas completas. Sin rangos hay
     reproductores de TV que directamente no arrancan un video, y el que
     arranca no puede buscar. La rama sin `Range` quedó idéntica.

   Para redesplegarlo: PUT multipart a
   `/accounts/<id>/workers/scripts/asciline-player` con este archivo como parte
   `worker.js`, `main_module: "worker.js"` y el binding R2 `BUCKET` →
   `asciline-player`. El secret `UPLOAD_TOKEN` NO viaja en el redeploy: los
   secrets sobreviven al despliegue del script. */

var TYPES={html:'text/html; charset=utf-8',js:'application/javascript; charset=utf-8',png:'image/png',asclv:'application/octet-stream',slots:'application/octet-stream',txt:'text/plain; charset=utf-8',json:'application/json',mp4:'video/mp4',webm:'video/webm',mp3:'audio/mpeg',tsv:'text/plain; charset=utf-8',m3u8:'application/vnd.apple.mpegurl',mpd:'application/dash+xml',ts:'video/mp2t',m4s:'video/iso.segment'};
function ctype(key){var i=key.lastIndexOf('.');var ext=i<0?'':key.slice(i+1).toLowerCase();return TYPES[ext]||'application/octet-stream';}
export default {
  async fetch(request, env) {
    var url = new URL(request.url);
    var path = url.pathname;
    if (path === '/player') return Response.redirect(url.origin + '/player/', 301);
    if (path.indexOf('/player/') === 0) path = path.slice(7);
    if (request.method === 'PUT' && path.indexOf('/__upload/') === 0) {
      if (!env.UPLOAD_TOKEN || request.headers.get('x-upload-token') !== env.UPLOAD_TOKEN) return new Response('forbidden\n',{status:403});
      var key = decodeURIComponent(path.slice(10));
      if (!key || key.indexOf('..') >= 0) return new Response('bad key\n',{status:400});
      var sha = request.headers.get('x-sha256');
      try {
        var obj = await env.BUCKET.put(key, request.body, sha ? {sha256: sha} : undefined);
        return new Response(JSON.stringify({ok:true,key:key,size:obj.size,etag:obj.httpEtag}),{headers:{'content-type':'application/json'}});
      } catch (e) {
        return new Response(JSON.stringify({ok:false,key:key,error:String(e)}),{status:400,headers:{'content-type':'application/json'}});
      }
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') return new Response('method not allowed\n',{status:405});
    var last = path.split('/').pop();
    if (path.charAt(path.length-1) !== '/' && last.indexOf('.') < 0) {
      return Response.redirect(url.origin + url.pathname + '/' + url.search, 301);
    }
    if (path.charAt(path.length-1) === '/') path += 'index.html';
    var k = path.replace(/^\/+/, '');
    if (!k) k = 'index.html';
    /* Range (2026-09-01): un <video> de TV suele pedir por rangos, y varios
       reproductores no arrancan si el servidor no los sirve. Se resuelve con
       un head + un get acotado; la rama sin Range quedo igual que antes. */
    var rangeHeader = request.headers.get('range');
    var rangeMatch = rangeHeader ? /^bytes=(\d*)-(\d*)$/.exec(rangeHeader.replace(/\s/g,'')) : null;
    if (rangeMatch) {
      var head = await env.BUCKET.head(k);
      if (!head) return new Response('not found\n',{status:404});
      var total = head.size, start, end;
      if (rangeMatch[1] === '') {
        var suffix = parseInt(rangeMatch[2],10);
        if (!(suffix > 0)) suffix = 0;
        start = suffix >= total ? 0 : total - suffix;
        end = total - 1;
      } else {
        start = parseInt(rangeMatch[1],10);
        end = rangeMatch[2] === '' ? total - 1 : parseInt(rangeMatch[2],10);
        if (end > total - 1) end = total - 1;
      }
      var rbase = k.split('/').pop();
      var rheaders = {'content-type': ctype(k), 'etag': head.httpEtag, 'accept-ranges':'bytes', 'cache-control': /^clip\.[0-9a-f]{8,64}\.asclv$/.test(rbase) ? 'public, max-age=31536000, immutable' : 'no-cache', 'access-control-allow-origin':'*'};
      if (!(start >= 0) || !(end >= start) || start >= total) {
        rheaders['content-range'] = 'bytes */' + total;
        return new Response(null,{status:416,headers:rheaders});
      }
      var part = await env.BUCKET.get(k,{range:{offset:start,length:end-start+1}});
      if (!part) return new Response('not found\n',{status:404});
      rheaders['content-range'] = 'bytes ' + start + '-' + end + '/' + total;
      rheaders['content-length'] = String(end - start + 1);
      if (request.method === 'HEAD') return new Response(null,{status:206,headers:rheaders});
      return new Response(part.body,{status:206,headers:rheaders});
    }
    var object = await env.BUCKET.get(k);
    if (!object) return new Response('not found\n',{status:404});
    var etag = object.httpEtag;
    /* CACHE-001 (F6-4): un clip versionado por contenido es inmutable y
       cacheable a un anio; todo lo demas sigue no-cache + ETag/304. */
    var base = k.split('/').pop();
    var immutable = /^clip\.[0-9a-f]{8,64}\.asclv$/.test(base);
    var headers = {'content-type': ctype(k), 'etag': etag, 'accept-ranges': 'bytes', 'cache-control': immutable ? 'public, max-age=31536000, immutable' : 'no-cache', 'access-control-allow-origin': '*'};
    var inm = request.headers.get('if-none-match');
    if (inm && inm === etag) return new Response(null,{status:304,headers:headers});
    headers['content-length'] = String(object.size);
    if (request.method === 'HEAD') return new Response(null,{headers:headers});
    return new Response(object.body,{headers:headers});
  }
};
