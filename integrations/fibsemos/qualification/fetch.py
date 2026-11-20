"""Anonymous exact-byte fetch; no payload import, archive extraction or execution."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from artifacts import SOURCE_BYTES, SOURCE_COMMIT, SOURCE_SHA256, read_regular, require

REGISTRY = 'registry-1.docker.io'
CDN = {'production.cloudflare.docker.com', 'production.cloudfront.docker.com'}
HOSTS = {REGISTRY, 'auth.docker.io', 'files.pythonhosted.org', 'codeload.github.com'} | CDN


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def request(url, token=None):
    parsed = urlsplit(url)
    require(parsed.scheme == 'https' and not parsed.username and not parsed.password
            and not parsed.fragment and parsed.port in (None, 443) and parsed.hostname in HOSTS,
            'unapproved HTTPS fetch authority')
    require(not token or parsed.hostname == REGISTRY, 'registry token cannot leave registry')
    headers = {'User-Agent': 'vSEM-approved-M05B1-qualification'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    return OPENER.open(urllib.request.Request(url, headers=headers), timeout=60)


def download(spec, directory, token=None):
    require(re.fullmatch(r'[A-Za-z0-9_.+-]+', spec['filename']) is not None, 'unsafe input filename')
    path = Path(directory) / spec['filename']
    require(not path.exists(), 'fresh fetch destination required')
    try:
        response = request(spec['url'], token)
    except urllib.error.HTTPError as error:
        require(error.code in (301, 302, 303, 307, 308)
                and urlsplit(spec['url']).hostname == REGISTRY, 'unapproved fetch redirect/status')
        destination = error.headers.get('Location', '')
        require(urlsplit(destination).hostname in CDN, 'unapproved registry CDN')
        response = request(destination)  # Do not forward the anonymous registry token.
    temporary = path.with_name(path.name + '.part')
    digest, total = hashlib.sha256(), 0
    with response, temporary.open('xb') as output:
        while True:
            chunk = response.read(1024**2)
            if not chunk:
                break
            total += len(chunk)
            require(total <= spec['size'], 'download exceeded exact input size')
            digest.update(chunk)
            output.write(chunk)
    require(total == spec['size'] and digest.hexdigest() == spec['sha256'], 'download identity mismatch')
    temporary.rename(path)
    return {'filename': path.name, 'size': total, 'sha256': digest.hexdigest()}


def fetch_inputs(approved, destination):
    destination = Path(destination)
    (destination / 'wheels').mkdir()
    (destination / 'oci').mkdir()
    specs = [(r['wheel'], destination / 'wheels', False) for r in approved['records']]
    specs.append(({'filename': 'upstream.zip', 'size': SOURCE_BYTES, 'sha256': SOURCE_SHA256,
                   'url': 'https://codeload.github.com/fibsem-os/fibsem-os/zip/' + SOURCE_COMMIT},
                  destination, False))
    base = approved['base_environment']
    for index, item in enumerate([base['config'], *base['layers']]):
        digest = item['digest']
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', digest) is not None, 'bad OCI digest')
        specs.append(({'filename': digest[7:] + ('.json' if index == 0 else '.tar.gz'),
                       'size': item['size'], 'sha256': digest[7:],
                       'url': 'https://' + REGISTRY + '/v2/library/python/blobs/' + digest},
                      destination / 'oci', True))
    with request('https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull') as response:
        raw = response.read(1024**2 + 1)
    require(len(raw) <= 1024**2, 'registry token response too large')
    token = json.loads(raw)['token']  # Anonymous public-read scope, memory only.
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(download, spec, folder, token if registry else None): spec
                for spec, folder, registry in specs}
        for future in as_completed(jobs):
            try:
                results.append(future.result())
            except Exception as error:
                # Exception URLs can contain temporary CDN signatures: record only type/name.
                errors.append({'filename': jobs[future]['filename'], 'error_type': type(error).__name__})
    require(not errors, 'frozen input fetch failed: ' + json.dumps(errors))
    config = json.loads(read_regular(destination / 'oci' / (base['config']['digest'][7:] + '.json'),
                                     expected_sha=base['config']['digest'][7:],
                                     expected_size=base['config']['size']))
    require(config['architecture'] == 'amd64' and config['os'] == 'linux', 'wrong OCI platform')
    return sorted(results, key=lambda r: r['filename']), config
