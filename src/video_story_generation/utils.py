import hashlib
import time


def generate_slug(text: str) -> str:
    my_timestamp = time.time()

    # Combine string and timestamp
    raw_data = f"{text}-{my_timestamp}".encode("utf-8")

    # Create a compact 5-byte hash using blake2b
    digest = hashlib.blake2b(raw_data, digest_size=5).digest()

    # Map to lowercase a-z letters
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    value = int.from_bytes(digest, "big")

    chars = []
    for _ in range(5):
        value, remainder = divmod(value, 26)
        chars.append(alphabet[remainder])

    return "".join(chars)
