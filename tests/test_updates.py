import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['APP_ENV'] = 'test'
os.environ['RISK_MODEL_PROVIDER'] = 'disabled'
import io
import json
import re
from datetime import date, datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from backend.main import app
from backend.database import SessionLocal, EmailJob, EmailVerification, User
from backend import mail, hosted_model

HEADERS = {'X-Bloom-Request': '1'}
VALUES = {'Age':25,'SystolicBP':120,'DiastolicBP':80,'FastingGlucose':135.1365,'BodyTempF':98.6,'HeartRate':75}
UNITS = {'Age':'years','SystolicBP':'mmHg','DiastolicBP':'mmHg','FastingGlucose':'mg/dL','BodyTempF':'degF','HeartRate':'bpm'}

def setup(client, email):
    assert client.post('/api/auth/register',headers=HEADERS,json={'name':'Synthetic Test','email':email,'password':'test-password-123'}).status_code == 201
    return client.post('/api/pregnancies',headers=HEADERS,json={'lmp':str(date.today()-timedelta(weeks=20)),'month':5}).json()['id']

def test_month_email_verification_deduplication_and_optout(monkeypatch):
    monkeypatch.setenv('RESEND_API_KEY','synthetic-test-key')
    monkeypatch.setenv('EMAIL_FROM','Bloom <test@example.invalid>')
    monkeypatch.setenv('APP_PUBLIC_URL','https://example.invalid')
    monkeypatch.setenv('CRON_SECRET','synthetic-worker-secret')
    sent=[]
    monkeypatch.setattr(mail,'send_provider',lambda recipient,subject,body,key: sent.append((recipient,subject,body,key)) or 'fake-provider-id')
    with TestClient(app) as client:
        pid=setup(client,'updates@example.invalid')
        route=f'/api/pregnancies/{pid}'
        prefs={'month':5,'email_enabled':True,'remote_assessment_enabled':False}
        assert client.put(route+'/preferences',headers=HEADERS,json=prefs).json()['email']['status']=='accepted'
        assert len(sent)==1 and sent[0][0]=='updates@example.invalid'
        token=re.search(r'email_token=([\w-]+)',sent[0][2]).group(1)
        assert client.post('/api/email/verify',headers=HEADERS,json={'token':token}).status_code==200
        assert len(sent)==2 and 'month 5' in sent[1][2].lower()
        assert sent[1][2].startswith('Hello Synthetic Test,')
        assert 'does not replace' not in sent[1][2]
        assert 'midwife or doctor' in sent[1][2]
        assert client.post('/api/email/verify',headers=HEADERS,json={'token':token}).status_code==400
        assert client.post(route+'/email-guidance',headers=HEADERS).json()['status']=='accepted'
        assert len(sent)==2
        dash=client.get(route+'/dashboard').json()
        assert dash['preferences']['email_verified']
        assert all(g['scope']!='month' or g['month']==5 for g in dash['guidance'])
        prefs['month']=6
        assert client.put(route+'/preferences',headers=HEADERS,json=prefs).status_code==200
        assert len(sent)==3 and 'month 6' in sent[-1][2].lower()
        prefs['email_enabled']=False
        assert client.put(route+'/preferences',headers=HEADERS,json=prefs).status_code==200
        assert client.post(route+'/email-guidance',headers=HEADERS).status_code==409
        assert client.get('/api/jobs/emails').status_code==401
        assert client.get('/api/jobs/emails',headers={'Authorization':'Bearer synthetic-worker-secret'}).status_code==200
        assert len(sent)==3
        jid=dash['emails'][0]['id']
        client.post('/api/auth/logout',headers=HEADERS)
        setup(client,'other-updates@example.invalid')
        assert client.put(route+'/preferences',headers=HEADERS,json=prefs).status_code==404
        assert client.post(f'/api/emails/{jid}/retry',headers=HEADERS).status_code==404

def test_mail_failure_preserves_preferences_and_no_health_before_verification(monkeypatch):
    monkeypatch.setenv('RESEND_API_KEY','synthetic-test-key')
    monkeypatch.setenv('EMAIL_FROM','Bloom <test@example.invalid>')
    monkeypatch.setenv('APP_PUBLIC_URL','https://example.invalid')
    def fail(*args): raise mail.MailFailure('email_provider_http_429')
    monkeypatch.setattr(mail,'send_provider',fail)
    with TestClient(app) as client:
        pid=setup(client,'failed-updates@example.invalid')
        r=client.put(f'/api/pregnancies/{pid}/preferences',headers=HEADERS,json={'month':8,'email_enabled':True})
        assert r.status_code==200 and r.json()['email']['status']=='failed'
        dash=client.get(f'/api/pregnancies/{pid}/dashboard').json()
        assert dash['preferences']['month']==8
        assert [j['kind'] for j in dash['emails']]==['verification']
        with SessionLocal() as db:
            job=db.get(EmailJob,dash['emails'][0]['id'])
            token=re.search(r'email_token=([\w-]+)',job.body).group(1)
            verification=db.get(EmailVerification,job.user_id)
            verification.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            db.commit()
        assert client.post('/api/email/verify',headers=HEADERS,json={'token':token}).status_code==400

def test_external_consent_and_risk_email(monkeypatch):
    monkeypatch.setenv('RISK_MODEL_PROVIDER','huggingface')
    monkeypatch.setenv('RESEND_API_KEY','synthetic-test-key')
    monkeypatch.setenv('EMAIL_FROM','Bloom <test@example.invalid>')
    sent=[]
    monkeypatch.setattr(mail,'send_provider',lambda *args:sent.append(args) or 'fake-risk-id')
    calls=[]
    def model(values):
        calls.append(values)
        return {'category':'high','probabilities':{'low':.1,'mid':.2,'high':.7},'outside_training_range':[]}
    monkeypatch.setattr(hosted_model,'predict',model)
    with TestClient(app) as client:
        pid=setup(client,'risk-updates@example.invalid')
        oid=client.post(f'/api/pregnancies/{pid}/observations',headers=HEADERS,json={'observed_at':datetime.now(timezone.utc).isoformat(),'values':VALUES,'units':UNITS}).json()['id']
        assert client.post(f'/api/observations/{oid}/predict',headers=HEADERS).status_code==409
        assert not calls
        with SessionLocal() as db:
            user=db.scalar(select(User).where(User.email=='risk-updates@example.invalid'))
            db.add(EmailVerification(user_id=user.id,verified_at=datetime.now(timezone.utc)));db.commit()
        assert client.put(f'/api/pregnancies/{pid}/preferences',headers=HEADERS,json={'month':5,'email_enabled':True,'remote_assessment_enabled':True}).status_code==200
        result=client.post(f'/api/observations/{oid}/predict',headers=HEADERS)
        assert result.status_code==200 and result.json()['category']=='high'
        assert len(calls)==1 and len(sent)==2
        assert 'midwife or doctor' in sent[-1][2] and '135.1365' not in sent[-1][2]
        assert 'not a diagnosis' not in sent[-1][2]
        assert sent[-1][2].endswith('discuss your next steps.')
        assert client.post(f'/api/observations/{oid}/predict',headers=HEADERS).status_code==200
        assert len(sent)==2

def test_hosted_contract_units_revision_and_html_ignored(monkeypatch):
    monkeypatch.setenv('RISK_MODEL_PROVIDER','huggingface')
    requests=[]
    revision={'sha':hosted_model.REVISION,'runtime':{'sha':hosted_model.REVISION}}
    outputs=['MID RISK','68.3%',{'confidences':[{'label':'Low Risk','confidence':.2657},{'label':'Mid Risk','confidence':.683},{'label':'High Risk','confidence':.0513}]},'<script>untrusted()</script>']
    def open_fake(request,timeout):
        url=request if isinstance(request,str) else request.full_url
        requests.append(request)
        if '/api/spaces/' in url: return io.BytesIO(json.dumps(revision).encode())
        if not isinstance(request,str) and request.get_method()=='POST': return io.BytesIO(json.dumps({'event_id':'a'*32}).encode())
        return io.BytesIO(('event: complete\ndata: '+json.dumps(outputs)+'\n\n').encode())
    monkeypatch.setattr(hosted_model,'urlopen',open_fake)
    result=hosted_model.predict(VALUES)
    assert result['category']=='mid' and 'script' not in json.dumps(result)
    payload=json.loads(requests[1].data)
    assert payload['data']==pytest.approx([25,120,80,7.5,98.6,75])
    assert len(payload['data'])==6
    revision['sha']='changed'
    with pytest.raises(hosted_model.ModelUnavailable,match='version changed'):hosted_model.predict(VALUES)
    outputs[2]['confidences'][0]['confidence']=float('nan')
    revision['sha']=hosted_model.REVISION
    with pytest.raises(hosted_model.ModelUnavailable):hosted_model.predict(VALUES)
    count=len(requests)
    with pytest.raises(hosted_model.ModelUnavailable,match='does not support'):hosted_model.predict({**VALUES,'FastingGlucose':88})
    assert len(requests)==count

def test_celsius_records_units_and_provider_conversion():
    values={key:value for key,value in VALUES.items() if key!='BodyTempF'}
    values['BodyTempC']=37
    units={key:value for key,value in UNITS.items() if key!='BodyTempF'}
    units['BodyTempC']='degC'
    with TestClient(app) as client:
        pid=setup(client,'celsius@example.invalid')
        route=f'/api/pregnancies/{pid}/observations'
        payload={'observed_at':datetime.now(timezone.utc).isoformat(),'values':values,'units':units}
        assert client.post(route,headers=HEADERS,json=payload).status_code==201
        stored=client.get(f'/api/pregnancies/{pid}/dashboard').json()['observations'][0]['values']
        assert stored['BodyTempC']==37 and 'BodyTempF' not in stored
        assert hosted_model.feature_payload(stored)['BodyTemp']==pytest.approx(98.6)
        bad={**payload,'units':{**units,'BodyTempC':'degF'}}
        assert client.post(route,headers=HEADERS,json=bad).status_code==422

        bad={**payload,'values':{**values,'BodyTempC':98.6}}
        assert client.post(route,headers=HEADERS,json=bad).status_code==422
        bad={**payload,'values':{**values,'BodyTempF':98.6},'units':{**units,'BodyTempF':'degF'}}
        assert client.post(route,headers=HEADERS,json=bad).status_code==422

def test_guidance_email_preserves_urgent_instructions_and_closes_with_visit_advice():
    from backend.guidance_service import email_content
    from backend.notification_messages import VISIT_RECOMMENDATION
    entries=[{'id':1,'month':8,'title':'Baby movements','body':'Contact your maternity team immediately if movements change. Do not wait for an email or an app prediction.\n\nMonth labels are approximate. Follow your care team\'s personalised advice.','source_url':'https://example.invalid/approved-source'}]
    subject,body,identity=email_content(8,entries,'Test Mother')
    assert 'pregnancy month 8' in subject
    assert 'Contact your maternity team immediately if movements change.' in body
    assert 'Do not wait for an email or an app prediction.' in body
    assert 'Month labels are approximate' not in body
    assert body.endswith(VISIT_RECOMMENDATION)
    assert entries[0]['body'].endswith('personalised advice.')
    assert email_content(8,entries,'Another Name')[2]==identity

def test_refresh_only_unattempted_pending_guidance():
    with TestClient(app) as client:
        pid=setup(client,'pending-copy@example.invalid')
        with SessionLocal() as db:
            user=db.scalar(select(User).where(User.email=='pending-copy@example.invalid'))
            job=mail.queue(db,user,pid,'monthly_guidance','Old subject','Old copy','same-guidance')
            db.commit()
            refreshed=mail.queue(db,user,pid,'monthly_guidance','Warm subject','Warm copy','same-guidance')
            assert refreshed.id==job.id and refreshed.body=='Warm copy'
            refreshed.status='failed';refreshed.attempts=1;db.commit()
            retry=mail.queue(db,user,pid,'monthly_guidance','Another subject','Different copy','same-guidance')
            assert retry.id==job.id and retry.body=='Warm copy'
