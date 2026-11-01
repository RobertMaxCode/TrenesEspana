"""Genera assets/gtfs.js desde el GTFS de Cercanías de Renfe.

Uso: python -I build_gtfs.py <carpeta_gtfs> <salida_gtfs.js>
Salida: window.RUTAS = [[linea, id_origen, id_destino], ...]
        window.TRIPS = {"clave_sin_servicio": indice_ruta, ...}
"""
import csv
import json
import re
import sys
import collections


def rows(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {(k.strip() if isinstance(k, str) else k):
                   (v.strip() if isinstance(v, str) else v)
                   for k, v in row.items()}


def main(gtfs_dir, out_path):
    routes = []
    route_index = {}
    for r in rows(gtfs_dir + '/routes.txt'):
        rid = r['route_id']
        if rid in route_index:
            continue
        route_index[rid] = len(routes)
        routes.append({'short': r.get('route_short_name', ''),
                       'long': r.get('route_long_name', ''),
                       'o': None, 'd': None, 'stops': []})

    trips_map = {}
    collisions = 0
    reps = collections.defaultdict(list)
    for t in rows(gtfs_dir + '/trips.txt'):
        tid = t['trip_id']
        sid = t['service_id']
        ri = route_index.get(t['route_id'])
        if ri is None or not tid.startswith(sid):
            continue
        key = tid[len(sid):]
        if key in trips_map:
            if trips_map[key] != ri:
                collisions += 1
            continue
        trips_map[key] = ri
        if len(reps[ri]) < 30:
            reps[ri].append(tid)

    repset = {tid: ri for ri, lst in reps.items() for tid in lst}
    endpoints = {}
    paradas = collections.defaultdict(list)
    with open(gtfs_dir + '/stop_times.txt', newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        i_trip = header.index('trip_id')
        i_stop = header.index('stop_id')
        i_seq = header.index('stop_sequence')
        for row in reader:
            tid = row[i_trip].strip()
            if tid not in repset:
                continue
            stop = row[i_stop].strip()
            try:
                seq = int(row[i_seq])
            except ValueError:
                continue
            paradas[tid].append((seq, stop))
            cur = endpoints.get(tid)
            if cur is None:
                endpoints[tid] = [seq, stop, seq, stop]
            else:
                if seq < cur[0]:
                    cur[0] = seq
                    cur[1] = stop
                if seq > cur[2]:
                    cur[2] = seq
                    cur[3] = stop

    missing = 0
    inconsistent = 0
    for ri, lst in reps.items():
        pairs = []
        for tid in lst:
            e = endpoints.get(tid)
            if e:
                pairs.append((e[1], e[3]))
        if not pairs:
            missing += 1
            print('sin extremos: route_index=%d short=%s' % (ri, routes[ri]['short']))
            continue
        counts = collections.Counter(pairs)
        (origin, dest), _ = counts.most_common(1)[0]
        routes[ri]['o'] = origin
        routes[ri]['d'] = dest
        if len(counts) > 1:
            inconsistent += 1

    for ri, lst in reps.items():
        mejor = None
        for tid in lst:
            parada = paradas.get(tid)
            if parada and (mejor is None or len(parada) > len(mejor)):
                mejor = parada
        if mejor:
            vistos = set()
            for _, stop in sorted(mejor):
                if stop not in vistos:
                    vistos.add(stop)
                    routes[ri]['stops'].append(stop)

    fallback = 0
    for r in routes:
        if r['o'] is not None or r['d'] is not None:
            continue
        cleaned = re.sub(r'\s+', ' ', r.get('long', '')).strip()
        parts = re.split(r'\s+-(?=\S)', cleaned)
        origin = dest = None
        if len(parts) == 2 and parts[0] and parts[1]:
            origin, dest = parts[0].strip(), parts[1].strip()
        elif len(parts) == 1:
            only = parts[0].strip()
            if cleaned.startswith('-'):
                dest = only.lstrip('- ').strip() or None
            elif cleaned.endswith('-'):
                origin = only.rstrip('- ').strip() or None
        r['o'] = origin
        r['d'] = dest
        if origin or dest:
            fallback += 1

    out_routes = [[r['short'], r['o'], r['d'], r['stops']] for r in routes]
    data = 'window.RUTAS = ' + json.dumps(out_routes, ensure_ascii=False, separators=(',', ':')) + ';\n'
    data += 'window.TRIPS = ' + json.dumps(trips_map, ensure_ascii=False, separators=(',', ':')) + ';\n'
    with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(data)

    print('routes=%d trips_keys=%d collisions=%d missing_endpoints=%d inconsistent=%d fallback_names=%d bytes=%d'
          % (len(routes), len(trips_map), collisions, missing, inconsistent, fallback, len(data)))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
