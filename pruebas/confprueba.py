import logging
import os
import sys
import termios

from dued.vendor.six import iteritems
import pytest
from mock import patch

from _util import soporte


# pytest parece modificar el registro de modo que los registros de depuración
# de dued vayan a stderr, que luego es hella spam si uno está usando
# --capture = no (que es necesario para probar bajo nivel terminal IO cosas,
# ¡como lo hacemos nosotros!) explícitamente desactivamos el registro 
# predeterminado.
# NOTE: no hay mejor lugar para poner esto que aquí
# TODO: una vez que pytest -relajado funcione con pytest 3.3, vea si podemos 
# usar su nueva funcionalidad de registro para eliminar la necesidad de esto.
logging.basicConfig(level=logging.INFO)


@pytest.fixture
def restablecer_entorno():
    """
    Restablece `os.environ` a su estado anterior después de que finaliza la 
    prueba fijada.
    """
    entorno_viejo = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(entorno_viejo)


@pytest.fixture
def soporte_chdir():
    # Siempre hacer cosas relativas a pruebas/_soporte
    os.chdir(soporte)
    yield
    # Chdir volver a la raíz del proyecto para evitar problemas
    os.chdir(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def limpiar_modulos_sys():
    # TODO: _ posiblemente_ ¿podría ser más limpio registrar esto como 
    # 'finalizador'? no es que el rendimiento no sea legible aquí, es un
    #  accesorio que solo realiza desmontaje.
    yield
    # Elimine las colecciones de artefacto de prueba-soporte de sys.modules
    # para evitar el sangrado de estado entre pruebas; de lo contrario, las 
    # pruebas pueden pasar incorrectamente a pesar de no cargar/hacer cd
    # explícitamente para obtener los artefactos que llaman cargados.
    for nombre, modulo in iteritems(sys.modules.copy()):
        # Obtenga un valor __file__ ruta comparable, incluido el manejo de 
        # casos en los que es None en lugar de indefinido (¿parece nuevo en
        # Python 3.7?)
        if modulo and soporte in (getattr(modulo, "__file__", "") or ""):
            del sys.modules[nombre]


@pytest.fixture
def integracion(restablecer_entorno, soporte_chdir, limpiar_modulos_sys):
    yield


@pytest.fixture
def mock_termios():
    with patch("dued.terminales.termios") as mocked:
        # Asegúrese de que los termios simulados tengan valores 'reales'
        # para las constantes ... de lo contrario, hacer aritmética de bits
        # en Mocks es un poco frustrante.
        mocked.ECHO = termios.ECHO
        mocked.ICANON = termios.ICANON
        mocked.VMIN = termios.VMIN
        mocked.VTIME = termios.VTIME
        yield mocked
