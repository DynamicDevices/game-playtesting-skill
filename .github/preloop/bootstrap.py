"""Run only signature-verified modules, under python3 -I -B. Assisted-by: Briar."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

KEY = 'SHA256:vBkafuWAZYu5NnpYdbW8z1ZbZp/VFuSl8mad9jo0UFc'
NAMESPACE = 'briar-preloop-publication'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate policy member')
        result[key] = value
    return result


def regular(root, relative):
    path = root / relative
    require(path.is_file() and path.resolve() == path.absolute(), 'Unsafe source path')
    return path.read_bytes()


def verified_sources(root):
    root = root.absolute()
    raw = regular(root, '.github/preloop-publication-authority.json')
    signature = regular(root, '.github/preloop-publication-authority.json.sig')
    key = regular(root, '.github/preloop-publication-key.pub')
    with tempfile.TemporaryDirectory(prefix='preloop-signature-') as folder:
        folder = Path(folder)
        public = folder / 'key.pub'
        public.write_bytes(key)
        observed = subprocess.check_output(['/usr/bin/ssh-keygen', '-lf', str(public), '-E', 'sha256'],
                                           text=True, timeout=15).split()[1]
        require(observed == KEY, 'Authority signer changed')
        signers = folder / 'signers'
        signers.write_bytes(b'ajlennon@dynamicdevices.co.uk ' + key.strip() + b'\n')
        detached = folder / 'signature'
        detached.write_bytes(signature)
        result = subprocess.run(['/usr/bin/ssh-keygen', '-Y', 'verify', '-f', str(signers),
            '-I', 'ajlennon@dynamicdevices.co.uk', '-n', NAMESPACE, '-s', str(detached)],
            input=raw, capture_output=True, timeout=15)
        require(result.returncode == 0, 'Authority signature invalid')
    grant = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda _: require(False, 'Nonfinite policy number'))
    authority = grant['publisher_authority']
    now = datetime.datetime.now(datetime.timezone.utc)
    require(datetime.datetime.fromisoformat(authority['issued_at']) <= now <
            datetime.datetime.fromisoformat(authority['expires_at']) and
            authority['non_delegable'] is True, 'Authority expired or delegable')
    files, blobs = authority['files'], authority['git_blobs']
    require(type(files) is dict and type(blobs) is dict and files and
            set(files) == set(blobs) and '.github/preloop/bootstrap.py' in files,
            'Incomplete source manifest')
    verified = {}
    for rel, expected in files.items():
        require(type(rel) is str and rel.startswith('.github/') and
                '..' not in Path(rel).parts and Path(rel).as_posix() == rel and
                not rel.endswith(('.pyc', '.pyo')), 'Unsafe manifest path')
        source = regular(root, rel)
        require(hashlib.sha256(source).hexdigest() == expected and
                hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest() == blobs[rel],
                'Unapproved source bytes: ' + rel)
        verified[rel] = source
    verified.update({'.github/preloop-publication-authority.json': raw,
        '.github/preloop-publication-authority.json.sig': signature,
        '.github/preloop-publication-key.pub': key})
    return verified


def main():
    require(sys.flags.isolated and sys.dont_write_bytecode, 'Use python3 -I -B')
    args = sys.argv[1:]
    require(args in [['publisher', 'authenticate'], ['publisher', 'publish'],
                     ['publisher', 'late-failure'], ['trigger', 'prepare'],
                     ['trigger', 'start'], ['trigger', 'startup'], ['finalize', 'prepare'],
                     ['finalize', 'release'], ['event']], 'Unknown entry point')
    files = verified_sources(Path.cwd())
    with tempfile.TemporaryDirectory(prefix='preloop-verified-') as folder:
        stage = Path(folder)
        for rel, raw in files.items():
            destination = stage / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        os.chdir(stage)
        sys.path.insert(0, str(stage / '.github/preloop'))
        if args == ['event']:
            import runtime
            runtime.record_trigger_event()
        else:
            target = stage / '.github/preloop' / (args[0] + '.py')
            sys.argv = [str(target), args[1]]
            runpy.run_path(str(target), run_name='__main__')


if __name__ == '__main__':
    main()
