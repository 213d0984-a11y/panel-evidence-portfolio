"""Private reviewer notes must not enter a public distribution."""
import importlib.util
import zipfile
import pytest
from pathlib import Path


def test_release_includes_only_approved_portfolio_documents(tmp_path):
    source = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('release_test', source/'scripts/build_release.py')
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    release.ROOT = tmp_path
    files = ['README.md', 'NOTICE.md', 'LICENSE', 'requirements-tested-windows.txt',
             'run_demo.ps1', '.gitignore', '.gitattributes', '.env.example', 'streamlit_app.py',
             'docs/architecture.md', 'docs/architecture.svg', 'scripts/evaluate_benchmark.py',
             'scripts/recheck_audit.py', 'scripts/report_audit.py', 'scripts/build_release.py',
             'docs/portfolio/case-study.md','docs/portfolio/demo_crowdworks_v052.mp4',
             'docs/portfolio/demo_crowdworks_v052.srt','docs/portfolio/video_edit/project.json',
             'docs/portfolio/video_edit/render.py','docs/portfolio/public-release-check.md',
             'docs/portfolio/public-release-metrics.json']
    for relative in files:
        p = tmp_path/relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('Public fixture', encoding='utf-8')
    (tmp_path/'pyproject.toml').write_text('[project]\nversion="0.0.0"\n', encoding='utf-8')
    for name in ['independent-audit-private.txt', 'unreviewed.md']:
        (tmp_path/'docs/portfolio'/name).write_text('PRIVATE_REVIEW_MARKER', encoding='utf-8')
    (tmp_path/'docs/portfolio/video_edit/private-review.md').write_text('PRIVATE_REVIEW_MARKER',encoding='utf-8')
    release.main()
    with zipfile.ZipFile(tmp_path/'dist/panel-evidence-v0.0.0.zip') as archive:
        names = archive.namelist()
        assert 'panel-evidence/docs/portfolio/case-study.md' in names
        assert 'panel-evidence/docs/portfolio/demo_crowdworks_v052.mp4' in names
        assert 'panel-evidence/docs/portfolio/video_edit/render.py' in names
        assert 'panel-evidence/docs/portfolio/public-release-check.md' in names
        assert 'panel-evidence/docs/portfolio/public-release-metrics.json' in names
        assert not any('independent-audit' in name or 'unreviewed' in name for name in names)
        assert all(b'PRIVATE_REVIEW_MARKER' not in archive.read(name) for name in names)
    original=(tmp_path/'dist/panel-evidence-v0.0.0.zip').read_bytes()
    with pytest.raises(FileExistsError):
        release.main()
    release.main(label='portfolio')
    assert (tmp_path/'dist/panel-evidence-v0.0.0.zip').read_bytes()==original
    assert (tmp_path/'dist/panel-evidence-v0.0.0-portfolio.zip').is_file()
    with pytest.raises(ValueError):
        release.main(label='../outside')
