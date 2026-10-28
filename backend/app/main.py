import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import select, text, func
from .db import Base, engine, Session, Station, Snapshot, Observation
from .source import save_snapshot
from .operators import fetch_network
from .insights import generate_briefing, cached_briefing, answer_question, Question

log = logging.getLogger('uvicorn.error')
last_error = None

sync_lock = asyncio.Lock()
last_sync = 0.0
MIN_MANUAL_INTERVAL = 30

async def sync_once():
    global last_error, last_sync
    async with sync_lock:
        try:
            stations, updated, metadata = await fetch_network()
            await asyncio.to_thread(save_snapshot, stations, updated, metadata)
            last_error = None
            log.info('Synced %d stations from %s', len(stations), metadata['source'])
            await generate_briefing()
        except Exception as exc:
            last_error = 'Source refresh failed; retaining last successful snapshot.'
            log.warning('Source sync failed: %s', exc)
        last_sync = time.monotonic()

async def sync_loop():
    while True:
        await sync_once()
        await asyncio.sleep(900 if last_error is None else 120)

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    task = asyncio.create_task(sync_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(title='LIFT//AI', version='1.0.0', lifespan=lifespan, docs_url='/api/docs', openapi_url='/api/openapi.json')

@app.get('/api/health')
def health():
    with Session() as db:
        db.execute(text('SELECT 1'))
    return {'status': 'ok'}

NEW_WINDOW = timedelta(hours=2)

def mark_new_outages(db, data):
    """Flag outages whose latest change to "outage" happened within NEW_WINDOW.

    Outages already present when monitoring began have an unknown start, so they are never "new".
    """
    started = db.scalar(select(func.min(Observation.observed_at)))
    ids = [e['id'] for s in data['stations'] for e in s['elevators'] if e['status'] == 'outage']
    since = dict(db.execute(select(Observation.elevator_id, func.max(Observation.observed_at)).where(Observation.elevator_id.in_(ids), Observation.status == 'outage').group_by(Observation.elevator_id)).all()) if ids else {}
    utc = lambda t: t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - NEW_WINDOW
    for station in data['stations']:
        station['new_outages'] = 0
        for e in station['elevators']:
            if e['status'] != 'outage' or e['id'] not in since:
                continue
            e['since'] = utc(since[e['id']]).isoformat()
            e['new'] = utc(since[e['id']]) > cutoff and started is not None and utc(since[e['id']]) > utc(started) + timedelta(minutes=5)
            station['new_outages'] += e['new']
    data['stats'] = {**data['stats'], 'new_outages': sum(s['new_outages'] for s in data['stations'])}

@app.get('/api/dashboard')
def dashboard():
    with Session() as db:
        snapshot = db.scalar(select(Snapshot).order_by(Snapshot.id.desc()))
        if not snapshot:
            raise HTTPException(503, 'Waiting for first complete source sync. Please retry shortly.')
        data = dict(snapshot.data)
        stamp = datetime.fromisoformat(data['fetched_at'])
        data['stale'] = datetime.now(timezone.utc) - stamp > timedelta(minutes=30)
        data['refresh_error'] = last_error
        data['stations'] = sorted([s.data for s in db.scalars(select(Station))], key=lambda s: (-s['outages'], s['name']))
        mark_new_outages(db, data)
        history = list(db.scalars(select(Snapshot).where(Snapshot.observed_at > datetime.now(timezone.utc) - timedelta(hours=24)).order_by(Snapshot.id)))
        data['history'] = [{'at': s.data['fetched_at'], 'outages': s.data['stats']['outages']} for s in history]
        return data

@app.post('/api/refresh')
async def refresh():
    if not sync_lock.locked() and time.monotonic() - last_sync > MIN_MANUAL_INTERVAL:
        await sync_once()
    return {'refreshed': last_error is None}

@app.get('/api/stations/{station_id}/history')
def station_history(station_id: int):
    with Session() as db:
        station = db.get(Station, station_id)
        if not station:
            raise HTTPException(404, 'Station not found')
        ids = [e['id'] for e in station.data['elevators']]
        rows = db.scalars(select(Observation).where(Observation.elevator_id.in_(ids)).order_by(Observation.observed_at.desc()).limit(40))
        return [{'elevator_id': r.elevator_id, 'status': r.status, 'observed_at': r.observed_at.isoformat()} for r in rows]

@app.get('/api/briefing')
def briefing(lang: str = Query('en', pattern='^(en|de)$')):
    result=cached_briefing(lang=lang)
    if result is None:raise HTTPException(503,'Waiting for a complete source snapshot')
    return result

@app.post('/api/copilot')
async def copilot(request: Question):
    if not request.question.strip():raise HTTPException(422,'Question must not be blank')
    result=await answer_question(request.question.strip(),request.lang)
    if result is None:raise HTTPException(503,'Waiting for a complete source snapshot')
    return result
