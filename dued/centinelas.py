import re
import threading

from .excepciones import RespuestaNoAceptada


class StreamCentinela(threading.local):
    """
    Una clase cuyas subclases pueden actuar sobre el flujo de datos vistos
    de los subprocesos.

    Las subclases deben exhibir la siguiente API; ver `Respondedor` para un
    ejemplo concreto.

    * ``__init__`` depende completamente de cada subclase, aunque, como es 
      habitual, las subclases *de* subclases deben tener cuidado de hacer uso
      de `super` donde sea apropiado.
    * `envio` debe aceptar todo el contenido actual de la transmisión que se
      está viendo, como una cadena Unicode, y opcionalmente puede devolver un
      iterable de cadenas Unicode (o actuar como un iterador generador, es 
      decir, múltiples llamadas a ``yield <cadena Unicode>``), cada uno de los
      cuales se escribirá en la entrada estándar del subproceso.

    .. note::
        Las subclases `StreamCentinela` existen en parte para permitir el 
        seguimiento del estado, como detectar cuándo una contraseña enviada no
        uncionó y presenta errores (o preguntar a un usuario, etc.). Dicha 
        contabilidad no se puede lograr fácilmente con funciones simples de 
        devolución de llamada.

    .. note::
        `StreamCentinela` subclases `threading.local` de modo que sus instancias
        se pueden usar para 'observar' tanto el subproceso stdout como el stderr
        en subprocesos separados.

    .. versionadded:: 1.0
    """

    def envio(self, stream):
        """
        Actua sobre los datos de ``stream``, lo que potencialmente devuelve
        respuestas.

        :param unicode stream:
            Todos los datos leídos en este stream desde el inicio de la
            sesión.

        :returns:
            Un iterable de cadenas Unicode (que pueden estar vacías).

        .. versionadded:: 1.0
        """
        raise NotImplementedError


class Respondedor(StreamCentinela):
    """
    Un objeto parametrizable que envía respuestas a patrones específicos.

    Se usa comúnmente para implementar la respuesta automática de contraseña
    para cosas como ``sudo``.

    .. versionadded:: 1.0
    """

    def __init__(self, patron, respuesta):
        r"""
        Imprima este `Respondedor` con los parámetros necesarios.

        :param patron:
            Una cadena sin formato (p ej., ``r"\[sudo\] password para .*:"``)
            que se convertirá en una expresión regular.

        :param respuesta:
            La cadena que se enviará al subproceso' stdin cuando ``patron``
            es detectado.
        """
        # TODO: precompile the keys into regex objects
        self.patron = patron
        self.respuesta = respuesta
        self.indice = 0

    def coincidencias_de_patron(self, stream, patron, atrib_de_indice):
        """
        Comportamiento genérico de "búsqueda de un patron en el flujo, usando índice".

        Se usa aquí y en algunas subclases que desean rastrear múltiples 
        patrones al mismo tiempo.

        :param unicode stream: Los mismos datos pasados a ``envio``.
        :param unicode patron: El patrón a buscar.
        :param unicode atrib_de_indice: El nombre del atributo de índice a usar.
        :returns: un iterable de cadenas coincidentes.

        .. versionadded:: 1.0
        """
        # NOTE: genera el escaneo para que se pueda usar para buscar >1 patron
        # a la vez, p. Ej. en DetectorDeRespuestasIncorrectas.
        # Solo mire los contenidos del stream que aún no hemos visto,
        # para evitar engaños.
        indice = getattr(self, atrib_de_indice)
        new_ = stream[indice:]
        # buscar, a través de líneas si es necesario
        matches = re.findall(patron, new_, re.S)
        # Actualizar el índice de búsqueda si hemos coincidido
        if matches:
            setattr(self, atrib_de_indice, indice + len(new_))
        return matches

    def envio(self, stream):
        # Itere sobre respuesta findall() en caso de que ocurriera >1 coincidencia.
        for _ in self.coincidencias_de_patron(stream, self.patron, "indice"):
            yield self.respuesta


class DetectorDeRespuestasIncorrectas(Respondedor):
    """
    Variante de `Respondedor` que es capaz de detectar respuestas incorrectas.

    This class adds a ``centinela`` parameter to ``__init__``, and its
    ``envio`` will raise `.RespuestaNoAceptada` if it detects that centinela
    valor in the stream.
    Esta clase agrega un parámetro ``centinela`` a ``__init__``, y su 
    ``envio`` generará `.RespuestaNoAceptada` si detecta ese valor centinela
    en el flujo.

    .. versionadded:: 1.0
    """

    def __init__(self, patron, respuesta, centinela):
        super(DetectorDeRespuestasIncorrectas, self).__init__(patron, respuesta)
        self.centinela = centinela
        self.indice_de_fallo = 0
        self.intento = False

    def envio(self, stream):
        # Comportarse como Respondedor habitual inicialmente
        respuesta = super(DetectorDeRespuestasIncorrectas, self).envio(stream)
        # También verifique el stram de nuestra falla centinela
        fallado = self.coincidencias_de_patron(stream, self.centinela, "indice_de_fallo")
        # Error si parece que hemos fallado después de una respuesta anterior.
        if self.intento and fallado:
            err = 'Auto-respuesta a r"{}" falló con {!r}!'.format(
                self.patron, self.centinela
            )
            raise RespuestaNoAceptada(err)
        # Una vez que veamos que tenemos una respuesta, tome nota
        if respuesta:
            self.intento = True
        # Nuevamente, comportarse con regularidad por defecto.
        return respuesta
