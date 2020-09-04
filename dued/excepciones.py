"""
Clases de excepción personalizadas.

Estas varían en el caso de uso, desde "necesitábamos un diseño de estructura
de datos específico en las excepciones utilizadas para el paso de mensajes"
hasta simplemente "necesitábamos expresar una condición de error de una
manera fácil de distinguir de otros errores verdaderamente inesperados".

"""

from traceback import format_exception
from pprint import pformat

from .util import six


class ColeccionNoEcontrada(Exception):
    def __init__(self, nombre, inicio):
        self.nombre = nombre
        self.inicio = inicio


class Falla(Exception):
    """
    Subclase de excepción que representa la falla de la ejecución de un 
    comando.

    "Falla" puede significar que el comando se ejecutó y el shell indicó un
    resultado inusual (generalmente, un código de salida distinto de cero), o
    puede significar algo más, como un comando ``sudo`` que fue abortado 
    cuando la contraseña proporcionada falló la autenticación.

    Dos atributos permiten que la introspección determine la naturaleza del
    problema:

    * ``resultado``: a `.Resultado` instancia con información sobre el
      comando que se está ejecutando y, si se ejecutó hasta su finalización,
      cómo salió
    * ``motivo``: una instancia de excepción envuelta si corresponde (por
      ejemplo, un `.StreamCentinela` generado `ErrorDeCentinela`) o  de lo
      contrario ``None``, en cuyo caso, probablemente sea una subclase 
      `Falla` que indica su propia naturaleza específica, como como
      `SalidaInesperada` o` CaducoComando`.

    Esta clase rara vez se plantea por sí misma; la mayoría de las veces
    `.Corredor.correr` (o una envoltura del mismo, como `.Contexto.sudo`)
    generará una subclase específica como `SalidaInesperada` o 
    `FallaAutenticacion`.

    .. versionadded:: 1.0
    """

    def __init__(self, resultado, motivo=None):
        self.resultado = resultado
        self.motivo = motivo

    def streams_para_mostrar(self):
        """
        Devuelve stdout/err streams según sea necesario para mostrar el error.

        Sujeto a las siguientes reglas:

        - Si una secuencia determinada *no* se ocultó durante la ejecución,
          se usa un marcador de posición en su lugar para evitar imprimirla 
          dos veces.
        - Solo se incluyen las últimas 10 líneas de texto continuo.
        - La ejecución impulsada por PTY carecerá de stderr, y se devuelve un
          mensaje específico a este efecto en lugar de un volcado de stderr.

        :returns: Dos tuplas de cadenas stdout, stderr.

        .. versionadded:: 1.3
        """
        already_printed = " ya impreso"
        if "stdout" not in self.resultado.ocultar:
            stdout = already_printed
        else:
            stdout = self.resultado.cola("stdout")
        if self.resultado.pty:
            stderr = " n/a (PTYs no tienen stderr)"
        else:
            if "stderr" not in self.resultado.ocultar:
                stderr = already_printed
            else:
                stderr = self.resultado.cola("stderr")
        return stdout, stderr

    def __repr__(self):
        return self._repr()

    def _repr(self, **kwargs):
        """
        Devuelve un valor similar a ``__repr__`` del resultado interno + 
        cualquier kwargs.
        """
        # TODO: expandir?
        # TODO: truncar comando?
        plantilla = "<{}: cmd={!r}{}>"
        resto = ""
        if kwargs:
            resto = " " + " ".join(
                "{}={}".format(clave, valor) for clave, valor in kwargs.items()
            )
        return plantilla.format(
            self.__class__.__name__, self.resultado.comando, resto
        )


class SalidaInesperada(Falla):
    """
    Un comando de shell se ejecutó hasta completarse pero salió con un código
    de salida inesperado.

     Su representación de cadena muestra lo siguiente:

     - Comando ejecutado;
     - Código de salida;
     - Las últimas 10 líneas de stdout, si estaba oculto;
     - Las últimas 10 líneas de stderr, si estaba oculto y no estaba vacío 
       (p. Ej. pty=False; cuando pty=True, stderr nunca ocurre).

    .. versionadded:: 1.0
    """

    def __str__(self):
        stdout, stderr = self.streams_para_mostrar()
        comando = self.resultado.comando
        salida = self.resultado.salida
        plantilla = """¡Encontré un código de salida de comando incorrecto!

Comando: {!r}

Cod de Salida: {}

Stdout:{}

Stderr:{}

"""
        return plantilla.format(comando, salida, stdout, stderr)

    def __repr__(self):
        return self._repr(salida=self.resultado.salida)


class CaducoComando(Falla):
    """
    Se genera cuando un subproceso no se cierra dentro de un período de 
    tiempo deseado.
    """

    def __init__(self, resultado, tiempofuera):
        super(CaducoComando, self).__init__(resultado)
        self.tiempofuera = tiempofuera

    def __repr__(self):
        return self._repr(tiempofuera=self.tiempofuera)

    def __str__(self):
        stdout, stderr = self.streams_para_mostrar()
        comando = self.resultado.comando
        plantilla = """El comando no se completó en {} segundos!

Comando: {!r}

Stdout:{}

Stderr:{}

"""
        return plantilla.format(self.tiempofuera, comando, stdout, stderr)


class FallaAutenticacion(Falla):
    """
    Una falla de autenticación, p. Ej. debido a contraseña ``sudo`` incorrecta.

    .. note::
        Los objetos `.Resultado` adjuntos a estas excepciones generalmente 
        carecen de información de código de salida, ya que el comando nunca
        se ejecutó por completo; en su lugar, se generó la excepción.

    .. versionadded:: 1.0
    """

    def __init__(self, resultado, prompt):
        self.resultado = resultado
        self.prompt = prompt

    def __str__(self):
        err = "La contraseña enviada para solicitar {!r} fue rechazada."
        return err.format(self.prompt)


class ErrorDeAnalisis(Exception):
    """
    Un error que surge del análisis sintáctico de los indicadores/argumentos
    de la línea de comando.

    Entrada ambigua, nombres de artefactos no válidos, banderas no válidas, 
    etc.

    .. versionadded:: 1.0
    """

    def __init__(self, msj, contexto=None):
        super(ErrorDeAnalisis, self).__init__(msj)
        self.contexto = contexto


class Salida(Exception):
    """
    Suplente personalizado simple para SystemExit.

    Reemplaza las llamadas sys.exit dispersas, mejora la capacidad de prueba,
    permite capturar una solicitud de salida sin interceptar SystemExit 
    reales (generalmente es algo poco amigable, ya que la mayoría de los
    usuarios que llaman a `sys.exit` prefieren esperar que realmente salga).

    Se establece de forma predeterminada en un comportamiento de terminación
    compatible con la salida 0 que no se imprime si no se detecta la 
    excepción.

    Si se proporciona ``code`` (un int), ese código se usa para salir.

    Si se proporciona un ``mensaje`` (una cadena), se imprime con un error 
    estándar y el programa sale con el código ``1`` por defecto (a menos que
    se anule dando también ``código`` explícitamente).

    .. versionadded:: 1.0
    """

    def __init__(self, mensaje=None, code=None):
        self.mensaje = mensaje
        self._code = code

    @property
    def code(self):
        if self._code is not None:
            return self._code
        return 1 if self.mensaje else 0


class ErrorEnPlatafoma(Exception):
    """
    Se genera cuando se produce una operación ilegal en la plataforma actual.

    P.ej. Los usuarios de Windows que intentan utilizar la funcionalidad que
    requiere el módulo ``pty``.

    Normalmente se utiliza para presentar un mensaje de error más claro al 
    usuario.

    .. versionadded:: 1.0
    """

    pass


class VarEntAmbigua(Exception):
    """
    Se genera al cargar claves de config de var-ent tiene un objetivo ambiguo.

    .. versionadded:: 1.0
    """

    pass


class VarEntInestable(Exception):
    """
    Se genera en cargas de var-ent intentadas cuyos valores predeterminados
    son demasiado ricos.

    P.ej. intentar meter ``MI_VAR = "foo"`` en ``{'mi_var': ['uh', 'oh']}``
    no tiene ningún sentido hasta/si implementamos algún tipo de opción de
    transformación.

    .. versionadded:: 1.0
    """

    pass


class TipoDeArchivoDesconocido(Exception):
    """
    Se especificó un archivo de config de un tipo desconocido y no se puede
    cargar.

    .. versionadded:: 1.0
    """

    pass


class MiembroDeConfigNoSeleccionable(Exception):
    """
    Un archivo de configuración contenía objetos de módulo, que no se pueden
    escanear/copiar.

    Generamos esta excepción más fácil de detectar en lugar de dejar que el
    (no muy claro) TypeError salga del módulo pickle. (Sin embargo, para 
    evitar nuestra frágil detección de ese error, lo evitamos probando 
    explícitamente los miembros del módulo).

    .. versionadded:: 1.0.2
    """

    pass


def _kwargs_imprimibles(kwargs):
    """
    Devuelve una versión imprimible de un dicc ``kwargs`` relacionado con
    subprocesos.

    Se tiene especial cuidado con los miembros ``args`` que son iterables muy
    largos; es necesario truncarlos para que sean útiles.
    """
    imprimible = {}
    for clave, valor in six.iteritems(kwargs):
        item = valor
        if clave == "args":
            item = []
            for arg in valor:
                nuevo_arg = arg
                if hasattr(arg, "__len__") and len(arg) > 10:
                    msj = "<... resto truncado durante la visualización del error ...>"
                    nuevo_arg = arg[:10] + [msj]
                item.append(nuevo_arg)
        imprimible[clave] = item
    return imprimible


class ExcepcionDeHilo(Exception):
    """
    Se plantearon una o más excepciones en subprocesos de fondo.

    Las excepciones subyacentes reales se almacenan en el atributo 
    `excepciones`; consulte su documentación para obtener detalles sobre la
    estructura de datos.

    .. note::
        Los subprocesos que no encontraron una excepción, no contribuyen a 
        este objeto de excepción y, por lo tanto, no están presentes dentro
        de `excepciones`.

    .. versionadded:: 1.0
    """

    #: Una tupla de `ExceptionWrappers <dued.util.EnvolturaDeExcepcion>` que contiene
    #: el constructor del hilo inicial kwargs (porque las subclases `threading.Thread`
    #: siempre deben llamarse con kwargs) y la excepción capturada para ese hilo como
    #: se ve en` sys.exc_info `(entonces: tipo, valor, rastreo).
    #:
    #: .. Nota::
    #:      El orden de este atributo no está bien definido.
    #:
    #: .. Nota::
    #:      Los kwargs de hilo que parecen ser muy largos (por ejemplo,
    #:      búferes IO) se truncarán cuando se impriman, para evitar una
    #:      gran visualización de errores ilegibles.
    excepciones = tuple()

    def __init__(self, excepciones):
        self.excepciones = tuple(excepciones)

    def __str__(self):
        details = []
        for x in self.excepciones:
            # Build useful display
            detalle = "Argumentos de hilo: {}\n\n{}"
            details.append(
                detalle.format(
                    pformat(_kwargs_imprimibles(x.kwargs)),
                    "\n".join(format_exception(x.type, x.valor, x.traceback)),
                )
            )
        args = (
            len(self.excepciones),
            ", ".join(x.type.__name__ for x in self.excepciones),
            "\n\n".join(details),
        )
        return """
 {} excepciones dentro de los hilos ({}):


{}
""".format(
            *args
        )


class ErrorDeCentinela(Exception):
    """
    Clase de excepción principal genérica para errores relacionados con
    `.StreamCentinela`.

    Normalmente, una de estas excepciones indica que un `.StreamCentinela`
    notó algo anómalo en un flujo de salida, como una falla de respuesta de
    autenticación.

    `.Corredor` los captura y los adjunta a las excepciones de `.Falla` para
    que puedan ser referenciados por un código intermedio y/o actuar como
    información adicional para los usuarios finales.

    .. versionadded:: 1.0
    """

    pass


class RespuestaNoAceptada(ErrorDeCentinela):
    """
    Una clase de respondedor/centinela notó una 'mala' respuesta a su 
    presentación.

    Usado principalmente por `.DetectorDeRespuestasIncorrectas` y subclases,
    p. Ej. "Dios mío, envié automáticamente una contraseña de sudo y era 
    incorrecta".

    .. versionadded:: 1.0
    """

    pass


class ErrorEnTuberiaDeSubP(Exception):
    """
    Se encontró algún problema manejando las tuberías de subproceso 
    (stdout/err /in).

    Normalmente solo para casos de esquina; la mayoría de las veces, los 
    errores en esta área son planteados por el intérprete o el sistema 
    operativo y terminan envueltos en un `.ExcepcionDeHilo`.

    .. versionadded:: 1.3
    """

    pass
