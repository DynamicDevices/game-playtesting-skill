"""Preserve exact signed policy bytes, including trailing newlines."""
import os
from pathlib import Path

policy = os.environ['PRELOOP_PUBLICATION_AUTHORITY']
signature = os.environ['PRELOOP_PUBLICATION_SIGNATURE']
if not policy or not signature:
    raise SystemExit('Missing exact signed service authority')
for name, value in [('preloop-publication-authority.json', policy),
                    ('preloop-publication-authority.json.sig', signature)]:
    with Path('.github', name).open('xb') as stream:
        stream.write(value.encode('utf-8'))
