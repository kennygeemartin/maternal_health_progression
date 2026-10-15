from datetime import date, datetime, timezone
import pytest
from backend.care_assessment import assess

VALUES = dict(Age=26, SystolicBP=112, DiastolicBP=72, FastingGlucose=88, BodyTempC=37, HeartRate=78)

@pytest.mark.parametrize("changes,expected", [
    ({}, "routine"), ({"SystolicBP":135},"monitor"), ({"DiastolicBP":85},"monitor"),
    ({"SystolicBP":140},"today"), ({"DiastolicBP":90},"today"),
    ({"SystolicBP":150},"today"), ({"DiastolicBP":100},"today"),
    ({"SystolicBP":160},"urgent"), ({"DiastolicBP":110},"urgent"),
    ({"BodyTempC":38},"urgent"), ({"BodyTempC":37.5},"monitor"),
    ({"BodyTempC":34.9},"urgent"), ({"HeartRate":121},"urgent"),
    ({"HeartRate":39},"urgent"), ({"HeartRate":100},"monitor"),
    ({"SystolicBP":85},"today"), ({"FastingGlucose":70},"urgent"),
    ({"FastingGlucose":96},"today"), ({"FastingGlucose":600},"today"),
])
def test_action_boundaries(changes,expected):
    result=assess({**VALUES,**changes},5,20)
    assert result['level']==expected
    assert all(f['source_url'].startswith('https://') for f in result['findings'])

@pytest.mark.parametrize("symptom", ['chest_breathing','headache_vision','bleeding_fluid','severe_pain','faint_confused','cannot_drink','reduced_movement','severe_swelling'])
def test_symptoms_override_reassuring_numbers_at_any_stage(symptom):
    result=assess({**VALUES,'_symptoms':[symptom]},1,5)
    assert result['level']=='urgent'
    assert result['findings'][0]['level']=='urgent'


def test_units_stage_and_no_imputation():
    c=assess(VALUES,5,20)
    f=assess({k:v for k,v in {**VALUES,'BodyTempF':98.6}.items() if k!='BodyTempC'},5,20)
    assert c==f
    assert 'pre-eclampsia' in assess({**VALUES,'SystolicBP':140},5,20)['stage_advice']
    assert 'pre-eclampsia' not in assess({**VALUES,'SystolicBP':140},3,12)['stage_advice']
    assert 'Mild nausea' in assess(VALUES,1,5)['stage_advice']
    assert not assess({},1)['findings']
    assert assess({},1)['level']!='routine'


def test_urgent_actions_and_email_work_when_model_is_unavailable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("APP_ENV", "test")
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend import mail,inference
    from backend.database import SessionLocal,User,EmailVerification
    from sqlalchemy import select
    monkeypatch.setenv('RISK_MODEL_PROVIDER','bundled')
    monkeypatch.setenv('RESEND_API_KEY','synthetic-test-key')
    monkeypatch.setenv('EMAIL_FROM','Bloom <test@example.invalid>')
    sent=[]
    monkeypatch.setattr(mail,'send_provider',lambda *args:sent.append(args) or 'fake-id')
    monkeypatch.setattr(inference,'predict',lambda values: (_ for _ in ()).throw(RuntimeError('offline')))
    h={'X-Bloom-Request':'1'}
    with TestClient(app) as client:
        assert client.post('/api/auth/register',headers=h,json={'name':'Synthetic Check','email':'actions@example.invalid','password':'test-password-123'}).status_code==201
        pid=client.post('/api/pregnancies',headers=h,json={'lmp':str(date.today()),'month':1}).json()['id']
        with SessionLocal() as db:
            user=db.scalar(select(User).where(User.email=='actions@example.invalid'))
            db.add(EmailVerification(user_id=user.id,verified_at=datetime.now(timezone.utc)));db.commit()
        client.put(f'/api/pregnancies/{pid}/preferences',headers=h,json={'month':1,'email_enabled':True})
        units={'Age':'years','SystolicBP':'mmHg','DiastolicBP':'mmHg','FastingGlucose':'mg/dL','BodyTempC':'degC','HeartRate':'bpm'}
        payload={'observed_at':datetime.now(timezone.utc).isoformat(),'values':{**VALUES,'SystolicBP':160},'units':units,'symptoms':['headache_vision']}
        response=client.post(f'/api/pregnancies/{pid}/observations',headers=h,json=payload)
        assert response.status_code==201,response.text
        assert response.json()['care_assessment']['level']=='urgent'
        assert 'Get medical help now' in sent[-1][2]
        count=len(sent)
        oid=response.json()['id']
        assert client.post(f'/api/observations/{oid}/predict',headers=h).status_code==503
        dash=client.get(f'/api/pregnancies/{pid}/dashboard').json()
        assert dash['observations'][0]['care_assessment']['level']=='urgent'
        assert dash['observations'][0]['prediction'] is None
        assert len(sent)==count
        payload['symptoms']=['unrecognised']
        assert client.post(f'/api/pregnancies/{pid}/observations',headers=h,json=payload).status_code==422
