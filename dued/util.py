from collections import namedtuple
from contextlib import contextmanager
import io
import logging
import os
import threading
import sys

# NOTE: Esta es la ubicación canónica para los módulos vendorizados
# utilizados-comúnmente, que es el único lugar que realiza este intento/excepto
# para permitir que Dued reempaquetado funcione (por ejemplo, paquetes de 
# distribución que eliminan los bits bndorizados y, por lo tanto, deben importar
# nuestro material 'vendorizado' del entorno general.)
# Todos los demás usos de six, Lexicon, etc. deberían hacer 'from .util import six' etc.
# Nos ahorra tener que actualizar la misma lógica en una docena de lugares.
# TODO: ¿tendría más sentido poner _en_ dued.vendor? De esa manera, las líneas de
# importación que ahora leen 'from .util import <terceros>' serían más obvias. 
# Requiere que los empaquetadores dejen dued/vendor/ __ init__.py solo aunque
# NOTE: también tomamos los componentes internos de six.moves directamente para
# que otros módulos no tengan que preocuparse por eso (no pueden confiar en los
# 'six' importados directamente a través del acceso a atributos, ya que six.moves
# importa travesuras).
try:
    from .vendor.lexicon import Lexicon  # noqa
    from .vendor import six
    from .vendor.six.moves import reduce  # noqa

    if six.PY3:
        from .vendor import yaml3 as yaml  # noqa
    else:
        from .vendor import yaml2 as yaml  # noqa
except ImportError:
    from lexicon import Lexicon  # noqa
    import six
    from six.moves import reduce  # noqa
    import yaml  # noqa


LOG_FORMAT = "%(nombre)s.%(modulo)s.%(nombreFunc)s: %(mensaje)s"


def habilita_logs():
    logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)

# Permitir la depuración desde-el-principio (vs alternar durante la carga de
# modulos artefactos) a través de shell var entorno.
if os.environ.get("DUED_DEBUG"):
    habilita_logs()

# Agregue funciones de rlogeo de nivel superior al hangar global. Meh.
log = logging.getLogger("dued")
for x in ("debug",):
    globals()[x] = getattr(log, x)

def clave_orden_del_nombre_de_artefacto(nombre):
    """
    Tupla de clave de retorno para usar ordenando los nombres de artefactos
    con puntos, por ejemplo, `sorted`.

    .. versionadded:: 1.0
    """
    partes = nombre.split(".")
    return (
        # Primero agrupa/ordena por componentes de ruta sin-rama. Esto mantiene
        # todo agrupado en su jerarquía y, de paso, coloca los artefactos de
        # nivel-superior (cuyo set de ruta sin-rama es la lista vacía) primero,
        # donde los queremos.
        partes[:-1],
        # Luego ordenamos lexicográficamente por el nombre del artefacto real
        partes[-1],
    )


# TODO: Haz parte de la API pública en algún momento
@contextmanager
def cd(where):
    cwd = os.getcwd()
    os.chdir(where)
    try:
        yield
    finally:
        os.chdir(cwd)


def tiene_fileno(stream):
    """
    Determine claramente si ``stream`` tiene un ``.fileno()`` útil.

    .. note::
        Esta función ayuda a determinar si un objeto como-archivo dado se
        puede usar con varios módulos y funciones orientados-a-terminal como
        `select`,`termios` y `tty`. Para la mayoría de ellos, un fileno es
        todo lo que se requiere; Funcionarán incluso si ``stream.esuntty()``
        es `` False ''.

    :param stream: Un objeto como-archivo.

    :returns:
        ``True`` si ``stream.fileno()`` retorna in entero, de lo contrario 
        ``False`` (esto incluye cuando ``stream`` carece de un método 
        ``fileno``).

    .. versionadded:: 1.0
    """
    try:
        return isinstance(stream.fileno(), int)
    except (AttributeError, io.UnsupportedOperation):
        return False


def esuntty(stream):
    """
    Determine claramente si el ``stream`` es un TTY.

    Específicamente, primero intenta llamar a ``stream.esuntty()``, y si eso
    falla (por ejemplo, debido a la falta del método por completo) recurre a
    `os.isatty`.

    .. note::
        La mayoría de las veces, en realidad no nos importa el verdadero 
        TTY-ness, sino simplemente si la transmisión parece tener un fileno
        (con la prueba de si `tiene_fileno`). Sin embargo, en algunos casos 
        (notablemente el uso de `pty.fork` para presentar un pseudoterminal
        local) necesitamos saber si una secuencia dada tiene un número de 
        archivo válido pero *no* está vinculado a una terminal real. Por lo
        tanto, esta función.

    :param stream: Un objeto como-archivo.

    :returns:
        Un booleano dependiendo del resultado de llamar a ``.esuntty()`` y/o
        `os.isatty`.

    .. versionadded:: 1.0
    """
    # Si hay *es* un .esuntty, pregúntelo.
    if hasattr(stream, "esuntty") and callable(stream.esuntty):
        return stream.esuntty()
    # Si no lo hay, mira si tiene fileno, y si es así pregunta a os.esuntty
    elif tiene_fileno(stream):
        return os.isatty(stream.fileno())
    # Si llegamos aquí, nada de lo anterior funcionó, por lo que es razonable
    # suponer que la maldita cosa no es un TTY real.
    return False


def codificar_salida(cadena, codificacion):
    """
    Transforma el objeto ``cadena`` en forma de cadena en bytes mediante 
    ``encoding``.

    :returns: una cadena de bytes (``str`` en Python 2, ``bytes`` en 
    Python 3.)

    .. versionadded:: 1.0
    """
    # Codifique solo en Python 2, debido al problema común donde sys.stdout/err
    # en Python 2 terminan usando sys.getdefaultencoding(), que con frecuencia
    # NO es lo mismo que la codificación de terminal local real (reflejada
    # como sys.stdout. codificación). Es decir. incluso 
    # cuando sys.stdout.codificacion es UTF-8, ascii todavía se usa y explota.
    # Python 3 no tiene este problema, por lo que delegamos la codificación a
    # las clases io. * Writer involucradas.

    if six.PY2:
        # TODO: dividir la configuración de codificación (actualmente, la que se
        # nos da, a menudo un valor de Corredor.codificación, se usa tanto para
        # la entrada como para la salida), solo use la de 'codificación local' aquí.
        cadena = cadena.encode(codificacion)
    return cadena


def lineadeayuda(obj):
    """
    Produce la primera línea de textdocs de un objeto o una cadena vacía.

    .. versionadded:: 1.0
    """
    textdocs = obj.__doc__
    if not textdocs or textdocs == type(obj).__doc__:
        return None
    return textdocs.lstrip().splitlines()[0]


class hilo_de_manejo_de_excepciones(threading.Thread):
    """
    Controlador de SubP que facilita a los padres el manejo de excepciones
    de SubP.

    Basado en parte en ThreadHandler de Fabric 1. Consulte también el número
    204 de Fabric GH.

    Cuando se usa directamente, se puede usar en lugar de un
    ``threading.Thread``.
    Si tiene una subclase, la subclase debe hacer una de las siguientes cosas:

    - suministrar ``objetivo`` a ``__init__``
    - define ``_corre()`` en lugar de ``correr()``

    Esto se debe a que el objetivo de este hilo es ajustar el comportamiento
    alrededor de la ejecución del hilo; Las subclases no pudieron redefinir
    ``correr()`` sin romper esa funcionalidad.

    .. versionadded:: 1.0
    """

    def __init__(self, **kwargs):
        """
        Cree una nueva instancia de subproceso de manejo-de-excepciones.

        Toma todos los argumentos de palabras clave `threading.Thread`,
        a través de ``** kwargs`` para una visualización más fácil de la
        identidad del hilo al generar excepciones capturadas.
        """
        super(hilo_de_manejo_de_excepciones, self).__init__(**kwargs)
        # No hay registro de por qué, pero Fabric usó hilos de demonio desde
        # que se cambió de select.select, así que sigamos haciéndolo.
        self.daemon = True
        # seguimiento de excepciones planteadas en correr()
        self.kwargs = kwargs
        self.exc_info = None

    def correr(self):
        try:
            # Permitir que las subclases se implementen usando el enfoque
            # "anular el cuerpo de correr()" para trabajar, usando _corre()
            # en lugar de correr(). Si ese no parece ser el caso, entonces
            # asuma que estamos siendo usados directamente y simplemente 
            # usemos super() nosotros mismos.

            if hasattr(self, "_corre") and callable(self._corre):
                # TODO: esto podría ser:
                # - worker io sin 'resultado' (siempre local)
                # - worker del túnel, también sin 'resultado' (también 
                #   siempre local)
                # - subproceso concurrente correr(), sudo(), put(), etc., con
                #   un resultado (no necesariamente local; podría querer ser 
                #   un subproc o lo que sea eventualmente)
                # TODO: entonces, ¿cuál es la mejor manera de agregar un
                # condicionalmente "valor de captura de resultado de algún tipo"?
                # - actualice para que todos los casos de uso usen subclases,
                #   agregue funcionalidad junto con self.exception() que es
                #   para el resultado de _corre()
                # - dividir la clase a la que no le importa el resultado de
                #   _corre() y dejar que continúe actuando como un hilo normal
                #  (bah)
                # - suponga que el caso correr/sudo/etc usará una cola dentro
                #   de su cuerpo de worker, ortogonal a cómo funciona el 
                #   manejo de excepciones
                self._corre()
            else:
                super(hilo_de_manejo_de_excepciones, self).run()
        except BaseException:
            # Almacenar para volver a subir más tarde
            self.exc_info = sys.exc_info()
            # E iniciar sesión ahora, en caso de que nunca lleguemos más tarde
            # (por ejemplo, si la ejecución del programa se cuelga esperando
            # que hagamos algo)
            msj = "Se encontró una excepción {!r} en el hilo de {!r}"
            # Nombre es el dunder-nombre de la función de destino, o simplemente
            # "_corre" si corriéramos por subclase.
            nombre = "_corre"
            if "objetivo" in self.kwargs:
                nombre = self.kwargs["objetivo"].__name__
            debug(msj.format(self.exc_info[1], nombre))  # noqa

    def excepcion(self):
        """
        Si ocurrió una excepción, devuelve una `.EnvolturaDeExcepcion` a su
        alrededor.

        :returns:
            Una `.EnvolturaDeExcepcion` que administra el resultado de 
            `sys.exc_info`, si se generó una excepción durante la ejecución
            del hilo. Si no ocurrió ninguna excepción, devuelve ``None`` en
            su lugar.

        .. versionadded:: 1.0
        """
        if self.exc_info is None:
            return None
        return EnvolturaDeExcepcion(self.kwargs, *self.exc_info)

    @property
    def esta_muerto(self):
        """
        Devuelve ``True`` si no está vivo y tiene una excepción almacenada.

        Se utiliza para detectar subprocesos que se han exceptuado y cerrado.

        .. versionadded:: 1.0
        """
        # NOTE: parece muy poco probable que un hilo aún pueda estar 
        # is_alive() (estoy_vivo) pero también haya encontrado una excepción.
        # Pero hey. ¿Por qué no ser minucioso?
        return (not self.is_alive()) and self.exc_info is not None

    def __repr__(self):
        # TODO: refuerza esto más
        return self.kwargs["objetivo"].__name__

# NOTE: La EnvolturaDeExcepcion definida aquí, no en excepciones.py, para 
# evitar problemas de dependencia circular (por ejemplo, las subclases de
# Falla necesitan usar algunos bits de este módulo ...)
#: Una namedtuple que envuelve una excepción transmitida-por-un-hilo
#: y los argumentos de ese hilo.
#: Se utiliza principalmente como un intermedio entre 
#: `.hilo_de_manejo_de_excepciones` (que conserva las excepciones iniciales) y
#: `.ExcepcionDeHilo` (que contiene 1..N tales: excepciones, ya que normalmente
#: hay varios subprocesos involucrados).

EnvolturaDeExcepcion = namedtuple(
    "EnvolturaDeExcepcion", "kwargs type value traceback"
)
