import os
import hashlib
import base64
import struct
import json


try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


def is_available():
    return _HAS_CRYPTO


def _derive_key(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return key, salt


def encrypt_data(data_bytes, password):
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography package not installed. Install with: pip install cryptography")
    key, salt = _derive_key(password)
    fernet = Fernet(key)
    encrypted = fernet.encrypt(data_bytes)
    return salt + encrypted


def decrypt_data(encrypted_bytes, password):
    if not _HAS_CRYPTO:
        raise RuntimeError("cryptography package not installed. Install with: pip install cryptography")
    salt = encrypted_bytes[:16]
    ciphertext = encrypted_bytes[16:]
    key, _ = _derive_key(password, salt)
    fernet = Fernet(key)
    return fernet.decrypt(ciphertext)


def encrypt_file(input_path, output_path, password):
    with open(input_path, 'rb') as f:
        data = f.read()
    encrypted = encrypt_data(data, password)
    with open(output_path, 'wb') as f:
        f.write(encrypted)


def decrypt_file(input_path, output_path, password):
    with open(input_path, 'rb') as f:
        encrypted = f.read()
    decrypted = decrypt_data(encrypted, password)
    with open(output_path, 'wb') as f:
        f.write(decrypted)


def encrypt_lance_db(db_path, password, output_path=None):
    if output_path is None:
        output_path = db_path + ".encrypted"
    os.makedirs(output_path, exist_ok=True)
    for root, dirs, files in os.walk(db_path):
        rel = os.path.relpath(root, db_path)
        dest_dir = os.path.join(output_path, rel) if rel != '.' else output_path
        os.makedirs(dest_dir, exist_ok=True)
        for fn in files:
            src = os.path.join(root, fn)
            dst = os.path.join(dest_dir, fn)
            encrypt_file(src, dst, password)
    meta_path = os.path.join(output_path, ".encrypted_manifest.json")
    manifest = {"version": 1, "encrypted": True}
    with open(meta_path, 'w') as f:
        json.dump(manifest, f)
    return output_path


def decrypt_lance_db(encrypted_path, password, output_path):
    os.makedirs(output_path, exist_ok=True)
    for root, dirs, files in os.walk(encrypted_path):
        rel = os.path.relpath(root, encrypted_path)
        dest_dir = os.path.join(output_path, rel) if rel != '.' else output_path
        os.makedirs(dest_dir, exist_ok=True)
        for fn in files:
            if fn == ".encrypted_manifest.json":
                continue
            src = os.path.join(root, fn)
            dst = os.path.join(dest_dir, fn)
            decrypt_file(src, dst, password)
    return output_path
