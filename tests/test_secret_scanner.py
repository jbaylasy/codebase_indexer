from code_index.secret_scanner import scan_and_redact, redact_chunk, _shannon_entropy


def test_detects_aws_access_key():
    text = 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"'
    redacted, findings = scan_and_redact(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "***REDACTED_SECRET***" in redacted
    assert any(f["type"] == "aws_access_key_id" for f in findings)


def test_detects_jwt_token():
    text = 'token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"'
    redacted, findings = scan_and_redact(text)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
    assert "***REDACTED_SECRET***" in redacted


def test_detects_database_connection_string():
    text = 'DB_URL = "postgresql://user:pass@host:5432/mydb"'
    redacted, findings = scan_and_redact(text)
    assert "postgresql://user:pass@host:5432/mydb" not in redacted
    assert any(f["type"] == "database_connection_string" for f in findings)


def test_detects_github_token():
    text = 'GITHUB_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklm"'
    redacted, findings = scan_and_redact(text)
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklm" not in redacted
    assert any(f["type"] == "github_token" for f in findings)


def test_detects_private_key():
    text = 'key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"'
    redacted, findings = scan_and_redact(text)
    assert "BEGIN RSA PRIVATE KEY" not in redacted
    assert any(f["type"] == "private_key" for f in findings)


def test_detects_password():
    text = 'password = "SuperSecretPass123!"'
    redacted, findings = scan_and_redact(text)
    assert "SuperSecretPass123!" not in redacted
    assert any(f["type"] == "password" for f in findings)


def test_detects_generic_api_key():
    text = 'api_key = "XX_TEST_FAKE_KEY_abcdefghijklmnopqrstuvwxyz1234567890_XX"'
    redacted, findings = scan_and_redact(text)
    assert "XX_TEST_FAKE_KEY_abcdefghijklmnopqrstuvwxyz1234567890_XX" not in redacted
    assert any(f["type"] == "generic_api_key" for f in findings)


def test_no_secrets_returns_unchanged():
    text = "def hello_world():\n    print('hello')\n"
    redacted, findings = scan_and_redact(text)
    assert redacted == text
    assert findings == []


def test_redact_chunk():
    chunk = {
        "text": 'db_url = "postgresql://admin:password@localhost:5432/prod"',
        "metadata": {"file": "config.py", "start_line": 1, "type": "function", "name": "config"},
    }
    result = redact_chunk(chunk)
    assert "postgresql://admin:password@localhost:5432/prod" not in result["text"]
    assert "redacted_secrets" in result
    assert result["metadata"] == chunk["metadata"]


def test_redact_chunk_no_secrets():
    chunk = {
        "text": "def hello():\n    return 'world'\n",
        "metadata": {"file": "hello.py", "start_line": 1, "type": "function", "name": "hello"},
    }
    result = redact_chunk(chunk)
    assert result["text"] == chunk["text"]
    assert "redacted_secrets" not in result


def test_shannon_entropy():
    assert _shannon_entropy("") == 0.0
    assert _shannon_entropy("aaaa") < 1.0
    assert _shannon_entropy("aAbBcCdDeEfFgGhH") > 3.0


def test_high_entropy_detection():
    high_entropy = 'token = "a8f3b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0"'
    redacted, findings = scan_and_redact(high_entropy)
    assert len(findings) > 0


def test_multiple_secrets_in_same_text():
    text = '''
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
password = "MySecretPassword123!"
api_key = "XX_TEST_FAKE_KEY_abcdefghijklmnopqrstuvwxyz1234567890_XX"
'''
    redacted, findings = scan_and_redact(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "MySecretPassword123!" not in redacted
    assert "***REDACTED_SECRET***" in redacted


def test_stripe_secret_key():
    text = 'STRIPE_KEY = "XX_FAKE_STRIPE_abcdefghijklmnopqrstuvwxyz1234567890_XX"'
    redacted, findings = scan_and_redact(text)
    assert "XX_FAKE_STRIPE_abcdefghijklmnopqrstuvwxyz1234567890_XX" not in redacted
    assert "***REDACTED_SECRET***" in redacted
    assert any("secret" in f["type"] or "key" in f["type"] for f in findings)


def test_azure_credential():
    text = 'AZURE_CLIENT_SECRET = "ThisIsALongAzureSecretKey1234567"'
    redacted, findings = scan_and_redact(text)
    assert "ThisIsALongAzureSecretKey1234567" not in redacted
    assert "***REDACTED_SECRET***" in redacted
    assert any(f["type"] == "azure_credential" for f in findings)


def test_google_api_key():
    text = 'GCP_KEY = "AIzaSyDaGmWKa4VuX0h2Z2m0hVdWYmWYmWYmWYmWYmW"'
    redacted, findings = scan_and_redact(text)
    assert "AIzaSyDaGmWKa4VuX0h2Z2m0hVdWYmWYmWYmWYmWYmW" not in redacted
    assert "***REDACTED_SECRET***" in redacted
    assert any(f["type"] == "google_api_key" for f in findings)


def test_generic_uuid():
    text = 'uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"'
    redacted, findings = scan_and_redact(text)
    assert "a1b2c3d4-e5f6-7890-abcd-ef1234567890" not in redacted
    assert "***REDACTED_SECRET***" in redacted
    assert any(f["type"] == "generic_uuid" for f in findings)


def test_unquoted_secret():
    text = "api_key = abcdefghijklmnopqrstuvwxyz1234567890XYZ"
    redacted, findings = scan_and_redact(text)
    assert "abcdefghijklmnopqrstuvwxyz1234567890XYZ" not in redacted
    assert "***REDACTED_SECRET***" in redacted
    assert any(f["type"] == "unquoted_secret" for f in findings)
