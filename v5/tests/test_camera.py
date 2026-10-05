import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from social_v5.camera import CameraBridge
from social_v5.server import app


def test_frame_requires_both_owner_and_lease():
    camera=CameraBridge();camera.owner='owner';camera.lease='secret';camera.jpeg=b'frame'
    for owner,lease in [('other','secret'),('owner',''),('owner','wrong')]:
        with pytest.raises(HTTPException):camera.frame(owner,lease)
    assert camera.frame('owner','secret')==b'frame'
    camera.stop('other','secret')
    assert camera.lease=='secret'
    camera.stop('owner','secret')
    with pytest.raises(HTTPException):camera.frame('owner','secret')


def test_camera_rejects_cross_site_and_remote_access(monkeypatch):
    monkeypatch.delenv('SOCIAL_API_TOKEN',raising=False)
    client=TestClient(app)
    assert client.post('/v1/camera/start',headers={'origin':'https://example.com'}).status_code==403
    assert client.get('/v1/camera/frame').status_code==410
    remote=TestClient(app,client=('192.168.1.20',12345))
    assert remote.post('/v1/camera/start').status_code==403
