import asyncio
from copy import deepcopy
import pytest
from app import insights

@pytest.fixture
def ctx():
    return {'snapshot':{'source':'BVG + S-Bahn Berlin','coverage':'reports','fetched_at':'2099-01-01T00:00:00+00:00','stats':{'outages':2,'affected_stations':1,'unknown':1,'operational':0}},'stations':[{'id':788,'name':'Alexanderplatz','outages':2,'unknown':1,'modes':['U-Bahn','S-Bahn'],'elevators':[{'id':5,'status':'outage','description':'Street ↔ U8','operator':'BVG'}]}]}

def test_hallucinated_fact_and_title_rejected(ctx):
    facts=insights.facts_for(ctx)
    with pytest.raises(ValueError):insights.validate_selection({'title':insights.TITLES[0],'fact_ids':['invented']},facts)
    with pytest.raises(ValueError):insights.validate_selection({'title':'Everything works','fact_ids':['network']},facts)

def test_extra_prose_and_duplicates_rejected(ctx):
    facts=insights.facts_for(ctx)
    with pytest.raises(ValueError):insights.validate_selection({'title':insights.TITLES[0],'fact_ids':['network'],'answer':'All elevators repaired'},facts)
    with pytest.raises(ValueError):insights.validate_selection({'title':insights.TITLES[0],'fact_ids':['network','network']},facts)

def test_cache_invalidates_on_status_change(ctx):
    changed=deepcopy(ctx);changed['stations'][0]['outages']=1
    assert insights.fingerprint(ctx)!=insights.fingerprint(changed)

def test_render_mandatory_coverage(ctx):
    facts=insights.facts_for(ctx)
    result=insights.render({'title':insights.TITLES[0],'fact_ids':['s788']},facts,ctx,'ollama')
    assert result['sources']==[{'id':788,'name':'Alexanderplatz'}]
    assert any('not a full inventory' in s for s in result['sentences'])
    assert any('2 elevator disruption reports' in s for s in result['sentences'])

def test_station_retrieval_and_no_route_prediction(ctx,monkeypatch):
    monkeypatch.setattr(insights,'context',lambda:ctx)
    result=asyncio.run(insights.answer_question('Is Alexanderplatz accessible?'))
    assert result['sources'][0]['id']==788
    assert any('do not establish a step-free route' in s for s in result['sentences'])
    result=asyncio.run(insights.answer_question('When will elevators be repaired tomorrow?'))
    assert any('cannot predict repair times' in s for s in result['sentences'])

def test_unknown_station_is_not_claimed_healthy(ctx,monkeypatch):
    monkeypatch.setattr(insights,'context',lambda:ctx)
    result=asyncio.run(insights.answer_question('What is the status at Hogwarts?'))
    assert result['sources']==[]
    assert 'could not match' in result['sentences'][0]

def test_failed_inference_falls_back_to_records(ctx,monkeypatch):
    monkeypatch.setattr(insights,'context',lambda:ctx)
    monkeypatch.setenv('LIVE_AI','true')
    async def fail(*args):raise RuntimeError('Offline')
    monkeypatch.setattr(insights,'select_with_ollama',fail)
    result=asyncio.run(insights.answer_question('What is the status at Alexanderplatz?'))
    assert result['mode']=='database'
    assert result['sources'][0]['id']==788

def test_german_rendering_shares_cache_fingerprint(ctx,monkeypatch):
    facts_de=insights.facts_for(ctx,'de')
    assert facts_de[0]['text'].startswith('2 Aufzugsstörungsmeldungen an 1 Stationen')
    assert [f['id'] for f in facts_de]==[f['id'] for f in insights.facts_for(ctx,'en')]
    result=insights.render({'title':insights.TITLES[1],'fact_ids':['s788']},facts_de,ctx,'ollama',lang='de')
    assert result['title']=='Störungen, die du prüfen solltest.'
    assert any('kein vollständiges Inventar' in s for s in result['sentences'])

def test_german_questions_route_like_english(ctx,monkeypatch):
    monkeypatch.setattr(insights,'context',lambda:ctx)
    result=asyncio.run(insights.answer_question('Wie ist der Status am Alexanderplatz?','de'))
    assert result['sources'][0]['id']==788 and any('stufenfreie Route' in s for s in result['sentences'])
    result=asyncio.run(insights.answer_question('Wie viele Aufzüge sind in Betrieb?','de'))
    assert result['sentences'][0].startswith('2 Aufzugsstörungsmeldungen')
    result=asyncio.run(insights.answer_question('Wann wird der Aufzug repariert?','de'))
    assert 'keine Reparaturzeiten' in result['sentences'][0]
    monkeypatch.setattr(insights,'cached_briefing',lambda c,lang:{'lang':lang})
    assert asyncio.run(insights.answer_question('Welche Stationen haben Aufzugsstörungen?','de'))=={'lang':'de'}

def test_platform_without_elevator_is_always_stated(ctx,monkeypatch):
    ctx['stations'].append({'id':462,'name':'Yorckstr.','outages':0,'unknown':0,'modes':['S-Bahn','U-Bahn'],'elevators':[],'no_elevator':['S2','S25','S26'],'step_free':False})
    monkeypatch.setattr(insights,'context',lambda:ctx)
    result=asyncio.run(insights.answer_question('What is the status at Yorckstraße?'))
    assert any('no elevator to the S2, S25, S26 platforms' in s for s in result['sentences'])
    result=asyncio.run(insights.answer_question('Wie ist der Status an der Yorckstraße?','de'))
    assert any('Linien S2, S25, S26 gibt es keinen Aufzug' in s for s in result['sentences'])
    # A live model selection must not drop the fact.
    monkeypatch.setenv('LIVE_AI','true')
    async def pick(facts,question):return {'title':insights.TITLES[0],'fact_ids':['coverage']}
    monkeypatch.setattr(insights,'select_with_ollama',pick)
    result=asyncio.run(insights.answer_question('What is the status at Yorckstraße?'))
    assert any('no elevator' in s for s in result['sentences'])


def test_station_without_any_elevator(ctx,monkeypatch):
    ctx['stations'].append({'id':800000001,'name':'Nöldnerplatz','outages':0,'unknown':0,'modes':['S-Bahn'],'elevators':[],'no_elevator':['S5','S7','S75'],'step_free':False,'source':'osm'})
    ctx['stations'].append({'id':1013,'name':'Karl-Bonhoeffer-Nervenklinik','outages':0,'unknown':0,'modes':['U-Bahn','S-Bahn'],'elevators':[],'no_elevator':['S25']})
    monkeypatch.setattr(insights,'context',lambda:ctx)
    result=asyncio.run(insights.answer_question('Is there an elevator at Nöldnerplatz?'))
    assert result['sentences'][0]=='Nöldnerplatz: there is no elevator to the S5, S7, S75 platforms, so they are not step-free.'
    assert not any('Availability is unconfirmed' in s for s in result['sentences'])
    result=asyncio.run(insights.answer_question('What about Karl-Bonhoeffer-Nervenklinik?'))
    assert 'Karl-Bonhoeffer-Nervenklinik: there is no elevator to the S25 platform.' in result['sentences']
