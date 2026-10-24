"""BrokenLifts' public website JSON endpoints. Fail closed on incomplete pagination."""
import asyncio
import re
from datetime import timedelta
import httpx
from sqlalchemy import select, delete
from .db import Station, Elevator, Observation, Snapshot, Session, now

SOURCE = 'https://brokenlifts.org'
MODES = {1: 'S-Bahn', 2: 'U-Bahn', 3: 'Regional'}


def normalize(raw):
    result = []
    seen = set()
    for s in raw:
        if s['id'] in seen:
            raise ValueError('Duplicate station in source pagination')
        seen.add(s['id'])
        elevator_page = s['operational_status']['elevators']
        if elevator_page.get('hasNextPage'):
            raise ValueError('Truncated station elevator list')
        elevators = []
        for e in elevator_page['docs']:
            if e is None or e.get('deletedAt'):
                continue
            status = e['operational_status']['operational_status']
            status = {'in_service': 'operational', 'out_of_service': 'outage'}.get(status, 'unknown')
            xy = e.get('location', {}).get('centroid')
            if not isinstance(xy, list) or len(xy) != 2 or not all(isinstance(n, (float, int)) for n in xy) or not (12 < xy[0] < 15 and 51 < xy[1] < 54):
                xy = None
            original = e.get('linked_data', {}).get('original_data', {}) or {}
            elevators.append({'id': e['id'], 'status': status, 'description': e.get('function', {}).get('short_visual') or 'Elevator', 'coordinates': xy, 'operator': 'BVG' if e.get('linked_data', {}).get('operator_org') == 3 else 'DB / other', 'source_imported_at': original.get('importedAt') or original.get('imported_at')})
        coords = [e['coordinates'] for e in elevators if e['coordinates']]
        name = re.sub(r'^(S\+U |S |U )', '', s['internal_description'])
        name = re.sub(r'\s*(Bhf)?\s*\(Berlin\)$', '', name).strip()
        result.append({'id': s['id'], 'name': name, 'identifier': s.get('main_identifier'), 'modes': [MODES.get(m['id'], 'Other') for m in s.get('modes', {}).get('servicedTransportModes', [])], 'coordinates': [sum(c[i] for c in coords)/len(coords) for i in range(2)] if coords else None, 'elevators': elevators, 'outages': sum(e['status'] == 'outage' for e in elevators), 'unresolved_elevators': sum(e is None for e in elevator_page['docs']), 'unknown': sum(e['status'] == 'unknown' for e in elevators) + sum(e is None for e in elevator_page['docs'])})
    if not result or not any(s['elevators'] for s in result):
        raise ValueError('Empty source response')
    return result


async def fetch_stations():
    async with httpx.AsyncClient(timeout=35, follow_redirects=True, headers={'User-Agent': 'LIFT-AI/1.0 (Berlin accessibility portfolio; 15-minute refresh)'}) as client:
        records, page, expected, timestamps = [], 1, None, []
        while page <= 100:
            response = await client.get(f'{SOURCE}/api/station/list', params={'page': page})
            response.raise_for_status()
            data = response.json()
            if data['page'] != page:
                raise ValueError('Unexpected source page')
            expected = data['totalDocs'] if expected is None else expected
            if data['totalDocs'] != expected:
                raise ValueError('Source pagination changed during fetch')
            records.extend(data['docs'])
            if data.get('lastUpdated'):
                timestamps.append(data['lastUpdated'])
            if not data['hasNextPage']:
                break
            page += 1
            await asyncio.sleep(.15)
        if len(records) != expected:
            raise ValueError('Incomplete source response')
        return normalize(records), min(timestamps) if timestamps else None


def save_snapshot(stations, source_updated_at, metadata=None):
    stamp = now()
    flat = [e for s in stations for e in s['elevators']]
    if len({e['id'] for e in flat}) != len(flat):
        raise ValueError('Duplicate elevators')
    with Session.begin() as db:
        previous = {e.id: e.status for e in db.scalars(select(Elevator))}
        for station in stations:
            db.merge(Station(id=station['id'], data=station))
        db.flush()
        for station in stations:
            for elevator in station['elevators']:
                db.merge(Elevator(id=elevator['id'], station_id=station['id'], status=elevator['status'], data=elevator))
                if previous.get(elevator['id']) != elevator['status']:
                    db.add(Observation(elevator_id=elevator['id'], status=elevator['status'], observed_at=stamp))
        db.execute(delete(Elevator).where(Elevator.id.not_in([e['id'] for e in flat])))
        db.execute(delete(Station).where(Station.id.not_in([s['id'] for s in stations])))
        for removed_id in previous.keys() - {e['id'] for e in flat}:
            db.add(Observation(elevator_id=removed_id, status='not_reported', observed_at=stamp))
        stats = {'elevators': len(flat), 'outages': sum(e['status'] == 'outage' for e in flat), 'unknown': sum(e['status'] == 'unknown' for e in flat), 'unresolved_elevators': sum(s['unresolved_elevators'] for s in stations), 'operational': sum(e['status'] == 'operational' for e in flat), 'stations': len(stations), 'affected_stations': sum(s['outages'] > 0 for s in stations)}
        data = {'stats': stats, 'source_updated_at': source_updated_at, 'source': 'BrokenLifts', 'source_url': SOURCE, 'fetched_at': stamp.isoformat()}
        data.update(metadata or {'coverage': 'inventory'})
        db.add(Snapshot(observed_at=stamp, data=data))
        db.execute(delete(Snapshot).where(Snapshot.observed_at < stamp - timedelta(days=30)))
        db.execute(delete(Observation).where(Observation.observed_at < stamp - timedelta(days=90)))
    return data
