"""
HMAC-SHA256 authentication for BTicino XOpen v3 protocol.

The handshake works as follows:
1. Server sends RandomStringHMAC with Ra (random bytes as decimal text)
2. Client generates Rb (32 random bytes), computes:
   digest = SHA256(Ra_hex + Rb_hex + A_STR + B_STR + SHA256_hex(password))
   NOTE: SHA256 hashes the concatenated hex STRING as UTF-8, NOT hex-decoded bytes
3. Server verifies and sends ServerHandshakeHMAC with its own digest:
   server_digest = SHA256(Ra_hex + Rb_hex + SHA256_hex(password))
   (same order Ra+Rb, but without A/B constants)
4. Client verifies server_digest and sends AckMsg

The "decimal text" format encodes each byte as two 2-digit decimal numbers,
one for each hex nibble. E.g. byte 0xA3 -> hex "a3" -> decimal "1003"
(because 0xa=10, 0x3=03).
"""
import hashlib
import os


# Constants from decompiled app (Eliot.DriverAxia.cs lines 2902-2904)
A_STR = "736F70653E"
B_STR = "636F70653E"


def to_hex_text_from_bytes(data: bytes) -> str:
    """Convert raw bytes to hex text (lowercase, 2 chars per byte).

    Mirrors C# ToHexTextVersion(byte[] input).
    E.g. b'\\xa3\\x0f' -> 'a30f'
    """
    return data.hex()


def to_hex_text_from_decimal(decimal_text: str) -> str:
    """Convert decimal text representation to hex text.

    Mirrors C# ToHexTextVersion(string input).
    Each pair of decimal digits represents one hex nibble.
    E.g. '10030015' -> nibbles [10,03,00,15] -> hex [a,3,0,f] -> 'a30f'

    Note: C# uses ToString("x") WITHOUT padding, producing 1 char per nibble.
    """
    result = []
    for i in range(0, len(decimal_text), 2):
        nibble_dec = int(decimal_text[i:i + 2])
        result.append(format(nibble_dec, 'x'))
    return ''.join(result)


def to_decimal_text(data: bytes) -> str:
    """Convert raw bytes to decimal text representation.

    Mirrors C# ToDecimalTextVersion(byte[] input).
    Each byte is split into two hex nibbles, each nibble is represented
    as a 2-digit decimal number.
    E.g. byte 0xA3 -> hex 'a3' -> nibbles [a=10, 3=03] -> '1003'
    """
    result = []
    for b in data:
        hex_str = format(b, '02x')
        hi_nibble = int(hex_str[0], 16)
        lo_nibble = int(hex_str[1], 16)
        result.append(f"{hi_nibble:02d}")
        result.append(f"{lo_nibble:02d}")
    return ''.join(result)


def _hash_sha256_of_string(text: str) -> bytes:
    """Compute SHA256 of a string encoded as UTF-8 bytes.

    Mirrors C# Hash_SHA(inputStr, SHA2) which does:
        SHA256.Create().ComputeHash(Encoding.UTF8.GetBytes(inputStr))

    IMPORTANT: This hashes the UTF-8 encoded string characters,
    NOT hex-decoded bytes. E.g. "a30f" is hashed as [0x61,0x33,0x30,0x66].
    """
    return hashlib.sha256(text.encode('utf-8')).digest()


def _hash_sha256_to_str(text: str) -> str:
    """Compute SHA256 of a string, return as lowercase hex.

    Mirrors C# Hash_SHA_ToStr(inputStr, SHA2) which computes
    SHA256(UTF8(inputStr)) and returns each byte as "x".PadLeft(2,'0').
    """
    digest = hashlib.sha256(text.encode('utf-8')).digest()
    return digest.hex()


def generate_random(num_bytes: int = 32) -> bytes:
    """Generate cryptographic random bytes."""
    return os.urandom(num_bytes)


def make_hmac(password: str, ra_decimal_text: str,
              a_str: str = A_STR, b_str: str = B_STR) -> tuple[str, str]:
    """Compute the client HMAC response for the handshake.

    Mirrors C# MakeSHA(SHA2, PwdOpen, A_Str, B_Str, Ra_dec_chars, ...).

    Args:
        password: The XOpen password (plain text)
        ra_decimal_text: Server's random string Ra in decimal text format
        a_str: Constant A (default from decompiled code)
        b_str: Constant B (default from decompiled code)

    Returns:
        (rb_decimal_text, digest_decimal_text) - client's random and HMAC digest,
        both in decimal text format ready to be sent in the XML message.
    """
    # Step 1: Convert server's Ra from decimal text to hex
    ra_hex = to_hex_text_from_decimal(ra_decimal_text)

    # Step 2: Generate client's Rb (32 bytes for SHA256)
    rb_bytes = generate_random(32)
    rb_hex = to_hex_text_from_bytes(rb_bytes)
    rb_decimal = to_decimal_text(rb_bytes)

    # Step 3: Hash the password to hex string
    pwd_hash = _hash_sha256_to_str(password)

    # Step 4: Concatenate: Ra_hex + Rb_hex + A_str + B_str + pwd_hash
    concat = ra_hex + rb_hex + a_str + b_str + pwd_hash

    # Step 5: SHA256 of the concatenated string AS UTF-8 (not hex-decoded!)
    digest_bytes = _hash_sha256_of_string(concat)
    digest_decimal = to_decimal_text(digest_bytes)

    return rb_decimal, digest_decimal


def verify_hmac(password: str, ra_decimal_text: str, rb_decimal_text: str,
                server_digest: str) -> bool:
    """Verify the server's HMAC response.

    Mirrors C# EvalueteSHA(SHA2, PwdOpen, Ra_dec_chars, Rb_dec_chars, Digest).

    Args:
        password: The XOpen password (plain text)
        ra_decimal_text: Server's original random Ra
        rb_decimal_text: Client's random Rb (sent in ClientHandshakeHMAC)
        server_digest: Server's digest from ServerHandshakeHMAC

    Returns:
        True if the server's digest is valid.

    Note: Order is Ra_hex + Rb_hex + pwd_hash (no A_str, B_str).
    """
    # Step 1: Hash password
    pwd_hash = _hash_sha256_to_str(password)

    # Step 2: Convert randoms to hex
    ra_hex = to_hex_text_from_decimal(ra_decimal_text)
    rb_hex = to_hex_text_from_decimal(rb_decimal_text)

    # Step 3: Concatenate: Ra_hex + Rb_hex + pwd_hash
    concat = ra_hex + rb_hex + pwd_hash

    # Step 4: SHA256 of concatenated string AS UTF-8
    expected_bytes = _hash_sha256_of_string(concat)
    expected_decimal = to_decimal_text(expected_bytes)

    return expected_decimal == server_digest
