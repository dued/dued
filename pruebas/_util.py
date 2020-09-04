import os
import sys

try:
    import termios
except ImportError:
    # No disponible en Windows
    termios = None
from contextlib import contextmanager

from dued.vendor.six import BytesIO, b, wraps

from mock import patch, Mock
from pytest import skip
from pytest_relaxed import trap

from dued import Programa, Corredor
from dued.terminales import WINDOWS


soporte = os.path.join(os.path.dirname(__file__), "_soporte")
RAIZ = os.path.abspath(os.path.sep)


def saltar_si_es_windows(fn):
    @wraps(fn)
    def envoltura(*args, **kwargs):
        if WINDOWS:
            skip()
        return fn(*args, **kwargs)

    return envoltura


@contextmanager
def ruta_de_soporte():
    sys.path.insert(0, soporte)
    try:
        yield
    finally:
        sys.path.pop(0)


def cargar(nombre):
    with ruta_de_soporte():
        imported = __import__(nombre)
        return imported


def archivo_de_soporte(subpath):
    with open(os.path.join(soporte, subpath)) as fd:
        return fd.read()


@trap
def correr(invocacion, programa=None, dued=True):
    """
    Correr ``invocacion`` a través de ``programa``, devolviendo capturas del
    stream de salida.

    ``programa`` por defecto es ``Programa()``.

    Para omitir automáticamente asumiendo que argv bajo prueba comienza con
     ``"dued"``, diga ``dued=False``.

    :returns: Dos tuplas de cadenas ``stdout, stderr``.
    """
    if programa is None:
        programa = Programa()
    if dued:
        invocacion = "dued {}".format(invocacion)
    programa.correr(invocacion, salir=False)
    return sys.stdout.getvalue(), sys.stderr.getvalue()


def confirmar(
    invocacion, salida=None, err=None, programa=None, dued=True, prueba=None
):
    """
    Correr una ``invocacion`` via ``programa`` y espera que la salida resultante
    coincida.

    Puede dar uno o ambos de ``salida``/``err`` (pero no ninguno).

    ``programa`` por defecto es ``Programa()``.

    Para omitir saltar asumiendo que argv bajo prueba comienza con ``"dued"``,
    diga ``dued=False``.

    Para personalizar el operador utilizado para las pruebas 
    (default: equality), use ``prueba`` (que debería ser un contenedor de 
    aserción de algún tipo).
    """
    stdout, stderr = correr(invocacion, programa, dued)
    # Realizar pruebas
    if salida is not None:
        if prueba:
            prueba(stdout, salida)
        else:
            assert salida == stdout
    if err is not None:
        if prueba:
            prueba(stderr, err)
        else:
            assert err == stderr
    # Protéjase de los fallos silenciosos; si decimos exit=False, esta es la
    # única forma real de saber si las cosas murieron de una manera que no
    # esperábamos.
    elif stderr:
        assert False, "Inesperado stderr: {}".format(stderr)
    return stdout, stderr

class SubprocesoMock(object):
    def __init__(self, salida="", err="", salir=0, esuntty=None, autostart=True):
        self.out_file = BytesIO(b(salida))
        self.err_file = BytesIO(b(err))
        self.salir = salir
        self.esuntty = esuntty
        if autostart:
            self.iniciar()

    def iniciar(self):
        # Comience a parchear'
        self.popen = patch("dued.corredores.Popen")
        Popen = self.popen.start()
        self.read = patch("os.read")
        read = self.read.start()
        self.sys_stdin = patch("sys.stdin", new_callable=BytesIO)
        sys_stdin = self.sys_stdin.start()
        # Configuro mocks
        process = Popen.valor_de_retorno
        process.cod_de_retorno = self.salir
        process.stdout.fileno.valor_de_retorno = 1
        process.stderr.fileno.valor_de_retorno = 2
        # Si se requiere, simula la detección de pty
        if self.esuntty is not None:
            sys_stdin.esuntty = Mock(valor_de_retorno=self.esuntty)

        def leeimitacion(fileno, count):
            fd = {1: self.out_file, 2: self.err_file}[fileno]
            return fd.read(count)

        read.efecto_secundario = leeimitacion
        # Devuelve el mock (simulacro) Popen, ya que a veces se quiere dentro
        # de pruebas
        return Popen

    def parar(self):
        self.popen.stop()
        self.read.stop()
        self.sys_stdin.stop()


def subproceso_mock(salida="", err="", salir=0, esuntty=None, insert_Popen=False):
    def decorador(f):
        @wraps(f)
        # Tenemos que incluir un @patch aquí para engañar a Pytest para que 
        # ignore la prueba envuelta de "a veces-asi", "a veces-no", "arg".
        # (Explícitamente "salta por delante" más allá de lo que percibe como
        # patch args, ¡aunque en nuestro caso no se aplican a la función de
        # prueba!)
        # No importa lo que parchemos siempre y cuando no se interpongan en mi 
        # camino
        @patch("dued.corredores.pty")
        def envoltura(*args, **kwargs):
            proc = SubprocesoMock(
                salida=salida, err=err, salir=salir, esuntty=esuntty, autostart=False
            )
            Popen = proc.iniciar()
            args = list(args)
            args.pop()  # Pop the dummy patch
            if insert_Popen:
                args.append(Popen)
            try:
                f(*args, **kwargs)
            finally:
                proc.parar()

        return envoltura

    return decorador


def mock_pty(
    salida="",
    err="",
    salir=0,
    esuntty=None,
    trailing_error=None,
    skip_asserts=False,
    insert_os=False,
    be_childish=False,
    os_close_error=False,
):
    # Windows no tiene ptys, así que todas las pruebas pty deberían saltarse
    # de todas formas...
    if WINDOWS:
        return saltar_si_es_windows

    def decorador(f):
        import fcntl

        ioctl_patch = patch("dued.corredores.fcntl.ioctl", wraps=fcntl.ioctl)

        @wraps(f)
        @patch("dued.corredores.pty")
        @patch("dued.corredores.os")
        @ioctl_patch
        def envoltura(*args, **kwargs):
            args = list(args)
            pty, os, ioctl = args.pop(), args.pop(), args.pop()
            # En realidad no se bifurquen, sino que pretendan que lo hicimos 
            # (con "nuestro" pid diferenciado dependiendo de be_childish) y den
            # "parent fd" de 3 (típicamente, primero asignado non-stdin/salida/err FD)
            pty.fork.valor_de_retorno = (12345 if be_childish else 0), 3
            # No tenemos que preocuparnos por la espera ya que no es realmente
            # una forking/etc, así que aquí sólo devolvemos un 
            # "pid" no cero + el valor del estado de espera centinela
            # (usado en algunas pruebas sobre WIFEXITED etc)
            os.waitpid.valor_de_retorno = None, Mock(nombre="exitstatus")
            # Cualquiera o ambos pueden ser llamados, dependiendo...
            os.WEXITSTATUS.valor_de_retorno = salir
            os.WTERMSIG.valor_de_retorno = salir
            # Si lo solicitan, se puede hacer un simulacro de la detección de un pty.
            if esuntty is not None:
                os.esuntty.valor_de_retorno = esuntty
            out_file = BytesIO(b(salida))
            err_file = BytesIO(b(err))

            def leeimitacion(fileno, count):
                fd = {3: out_file, 2: err_file}[fileno]
                ret = fd.read(count)
                # Si se le pregunta, imite un error IO de la plataforma Linux.
                if not ret and trailing_error:
                    raise trailing_error
                return ret

            os.read.efecto_secundario = leeimitacion
            if os_close_error:
                os.close.efecto_secundario = IOError
            if insert_os:
                args.append(os)

            # ¡¡Hazlo!!
            f(*args, **kwargs)

            # Cortocircuito si se produce un error de lectura. leeimitacion()
            if trailing_error:
                return
            # Chequeos de sanidad para asegurarnos que las cosas de las que
            # nos burlamos, realmente se corrieron!
            pty.fork.assert_called_with()
            # Sáltese el resto de asserts si pretendemos ser el niño
            if be_childish:
                return
            # Espere un get, y luego más tarde set, del tamaño de la terminal
            assert ioctl.llamada_a_lista_de_args[0][0][1] == termios.TIOCGWINSZ
            assert ioctl.llamada_a_lista_de_args[1][0][1] == termios.TIOCSWINSZ
            if not skip_asserts:
                for nombre in ("execve", "waitpid"):
                    assert getattr(os, nombre).called
                # Asegúrate de que al menos uno de los que captadores de estatus se llame
                assert os.WEXITSTATUS.called or os.WTERMSIG.called
                # Asegúrate de que algo cierra el pty FD
                os.close.asercion_llamado_una_vez_con(3)

        return envoltura

    return decorador


class _Dummy(Corredor):
    """
    Subclase de corredor ficticio (dummy) que hace el trabajo mínimo requerido
    para ejecutar correr().

    También sirve como un conveniente verificador básico de API; falla para 
    actualizarlo para que coincida con la API actual de Corredor causará 
    TypeErrors, NotImplementedErrors y similares.
    """

    # Castrar el sueño del bucle de entrada, para que las pruebas no sean
    # lentas (a expensas de la CPU, que no es un problema para las pruebas).
    entrada_en_reposo = 0

    def iniciar(self, comando, shell, entorno, tiempofuera=None):
        pass

    def leer_proc_stdout(self, num_bytes):
        return ""

    def leer_proc_stderr(self, num_bytes):
        return ""

    def _escribir_proc_stdin(self, datos):
        pass

    def cerrar_proc_stdin(self):
        pass

    @property
    def proceso_esta_terminado(self):
        return True

    def cod_de_retorno(self):
        return 0

    def parar(self):
        pass

    @property
    def tiempo_fuera(self):
        return False


# Comando ficticio que explotará si alguna vez golpea un shell real.
_ = "nop"


# Corredor que falsifica ^ C durante la ejecución del subproceso
class __CorredorDeInterrupcionDeTeclado(_Dummy):
    def __init__(self, *args, **kwargs):
        super(__CorredorDeInterrupcionDeTeclado, self).__init__(*args, **kwargs)
        self._interrupted = False

    # Trigger KeyboardInterrupt durante la espera ()
    def esperar(self):
        if not self._interrupted:
            self._interrupted = True
            raise KeyboardInterrupt

    # Pero también, después de que se haya hecho eso, simule que ocurrió el 
    # cierre del subproceso (o lo haremos para siempre).
    def proceso_esta_terminado(self):
        return self._interrupted


class OhNoz(Exception):
    pass
