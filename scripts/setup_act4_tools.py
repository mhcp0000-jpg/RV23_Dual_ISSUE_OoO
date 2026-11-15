"""Download verified portable tools pinned by official ACT4 4.1.0."""
import concurrent.futures
import hashlib
import json
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from sim_runner import ROOT,DEV,dump,sha

folder=ROOT/'out/act4/setup';folder.mkdir(parents=True,exist_ok=True)
specs=[('oneclick/rubyinstaller2','RubyInstaller-3.4.10-1','rubyinstaller-3.4.10-1-x64.7z','C:/rv_toolchains/ruby-act4'),
       ('astral-sh/uv','0.11.33','uv-x86_64-pc-windows-msvc.zip','C:/rv_toolchains/uv-0.11.33')]
def fetch(spec):
    repo,tag,name,destination=spec
    meta=json.load(urllib.request.urlopen(f'https://api.github.com/repos/{repo}/releases/tags/{tag}',timeout=30))
    asset=next(asset for asset in meta['assets'] if asset['name']==name)
    archive=Path('C:/rv_toolchains/downloads')/name
    expected=asset['digest'].removeprefix('sha256:')
    if not archive.exists() or sha(archive)!=expected:
        with urllib.request.urlopen(asset['browser_download_url'],timeout=120) as source:
            archive.write_bytes(source.read())
    assert sha(archive)==expected
    target=Path(destination);target.mkdir(parents=True,exist_ok=True)
    if archive.suffix=='.zip':
        with zipfile.ZipFile(archive) as zipped:zipped.extractall(target)
    else:
        with (folder/'ruby_extract.log').open('w',encoding='utf-8') as stream:
            subprocess.run([str(DEV/'cmake.exe'),'-E','tar','xf',str(archive)],cwd=target,
                           stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=180)
    return dict(repository=repo,tag=tag,url=asset['browser_download_url'],sha256=expected,destination=destination)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:records=list(pool.map(fetch,specs))
dump(folder/'portable_tools.json',dict(passed=True,generator_sha256=sha(__file__),tools=records))
print('PASS verified ACT4 uv/Ruby portable tool downloads',flush=True)
