from copy import deepcopy
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app import source
from app.db import Base, Station, Snapshot, Observation

@pytest.fixture
def raw():
    return [{'id':1,'internal_description':'U Testplatz (Berlin)','operational_status':{'elevators':{'hasNextPage':False,'docs':[{'id':100,'operational_status':{'operational_status':'out_of_service'},'location':{'centroid':[13.4,52.52]},'function':{'short_visual':'Street ↔ platform'},'linked_data':{'operator_org':3}}]}},'modes':{'servicedTransportModes':[{'id':2}]}}]

@pytest.fixture
def db(tmp_path,monkeypatch):
    engine=create_engine(f'sqlite:///{tmp_path}/test.db')
    Base.metadata.create_all(engine)
    sessions=sessionmaker(engine,expire_on_commit=False)
    monkeypatch.setattr(source,'Session',sessions)
    return sessions

def test_unknown_is_not_operational(raw):
    raw[0]['operational_status']['elevators']['docs'][0]['operational_status']['operational_status']='unrecognized_status'
    station=source.normalize(raw)[0]
    assert station['unknown']==1
    assert station['outages']==0
    assert station['elevators'][0]['status']=='unknown'

def test_unresolved_refs_are_explicit(raw):
    raw[0]['operational_status']['elevators']['docs'].append(None)
    station=source.normalize(raw)[0]
    assert station['unknown']==1 and station['unresolved_elevators']==1
    assert len(station['elevators'])==1

def test_truncated_and_duplicate_data_rejected(raw):
    with pytest.raises(ValueError):source.normalize(raw*2)
    raw[0]['operational_status']['elevators']['hasNextPage']=True
    with pytest.raises(ValueError):source.normalize(raw)

def test_no_invented_coordinates(raw):
    raw[0]['operational_status']['elevators']['docs'][0]['location']['centroid']=[0,0]
    assert source.normalize(raw)[0]['coordinates'] is None

def test_history_only_records_changes(raw,db):
    stations=source.normalize(raw)
    source.save_snapshot(stations,None)
    source.save_snapshot(stations,None)
    raw[0]['operational_status']['elevators']['docs'][0]['operational_status']['operational_status']='in_service'
    source.save_snapshot(source.normalize(raw),None)
    with db() as session:
        assert len(list(session.scalars(select(Snapshot))))==3
        assert [o.status for o in session.scalars(select(Observation))]==['outage','operational']

def test_duplicate_elevators_keep_previous_snapshot(raw,db):
    stations=source.normalize(raw)
    source.save_snapshot(stations,None)
    bad=deepcopy(stations)
    bad[0]['elevators']*=2
    with pytest.raises(ValueError):source.save_snapshot(bad,None)
    with db() as session:
        assert len(list(session.scalars(select(Snapshot))))==1
        assert session.get(Station,1).data['outages']==1

def test_unknowns_and_totals_reconcile(raw,db):
    raw[0]['operational_status']['elevators']['docs'].append(None)
    stats=source.save_snapshot(source.normalize(raw),None)['stats']
    assert stats['elevators']==stats['operational']+stats['outages']+stats['unknown']
    assert stats['unresolved_elevators']==1

def test_report_removal_is_not_a_repair(raw,db):
    stations=source.normalize(raw)
    source.save_snapshot(stations,None)
    stations[0]['elevators']=[]
    stations[0]['outages']=0
    source.save_snapshot(stations,None)
    with db() as session:
        assert [o.status for o in session.scalars(select(Observation))]==['outage','not_reported']



def test_new_outages_within_two_hours(tmp_path):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import create_engine
    from app import db, main
    engine = create_engine(f'sqlite:///{tmp_path}/t.db')
    db.Base.metadata.create_all(engine)
    db.Session.configure(bind=engine)
    now = datetime.now(timezone.utc)
    with db.Session.begin() as s:
        s.add(db.Observation(elevator_id=1, status='outage', observed_at=now - timedelta(hours=5)))   # present at monitoring start
        s.add(db.Observation(elevator_id=2, status='outage', observed_at=now - timedelta(minutes=30)))  # new
        s.add(db.Observation(elevator_id=3, status='outage', observed_at=now - timedelta(hours=3)))   # older than 2 h
    data = {'stats': {}, 'stations': [{'elevators': [{'id': i, 'status': 'outage'} for i in (1, 2, 3)] + [{'id': 4, 'status': 'unknown'}]}]}
    with db.Session() as s:
        main.mark_new_outages(s, data)
    assert [e.get('new') for e in data['stations'][0]['elevators']] == [False, True, False, None]
    assert data['stations'][0]['new_outages'] == 1 and data['stats']['new_outages'] == 1
