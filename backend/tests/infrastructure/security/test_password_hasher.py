from app.infrastructure.security.password_hasher import Argon2PasswordHasher


def test_hash_verifies_and_is_salted():
    hasher = Argon2PasswordHasher()
    first, second = hasher.hash("correct-horse"), hasher.hash("correct-horse")
    assert first != second  # random salt
    assert "correct-horse" not in first
    assert hasher.verify("correct-horse", first)
    assert not hasher.verify("wrong-horse", first)


def test_malformed_hash_is_just_a_failed_verification():
    assert not Argon2PasswordHasher().verify("anything", "not-a-real-hash")
