#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mp4_dedup.py - un mp4 COMUN y reproducible en el que cada cuadro repetido se
guarda UNA sola vez. Lo que xz logra comprimiendo, pero sin descomprimir nada.

Como funciona: un mp4 tiene los datos de cada muestra (cuadro codificado) en
`mdat` y un indice por pista (`stbl`: `stsz` tamanos, `stsc` + `stco`/`co64`
posiciones) que le dice al reproductor donde esta cada una. Nada obliga a que
dos muestras vivan en bytes distintos: si una muestra tiene exactamente el
mismo contenido que otra anterior, su entrada del indice apunta a esa copia.
El reproductor busca cada muestra donde dice el indice y recibe la MISMA
secuencia de bytes que en el archivo original; no puede notar la diferencia.

Medido el 2026-10-17 (docs/INTRO-Y-LOOP.md §6): intro + 9 vueltas del loop de
intro_D, pegadas sin recodificar = 4.578.034 B; deduplicado = 1.266.930 B
(xz -9 del mismo archivo: 1.262.632 B). 397 cuadros, 117 unicos. ffmpeg
decodifica los 397 identicos; Chromium da los mismos pixeles saltando a la
intro y a las vueltas 1/3/6/9 y reproduce de corrido sin cuadros caidos.

Condiciones:
  - las repeticiones tienen que ser BYTES IDENTICOS: codificar el loop una
    vez y pegarlo N veces (tools/emit_intro_loop.py lo hace). Recodificar el
    video entero nunca da vueltas identicas;
  - mp4/ISO BMFF no fragmentado (sin `moof`). MPEG-TS no tiene indice y WebM
    guarda los bloques dentro de los clusters: ahi no se puede;
  - el reproductor tiene que seguir el indice (Chromium y ffmpeg lo hacen;
    un reproductor de hardware que lea el archivo de corrido podria no).

Lo que cambia en el archivo: solo `mdat` (las muestras unicas, en orden de
primera aparicion) y, en cada pista, `stsc` (una muestra por chunk) y
`stco`/`co64` (una posicion por muestra). Todo lo demas (tiempos `stts`,
`ctts`, keyframes `stss`, `stsd`, edit lists) se copia tal cual. Al terminar
se relee el archivo escrito y se exige que cada muestra de cada pista tenga
exactamente los bytes del original.

Uso:
  python tools/mp4_dedup.py entrada.mp4 salida.mp4
"""

import hashlib
import struct
import sys

# Cajas que se recorren por dentro; el resto se copia como bytes.
CONTENEDORES = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf", b"mvex"}


class NoSoportado(ValueError):
    pass


# --------------------------------------------------------------------------
# Cajas

def leer_cajas(data, inicio=0, fin=None):
    """Lista de [tipo, contenido]: contenido es otra lista para los
    contenedores y bytes (sin cabecera) para el resto."""
    fin = len(data) if fin is None else fin
    cajas = []
    i = inicio
    while i < fin:
        if fin - i < 8:
            raise ValueError("caja truncada en %d" % i)
        size, tipo = struct.unpack(">I4s", data[i:i + 8])
        cab = 8
        if size == 1:
            size = struct.unpack(">Q", data[i + 8:i + 16])[0]
            cab = 16
        elif size == 0:
            size = fin - i
        if size < cab or i + size > fin:
            raise ValueError("caja %r con tamano invalido en %d" % (tipo, i))
        if tipo in CONTENEDORES:
            cajas.append([tipo, leer_cajas(data, i + cab, i + size)])
        else:
            cajas.append([tipo, data[i + cab:i + size]])
        i += size
    return cajas


def escribir(cajas):
    partes = []
    for tipo, cont in cajas:
        cuerpo = escribir(cont) if isinstance(cont, list) else cont
        if 8 + len(cuerpo) > 0xFFFFFFFF:
            partes.append(struct.pack(">I4sQ", 1, tipo, 16 + len(cuerpo)) + cuerpo)
        else:
            partes.append(struct.pack(">I4s", 8 + len(cuerpo), tipo) + cuerpo)
    return b"".join(partes)


def buscar(cajas, tipo):
    for caja in cajas:
        if caja[0] == tipo:
            return caja
    return None


def stbl_de(trak):
    mdia = buscar(trak[1], b"mdia")
    minf = buscar(mdia[1], b"minf") if mdia else None
    stbl = buscar(minf[1], b"stbl") if minf else None
    if stbl is None:
        raise NoSoportado("pista sin stbl")
    return stbl


# --------------------------------------------------------------------------
# El indice de una pista

def tamanos_de(stbl):
    stsz = buscar(stbl[1], b"stsz")
    if stsz is None:
        raise NoSoportado("pista sin stsz (stz2 no soportado)")
    fijo, n = struct.unpack(">II", stsz[1][4:12])
    if fijo:
        return [fijo] * n
    return list(struct.unpack(">%dI" % n, stsz[1][12:12 + 4 * n]))


def posiciones_de(stbl, tamanos):
    """Posicion absoluta de cada muestra, recorriendo stsc + stco/co64."""
    stsc = buscar(stbl[1], b"stsc")[1]
    corridas = [struct.unpack(">III", stsc[8 + 12 * k:20 + 12 * k])
                for k in range(struct.unpack(">I", stsc[4:8])[0])]
    caja = buscar(stbl[1], b"stco") or buscar(stbl[1], b"co64")
    if caja is None:
        raise NoSoportado("pista sin stco/co64")
    n_chunks = struct.unpack(">I", caja[1][4:8])[0]
    fmt = (">%dI" if caja[0] == b"stco" else ">%dQ") % n_chunks
    chunks = struct.unpack(fmt, caja[1][8:8 + struct.calcsize(fmt)])
    posiciones = []
    muestra = 0
    corrida = 0
    for c, inicio_chunk in enumerate(chunks, start=1):
        while corrida + 1 < len(corridas) and corridas[corrida + 1][0] <= c:
            corrida += 1
        pos = inicio_chunk
        for _ in range(corridas[corrida][1]):
            if muestra >= len(tamanos):
                break
            posiciones.append(pos)
            pos += tamanos[muestra]
            muestra += 1
    if muestra != len(tamanos):
        raise ValueError("el indice describe %d muestras y stsz %d" % (muestra, len(tamanos)))
    return posiciones


def muestras_de(data, trak):
    stbl = stbl_de(trak)
    tamanos = tamanos_de(stbl)
    return [data[p:p + t] for p, t in zip(posiciones_de(stbl, tamanos), tamanos)]


def reemplazar_indice(stbl, posiciones):
    """stsc = una muestra por chunk; stco (o co64 si alguna no entra en 32
    bits) = una posicion por muestra."""
    stbl[1] = [c for c in stbl[1] if c[0] not in (b"stsc", b"stco", b"co64")]
    stbl[1].append([b"stsc", struct.pack(">IIIII", 0, 1, 1, 1, 1)])
    n = len(posiciones)
    if posiciones and max(posiciones) > 0xFFFFFFFF:
        stbl[1].append([b"co64", struct.pack(">II", 0, n) + struct.pack(">%dQ" % n, *posiciones)])
    else:
        stbl[1].append([b"stco", struct.pack(">II", 0, n) + struct.pack(">%dI" % n, *posiciones)])


# --------------------------------------------------------------------------
# Deduplicar

def plan(muestras_por_pista):
    """(unicas, relativas): las muestras unicas de TODAS las pistas en orden de
    primera aparicion, y para cada pista la posicion relativa (dentro del mdat
    nuevo) de cada una de sus muestras. Dos muestras son la misma si tienen
    los mismos bytes (SHA-256 + comparacion completa)."""
    unicas = []
    vistas = {}
    relativas = []
    offset = 0
    for muestras in muestras_por_pista:
        rel = []
        for muestra in muestras:
            clave = hashlib.sha256(muestra).digest()
            previa = vistas.get(clave)
            if previa is not None and unicas[previa[1]] == muestra:
                rel.append(previa[0])
                continue
            vistas[clave] = (offset, len(unicas))
            unicas.append(muestra)
            rel.append(offset)
            offset += len(muestra)
        relativas.append(rel)
    return unicas, relativas


def deduplicar(data):
    """Bytes de un mp4 -> (bytes del mp4 deduplicado, resumen)."""
    top = leer_cajas(data)
    if any(c[0] == b"moof" for c in top):
        raise NoSoportado("mp4 fragmentado (moof): no soportado")
    moov = buscar(top, b"moov")
    if moov is None:
        raise NoSoportado("sin moov")
    traks = [c for c in moov[1] if c[0] == b"trak"]
    if not traks:
        raise NoSoportado("sin pistas")
    originales = [muestras_de(data, trak) for trak in traks]
    unicas, relativas = plan(originales)

    cabeza_cajas = [c for c in top if c[0] != b"mdat"]
    # Primero con posiciones provisorias para medir la cabeza; si alguna
    # posicion pasa a co64 la cabeza crece, asi que se repite hasta que quede fija.
    inicio = 0
    for _ in range(4):
        for trak, rel in zip(traks, relativas):
            reemplazar_indice(stbl_de(trak), [inicio + r for r in rel])
        cabeza = escribir(cabeza_cajas)
        tam_datos = sum(len(m) for m in unicas)
        cab_mdat = 8 if 8 + tam_datos <= 0xFFFFFFFF else 16
        nuevo_inicio = len(cabeza) + cab_mdat
        if nuevo_inicio == inicio:
            break
        inicio = nuevo_inicio
    else:
        raise ValueError("la cabeza no se estabilizo")
    if cab_mdat == 8:
        mdat = struct.pack(">I4s", 8 + tam_datos, b"mdat")
    else:
        mdat = struct.pack(">I4sQ", 1, b"mdat", 16 + tam_datos)
    salida = cabeza + mdat + b"".join(unicas)
    total = sum(len(m) for muestras in originales for m in muestras)
    resumen = {"pistas": len(traks),
               "muestras": sum(len(m) for m in originales),
               "unicas": len(unicas),
               "datos_antes": total, "datos_despues": tam_datos,
               "bytes_antes": len(data), "bytes_despues": len(salida)}
    verificar(originales, salida)
    return salida, resumen


def verificar(originales, salida):
    """Relee el mp4 escrito y exige las mismas muestras, byte a byte, pista
    por pista. Si falla, el archivo no se entrega."""
    top = leer_cajas(salida)
    traks = [c for c in buscar(top, b"moov")[1] if c[0] == b"trak"]
    if len(traks) != len(originales):
        raise AssertionError("cambio la cantidad de pistas")
    for k, (trak, esperadas) in enumerate(zip(traks, originales)):
        if muestras_de(salida, trak) != esperadas:
            raise AssertionError("la pista %d no reproduce las mismas muestras" % k)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__)
        return 2
    with open(argv[0], "rb") as stream:
        data = stream.read()
    salida, r = deduplicar(data)
    with open(argv[1], "wb") as stream:
        stream.write(salida)
    print("pistas %d, muestras %d, unicas %d; datos %d -> %d B; archivo %d -> %d B (%.1f %%)"
          % (r["pistas"], r["muestras"], r["unicas"], r["datos_antes"], r["datos_despues"],
             r["bytes_antes"], r["bytes_despues"], 100.0 * r["bytes_despues"] / r["bytes_antes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
