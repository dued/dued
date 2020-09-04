"""
Funciones de utilidad que rodean los dispositivos terminales y E/S.

Gran parte de este código realiza bifurcaciones sensibles a la plataforma, 
p. Ej. Soporte de Windows.

Este es su propio módulo para abstraer lo que de otra manera distraerían las
interrupciones del flujo lógico.
"""

from contextlib import contextmanager
import os
import select
import sys

# TODO: mudarte aquí? Actualmente son independientes de la plataforma ...
from .util import tiene_fileno, esuntty


WINDOWS = sys.platform == "win32"
"""
Si la plataforma actual parece ser de naturaleza Windows o no.

Tenga en cuenta que Python de Cygwin está lo suficientemente cerca de los UNIX
"reales" que no necesita (¡o quiere!) Usar PyWin32, por lo que solo probamos
para configuraciones de Win32 literales (vanilla Python, ActiveState, etc.) 
aquí.

.. versionadded:: 1.0
"""

if WINDOWS:
    import msvcrt
    from ctypes import Structure, c_ushort, windll, POINTER, byref
    from ctypes.wintypes import HANDLE, _COORD, _SMALL_RECT
else:
    import fcntl
    import struct
    import termios
    import tty


def pty_dimension():
    """
    Determine las dimensiones actuales del pseudoterminal local.

    :returns:
        Un ``(num_cols, num_rows)`` dos tuplas que describen la dimension
        de la PTY. El valor predeterminado es ``(80, 24)`` si no se puede
        obtener un resultado razonable de forma dinámica. 

    .. versionadded:: 1.0
    """
    columnas, filas = _pty_dimension() if not WINDOWS else _win_pty_dimension()
    # TODO: ¿hacer configurables los valores predeterminados?
    return ((columnas or 80), (filas or 24))

def _pty_dimension():
    """
    Apto para la mayoría de las plataformas POSIX.

    .. versionadded:: 1.0
    """
    # valores de centinela serán sustituid. c/valores pord efecto por llamador
    dimension = (None, None)
    # Queremos dos enteros cortos sin signo (filas, columnas)
    fmt = "HH"
    # Create an empty (zeroed) buffer for ioctl to map onto. Yay for C!
    # Crea un búfer vacío (puesto a cero) p/que ioctl se asigne. ¡Hurra por C!
    buf = struct.pack(fmt, 0, 0)
    # Llamar TIOCGWINSZ to get window size of stdout, returns our filled
    # Llamar TIOCGWINSZ para obtener el tamaño de la ventana de stdout, 
    # devuelve nuestro buffer lleno
    try:
        resultado = fcntl.ioctl(sys.stdout, termios.TIOCGWINSZ, buf)
        # Desempaquete el búfer nuevamente en tipos de datos de Python
        # NOTE: este desempaquetado nos da filas x columnas, pero devolvemos
        # la inversa.
        filas, columnas = struct.unpack(fmt, resultado)
        return (columnas, filas)
    # Recurrir al valor de retorno vacío en varios casos de falla:
    # * sys.stdout está parcheado, como en las pruebas, y carece de .fileno
    # * sys.stdout tiene un .fileno pero en realidad no está conectado a un TTY
    # * termios que no tienen un atributo TIOCGWINSZ (sucede a veces ...)
    # * otras situaciones en las que ioctl no explota pero el resultado no es
    #   algo por tanto desempaquetar
    except (struct.error, TypeError, IOError, AttributeError):
        pass
    return dimension

def _win_pty_dimension():
    class CONSOLE_SCREEN_BUFFER_INFO(Structure):
        _fields_ = [
            ("dwSize", _COORD),
            ("dwCursorPosition", _COORD),
            ("wAttributes", c_ushort),
            ("srWindow", _SMALL_RECT),
            ("dwMaximumWindowSize", _COORD),
        ]

    GetStdHandle = windll.kernel32.GetStdHandle
    GetConsoleScreenBufferInfo = windll.kernel32.GetConsoleScreenBufferInfo
    GetStdHandle.restype = HANDLE
    GetConsoleScreenBufferInfo.argtypes = [
        HANDLE,
        POINTER(CONSOLE_SCREEN_BUFFER_INFO),
    ]

    hstd = GetStdHandle(-11)  # STD_OUTPUT_HANDLE = -11
    csbi = CONSOLE_SCREEN_BUFFER_INFO()
    ret = GetConsoleScreenBufferInfo(hstd, byref(csbi))

    if ret:
        sizex = csbi.srWindow.Right - csbi.srWindow.Left + 1
        sizey = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
        return sizex, sizey
    else:
        return (None, None)


def verfica_stdin_en_primer_plano_tty(stream):
    """
    Detectar si el ``stream`` de stdin parece estar en primer plano de un TTY.

    Específicamente, compara el ID del grupo de procesos de Python actual con
    el del descriptor de archivo de la secuencia para ver si coinciden; si no
    coinciden, es probable que el proceso se haya colocado en segundo plano.

    Esto se usa como prueba para determinar si debemos manipular un stdin
    activo para que se ejecute en un modo de búfer de caracteres; tocar el
    terminal de esta manera cuando el proceso está en segundo plano, hace que
    la mayoría de los shells pausen la ejecución.

    .. note::
        Los procesos que no están conectados a una terminal para empezar, 
        siempre fallarán esta prueba, ya que comienza con "¿tiene un ``fileno``
        real?.

    .. versionadded:: 1.0
    """
    if not tiene_fileno(stream):
        return False
    return os.getpgrp() == os.tcgetpgrp(stream.fileno())


def setear_cbreak_ahora(stream):
    # Explícitamente no está docstringneado para permanecer privado, por ahora. Eh.
    # Comprueba si tty.setcbreak parece haber sido ya ejecutado contra ``stream`` 
    # (si no de otra manera simplemente no haría nada).
    # Se usa para efectuar idempotencia para almacenar-caracteres en un stream, lo
    # que también nos evita múltiples ciclos de captura-luego-restauración.
    attrs = termios.tcgetattr(stream)
    lbanderas, cc = attrs[3], attrs[6]
    echo = bool(lbanderas & termios.ECHO)
    icanon = bool(lbanderas & termios.ICANON)
    # setcbreak sets ECHO and ICANON to 0/off, CC[VMIN] to 1-ish, and CC[VTIME]
    # to 0-ish. If any of that is not true we can reasonably assume it has not
    # yet been executed against this stream.
    centinelas = (
        not echo,
        not icanon,
        cc[termios.VMIN] in [1, b"\x01"],
        cc[termios.VTIME] in [0, b"\x00"],
    )
    return all(centinelas)


@contextmanager
def caracter_buffereado(stream):
    """
    Forzar que el ``stream`` de la terminal local sea de carácter, no de 
    línea, en búfer

    Solo se aplica a sistemas basados en Unix; en Windows, esto no es
    operativo.

    .. versionadded:: 1.0
    """
    if (
        WINDOWS
        or not esuntty(stream)
        or not verfica_stdin_en_primer_plano_tty(stream)
        or setear_cbreak_ahora(stream)
    ):
        yield
    else:
        config_antigua = termios.tcgetattr(stream)
        tty.setcbreak(stream)
        try:
            yield
        finally:
            termios.tcsetattr(stream, termios.TCSADRAIN, config_antigua)


def listo_para_leer(entrada_):
    """
    Prueba ``entrada_`` para determinar si una acción de lectura tendrá éxito.

    :param entrada_: Objeto de flujo de entrada (como-archivo)..

    :returns: ``True`` si una lectura debe tener éxito, ``False`` de l/contr.

    .. versionadded:: 1.0
    """
    # Un stdin terminal "real" necesita select/kbhit para decirnos cuándo 
    # está listo para una read() (lectura) sin bloqueo.
    # De lo contrario, suponga un objeto como-archivo "más seguro" que pueda 
    # ser leido sin bloquear (por ej. un StringIO o un archivo normal).
    if not tiene_fileno(entrada_):
        return True
    if WINDOWS:
        return msvcrt.kbhit()
    else:
        reads, _, _ = select.select([entrada_], [], [], 0.0)
        return bool(reads and reads[0] is entrada_)


def bytes_a_leer(entrada_):
    """
    Consulta el flujo ``entrada_`` para ver cuántos bytes se pueden leer.

    .. note::
        Si no podemos decirlo (por ejemplo, si ``entrada_`` no es un 
        descriptor de archivo verdadero o no es un TTY válido), recurrimos a
        la sugerencia de leer solo 1 byte.

    :param input: Objeto de flujo de entrada (como-archivo).

    :returns: `int` numero de bytes a leer.

    .. versionadded:: 1.0
    """
    # NOTE: tenemos que comprobar ambas posibilidades aquí; existen 
    # situaciones en las que no es un tty pero tiene un fileno, o viceversa;
    # normalmente ninguno de los dos va a funcionar re: ioctl().
    if not WINDOWS and esuntty(entrada_) and tiene_fileno(entrada_):
        fionread = fcntl.ioctl(entrada_, termios.FIONREAD, "  ")
        return struct.unpack("h", fionread)[0]
    return 1
