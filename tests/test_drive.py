import io
import pytest
from lusid_mock.models.drive import ScanState


def _upload(client, path="/WIG/inbound/test.dat", content=b"hello"):
    return client.post(
        "/drive/api/files",
        data={"path": path},
        files={"file": ("test.dat", io.BytesIO(content), "application/octet-stream")},
    )


def test_upload_returns_201(client):
    r = _upload(client)
    assert r.status_code == 201
    body = r.json()
    assert "id" in body
    assert body["path"] == "/WIG/inbound/test.dat"
    assert body["size"] == 5


def test_upload_scan_state_is_scanning(client, app):
    r = _upload(client)
    file_id = r.json()["id"]
    f = app.state.drive_store.get(file_id)
    assert f.scan_state == ScanState.SCANNING


def test_get_contents_returns_423_while_scanning(client):
    r = _upload(client)
    file_id = r.json()["id"]
    r2 = client.get(f"/drive/api/files/{file_id}/contents")
    assert r2.status_code == 423


def test_get_contents_returns_clean_after_scan(client, app):
    r = _upload(client)
    file_id = r.json()["id"]
    app.state.drive_store.set_scan_state(file_id, ScanState.CLEAN)
    r2 = client.get(f"/drive/api/files/{file_id}/contents")
    assert r2.status_code == 200
    assert r2.content == b"hello"


def test_get_contents_returns_410_for_malware(client, app):
    r = _upload(client)
    file_id = r.json()["id"]
    app.state.drive_store.set_scan_state(file_id, ScanState.MALWARE)
    r2 = client.get(f"/drive/api/files/{file_id}/contents")
    assert r2.status_code == 410


def test_get_contents_returns_404_unknown(client):
    r = client.get("/drive/api/files/no-such-id/contents")
    assert r.status_code == 404


def test_delete_file(client, app):
    r = _upload(client)
    file_id = r.json()["id"]
    r2 = client.delete(f"/drive/api/files/{file_id}")
    assert r2.status_code == 204
    assert app.state.drive_store.get(file_id) is None


def test_delete_unknown_returns_404(client):
    r = client.delete("/drive/api/files/no-such-id")
    assert r.status_code == 404


def test_malware_pattern_config(client, app):
    from lusid_mock.models.control import ScenarioConfig
    app.state.config = ScenarioConfig(malware_path_patterns=["*malware*"], virus_scan_delay_s=0)
    r = _upload(client, path="/WIG/malware/evil.dat")
    file_id = r.json()["id"]
    import time; time.sleep(0.05)
    f = app.state.drive_store.get(file_id)
    assert f.scan_state == ScanState.MALWARE
