import hashlib

from src.services.authentication.hashing import PasswordHasher


def test_password_hashes_are_salted_and_verified():
    first = PasswordHasher.hash_password("correct horse battery staple")
    second = PasswordHasher.hash_password("correct horse battery staple")

    assert first.startswith("pbkdf2_sha256$600000$")
    assert first != second
    assert PasswordHasher.verify_password("correct horse battery staple", first)
    assert not PasswordHasher.verify_password("wrong password", first)


def test_legacy_sha256_password_hash_can_be_migrated():
    legacy = hashlib.sha256(b"old password").hexdigest()

    assert PasswordHasher.verify_password("old password", legacy)
    assert not PasswordHasher.verify_password("wrong password", legacy)
