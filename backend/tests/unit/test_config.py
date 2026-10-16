from app.core.config import Settings, config_report


def test_missing_reports_missing_and_never_echoes_values():
    rep = config_report(Settings(_env_file=None, database_url="", session_pepper=""))
    assert rep["database_url"] == "missing"
    assert rep["session_pepper"] == "missing"


def test_configured_does_not_leak_password():
    s = Settings(_env_file=None, database_url="postgresql://u:p%40ss@h.example/db?sslmode=require",
                 session_pepper="x" * 32)
    rep = config_report(s)
    assert rep["database_url"] == "configured"
    assert "p%40ss" not in str(rep)


def test_production_rejects_insecure_cookie():
    s = Settings(_env_file=None, app_env="production", cookie_secure=False, session_pepper="x" * 32)
    assert config_report(s)["cookie_secure"] == "insecure_in_production"
