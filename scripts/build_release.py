"""Build a hash-manifested, whitelist-only local release. Never publishes."""
import argparse
import hashlib
import json
import shutil
import tomllib
import zipfile
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main(label=None):
    version=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    if label is not None and not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}',label):
        raise ValueError('Release label must use lowercase letters, numbers or hyphens')
    release_name=f'panel-evidence-v{version}'+(f'-{label}' if label else '')
    target=ROOT/'dist'/release_name
    archive=ROOT/'dist'/f'{release_name}.zip'
    if target.exists() or archive.exists():
        raise FileExistsError('Existing releases are preserved; use a new --label')
    files=[ROOT/n for n in ['README.md','NOTICE.md','LICENSE','pyproject.toml','requirements-tested-windows.txt',
                            'run_demo.ps1','.gitignore','.gitattributes','.env.example','streamlit_app.py']]
    for folder in ['src/panel_rag','tests','sample_data','benchmarks','.github','.streamlit']:
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
                     and not any(part in p.parts for part in ['__pycache__','recordings','private'])
                     and p.suffix!='.pyc')
    # Review notes can contain private paths/thread references. Only these
    # explicitly reviewed public documents/media belong in a release.
    approved_docs=['01-documents.png','02-evidence.png','03-refusal.png','04-quality.png','architecture.png',
                   'case-study.md','clean-install.md','completion-audit.md','demo.srt','demo.webm','metrics.json',
                   'tested-environment.json','validation.md','audit-v051.md','audit-v051-metrics.json',
                   'handoff-v052.md','handoff-v052-metrics.json',
                   'demo_crowdworks_v052.mp4','demo_crowdworks_v052.srt','portfolio-final-metrics.json',
                   'public-release-check.md','public-release-metrics.json']
    files += [ROOT/'docs/portfolio'/name for name in approved_docs if (ROOT/'docs/portfolio'/name).is_file()]
    approved_edit=['README.md','editing-report.md','project.json','render.py',
                   'check_output.py','verify_playback.cjs','verification.json']
    files += [ROOT/'docs/portfolio/video_edit'/name for name in approved_edit
              if (ROOT/'docs/portfolio/video_edit'/name).is_file()]
    files += [ROOT/'docs/architecture.md',ROOT/'docs/architecture.svg',
              ROOT/'scripts/evaluate_benchmark.py',ROOT/'scripts/recheck_audit.py',ROOT/'scripts/report_audit.py',ROOT/'scripts/build_release.py']
    manifest=[]
    for p in sorted(set(files)):
        relative=p.relative_to(ROOT);dst=target/relative;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dst)
        manifest.append(dict(path=relative.as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
    payload=json.dumps(manifest,ensure_ascii=False,indent=2)
    if label is None:
        (ROOT/'MANIFEST.json').write_text(payload,encoding='utf-8')
    (target/'MANIFEST.json').write_text(payload,encoding='utf-8')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for item in manifest:z.write(target/item['path'],'panel-evidence/'+item['path'])
        z.write(target/'MANIFEST.json','panel-evidence/MANIFEST.json')
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist())==len(manifest)+1
        for item in manifest:
            assert hashlib.sha256(z.read('panel-evidence/'+item['path'])).hexdigest()==item['sha256']
        for name in z.namelist():
            parts=Path(name).parts
            assert not any(part in parts for part in ['data','eval','sources','.git','.venv'])
            assert not name.endswith('.pdf') or '/sample_data/pdfs/' in name
            if Path(name).suffix in ['.md','.py','.json','.toml','.txt','.yml']:
                text=z.read(name).decode('utf-8')
                assert not re.search(r'\bsk-[A-Za-z0-9_-]{20,}',text)
                assert not re.search(r'[A-Za-z]:[/\\]Users[/\\][^/\\]+',text)
    report=dict(version=version,files=len(manifest),zip_bytes=archive.stat().st_size,
                zip_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),checks='manifest / whitelist / no manufacturer PDFs / no key patterns or personal paths')
    (ROOT/'eval').mkdir(exist_ok=True)
    audit_name=f'release-audit-{label}.json' if label else 'release-audit.json'
    (ROOT/'eval'/audit_name).write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',help='Optional new package label; existing releases are never replaced')
    main(parser.parse_args().label)
