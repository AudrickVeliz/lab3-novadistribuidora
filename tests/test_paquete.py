import novadistribuidora


def test_paquete_instalado_con_su_version():
    # Comprueba que el paquete se instala desde src/ con la versión de pyproject.toml.
    assert novadistribuidora.__version__ == "0.1.0"
