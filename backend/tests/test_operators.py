from app.operators import parse_sb_html,merge_reports
import pytest

def test_escalators_excluded_and_unknown_not_outage():
    html='''<div class="tx-sbb-mobility"><div class="c-accordion__tab"><h3 class="c-accordion__title">S+U Alexanderplatz</h3><li class="c-stations-equipment-icon-list__item"><span data-tooltip="Rolltreppe"></span><span data-equip-col="description">Escalator</span><span data-equip-col="announcement">Außer Betrieb</span></li><li class="c-stations-equipment-icon-list__item"><span data-tooltip="Aufzug"></span><span data-equip-col="description">Lift</span><span data-equip-col="announcement">Aktuell liegen keine Information vor</span></li></div></div>'''
    reports=parse_sb_html(html)
    assert len(reports)==1 and reports[0]['status']=='unknown'
    stations=merge_reports([],reports)
    alex=next(s for s in stations if s['name']=='Alexanderplatz')
    assert alex['unknown']==1 and alex['outages']==0
    assert not any(e['status']=='operational' for s in stations for e in s['elevators'])

def test_changed_source_structure_is_rejected():
    with pytest.raises(ValueError):parse_sb_html('<html>Unavailable</html>')

def test_scheduled_bvg_report_excluded():
    stations=merge_reports([{'messageType':'ELEVATOR','scheduled':True}],[])
    assert all(s['outages']==0 for s in stations)
