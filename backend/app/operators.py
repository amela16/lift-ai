"""Live primary-source outage reports; no availability inferred from absence.

The bootstrap catalog contains station metadata only, never cached elevator statuses.
"""
import os
import re
import json
import hashlib
import unicodedata
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
import httpx
from bs4 import BeautifulSoup
from .source import fetch_stations

BVG = 'https://www.bvg.de/disruption-reports-service/disruptions/v1/de'
SBAHN = 'https://sbahn.berlin/fahren/bahnhofsuebersicht/barrierefrei-unterwegs/aufzugs-fahrtreppenstoerung/'
CATALOG = json.loads(Path(__file__).with_name('catalog.json').read_text())

def name_key(name):
    name = re.sub(r'^(S\+U |S |U |Berlin )', '', name)
    name = name.replace('Hbf', 'Hauptbahnhof').replace('Bahnhof', '').replace('Bhf', '')
    name = name.replace('(Berlin)', '').replace('straße', 'str').replace('str.', 'str').replace('ß','ss')
    return ''.join(c for c in unicodedata.normalize('NFKD', name.lower()) if c.isalnum())

def report_id(namespace, text):
    return int(hashlib.sha256(f'{namespace}:{text}'.encode()).hexdigest()[:7], 16)

def parse_sb_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    container = soup.select_one('.tx-sbb-mobility')
    if container is None:
        raise ValueError('S-Bahn page structure changed')
    result = []
    for tab in container.select('.c-accordion__tab'):
        heading = tab.select_one('.c-accordion__title')
        if heading is None:
            raise ValueError('Station title missing from S-Bahn report')
        name = heading.get_text(' ', strip=True)
        for item in tab.select('.c-stations-equipment-icon-list__item'):
            if item.select_one('[data-tooltip="Aufzug"]') is None:
                continue  # Never mix escalators into elevator counts.
            desc, state = item.select_one('[data-equip-col="description"]'), item.select_one('[data-equip-col="announcement"]')
            if desc is None or state is None:
                raise ValueError('Malformed S-Bahn elevator report')
            description, announcement = desc.get_text(' ', strip=True), state.get_text(' ', strip=True)
            result.append({'station':name, 'id':report_id('sbahn',name+description), 'status':'outage' if 'Außer Betrieb' in announcement else 'unknown', 'description':description, 'announcement':announcement, 'operator':'S-Bahn / DB', 'source_url':SBAHN, 'source_imported_at':None})
    # An empty page is valid only if its structure explicitly says no disruptions.
    if not container.select('.c-accordion__tab') and not re.search(r'keine.*(Störung|stoerung)',container.get_text(),re.I):
        raise ValueError('S-Bahn feed contains no recognizable records')
    return result

def merge_reports(bvg_reports, sb_reports):
    stations = deepcopy(CATALOG)
    by_name = {name_key(s['name']):s for s in stations}
    by_hafas = {s['identifier'].split(':')[-1]:s for s in stations if s.get('identifier')}
    for s in stations:
        s.update(elevators=[],outages=0,unknown=0,unresolved_elevators=0)
    records=[]
    for r in bvg_reports:
        if r.get('messageType')!='ELEVATOR' or r.get('scheduled'):
            continue
        # Do not display future or expired disruptions as currently active.
        current=datetime.now(timezone.utc)
        if r.get('startDate') and datetime.fromisoformat(r['startDate'])>current:
            continue
        if r.get('endDate') and datetime.fromisoformat(r['endDate'])<current:
            continue
        name=r['stationOne']['displayName']
        description=' '.join(BeautifulSoup(c.get('content',''), 'html.parser').get_text(' ',strip=True) for c in r['content'])
        records.append({'station':name,'hafas':r.get('bahnhofHafasId'),'id':report_id('bvg',r['id']),'status':'outage','description':description,'operator':'BVG','source_url':'https://www.bvg.de/de/verbindungen/stoerungsmeldungen?type=elevator','source_imported_at':r.get('modDate')})
    records.extend(sb_reports)
    seen=set()
    for r in records:
        if r['id'] in seen:
            raise ValueError('Duplicate operator report')
        seen.add(r['id'])
        station=by_hafas.get(r.get('hafas')) or by_name.get(name_key(r['station']))
        if station is None:
            station={'id':report_id('station',r['station'])+500000000,'name':re.sub(r'^(S\+U |S |U )','',r['station']),'modes':['U-Bahn' if r['operator']=='BVG' else 'S-Bahn'],'coordinates':None,'elevators':[],'outages':0,'unknown':0,'unresolved_elevators':0}
            stations.append(station);by_name[name_key(r['station'])]=station
        station['elevators'].append({**{k:v for k,v in r.items() if k not in ['station','hafas']},'coordinates':None,'record_type':'report'})
        station['outages']+=r['status']=='outage'
        station['unknown']+=r['status']=='unknown'
    return stations

async def fetch_operator_reports():
    async with httpx.AsyncClient(timeout=35,follow_redirects=True,headers={'User-Agent':'LIFT-AI/1.0 accessibility observatory'}) as client:
        reports=[]
        expected=None
        for page in range(1,101):
            response=await client.get(BVG,params={'type':'ELEVATOR','page':page})
            response.raise_for_status();body=response.json()
            if body['page']!=page:
                raise ValueError('BVG returned wrong page')
            expected=body['numFound'] if expected is None else expected
            if body['numFound']!=expected:
                raise ValueError('BVG pagination changed')
            reports.extend(body['elements'])
            if page>=body['numPages']:break
        if len(reports)!=expected:raise ValueError('Incomplete BVG report list')
        response=await client.get(SBAHN);response.raise_for_status()
        sb_reports=parse_sb_html(response.text)
        return merge_reports(reports,sb_reports), None, {'source':'BVG + S-Bahn Berlin','source_url':SBAHN,'coverage':'reports','coverage_note':'Live disruption reports, not a complete elevator inventory. No report does not confirm an operational elevator. Station locations use a BrokenLifts catalog captured on 24 October 2026.','catalog_date':'2026-10-24','sources':[{'name':'BVG','url':BVG},{'name':'S-Bahn Berlin','url':SBAHN}]}

async def fetch_network():
    if os.getenv('SOURCE_MODE','operators')=='brokenlifts':
        stations,updated=await fetch_stations()
        return stations,updated,{'source':'BrokenLifts','source_url':'https://brokenlifts.org','coverage':'inventory'}
    return await fetch_operator_reports()
