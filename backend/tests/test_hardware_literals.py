import pytest
from fastapi.testclient import TestClient
from tenderready.api import create_app
from test_documents import config, workspace
from test_verification import transcribe, send_pdf, pdf

@pytest.mark.parametrize('clause,evidence,status',[
 ('LED Backlit Display: Below 16 inch;','Screen size: 16 inch\nDisplay backlight: LED','conflicting'),
 ('LED Backlit Display: Below 16 inch;','Screen size: 15.6 inch\nDisplay backlight: LED','supported'),
 ('LED Backlit Display: 11 inch or above','Screen size: 12 inch','inconclusive'),
 ('Tablet Screen Size: 8.9 inch or above;','Screen size: 9 cm','inconclusive'),
 ('Tablet Screen Size: 8.9 inch or above;','Screen size: 8.9 inch','supported'),
 ('Processor: 64 bit 2.3 GHz or above;', 'CPU architecture: 64 bit\nCPU speed: 2.5 GHz', 'supported'),
 ('Processor: 64 bit 2.3 GHz or above;', 'CPU architecture: 64 bit\nCPU speed: 2.0 GHz', 'conflicting'),
 ('Processor: 64 bit 2.3 GHz or above;', 'CPU architecture: 32 bit\nCPU speed: 2.5 GHz', 'conflicting'),
 ('Processor: 64 bit 2.3 GHz or above;', 'CPU speed: 2.5 GHz', 'inconclusive'),
 ('Processor: 64 bit 2.3 GHz or above;', 'CPU architecture: 64 bit\nCPU speed: 2500 MHz', 'inconclusive'),
 ('Port:- USB','USB: Present','supported'),
 ('Port:- USB','USB: Unsupported','inconclusive'),
 ('Operating System: Mac OS','Operating System: Mac OS','supported'),
 ('Operating System: Mac OS','Operating System: Windows','conflicting'),
 ('Bluetooth and Wifi:-Inbuilt','Bluetooth: Inbuilt\nWifi: Inbuilt','supported'),
 ('Bluetooth and Wifi:-Inbuilt','Bluetooth: Inbuilt','inconclusive'),
 ('Integrated HD Webcam & Speaker','Webcam: Integrated HD\nSpeaker: Integrated','supported'),
 ('Integrated HD Webcam & Speaker','Webcam: Integrated HD','inconclusive'),
 ('OS Android: Lollipop 5.1.1 or latest','Operating System: Android','inconclusive'),
])
def test_literal_hardware_checks(database,tmp_path,clause,evidence,status):
 engine,_=database
 with TestClient(create_app(config(tmp_path),engine),base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as c:
  wid=workspace(c);req,_=transcribe(c,wid,'Model: Atlas A14\n'+clause)
  send_pdf(c,wid,pdf('Model: Atlas A14\n'+evidence),'datasheet')
  r=c.post(f'/workspaces/{wid}/requirements/{req["id"]}/verify',json={})
  assert r.status_code==201,r.text
  assert r.json()['status']==status
  assert not r.json()['reviews']
  assert all(s['page']==1 for check in r.json()['checks'] for s in check.get('sources',[]))


@pytest.mark.parametrize('evidence,status', [
 ('HDMI: Present\nVGA: Present\nEthernet: RJ-45\nUSB 2.0 ports: 2\nUSB 3.0 ports: 2', 'supported'),
 ('HDMI: Present\nVGA: Present\nEthernet: RJ-45\nUSB 2.0 ports: 4\nUSB 3.0 ports: 0', 'conflicting'),
 ('HDMI: Present\nVGA: Present\nEthernet: RJ-45\nUSB 2.0 ports: 2', 'inconclusive'),
 ('HDMI: Unsupported\nVGA: Present\nEthernet: RJ-45\nUSB 2.0 ports: 2\nUSB 3.0 ports: 2', 'inconclusive'),
 ('HDMI: Present\nVGA: Present\nEthernet: wireless\nUSB 2.0 ports: 2\nUSB 3.0 ports: 2', 'conflicting'),
])
def test_port_versions_are_not_combined(database,tmp_path,evidence,status):
 test_literal_hardware_checks(database,tmp_path,
  'Port:- HDMI, VGA ,RJ-45 Ethernet, USB (2*3.0 & 2*2.0)',evidence,status)


@pytest.mark.parametrize('speed,status', [('1.6 GHz','inconclusive'),('2.4 GHz','inconclusive'),('1.0 GHz','conflicting')])
def test_compound_processor_speed_never_proves_family_or_core_support(database,tmp_path,speed,status):
 engine,_=database
 with TestClient(create_app(config(tmp_path),engine),base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as c:
  wid=workspace(c)
  req,_=transcribe(c,wid,'Model: Atlas A14\nProcessor: 1.6 GHz dual-core Intel Core i5 or above')
  send_pdf(c,wid,pdf('Model: Atlas A14\nCPU speed: '+speed),'datasheet')
  b=f'/workspaces/{wid}/requirements/{req["id"]}'
  plan=c.get(b+'/verification').json()['check_plan']
  assert plan['coverage']=='complete' and plan['auto_coverage_eligible']
  assert any(x['field']=='cpu_ghz' and x['expected']=='1.6' for x in plan['criteria'])
  r=c.post(b+'/verify',json={})
  assert r.status_code==201 and r.json()['status']==status
  assert not r.json()['reviews']


@pytest.mark.parametrize('cores,outcome', [('1 core','conflict'),('2 cores','pass'),('4 threads','inconclusive'),('2.5 cores','inconclusive')])
def test_compound_cpu_checks_physical_cores_not_threads(database,tmp_path,cores,outcome):
 engine,_=database
 with TestClient(create_app(config(tmp_path),engine),base_url='http://127.0.0.1:8000',client=('127.0.0.1',1)) as c:
  wid=workspace(c)
  req,_=transcribe(c,wid,'Model: Atlas A14\nProcessor: 1.6 GHz dual-core Intel Core i5 or above')
  send_pdf(c,wid,pdf('Model: Atlas A14\nCPU speed: 1.6 GHz\nCPU cores: '+cores),'datasheet')
  r=c.post(f'/workspaces/{wid}/requirements/{req["id"]}/verify',json={}).json()
  checks=[x for x in r['checks'] if x.get('field')=='cpu_cores']
  assert checks
  if outcome in {'pass','conflict'}: assert any(x['outcome']==outcome for x in checks)
  else: assert not any(x['outcome']=='pass' for x in checks)
  assert r['status']!='supported' and not r['reviews']


@pytest.mark.parametrize('clause,facts,status', [
 ('Processor: 5th Generation Intel Core i5 or above;', 'Processor: 5th Generation Intel Core i5', 'supported'),
 ('Processor: 5th Generation Intel Core i5 or above;', 'Processor: 12th Generation Intel Core i7', 'inconclusive'),
 ('Processor: 1.6 GHz dual-core Intel Core i5 or above', 'CPU speed: 1.6 GHz\nCPU cores: 2\nCPU family: Intel Core i5', 'supported'),
 ('Graphics: Intel HD 6000 or above', 'Graphics: Intel HD 6000', 'supported'),
 ('Graphics: Intel HD 6000 or above', 'Graphics: Intel HD 7000', 'inconclusive'),
 ('Graphics: Intel HD 4400 or above/Discrete Graphics', 'Graphics: Discrete Graphics', 'supported'),
])
def test_source_baselines_do_not_invent_hardware_rankings(database,tmp_path,clause,facts,status):
 test_literal_hardware_checks(database,tmp_path,clause,facts,status)
