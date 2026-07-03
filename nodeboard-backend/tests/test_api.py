from app.main import app, health
from app.schemas import BoardStateSave


def test_health_and_routes():
    assert health() == {"status": "ok"}
    paths = {route.path for route in app.routes}
    assert "/api/boards" in paths
    assert "/api/boards/{board_id}/state" in paths


def test_state_contract():
    state = BoardStateSave.model_validate({
        "nodes": [{
            "id": "node-1", "type": "card", "x": 10, "y": 20,
            "w": 280, "title": "Nodo", "ports": [], "blocks": [], "stages": [],
        }],
        "edges": [],
    })
    assert state.nodes[0].title == "Nodo"
