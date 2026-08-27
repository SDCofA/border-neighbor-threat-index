from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "bnti_update.yml").read_text(encoding="utf-8")


def test_update_workflow_exposes_failures_and_runs_tests():
    assert "python -m pytest -q" in WORKFLOW
    assert "python borderneighboursthreatindex.py" in WORKFLOW
    assert "Analyzer encountered issues but continuing" not in WORKFLOW
    assert "Always exit success" not in WORKFLOW
    assert WORKFLOW.count("continue-on-error: true") == 1


def test_pages_deploy_retries_without_reuploading_artifact():
    assert WORKFLOW.count("actions/upload-pages-artifact") == 1
    assert WORKFLOW.count("actions/deploy-pages@v5") == 2
    assert "if: steps.deployment.outcome == 'failure'" in WORKFLOW
    assert "steps.deployment_retry.outputs.page_url" in WORKFLOW
