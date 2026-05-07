import pytest
from fastapi.testclient import TestClient
from lusid_mock.app import create_app


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c
        c.post("/lusid-mock/control/reset")
