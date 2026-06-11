import os
import pytest
from code_index.encryption import (
    is_available,
    encrypt_data,
    decrypt_data,
    encrypt_file,
    decrypt_file,
    encrypt_lance_db,
    decrypt_lance_db,
)


@pytest.mark.skipif(not is_available(), reason="cryptography not installed")
def test_encrypt_decrypt_roundtrip():
    original = b"hello world, this is a secret message"
    password = "test_password_123"
    encrypted = encrypt_data(original, password)
    assert encrypted != original
    decrypted = decrypt_data(encrypted, password)
    assert decrypted == original


@pytest.mark.skipif(not is_available(), reason="cryptography not installed")
def test_encrypt_decrypt_file(tmp_path):
    src = tmp_path / "plain.txt"
    enc = tmp_path / "plain.txt.enc"
    dec = tmp_path / "plain_decrypted.txt"
    src.write_bytes(b"file content here")
    encrypt_file(str(src), str(enc), "mypass")
    assert enc.read_bytes() != src.read_bytes()
    decrypt_file(str(enc), str(dec), "mypass")
    assert dec.read_bytes() == src.read_bytes()


@pytest.mark.skipif(not is_available(), reason="cryptography not installed")
def test_encrypt_decrypt_lance_db(tmp_path):
    src_dir = tmp_path / "db_original"
    enc_dir = tmp_path / "db_encrypted"
    dec_dir = tmp_path / "db_decrypted"
    src_dir.mkdir()
    (src_dir / "data.lance").write_bytes(b"lance data payload")
    (src_dir / "metadata.json").write_bytes(b'{"version": 1}')
    encrypt_lance_db(str(src_dir), "db_password", str(enc_dir))
    assert (enc_dir / "data.lance").exists()
    assert (enc_dir / ".encrypted_manifest.json").exists()
    decrypt_lance_db(str(enc_dir), "db_password", str(dec_dir))
    assert (dec_dir / "data.lance").read_bytes() == b"lance data payload"


@pytest.mark.skipif(not is_available(), reason="cryptography not installed")
def test_wrong_password_fails():
    encrypted = encrypt_data(b"secret", "correct_password")
    with pytest.raises(Exception):
        decrypt_data(encrypted, "wrong_password")


def test_not_available_returns_bool():
    assert isinstance(is_available(), bool)
