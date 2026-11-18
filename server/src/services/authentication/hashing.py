import hashlib
import hmac
import secrets


class PasswordHasher:
    """
    Utility class for handling password hashing and verification.
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash passwords using PBKDF2-HMAC-SHA256 with a unique random salt.

        :param password: The plain text password to hash.
        :type password: str
        :return: The hashed password.
        :rtype: str
        """
        salt = secrets.token_bytes(16)
        iterations = 600_000
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify if the provided plain text password matches the hashed password.

        :param plain_password: The plain text password provided by the user.
        :type plain_password: str
        :param hashed_password: The hashed password stored in the system.
        :type hashed_password: str
        :return: True if the passwords match, False otherwise.
        :rtype: bool
        """
        if hashed_password.startswith("pbkdf2_sha256$"):
            try:
                algorithm, iterations, salt_hex, digest_hex = hashed_password.split("$")
                if algorithm != "pbkdf2_sha256":
                    return False
                digest = hashlib.pbkdf2_hmac(
                    "sha256",
                    plain_password.encode("utf-8"),
                    bytes.fromhex(salt_hex),
                    int(iterations),
                )
                return hmac.compare_digest(digest.hex(), digest_hex)
            except (ValueError, TypeError):
                return False

        # Accept existing SHA-256 hashes and upgrade them after successful login.
        legacy_digest = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_digest, hashed_password)
