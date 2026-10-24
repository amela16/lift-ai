#!/usr/bin/env python3
"""Build frontend/src/data/lines.json from OpenStreetMap route relations.

Usage: python3 -I scripts/build-lines.py routes.json [platforms.json inventory.json stations.json]

routes.json is an Overpass export of Berlin's U-Bahn and S-Bahn routes:

  [out:json];area["name"="Berlin"]["admin_level"="4"]->.b;
  relation["type"="route"]["route"~"^(subway|light_rail|train)$"]
          ["ref"~"^(U[1-9]|S[0-9]{1,2})$"](area.b);out body;>;out skel qt;

Lines run through every ordered stop. Stops near a catalog station are snapped
to its exact coordinates so the 3D nodes sit on the lines; stops without
elevator records keep their OpenStreetMap position.

With platforms.json (the route relations' platform members with tags:
`(node(id:…);way(id:…);relation(id:…););out tags center;`), inventory.json
(BrokenLifts /api/station/list pages merged into {"docs": [...]}) and
stations.json (OSM railway=station nodes) it also updates backend/app/catalog.json:

- Stations missing from the BrokenLifts elevator inventory that OSM tags
  `wheelchair=no` are added (`"source": "osm"`), so they can be listed as
  having no elevator. Missing-but-step-free stations are left out: the
  inventory may simply not cover them.
- `no_elevator` lists the lines at a station whose network has no elevator in
  the inventory; `step_free: false` is added only when OSM confirms it.
"""
import json
import hashlib
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = json.loads((ROOT / 'backend/app/catalog.json').read_text())
OUT = ROOT / 'frontend/src/data/lines.json'
CATALOG_PATH = ROOT / 'backend/app/catalog.json'
# Inner-city U-Bahn stations can be 400 m apart; S-Bahn platforms are long and stations sparse.
SNAP_METERS = {'U-Bahn': 250, 'S-Bahn': 400}
# Two catalog entries 230 m apart: the S1 stops at Großgörschenstraße, S2/S25/S26 and U7 at Yorckstraße.
SERVED_BY = {'Yorckstr. (Großgörschenstr.)': {'S1'}, 'Yorckstr.': {'S2', 'S25', 'S26', 'U7'}}
# OSM ends the U6 at Kurt-Schumacher-Platz during the northern closure; the BVG network map still shows it.
SUPPLEMENT = {'U6': [(13.327129, 52.5632274), (13.3126219, 52.5668172), (13.3029254, 52.5710338),
                     (13.2961132, 52.575692), (13.2905918, 52.5818407), (13.2837514, 52.5894565)]}


def distance(a, b):
    dx = (a[0] - b[0]) * 111320 * math.cos(math.radians(52.5))
    dy = (a[1] - b[1]) * 110540
    return math.hypot(dx, dy)


def main(path, platforms_path=None, inventory_path=None, stations_path=None):
    data = json.load(open(path))
    extra_inputs = platforms_path and inventory_path and stations_path
    if extra_inputs:
        add_stations_without_elevators(data, json.load(open(platforms_path)), json.load(open(inventory_path)), json.load(open(stations_path)))
    nodes = {e['id']: (e['lon'], e['lat']) for e in data['elements'] if e['type'] == 'node'}
    ways = {e['id']: e['nodes'] for e in data['elements'] if e['type'] == 'way'}

    def position(member):
        if member['type'] == 'node':
            return nodes.get(member['ref'])
        points = [nodes[n] for n in ways.get(member['ref'], []) if n in nodes]
        if points:
            return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
        return None

    def station_for(point, mode, ref):
        candidates = [s for s in CATALOG if s['coordinates'] and mode in s['modes'] and ref in SERVED_BY.get(s['name'], {ref})]
        best = min(((distance(point, s['coordinates']), s) for s in candidates), key=lambda x: x[0])
        return best[1] if best[0] <= SNAP_METERS[mode] else None

    def snap(point, mode, ref):
        station = station_for(point, mode, ref)
        if station:
            return tuple(station['coordinates'])
        # Both directions of a line have their own stop positions; merge them.
        for known in extra:
            if distance(known, point) <= 200:
                return known
        extra.append((round(point[0], 5), round(point[1], 5)))
        return extra[-1]

    extra = []

    lines = {}
    sequences = [(r['tags']['ref'], r['tags'].get('colour'), [m for m in r['members'] if m['role'].startswith('stop')] or [m for m in r['members'] if m['role'].startswith('platform')])
                 for r in data['elements'] if r['type'] == 'relation']
    sequences += [(ref, None, [{'type': 'point', 'at': p} for p in points]) for ref, points in SUPPLEMENT.items()]
    for ref, colour, members in sequences:
        mode = 'U-Bahn' if ref.startswith('U') else 'S-Bahn'
        line = lines.setdefault(ref, {'ref': ref, 'mode': mode, 'colour': '#888888', 'segments': set()})
        if colour:
            line['colour'] = colour.upper()
        previous = None
        for point in filter(None, (m['at'] if m['type'] == 'point' else position(m) for m in members)):
            point = snap(point, mode, ref)
            # Stop position and platform of one station collapse into a single point.
            if previous is not None and distance(previous, point) > 150:
                line['segments'].add(tuple(sorted((previous, point))))
            if previous is None or distance(previous, point) > 150:
                previous = point

    # Route variants that skip a stop create shortcut edges; drop A-B when A-C-B exists.
    for line in lines.values():
        neighbours = {}
        for a, b in line['segments']:
            neighbours.setdefault(a, set()).add(b)
            neighbours.setdefault(b, set()).add(a)
        line['segments'] = {(a, b) for a, b in line['segments']
                            if not any(max(distance(a, c), distance(c, b)) < distance(a, b) for c in neighbours[a] & neighbours[b])}

    result = []
    for ref in sorted(lines, key=lambda r: (r[0] != 'U', int(''.join(c for c in r[1:] if c.isdigit())))):
        line = lines[ref]
        if line['segments']:
            result.append({**line, 'segments': [[list(a), list(b)] for a, b in sorted(line['segments'])]})
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, separators=(',', ':')) + '\n')
    for line in result:
        print(f"{line['ref']:>4} {line['colour']} {len(line['segments'])} segments")
    if extra_inputs:
        write_access(data, json.load(open(platforms_path)), json.load(open(inventory_path)), station_for)


def elevator_modes(inventory):
    """Networks each station's elevators serve; an elevator without a hint counts for all."""
    modes = {}
    for station in inventory['docs']:
        elevators = (((station.get('operational_status') or {}).get('elevators') or {}).get('docs') or [])
        for elevator in (e for e in elevators if isinstance(e, dict)):
            text = ' '.join(v for v in (elevator.get('function') or {}).values() if v)
            served = ({'S-Bahn'} if re.search(r'S-Bahn|Gleis|\bS\d', text) else set()) | ({'U-Bahn'} if re.search(r'U-Bahn|\bU\d', text) else set())
            modes.setdefault(str(station['id']), set()).update(served or {'U-Bahn', 'S-Bahn'})
    return modes


def key(name):
    name = re.sub(r'^(S\+U |S |U )', '', name).split(' (')[0]
    name = name.replace('straße', 'str').replace('str.', 'str').replace('ß', 'ss')
    return re.sub(r'[^a-zäöü0-9]', '', name.lower())


def platform_point(platform):
    return (platform['lon'], platform['lat']) if 'lon' in platform else (platform['center']['lon'], platform['center']['lat'])


def add_stations_without_elevators(routes, platforms, inventory, stations):
    CATALOG[:] = [s for s in CATALOG if s.get('source') != 'osm']
    tags = {(e['type'], e['id']): e for e in platforms['elements']}
    served = [platform_point(tags[(m['type'], m['ref'])]) for r in routes['elements'] if r['type'] == 'relation'
              for m in r['members'] if m['role'].startswith('platform') and (m['type'], m['ref']) in tags]
    inventory_names = {key(s['internal_description']) for s in inventory['docs']}
    added = {}
    for node in stations['elements']:
        t = node.get('tags', {})
        mode = {'subway': 'U-Bahn', 'light_rail': 'S-Bahn'}.get(t.get('station'))
        point = (node['lon'], node['lat'])
        if not mode or t.get('wheelchair') != 'no' or key(t['name']) in inventory_names:
            continue
        if not any(distance(point, p) < 350 for p in served):
            continue
        if any(s['coordinates'] and distance(point, s['coordinates']) < 300 and mode in s['modes'] for s in CATALOG):
            continue
        # Stable ids above the operator-report range, so database rows survive rebuilds.
        station = added.setdefault(t['name'], {'id': 800_000_000 + int(hashlib.sha1(t['name'].encode()).hexdigest()[:6], 16), 'name': t['name'],
                                               'modes': [], 'coordinates': [round(point[0], 7), round(point[1], 7)], 'source': 'osm'})
        if mode not in station['modes']:
            station['modes'].append(mode)
    CATALOG.extend(sorted(added.values(), key=lambda s: s['name']))
    print(f'added {len(added)} stations without elevators:', sorted(added))


def write_access(routes, platforms, inventory, station_for):
    tags = {(e['type'], e['id']): e for e in platforms['elements']}
    served = elevator_modes(inventory)
    seen = {}
    for rel in (e for e in routes['elements'] if e['type'] == 'relation'):
        ref = rel['tags']['ref']
        mode = 'U-Bahn' if ref.startswith('U') else 'S-Bahn'
        for member in rel['members']:
            platform = tags.get((member['type'], member['ref']))
            if not member['role'].startswith('platform') or not platform:
                continue
            station = station_for(platform_point(platform), mode, ref)
            if station:
                seen.setdefault(str(station['id']), {}).setdefault(ref, set()).add(platform.get('tags', {}).get('wheelchair'))
    for station in CATALOG:
        sid = str(station['id'])
        lines = seen.get(sid, {})
        missing = [ref for ref in sorted(lines) if ('U-Bahn' if ref.startswith('U') else 'S-Bahn') not in served.get(sid, set())]
        station.pop('no_elevator', None)
        station.pop('step_free', None)
        if missing:
            station['no_elevator'] = missing
            if station.get('source') == 'osm' or all(lines[ref] == {'no'} for ref in missing):
                station['step_free'] = False
    CATALOG_PATH.write_text(json.dumps(CATALOG, ensure_ascii=False))
    print('no elevator:', {s['name']: s['no_elevator'] for s in CATALOG if 'no_elevator' in s})
    unplaced = [s['name'] for s in CATALOG if s.get('source') == 'osm' and 'no_elevator' not in s]
    if unplaced:
        print('warning: added stations without line platforms:', unplaced)

if __name__ == '__main__':
    main(*sys.argv[1:5])
