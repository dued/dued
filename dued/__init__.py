from ._version import __version_info__, __version__  # noqa
from .coleccion import Coleccion  # noqa
from .config import Config  # noqa
from .contexto import Contexto, ContextoSimulado  # noqa
from .excepciones import (  # noqa
    VarEntAmbigua,
    FallaAutenticacion,
    ColeccionNoEcontrada,
    Salida,
    ErrorDeAnalisis,
    ErrorEnPlatafoma,
    RespuestaNoAceptada,
    ErrorEnTuberiaDeSubP,
    ExcepcionDeHilo,
    VarEntInestable,
    SalidaInesperada,
    TipoDeArchivoDesconocido,
    MiembroDeConfigNoSeleccionable,
    ErrorDeCentinela,
    CaducoComando,
)
from .ejecutor import Ejecutor  # noqa
from .cargador import CargaDesdeElSitemaDeArchivos  # noqa
from .analizador import Argumento, Analizador, AnalizadorDeContexto, AnalizaResultado  # noqa
from .programa import Programa  # noqa
from .corredores import Corredor, Local, Falla, Resultado, Promesa  # noqa
from .artefactos import artefacto, llamar, Llamar, Artefacto  # noqa
from .terminales import pty_dimension  # noqa
from .centinelas import DetectorDeRespuestasIncorrectas, Respondedor, StreamCentinela  # noqa


def correr(comando, **kwargs):
    """
    Ejecuta un ``comando`` en un subproceso y retorna un objecto `.Resultado`.

    Ver `.Corredor.correr` para detalles de la API.

    .. note::
        Esta función es una envoltura conveniente alrededor de las API
        `.Contexto` y `.Corredor` de Dued.

        Específicamente, crea una instancia anónima `.Contexto` y llama a su
        método `~.Contexto.correr`, que a su vez usa una subclase de corredor
        `.Local` para la ejecución del comando.

    .. versionadded:: 1.0
    """
    return Contexto().correr(comando, **kwargs)


def sudo(comando, **kwargs):
    """
    Ejecuta un ``comando`` en un subproceso ``sudo`` y retorna un objeto `.Resultado`.

    Ver `.Contexto.sudo` para detalles de la API, como el kwarg ``password``.

    .. note::
        Esta función es una envoltura conveniente alrededor de las API
        `.Contexto` y `.Corredor` de Dued.

        Específicamente, crea una instancia anónima `.Contexto` y llama a su
        método `~.Contexto.sudo`, que a su vez usa de manera predeterminada una
        subclase de corredor `.Local` para la ejecución de comandos
        (más bits y piezas relacionadas con sudo).

    .. versionadded:: 1.4
    """
    return Contexto().sudo(comando, **kwargs)
