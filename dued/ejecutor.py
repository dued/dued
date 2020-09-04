from .util import six

from .config import Config
from .analizador import AnalizadorDeContexto
from .util import debug
from .artefactos import Llamar, Artefacto


class Ejecutor(object):
    """
    Una estrategia de ejecución para objetos Artefacto.

    Las subclases pueden anular varios puntos de extensión para cambiar,
    agregar o eliminar comportamientos.

    .. versionadded:: 1.0
    """

    def __init__(self, coleccion, config=None, nucleo=None):
        """
        Inicializar ejecutor con manejadores para las estructuras de datos
        necesarias.

        :param coleccion:
            Una `.Coleccion` usada para buscar artefactos solicitados (y sus
            datos de configuración predeterminados, si los hay) por nombre
             durante la ejecución.

        :param config:
            Un estado de configuración de participacion opcional `.Config`. 
            El valor predeterminado es un ".Config" vacío si no se 
            proporciona.

        :param nucleo:
            Un `.AnalizaResultado` opcional que contiene los argumentos
            centrales del programa analizados. Por defecto es ``None``.
        """
        self.coleccion = coleccion
        self.config = config if config is not None else Config()
        self.nucleo = nucleo

    def ejecutar(self, *artefactos):
        """
        Ejecute uno o más ``artefactos`` en secuencia.

        :param artefactos:
            Un iterable multipropósito de "artefactos para ejecutar", cada
            miembro del cual puede tomar una de las siguientes formas:

            **Una cadena** nombrando un artefacto de la `.Coleccion` del
            Ejecutor. Este nombre puede contener una sintaxis de puntos
            apropiada para llamar artefactos con espacios de nombres, 
            p. Ej. ``subcoleccion.nombredeartefacto``. Tales artefactos se
            ejecutan sin argumentos.

            **Una tupla de dos** cuyo primer elemento es una cadena de nombre
            de artefacto (como arriba) y cuyo segundo elemento es un dicc
            adecuado para usar como ``**kwargs`` cuando se llama al artefacto
            nombrado. P.ej.::

                [
                    ('artefacto1', {}),
                    ('artefacto2', {'arg1': 'val1'}),
                    ...
                ]

            es equivalente, aproximadamente, a::

                artefacto1()
                artefacto2(arg1='val1')

            **Una instancia `.AnalizadorDeContexto`**, cuyo atributo 
            ``.nombre`` se usa como nombre del artefacto y cuyo atributo 
            ``.como_kwargs`` se usa como artefacto kwargs (nuevamente 
            siguiendo las especificaciones anteriores).

            .. note::
                Cuando se llama sin ningún argumento (es decir, cuando 
                ``*artefactos`` está vacío), se usa el artefacto 
                predeterminado de ``self.coleccion``, si está definido.

        :returns:
            Este dict puede incluir pre y post-artefactos si alguno fue
            ejecutado. Por ejemplo, en una colección con un artefacto 
            ``fabricar`` que depende de otro artefacto llamado ``setup``, la
            ejecución de ``fabricar`` resultará en un dicc con dos claves, 
            una para ``fabricar`` y otra para ``setup``.

        .. versionadded:: 1.0
        """
        # Normalizar la entrada
        debug("Examinando artefactos de alto nivel {!r}".format([x for x in artefactos]))
        llamadas = self.normalizar(artefactos)
        debug("Artefactos (ahora Llamados) con kwargs: {!r}".format(llamadas))
        # Obtenga una copia de los artefactos proporcionados directamente, ya
        # que a veces deberían comportarse de manera diferente
        direct = list(llamadas)
        # Expandir artefactos pre/post
        # TODO: puede tener sentido agrupar la expansión y la deduplicación ahora, ¿eh?
        expandido = self.expand_llamadas(llamadas)
        # Obtenga un buen valor para la opción de deduplicación, incluso si la
        # configuración no tiene el árbol que esperamos. (Esta es una concesión
        # a las pruebas).
        try:
            dedupe = self.config.artefactos.dedupe
        except AttributeError:
            dedupe = True
        # Dedupe en toda el corredor ahora que sabemos todas las llamadas en orden
        llamadas = self.dedupe(expandido) if dedupe else expandido
        # Ejecuta
        resultado = {}
        # TODO: ¿tal vez clonar la configuración inicial aquí? Probablemente
        # no sea necesario, especialmente dado que Ejecutor no está diseñado
        # para ejecutar()>1 vez en este momento ...
        for llamar in llamadas:
            autoimpresion = llamar in direct and llamar.autoimpresion
            args = llamar.args
            debug("Ejecutando {!r}".format(llamar))
            # Referencia a la mano a nuestra configuración, que preservará las
            # modificaciones del usuario durante la vida útil de la sesión.
            config = self.config
            # Pero asegúrese de restablecer sus niveles sensibles-a-artefacto
            # cada vez (colección &  entorno shell)
            # TODO: cargar_coleccion debe omitirse si artefacto es anónimo 
            # (solo Fabric 2 u otras bibliotecas de subclases)
            config_de_coleccion = self.coleccion.configuracion(llamar.llamado_de)
            config.cargar_coleccion(config_de_coleccion)
            config.cargar_ent_de_shell()
            debug("Finalizada la carga de configuraciones de entorno de coleccion & shell")
            # Obtenga el contexto final de Llamar (que sabrá cómo generar uno
            # apropiado; por ejemplo, las subclases pueden usar datos 
            # adicionales al ser parametrizadas), entregando esta 
            # configuración para usar allí.
            contexto = llamar.crear_contexto(config)
            args = (contexto,) + args
            resultado = llamar.artefacto(*args, **llamar.kwargs)
            if autoimpresion:
                print(resultado)
            # TODO: maneja el caso/ sin deduplicación el mismo-artefacto-diferentes-argumentos,
            # donde un obj artefacto se asigna a >1 resultado.
            resultado[llamar.artefacto] = resultado
        return resultado

    def normalizar(self, artefactos):
        """
        Transforma la lista de artefactos arbitrarios c/ varios tipos, en
        objetos `.Llamar`.
        
        Consulte el textdocs de `~.Ejecutar.ejecutar` para más detalles.

        .. versionadded:: 1.0
        """
        llamadas = []
        for artefacto in artefactos:
            nombre, kwargs = None, {}
            if isinstance(artefacto, six.string_types):
                nombre = artefacto
            elif isinstance(artefacto, AnalizadorDeContexto):
                nombre = artefacto.nombre
                kwargs = artefacto.como_kwargs
            else:
                nombre, kwargs = artefacto
            c = Llamar(artefacto=self.coleccion[nombre], kwargs=kwargs, llamado_de=nombre)
            llamadas.append(c)
        if not artefactos and self.coleccion.default is not None:
            llamadas = [Llamar(artefacto=self.coleccion[self.coleccion.default])]
        return llamadas

    def dedupe(self, llamadas):
        """
        Deduplicar una lista de `artefactos <.Llamar>`.

        :param llamadas: 
            iterable de objetos `.Llamar` que representan artefactos.

        :returns: una lista de objetos `.Llamar`.

        .. versionadded:: 1.0
        """
        deduped = []
        debug("Deduplicando artefactos...")
        for llamar in llamadas:
            if llamar not in deduped:
                debug("{!r}: no se encontraron duplicados, ok".format(llamar))
                deduped.append(llamar)
            else:
                debug("{!r}: ya se encuentra en la lista, omitiendo".format(llamar))
        return deduped

    def expand_llamadas(self, llamadas):
        """
        Expanda una lista de obj `.Llamar` en una lista casi-final de los mismos.

        La implementación predeterminada de este método simplemente agrega una
        lista de artefacto pre/post-artefacto antes/después del artefacto en
        sí, según sea necesario.

        Las subclases pueden querer hacer otras cosas además (o en lugar de) 
        las anteriores, como multiplicar las `llamadas <.Llamar>` por vectores
        de argumento o similares.

        .. versionadded:: 1.0
        """
        ret = []
        for llamar in llamadas:
            # Normalizar a Llamar (este método a veces se llama con listas
            # pre/post artefacto, que pueden contener objetos Artefacto 
            # 'raw' -sin procesar- )
            if isinstance(llamar, Artefacto):
                llamar = Llamar(artefacto=llamar)
            debug("Expanding artefacto-llamar {!r}".format(llamar))
            # TODO: aquí es donde _utilizamos_ para llamar al 
            # Ejecutor.config_for(llamar, config) ...
            # TODO: ahora es posible que necesitemos preservar más información,
            # como de dónde vino el llamar, etc., pero siento que esa mierda
            # debería ir _en el propio llamar_ ¿verdad ???
            # TODO: nosotros _probablemente_ ya ni siquiera queremos la 
            # configuración aquí, queremos que esto _solo_ se trate de la
            # recursividad entre artefactos pre/post o parametrización ...?
            ret.extend(self.expand_llamadas(llamar.pre))
            ret.append(llamar)
            ret.extend(self.expand_llamadas(llamar.post))
        return ret
