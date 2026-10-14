import os
from datetime import date, timedelta, datetime, timezone
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['APP_ENV'] = 'test'
os.environ['RISK_MODEL_PROVIDER'] = 'disabled'
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import SessionLocal, User
from sqlalchemy import select

HEADERS = {'X-Bloom-Request': '1'}
VALUES = {'Age': 26, 'BodyTempF': 98.6, 'HeartRate': 78, 'SystolicBP': 112,
          'DiastolicBP': 72, 'BMI': 24, 'HbA1c': 5.2, 'FastingGlucose': 88}
UNITS = {'Age': 'years', 'BodyTempF': 'degF', 'HeartRate': 'bpm', 'SystolicBP': 'mmHg',
         'DiastolicBP': 'mmHg', 'BMI': 'kg/m2', 'HbA1c': '%', 'FastingGlucose': 'mg/dL'}

def register(client, email):
    r = client.post('/api/auth/register', headers=HEADERS, json={'email': email, 'name': 'Test Mother', 'password': 'test-password-123'})
    assert r.status_code == 201, r.text

def test_complete_workflow_and_isolation(monkeypatch):
    from backend import inference
    monkeypatch.setattr(inference, 'predict', lambda values: {'category':'low','probabilities':{'low':.7,'mid':.2,'high':.1},'outside_training_range':[]})
    with TestClient(app) as client:
        register(client, 'first@example.com')
        pid = client.post('/api/pregnancies', headers=HEADERS, json={'lmp': str(date.today()-timedelta(weeks=20))}).json()['id']
        payload = {'observed_at': datetime.now(timezone.utc).isoformat(), 'values': VALUES, 'units': UNITS}
        bad = {**payload, 'values': {**VALUES, 'HeartRate': -5}}
        assert client.post(f'/api/pregnancies/{pid}/observations', headers=HEADERS, json=bad).status_code == 422
        bad = {**payload, 'units': {**UNITS, 'BodyTempF': 'degC'}}
        assert client.post(f'/api/pregnancies/{pid}/observations', headers=HEADERS, json=bad).status_code == 422
        bad = {**payload, 'values': {k:v for k,v in VALUES.items() if k!='Age'}}
        assert client.post(f'/api/pregnancies/{pid}/observations', headers=HEADERS, json=bad).status_code == 422
        bad = {**payload, 'observed_at': (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()}
        assert client.post(f'/api/pregnancies/{pid}/observations', headers=HEADERS, json=bad).status_code == 422
        bad = {**payload, 'observed_at': datetime.now().isoformat()}
        assert client.post(f'/api/pregnancies/{pid}/observations', headers=HEADERS, json=bad).status_code == 422
        r = client.post(f'/api/pregnancies/{pid}/observations', headers=HEADERS, json=payload)
        assert r.status_code == 201, r.text
        oid = r.json()['id']
        prediction = client.post(f'/api/observations/{oid}/predict', headers=HEADERS)
        assert prediction.status_code == 200, prediction.text
        result = prediction.json()
        assert abs(sum(result['probabilities'].values())-1) < 1e-6
        assert result['category'] in ['low', 'mid', 'high']
        assert client.post(f'/api/observations/{oid}/predict', headers=HEADERS).json() == result
        assert len(client.get(f'/api/pregnancies/{pid}/dashboard').json()['observations']) == 1
        assert client.get('/api/admin').status_code == 403
        assert client.post('/api/auth/logout', headers=HEADERS).status_code == 200
        assert client.get('/api/me').status_code == 401
        register(client, 'second@example.com')
        assert client.get(f'/api/pregnancies/{pid}/dashboard').status_code == 404
        assert client.post(f'/api/observations/{oid}/predict', headers=HEADERS).status_code == 404
        assert client.post(f'/api/pregnancies/{pid}/observations', headers=HEADERS, json=payload).status_code == 404
        assert client.post('/api/pregnancies', json={'lmp': str(date.today())}).status_code == 403

def test_chronology_content_review_and_notifications(monkeypatch):
    from backend import inference
    monkeypatch.setattr(inference, 'predict', lambda values: {'category':'high','probabilities':{'low':.1,'mid':.2,'high':.7},'outside_training_range':[]})
    with TestClient(app) as client:
        register(client, 'reviewer@example.com')
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email=='reviewer@example.com'))
            user.role='admin'; db.commit()
        pid=client.post('/api/pregnancies',headers=HEADERS,json={'lmp':str(date.today()-timedelta(weeks=20))}).json()['id']
        for days in [0, 2]:
            payload={'observed_at':(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(),'values':VALUES,'units':UNITS}
            oid=client.post(f'/api/pregnancies/{pid}/observations',headers=HEADERS,json=payload).json()['id']
            assert client.post(f'/api/observations/{oid}/predict',headers=HEADERS).status_code==200
        dash=client.get(f'/api/pregnancies/{pid}/dashboard').json()
        assert dash['observations'][0]['observed_at'] < dash['observations'][1]['observed_at']
        assert len(dash['notifications']) == 2
        nid=dash['notifications'][0]['id']
        assert client.patch(f'/api/notifications/{nid}/read',headers=HEADERS).status_code==200
        g=client.post('/api/admin/guidance',headers=HEADERS,json={'title':'Test reviewed content','body':'Test body','stage':2,'category':'high','source_url':'https://example.com'}).json()
        assert g['id'] not in [x['id'] for x in client.get(f'/api/pregnancies/{pid}/dashboard').json()['guidance']]
        assert client.post(f'/api/admin/guidance/{g["id"]}/review',headers=HEADERS).status_code==200
        assert g['id'] in [x['id'] for x in client.get(f'/api/pregnancies/{pid}/dashboard').json()['guidance']]
        assert client.post(f'/api/pregnancies/{pid}/guidance/{g["id"]}/delivered',headers=HEADERS).status_code==200
        assert client.post(f'/api/pregnancies/{pid}/guidance/{g["id"]}/delivered',headers=HEADERS).status_code==200
        assert client.get('/api/admin').json()['audit']

def test_artifact_parity():
    import pytest
    import pickle
    import numpy as np
    import pandas as pd
    import torch
    from backend.inference import ROOT, FEATURES, load, predict_artifact, predict
    with pytest.raises(RuntimeError, match='dataset units'):
        predict(VALUES)
    source_values = {**VALUES, 'HbA1c': 41, 'FastingGlucose': 5.8}
    model, _ = load()
    with (ROOT/'maternal_model_scaler.pkl').open('rb') as f:
        scaler=pickle.load(f)
    array=scaler.transform(pd.DataFrame([[source_values[k] for k in FEATURES]],columns=FEATURES)).reshape(1,8,1)
    with torch.inference_mode():
        expected=torch.softmax(model(torch.tensor(array,dtype=torch.float32)),1).numpy()[0]
    np.testing.assert_allclose(list(predict_artifact(source_values)['probabilities'].values()),expected,rtol=1e-6)

def test_model_failure_preserves_record(monkeypatch):
    from backend import inference
    def unavailable(values):
        raise RuntimeError('Unavailable artifact')
    monkeypatch.setattr(inference, 'predict', unavailable)
    with TestClient(app) as client:
        register(client, 'failure@example.com')
        pid=client.post('/api/pregnancies',headers=HEADERS,json={'lmp':str(date.today()-timedelta(weeks=10))}).json()['id']
        oid=client.post(f'/api/pregnancies/{pid}/observations',headers=HEADERS,json={'observed_at':datetime.now(timezone.utc).isoformat(),'values':VALUES,'units':UNITS}).json()['id']
        assert client.post(f'/api/observations/{oid}/predict',headers=HEADERS).status_code == 503
        dash=client.get(f'/api/pregnancies/{pid}/dashboard').json()
        assert len(dash['observations'])==1
        assert dash['observations'][0]['prediction'] is None
