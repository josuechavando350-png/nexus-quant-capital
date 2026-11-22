"""Check archived package-signing chains against three distinct certificate stores."""
import base64
from pathlib import Path
import re
import ssl
import subprocess
import tempfile

from .product_census_header import pinned
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json


MITM = 'mitmproxy/mitmproxy'
TLSX = 'projectdiscovery/tlsx'
FIXTURES = 'test/mitmproxy/net/data/verificationcerts/'
INPUTS = {
    MITM: ('026-mitmproxy', 'c491986978a6280c29977482cb18698d6523a662', {
        FIXTURES + 'trusted-root.crt': '5f80f6c9f60950caf3850563f688bf15f3356337',
        FIXTURES + 'trusted-leaf.crt': '6dfb217d9d6fcf6de67461f7f006dfc3eb57d48c',
    }),
    TLSX: ('059-tlsx', '53e3d20a14f917e423c970b4db2944a202e6549a', {
        'assets/root-certs.pem': '4a38c72a9e1a35c4c24459989b18fd455be1b78e',
    }),
}
PROOF = 'superhunter/product_supply/clock-format-provenance.json'
PROOF_SHA = '90f0713975712cf97405d6e0e0d4230d3875185d8221a1604b15dfcc7c5a9bd6'
PACKAGES = ('litesvm', 'litesvm-linux-x64-gnu')
PUBLIC_CA_SHA = '1793927a0614549789adce2f8f34f7f0b66d0f3ae3a3b84d21ec15dbba4fadc7'
PEM = rb'-----BEGIN CERTIFICATE-----[^-]+-----END CERTIFICATE-----'


def source_files(root, repo):
    directory, revision, paths = INPUTS[repo]
    checkout = root / directory
    if checkout.is_symlink() or git(checkout, 'rev-parse', 'HEAD').decode().strip() != revision:
        raise EvidenceError('certificate reference checkout differs')
    files = {}
    for path, blob in paths.items():
        data = read_artifact(checkout, path)
        if git(checkout, 'rev-parse', revision + ':' + path).decode().strip() != blob or git_object('blob', data) != blob:
            raise EvidenceError('certificate reference blob differs')
        files[path] = data
    return files


def public_certificates(data):
    """Index the public CA bundle by exact certificate identity, ignoring its annotations."""
    pems = re.findall(PEM, data)
    if not pems or len(pems) != data.count(b'-----BEGIN ') or len(pems) != data.count(b'-----END '):
        raise EvidenceError('malformed public certificate bundle')
    table = {sha(ssl.PEM_cert_to_DER_cert(pem.decode('ascii'))): pem + b'\n' for pem in pems}
    if len(table) != len(pems):
        raise EvidenceError('duplicate public certificate in bundle')
    return table


def openssl(work, args):
    return subprocess.run(['/usr/bin/openssl', *args], cwd=work, env={'LC_ALL': 'C', 'OPENSSL_CONF': '/dev/null'},
                          stdin=subprocess.DEVNULL, capture_output=True, timeout=5)


def decision(work, leaf, authority, timestamp, *, intermediate=False):
    args = ['verify', '-no-CAfile', '-no-CApath', '-no-CAstore', '-CAfile', authority, '-attime', str(timestamp)]
    if intermediate:
        args.extend(['-untrusted', 'intermediate.pem'])
    probe = openssl(work, [*args, leaf])
    if probe.returncode == 0 and probe.stdout == (leaf + ': OK\n').encode():
        return 'accepted'
    codes = re.findall(rb'error (\d+) at (\d+) depth lookup', probe.stderr)
    reasons = {b'9': 'not_yet_valid', b'10': 'expired', b'20': 'issuer_unavailable'}
    if probe.returncode != 2 or len(codes) != 1 or codes[0][0] not in reasons:
        raise EvidenceError('unexpected certificate verifier failure')
    return reasons[codes[0][0]] + '_at_depth_' + codes[0][1].decode()


def check_envelope(work, name, envelope):
    media_type = envelope['payloadType'].encode('ascii')
    if media_type != b'application/vnd.in-toto+json' or len(envelope['signatures']) != 1:
        raise EvidenceError('unexpected release attestation envelope')
    body = base64.b64decode(envelope['payload'], validate=True)
    pae = b' '.join((b'DSSEv1', str(len(media_type)).encode(), media_type, str(len(body)).encode(), body))
    (work / 'attestation.bin').write_bytes(pae)
    (work / 'signature.bin').write_bytes(base64.b64decode(envelope['signatures'][0]['sig'], validate=True))
    key = openssl(work, ['x509', '-in', name, '-noout', '-pubkey'])
    if key.returncode:
        raise EvidenceError('package attestation public key unavailable')
    (work / 'signer.pem').write_bytes(key.stdout)
    validate = openssl(work, ['dgst', '-sha256', '-verify', 'signer.pem', '-signature', 'signature.bin',
                              'attestation.bin'])
    if validate.returncode or validate.stdout.strip() != b'Verified OK':
        raise EvidenceError('certificate does not authenticate this release envelope')


def bound_leaf(work, name, entry):
    der = base64.b64decode(entry['certificate_der'], validate=True)
    (work / name).write_text(ssl.DER_cert_to_PEM_cert(der), encoding='ascii')
    observation = openssl(work, ['x509', '-in', name, '-noout', '-dates', '-sha256', '-fingerprint'])
    if observation.returncode:
        raise EvidenceError('invalid package-signing certificate')
    fields = dict(row.split('=', 1) for row in observation.stdout.decode('ascii').splitlines())
    fingerprint = fields['sha256 Fingerprint'].replace(':', '').lower()
    before = ssl.cert_time_to_seconds(fields['notBefore'])
    after = ssl.cert_time_to_seconds(fields['notAfter'])
    when = entry['integrated_time']
    if fingerprint != sha(der) or type(when) is not int or not before <= when <= after:
        raise EvidenceError('signing timestamp or certificate identity differs')
    check_envelope(work, name, entry['envelope'])
    return {'sha256': fingerprint, 'not_before': before, 'not_after': after, 'integrated_time': when}


def inspect(work, proof, public, fixtures):
    authorities = public_certificates(public)
    if PUBLIC_CA_SHA not in authorities:
        raise EvidenceError('positive public root control absent')
    (work / 'web-roots.pem').write_bytes(public)
    (work / 'web-control.pem').write_bytes(authorities[PUBLIC_CA_SHA])
    for role in ('root', 'leaf'):
        (work / ('test-' + role + '.pem')).write_bytes(fixtures[FIXTURES + 'trusted-' + role + '.crt'])
    (work / 'fulcio.pem').write_text(proof['fulcio_root_pem'], encoding='ascii')
    (work / 'intermediate.pem').write_text(proof['fulcio_intermediate_pem'], encoding='ascii')
    if sorted(proof['bundles']) != sorted(PACKAGES):
        raise EvidenceError('unexpected package-signing inputs')
    test_chains = {}
    web_chains = {}
    temporal = {}
    for package in PACKAGES:
        leaf = package + '.pem'
        info = bound_leaf(work, leaf, proof['bundles'][package])
        when = info['integrated_time']
        for moment, expected in ((when, 'accepted'), (info['not_before'] - 1, 'not_yet_valid_at_depth_0'),
                                 (info['not_after'] + 1, 'expired_at_depth_0')):
            if decision(work, leaf, 'fulcio.pem', moment, intermediate=True) != expected:
                raise EvidenceError('package-signing validation window differs')
        temporal[package] = info
        test_chains[package] = decision(work, leaf, 'test-root.pem', when, intermediate=True)
        web_chains[package] = decision(work, leaf, 'web-roots.pem', when, intermediate=True)
    when = temporal[PACKAGES[0]]['integrated_time']
    if (set(test_chains.values()) != {'issuer_unavailable_at_depth_1'}
            or set(web_chains.values()) != {'issuer_unavailable_at_depth_1'}
            or decision(work, 'test-leaf.pem', 'test-root.pem', when) != 'accepted'
            or decision(work, 'web-control.pem', 'web-roots.pem', when) != 'accepted'
            or decision(work, 'test-leaf.pem', 'web-roots.pem', when) != 'issuer_unavailable_at_depth_0'):
        raise EvidenceError('certificate trust stores failed cross-substitution controls')
    test = {'test_chain_accepted': True, 'public_store_rejected_test_chain': True,
            'release_chains_with_test_ca': test_chains}
    web = {'roots': len(authorities), 'roots_sha256': sha(canonical(sorted(authorities))),
           'positive_control_root': PUBLIC_CA_SHA, 'release_chains_with_web_ca': web_chains}
    return {MITM: test, TLSX: web}, temporal


def review(root):
    inputs = {repo: source_files(root, repo) for repo in INPUTS}
    proof = strict_json(pinned(ROOT, PROOF, PROOF_SHA))
    with tempfile.TemporaryDirectory(prefix='nqc-cert-review-') as directory:
        results, temporal = inspect(Path(directory), proof, inputs[TLSX]['assets/root-certs.pem'], inputs[MITM])
    return {repo: {'revision': INPUTS[repo][1], 'operation': 'compare_release_signing_trust_stores',
                   'source_blobs': INPUTS[repo][2], 'proof_sha256': PROOF_SHA,
                   'release_windows': temporal, 'result': result}
            for repo, result in results.items()}
