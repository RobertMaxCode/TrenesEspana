"""Genera assets/rutas.js y assets/horarios.js desde los GTFS de Renfe.

Uso: python -I build_rutas.py <gtfs_cercanias> <gtfs_ld> <rutas.js> <horarios.js>
- rutas.js:     STOPS_C, STOPS_LD (coordenadas) y GEO_C (polilínea por ruta).
- horarios.js:  HORARIOS_C (clave con un solo horario), VARIANTES_C y SERVICIOS_C
                (claves con varios horarios, elegidos por service_id),
                HORARIOS_LD (lista de variantes por nº de tren).
"""
import collections
import csv
import json
import sys


def filas(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {(k.strip() if isinstance(k, str) else k):
                   (v.strip() if isinstance(v, str) else v)
                   for k, v in row.items()}


def hora(v):
    return (v or '')[:5]


def dgp(points, tol):
    n = len(points)
    if n < 3:
        return points
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        x1, y1 = points[i]
        x2, y2 = points[j]
        dx, dy = x2 - x1, y2 - y1
        den = dx * dx + dy * dy
        best = -1.0
        idx = None
        for k in range(i + 1, j):
            x, y = points[k]
            if den == 0:
                d2 = (x - x1) ** 2 + (y - y1) ** 2
            else:
                t = ((x - x1) * dx + (y - y1) * dy) / den
                t = max(0.0, min(1.0, t))
                d2 = (x - (x1 + t * dx)) ** 2 + (y - (y1 + t * dy)) ** 2
            if d2 > best:
                best = d2
                idx = k
        if best > tol * tol:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [points[k] for k in range(n) if keep[k]]


def leer_stops(path, con_nombre=False):
    out = {}
    for r in filas(path):
        try:
            lat = round(float(r['stop_lat']), 5)
            lon = round(float(r['stop_lon']), 5)
        except (KeyError, ValueError, TypeError):
            continue
        if con_nombre:
            out[r['stop_id']] = [lat, lon, r.get('stop_name', '')]
        else:
            out[r['stop_id']] = [lat, lon]
    return out


def cargar_trips_cercanias(gtfs):
    routes = []
    ridx = {}
    for r in filas(gtfs + '/routes.txt'):
        rid = r['route_id']
        if rid in ridx:
            continue
        ridx[rid] = len(routes)
        routes.append(r.get('route_short_name', ''))
    info = {}
    shapes = collections.defaultdict(collections.Counter)
    for t in filas(gtfs + '/trips.txt'):
        tid = t['trip_id']
        sid = t['service_id']
        ri = ridx.get(t['route_id'])
        if ri is None or not tid.startswith(sid):
            continue
        info[tid] = (tid[len(sid):], ri, sid)
        sh = t.get('shape_id', '')
        if sh:
            shapes[ri][sh] += 1
    return routes, info, shapes


def cargar_trips_ld(gtfs):
    info = {}
    for t in filas(gtfs + '/trips.txt'):
        short = t.get('trip_short_name', '')
        if short:
            info[t['trip_id']] = short
    return info


def cargar_shapes(path):
    crudo = collections.defaultdict(list)
    for r in filas(path):
        try:
            seq = int(float(r['shape_pt_sequence']))
            lat = float(r['shape_pt_lat'])
            lon = float(r['shape_pt_lon'])
        except (KeyError, ValueError, TypeError):
            continue
        crudo[r['shape_id']].append((seq, lat, lon))
    return {k: [(lat, lon) for _, lat, lon in sorted(v)] for k, v in crudo.items()}


def recorrer_stop_times(stop_times, cerrar):
    with open(stop_times, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        i_trip = header.index('trip_id')
        i_arr = header.index('arrival_time')
        i_dep = header.index('departure_time')
        i_stop = header.index('stop_id')
        i_seq = header.index('stop_sequence')
        actual = None
        rows = []
        for row in reader:
            tid = row[i_trip].strip()
            if tid != actual:
                if actual is not None:
                    cerrar(actual, rows)
                actual = tid
                rows = []
            rows.append((row[i_seq], row[i_stop].strip(),
                         row[i_arr].strip(), row[i_dep].strip()))
        if actual is not None:
            cerrar(actual, rows)


def firma(rows):
    rows.sort(key=lambda r: int(r[0]))
    return ';'.join('%s,%s,%s' % (r[1], hora(r[2]), hora(r[3])) for r in rows)


def horarios_cercanias(stop_times, trip_info):
    grupos = collections.defaultdict(dict)

    def cerrar(tid, rows):
        info = trip_info.get(tid)
        if not info:
            return
        key, _, sid = info
        sig = firma(rows)
        grupos[key].setdefault(sig, set()).add(sid)

    recorrer_stop_times(stop_times, cerrar)

    simples = {}
    variantes = {}
    servicios = {}
    for key, opciones in grupos.items():
        if len(opciones) == 1:
            simples[key] = next(iter(opciones))
            continue
        sigs = sorted(opciones)
        variantes[key] = sigs
        indice = {sig: i for i, sig in enumerate(sigs)}
        servicios[key] = {sid: indice[sig]
                          for sig, sids in opciones.items() for sid in sids}
    return simples, variantes, servicios


def horarios_ld(stop_times, trip_info):
    grupos = collections.defaultdict(set)

    def cerrar(tid, rows):
        key = trip_info.get(tid)
        if not key:
            return
        grupos[key].add(firma(rows))

    recorrer_stop_times(stop_times, cerrar)
    return {k: sorted(v) for k, v in grupos.items()}


def escribir(path, partes):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for nombre, obj in partes:
            f.write('window.%s = ' % nombre)
            json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))
            f.write(';\n')


def main(cgtfs, ldgtfs, out_rutas, out_horarios):
    routes, info_c, usos_shape = cargar_trips_cercanias(cgtfs)
    shapes = cargar_shapes(cgtfs + '/shapes.txt')

    geo = []
    for ri in range(len(routes)):
        pts = None
        if usos_shape[ri]:
            shape_id, _ = usos_shape[ri].most_common(1)[0]
            pts = shapes.get(shape_id)
        if pts:
            pts = dgp(pts, 0.0002)
            geo.append([[round(lat, 5), round(lon, 5)] for lat, lon in pts])
        else:
            geo.append(None)

    stops_c = leer_stops(cgtfs + '/stops.txt')
    stops_ld = leer_stops(ldgtfs + '/stops.txt', con_nombre=True)
    escribir(out_rutas, [('STOPS_C', stops_c), ('STOPS_LD', stops_ld), ('GEO_C', geo)])
    puntos = sum(len(g) for g in geo if g)
    print('rutas=%d con_geo=%d puntos=%d stopsC=%d stopsLD=%d'
          % (len(geo), sum(1 for g in geo if g), puntos, len(stops_c), len(stops_ld)))

    simples, variantes, servicios = horarios_cercanias(
        cgtfs + '/stop_times.txt', info_c)
    hor_ld = horarios_ld(ldgtfs + '/stop_times.txt', cargar_trips_ld(ldgtfs))
    escribir(out_horarios, [('HORARIOS_C', simples), ('VARIANTES_C', variantes),
                            ('SERVICIOS_C', servicios), ('HORARIOS_LD', hor_ld)])
    print('horariosC=%d variantesC=%d serviciosC=%d horariosLD=%d variantesLD=%d'
          % (len(simples), len(variantes), len(servicios),
             len(hor_ld), sum(len(v) for v in hor_ld.values())))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
