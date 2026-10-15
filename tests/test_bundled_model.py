"""Independent native CatBoost fixtures, generated only from synthetic inputs."""
import json
import math
import os
from pathlib import Path
from datetime import date, datetime, timezone
import pytest
os.environ['DATABASE_URL']='sqlite://'
os.environ['APP_ENV']='test'
os.environ['RISK_MODEL_PROVIDER']='disabled'
from fastapi.testclient import TestClient
from backend.main import app
from backend import bundled_model, hosted_model

def test_numeric_export_matches_native_model():
    fixture=json.loads((Path(__file__).parent/'fixtures'/'bundled_model_parity.json').read_text())
    assert fixture['artifact_sha256']==bundled_model.EXPECTED_SHA256
    assert len(fixture['rows'])==1219
    for row in fixture['rows']:
        scores=bundled_model.scores_for_features(row['features'])
        assert scores==pytest.approx(row['probabilities'],abs=1e-13,rel=1e-13)
        assert sum(scores)==pytest.approx(1)

def test_bundled_assessment_no_token_no_network_and_no_imputation(monkeypatch):
    monkeypatch.setenv('RISK_MODEL_PROVIDER','bundled')
    for key in ['HF_TOKEN','RISK_MODEL_TOKEN','RISK_MODEL_URL']:
        monkeypatch.delenv(key,raising=False)
    def forbidden(*args,**kwargs):
        pytest.fail('Bundled prediction must never access an external service')
    monkeypatch.setattr(hosted_model,'urlopen',forbidden)
    values={'Age':26,'SystolicBP':112,'DiastolicBP':72,'FastingGlucose':88,'BodyTempC':37,'HeartRate':78}
    result=bundled_model.predict(values)
    assert result['review_required'] and result['outside_training_range']==['BS']
    assert values['FastingGlucose']==88 and values['BodyTempC']==37
    assert result['probabilities']==pytest.approx({'low':.3243606137044568,'mid':.6260971551664719,'high':.049542231129071204})
    with pytest.raises(hosted_model.ModelUnavailable,match='Six measured inputs'):
        bundled_model.predict({key:value for key,value in values.items() if key!='HeartRate'})
    with pytest.raises(hosted_model.ModelUnavailable,match='finite'):
        bundled_model.predict({**values,'HeartRate':math.nan})

def test_bundled_integrity(monkeypatch):
    bundled_model.load.cache_clear()
    with monkeypatch.context() as context:
        context.setattr(bundled_model,'EXPECTED_SHA256','0'*64)
        with pytest.raises(hosted_model.ModelUnavailable,match='integrity'):
            bundled_model.load()
    bundled_model.load.cache_clear()

def test_default_style_bundled_api_with_review_notice(monkeypatch):
    monkeypatch.setenv('RISK_MODEL_PROVIDER','bundled')
    monkeypatch.delenv('RESEND_API_KEY',raising=False)
    headers={'X-Bloom-Request':'1'}
    with TestClient(app) as client:
        r=client.post('/api/auth/register',headers=headers,json={'name':'Synthetic Local Test','email':'bundled@example.invalid','password':'test-password-123'})
        assert r.status_code==201
        pid=client.post('/api/pregnancies',headers=headers,json={'lmp':str(date.today()),'month':1}).json()['id']
        values={'Age':26,'SystolicBP':112,'DiastolicBP':72,'FastingGlucose':88,'BodyTempC':37,'HeartRate':78}
        units={'Age':'years','SystolicBP':'mmHg','DiastolicBP':'mmHg','FastingGlucose':'mg/dL','BodyTempC':'degC','HeartRate':'bpm'}
        r=client.post(f'/api/pregnancies/{pid}/observations',headers=headers,json={'observed_at':datetime.now(timezone.utc).isoformat(),'values':values,'units':units})
        assert r.status_code==201
        result=client.post(f'/api/observations/{r.json()["id"]}/predict',headers=headers)
        assert result.status_code==200,result.text
        assert result.json()['assessment_mode']=='bundled'
        assert result.json()['review_required']
        dashboard=client.get(f'/api/pregnancies/{pid}/dashboard').json()
        assert dashboard['preferences']['remote_model'] is None
        assert dashboard['preferences']['assessment_model']['status']=='bundled-research-model'
        assert not dashboard['preferences']['remote_assessment_enabled']
        assert not dashboard['notifications']
        assert dashboard['observations'][0]['care_assessment']['level']=='routine'
        assert not dashboard['emails']
