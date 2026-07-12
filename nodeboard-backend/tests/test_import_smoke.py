"""Smoke test: verifica que app.main se importa sin NameError.

Detecta anotaciones de tipo que referencian nombres no importados en
runtime (e.g., `schemas.Foo` cuando solo `Foo` está importado).
"""


def test_app_main_imports_without_error():
    """Falla si cualquier módulo de app lanza NameError durante el import."""
    from app.main import app  # noqa: F401

    assert app is not None


def test_services_nodes_imports_without_error():
    """Falla si app.services.nodes lanza NameError durante el import."""
    import app.services.nodes as nodes_module

    assert hasattr(nodes_module, "move_node")
