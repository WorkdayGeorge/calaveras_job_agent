import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "browser_extension"


def test_extension_uses_active_tab_and_read_only_service_access():
    manifest = json.loads((ROOT / "manifest.json").read_text())

    assert manifest["manifest_version"] == 3
    assert "activeTab" in manifest["permissions"]
    assert "scripting" in manifest["permissions"]
    assert "<all_urls>" not in manifest.get("host_permissions", [])


def test_extension_has_manual_submit_and_sensitive_field_guards():
    script = (ROOT / "content.js").read_text()
    readme = (ROOT / "README.md").read_text()

    assert "SENSITIVE" in script
    assert "SUBMIT" in script
    assert "never submits an application" in readme
    assert "Fill This Application" in (ROOT / "popup.html").read_text()
