"""Real PostgreSQL regression test, enabled only for the disposable CI database."""
import os
import subprocess
import sys
import pytest

@pytest.mark.skipif(not os.getenv("POSTGRES_TEST_URL"), reason="Requires disposable PostgreSQL CI service")
def test_registration_with_incompatible_public_users_table():
    # A subprocess prevents the SQLite test suite's imported models from affecting PostgreSQL metadata.
    source = '''
from sqlalchemy import text
from sqlalchemy.engine import make_url
from fastapi.testclient import TestClient
from backend.database import engine, SCHEMA
from backend.main import app
assert make_url(str(engine.url)).database == "bloom_ci", "Only run against the disposable bloom_ci database"
assert SCHEMA == "bloom"
with engine.begin() as connection:
    connection.execute(text("CREATE TABLE public.users (id integer PRIMARY KEY, legacy_name text NOT NULL)"))
    connection.execute(text("INSERT INTO public.users VALUES (1, 'legacy sentinel')"))
headers = {"X-Bloom-Request": "1"}
credentials = {"email":"schema-regression@example.invalid", "password":"test-password-123"}
with TestClient(app) as client:
    response = client.post("/api/auth/register", headers=headers, json={**credentials, "name":"Schema Test"})
    assert response.status_code == 201, response.text
    assert client.get("/api/me").json()["name"] == "Schema Test"
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.post("/api/auth/login", headers=headers, json=credentials).status_code == 200
with engine.connect() as connection:
    assert connection.execute(text("SELECT legacy_name FROM public.users WHERE id=1")).scalar_one() == "legacy sentinel"
    assert connection.execute(text("SELECT count(*) FROM bloom.users")).scalar_one() == 1
    assert connection.execute(text("SELECT count(*) FROM bloom.login_sessions")).scalar_one() == 1
engine.dispose()
'''
    environment = dict(os.environ, DATABASE_URL=os.environ["POSTGRES_TEST_URL"], APP_ENV="test")
    environment.pop("VERCEL", None)
    result = subprocess.run([sys.executable, "-c", source], env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
