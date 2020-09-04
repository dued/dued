from contextlib import contextmanager
from resource import getrusage, RUSAGE_SELF
import sys
import time

from dued.vendor.six import wraps

from pytest import skip


def current_cpu_usage():
    rusage = getrusage(RUSAGE_SELF)
    return rusage.ru_utime + rusage.ru_stime


@contextmanager
def asegurar_el_uso_de_la_cpu(lt, verbose=False):
    """
    Ejecute el bloque encapsulado, afirmando que la utilización de la CPU
    fue inferior a ``lt``%.

    :param float lt: 
        porcentaje de uso de CPU por encima del cual ocurrirá
        una falla.
    :param bool verbose: si se imprime el porcentaje calculado.
    """
    start_usage = current_cpu_usage()
    start_time = time.time()
    yield
    end_usage = current_cpu_usage()
    end_time = time.time()

    usage_diff = end_usage - start_usage
    time_diff = end_time - start_time

    if time_diff == 0:  # Apparently possible!
        time_diff = 0.000001

    percentage = (usage_diff / time_diff) * 100.0

    if verbose:
        print("Used {0:.2}% CPU over {1:.2}s".format(percentage, time_diff))

    assert percentage < lt


def solo_utf8(f):
    """
    Decorador que hace que las pruebas se omitan si las tuberías de shell
    locales no son UTF-8.
    """
    # TODO: use etiquetas de selección de prueba reales o cualquier olfato que tenga
    @wraps(f)
    def interior(*args, **kwargs):
        if getattr(sys.stdout, "codificacion", None) == "UTF-8":
            return f(*args, **kwargs)
        # TODO: podría eliminar esto para que se muestren en verde, pero la 
        # figura amarilla es más apropiada
        skip()

    return interior
