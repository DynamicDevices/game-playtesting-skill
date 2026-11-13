"""Trusted publication support, adapted from the verified LMS reference.
Source: GenMinds-UK/innovateher-lms-work@4c66924dee4ad37e74a084366c35dc8865da9d18.
Never execute PR-head code with these credentials. Assisted-by: Briar.
"""
import base64
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from review_contract import InvalidReview, require
from completion_contract import strict_json

KEY = 'SHA256:vBkafuWAZYu5NnpYdbW8z1ZbZp/VFuSl8mad9jo0UFc'
NAMESPACE = 'briar-preloop-publication'
DIFF_ARGS = ['diff', '--no-ext-diff', '--no-textconv', '--no-color', '--full-index',
             '--no-renames', '--diff-algorithm=myers', '--no-indent-heuristic',
             '--unified=3', '--inter-hunk-context=0', '--src-prefix=a/', '--dst-prefix=b/']


def request(origin, path, token='', method='GET', body=None):
    require(origin in ['https://api.github.com', 'https://preloop.ai',
                       'https://token.actions.githubusercontent.com'] or
            (origin.startswith('https://') and
             urllib.parse.urlsplit(origin).hostname.endswith('.actions.githubusercontent.com')),
            'Unapproved API origin')
    require(path.startswith('/') and not path.startswith('//'), 'Unapproved API path')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None
    headers = {'Accept': 'application/json', 'Content-Type': 'application/json',
               'User-Agent': 'Briar-Preloop-Publisher/2'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(origin + path,
        data=None if body is None else json.dumps(body, allow_nan=False).encode(),
        method=method, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
            return strict_json(response.read())
    except urllib.error.HTTPError as error:
        raise InvalidReview('API failed HTTP' + str(error.code)) from None


def receipt_from_zip(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        require(archive.namelist() == ['receipt.json'], 'Unexpected receipt artifact files')
        return strict_json(archive.read('receipt.json'))

def verify_workload_jwt(token, jwks, binding, repository, run_id, now=None, workflow="preloop-review-publish.yml"):
    import time
    parts = token.split('.')
    require(len(parts) == 3 and len(token) <= 32_000, 'Invalid workload identity')
    def decode(value):
        return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    header, claims = (json.loads(decode(x)) for x in parts[:2])
    require(header.get('alg') == 'RS256', 'Unsupported workload signature')
    keys = [k for k in jwks['keys'] if k.get('kid') == header.get('kid') and k.get('kty') == 'RSA']
    require(len(keys) == 1, 'Unknown workload signing key')
    with tempfile.TemporaryDirectory() as temp:
        def der(tag, content):
            length = len(content)
            encoded = bytes([length]) if length < 128 else bytes([128 + ((length.bit_length() + 7) // 8)]) + length.to_bytes((length.bit_length() + 7) // 8, 'big')
            return bytes([tag]) + encoded + content
        def integer(value):
            number = decode(value).lstrip(b'\0') or b'\0'
            return der(2, (b'\0' if number[0] & 128 else b'') + number)
        require(256 <= len(decode(keys[0]['n'])) <= 1024, 'Unsafe RSA modulus size')
        encoded_key = Path(temp) / 'public.der'
        encoded_key.write_bytes(der(48, integer(keys[0]['n']) + integer(keys[0]['e'])))
        extracted = subprocess.run(['openssl', 'rsa', '-RSAPublicKey_in', '-inform', 'DER',
                                    '-in', str(encoded_key), '-pubout'], capture_output=True)
        require(extracted.returncode == 0, 'Invalid workload certificate')
        public_key = Path(temp) / 'public.pem'; public_key.write_bytes(extracted.stdout)
        signature = Path(temp) / 'signature'; signature.write_bytes(decode(parts[2]))
        verified = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(public_key),
                                   '-signature', str(signature)], input=(parts[0] + '.' + parts[1]).encode(),
                                  capture_output=True)
        require(verified.returncode == 0, 'Workload signature invalid')
    clock = int(time.time()) if now is None else now
    require(claims.get('iss') == 'https://token.actions.githubusercontent.com', 'Workload issuer mismatch')
    require(claims.get('aud') == 'briar-preloop-publication', 'Workload audience mismatch')
    require(claims['iat'] <= clock < claims['exp'], 'Workload token not current')
    require(claims.get('repository') == repository and
            str(claims.get('repository_id')) == str(binding['repository_id']), 'Workload repository mismatch')
    require(str(claims.get('run_id')) == str(run_id), 'Workload run mismatch')
    require(claims.get('ref') == 'refs/heads/' + binding['default_branch'], 'Untrusted workflow branch')
    require(workflow in ['preloop-review-publish.yml', 'preloop-review-trigger.yml'], 'Unapproved workflow')
    expected = repository + '/.github/workflows/' + workflow + '@refs/heads/' + binding['default_branch']
    require(claims.get('workflow_ref') == expected, 'Workload workflow mismatch')
    events = ['repository_dispatch', 'workflow_dispatch'] if workflow == 'preloop-review-publish.yml' else ['pull_request_target', 'workflow_dispatch']
    require(claims.get('event_name') in events, 'Unexpected workload event')
    return claims

def verify_workload(binding, repository, workflow="preloop-review-publish.yml"):
    url = os.environ['ACTIONS_ID_TOKEN_REQUEST_URL']
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname and parsed.hostname.endswith('.actions.githubusercontent.com') and
            parsed.username is None and parsed.port in [None, 443], 'Untrusted OIDC endpoint')
    separator = '&' if parsed.query else '?'
    endpoint = url + separator + 'audience=briar-preloop-publication'
    response = request('https://' + parsed.netloc, endpoint.split(parsed.netloc, 1)[1],
                       os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN'])
    jwks = request('https://token.actions.githubusercontent.com', '/.well-known/jwks', '')
    claims = verify_workload_jwt(response['value'], jwks, binding, repository, os.environ['GITHUB_RUN_ID'], workflow=workflow)
    require(claims['event_name'] == os.environ['GITHUB_EVENT_NAME'], 'Workload event changed')
    return claims

def binding_from_proof(package, root):
    binding = package['binding']
    raw = json.dumps(binding, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    digest = hashlib.sha256(b'\x00' + raw).digest()
    proof = package['proof']
    require(isinstance(proof, list) and len(proof) <= 32, 'Invalid binding proof')
    for step in proof:
        require(step['side'] in ['left', 'right'] and re.fullmatch('[0-9a-f]{64}', step['sha256']), 'Invalid proof step')
        sibling = bytes.fromhex(step['sha256'])
        left, right = (sibling, digest) if step['side'] == 'left' else (digest, sibling)
        digest = hashlib.sha256(b'\x01' + left + right).digest()
    require(digest.hex() == root, 'Repository binding is not in signed authority')
    return binding

def load_authority(folder, repository, now=None):
    folder = Path(folder)
    raw = (folder / 'preloop-publication-authority.json').read_bytes()
    key = folder / 'preloop-publication-key.pub'
    fingerprint = subprocess.check_output(['ssh-keygen', '-lf', str(key)], text=True).split()[1]
    require(fingerprint == KEY, 'Publisher authority key changed')
    with tempfile.TemporaryDirectory() as temp:
        signers = Path(temp) / 'signers'
        signers.write_text('ajlennon@dynamicdevices.co.uk ' + key.read_text().strip() + '\n')
        p = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', str(signers), '-I',
                            'ajlennon@dynamicdevices.co.uk', '-n', NAMESPACE, '-s',
                            str(folder / 'preloop-publication-authority.json.sig')], input=raw,
                           capture_output=True)
        require(p.returncode == 0, 'Publisher authority signature invalid')
    grant = json.loads(raw)
    clock = now or dt.datetime.now(dt.timezone.utc)
    authority = grant['publisher_authority']
    issued = dt.datetime.fromisoformat(authority['issued_at'])
    expires = dt.datetime.fromisoformat(authority['expires_at'])
    require(issued <= clock < expires, 'Publisher authority not currently valid')
    require(authority['non_delegable'] is True, 'Publisher grant must be non-delegable')
    if 'bindings_root' in authority:
        package = json.loads((folder / 'preloop-binding.json').read_text())
        binding = binding_from_proof(package, authority['bindings_root'])
        require(binding['repository'] == repository, 'Binding belongs to another repository')
    else:
        binding = next((b for b in authority['bindings'] if b['repository'] == repository), None)
    require(binding is not None, 'Repository not enrolled in publisher authority')
    for rel, expected in authority['files'].items():
        require(hashlib.sha256((folder.parent / rel).read_bytes()).hexdigest() == expected,
                'Publisher code/workflow changed since approval')
    require(set(authority.get('git_blobs', {})) == set(authority['files']), 'Missing exact source blob manifest')
    return {**binding, 'publication_enabled': authority.get('publication_enabled', False),
            'approved_files': authority['files'], 'approved_blobs': authority['git_blobs'],
            'native_ci_contract': authority.get('native_ci_contract'),
            'approved_workflow_sha256': authority['files']['.github/workflows/preloop-review-publish.yml']}

def verify_sources(github, binding, revision, paths):
    require(re.fullmatch('[0-9a-f]{40}', revision) is not None, 'Invalid workflow revision')
    # One authenticated commit-tree read normally replaces one API call per
    # file. A truncated GitHub tree uses the established exact-content fallback.
    tree = github('/repos/' + binding['repository'] + '/git/trees/' + revision + '?recursive=1')
    if tree.get('truncated') is False:
        entries = {entry['path']: entry for entry in tree['tree']}
        for path in paths:
            require(path in binding['approved_files'] and path in binding['approved_blobs'], 'Source not approved')
            entry = entries.get(path, {})
            require(entry.get('type') == 'blob' and entry.get('sha') == binding['approved_blobs'][path],
                    'Running source differs from signed source manifest')
        return
    for path in paths:
        expected = binding['approved_files'].get(path)
        require(expected is not None, 'Source not approved')
        source = github('/repos/' + binding['repository'] + '/contents/' + path + '?ref=' + revision)
        require(source.get('encoding') == 'base64', 'Unsupported source representation')
        require(hashlib.sha256(base64.b64decode(source['content'])).hexdigest() == expected,
                'Trigger source differs from approved code')

def download_trigger_artifact(repository, artifact_id, github_token):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None
    require(type(artifact_id) is int and artifact_id > 0, 'Invalid artifact ID')
    url = 'https://api.github.com/repos/' + repository + '/actions/artifacts/' + str(artifact_id) + '/zip'
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + github_token,
                                                  'Accept': 'application/vnd.github+json'})
    opener = urllib.request.build_opener(NoRedirect)
    try:
        response = opener.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        require(error.code == 302, 'Artifact download failed')
        location = urllib.parse.urlsplit(error.headers.get('Location', ''))
        require(location.scheme == 'https' and location.hostname and
                (location.hostname.endswith('.blob.core.windows.net') or
                 location.hostname.endswith('.actions.githubusercontent.com') or
                 location.hostname == 'objects.githubusercontent.com') and
                location.username is None and location.port in [None, 443], 'Untrusted artifact download host')
        # Never forward GitHub credentials to signed storage URLs or another redirect.
        response = opener.open(urllib.request.Request(location.geturl()), timeout=30)
    with response:
        data = response.read()
    return receipt_from_zip(data)

def trigger_workflow_sha(run, receipt, binding, head):
    # pull_request_target executes the trusted BASE revision, not the PR head.
    # This correction follows cursor-config PR306 at e82ebcb81255a4494c3bdefc1d96e2a0e45e62a2.
    require(run['event'] in ['pull_request_target', 'workflow_dispatch'], 'Unexpected trigger event')
    require(run.get('repository', {}).get('id') == binding['repository_id'], 'Wrong trigger repository')
    workflow_sha = run['head_sha']
    require(re.fullmatch('[0-9a-f]{40}', workflow_sha) and
            receipt.get('workflow_sha') == workflow_sha,
            'Trigger workflow revision mismatch')
    return workflow_sha
