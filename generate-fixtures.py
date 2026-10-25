import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

root = Path(__file__).resolve().parent
fixture_path = root / 'runtime-fixtures.json'
assert not fixture_path.exists(), 'Preserve the same signed inputs across before/after runs'
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()
public_pem = public_key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
(root / 'test-public-key.pem').write_bytes(public_pem)

def signed_payload(user_id, expiration_date='2099-12-31'):
    payload = {'user_id': user_id, 'expiration_date': expiration_date, 'max_users': 500, 'max_teams': 50, 'allowed_features': ['*']}
    message = json.dumps(payload, separators=(',', ':')).encode()
    for _ in range(100):
        signature = private_key.sign(message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
        if b'.' in signature:
            break
    else:
        raise RuntimeError('Could not generate the binary-dot signature control')
    public_key.verify(signature, message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    wire = message + b'.' + signature
    return {'payload': payload, 'license': base64.b64encode(wire).decode(), 'signature_contains_dot': True, 'cryptographically_valid': True}

fixtures = {
    'plain': signed_payload('qa-license-26231'),
    'dotted': signed_payload('qa.example.co.jp-license-26231'),
    'expired': signed_payload('qa.example.co.jp-license-26231', '2000-01-01'),
}
tampered_bytes = base64.b64decode(fixtures['dotted']['license']).replace(b'"max_users":500', b'"max_users":999', 1)
fixtures['tampered'] = {'license': base64.b64encode(tampered_bytes).decode(), 'cryptographically_valid': False}
fixtures['dotted-unpadded'] = {**fixtures['dotted'], 'license': fixtures['dotted']['license'].rstrip('=')}
for case, fixture in fixtures.items():
    (root / f'license-{case}.txt').write_text(fixture['license'])
fixture_path.write_text(json.dumps(fixtures, indent=2) + '\n')
metadata = {
    'trust_anchor': 'Generated test RSA public key, substituted only in private verification worktrees',
    'public_key_sha256': hashlib.sha256(public_pem).hexdigest(),
    'rsa_bits': public_key.key_size,
    'cases': {case: {k: v for k, v in fixture.items() if k != 'license'} for case, fixture in fixtures.items()},
    'customer_license_used': False,
}
(root / 'runtime-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps(metadata, indent=2))
