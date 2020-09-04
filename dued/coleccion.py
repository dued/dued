import copy
import types

from .util import six, Lexicon, lineadeayuda

from .config import fusionar_dics, copiar_dic
from .analizador import Contexto as AnalizadorDeContexto
from .artefactos import Artefacto


class Coleccion(object):
    """
    Una colección de artefactos ejecutables. Ver :doc:`conceptos/hangar`.

    .. versionadded:: 1.0
    """

    def __init__(self, *args, **kwargs):
        """
        Cree una nueva colección de artefactos/hangar.

        `.Coleccion` ofrece un conjunto de métodos para construir una 
        colección de artefactos desde cero, más un conveniente constructor que
        envuelve dicha API.

        En cualquier caso:

        * El primer argumento posicional puede ser una cadena, que (si se da) 
          se usa como el nombre predeterminado de la colección cuando se 
          realizan búsquedas de hangar;
        * Se puede dar como argumento la palabra clave ``cargado_de``, que
          establece metadatos que indican la ruta del sistema de archivos desde
          la que se cargó la colección. Esto se utiliza como guía al cargar 
          por proyecto: ref: `archivos de configuración <jerarquía-de-config>`.
        * Se puede dar un kwarg ``nombre_auto_guion``, controlando si los 
          nombres de artefacto y colección tienen guiones bajos convertidos en
          guiones en la mayoría de los casos; por default es ``True`` pero se
          puede configurar en ``False`` para deshabilitarlo.

           La maquinaria CLI pasará el valor del valor de configuración de 
           ``artefactos.nombre_auto_guion`` a este kwarg.

         **El enfoque del método**

        Puede inicializarse sin argumentos y usar métodos (por ejemplo,
        `.ad_artefacto`/`.ad_coleccion`) para insertar objetos::

            c = Coleccion()
            c.ad_artefacto(algun_artefacto)

        Si se proporciona un argumento de cadena inicial, se utiliza como 
        nombre predeterminado para esta colección, en caso de que se inserte
        en otra colección como sub_espacio_de_nombres::

            docs = Coleccion('docs')
            docs.ad_artefacto(doc_artefacto)
            hng = Coleccion()
            hng.ad_artefacto(artefacto_altonivel)
            hng.ad_coleccion(docs)
            # Los identificadores válidos ahora son 'artefacto_altonivel' y
            # 'docs.doc_artefacto' asumiendo que los objetos artefacto fueron 
            # nombrados de la misma manera que las variables que estamos 
            # usando :))

        Para obtener más detalles, consulte los documentos de la API para el 
        resto de la clase.

        **El enfoque del constructor**

        Se espera que todos los ``* args`` dados a `.Coleccion` (además del 
        argumento posicional opcional 'nombre' y kwarg `cargado_de`) sean 
        instancias de `.Artefacto` o `.Coleccion` que se pasarán a 
        `.ad_artefacto`/`.ad_coleccion` según corresponda. Los objetos de 
        módulo también son válidos (como lo son para `.ad_coleccion`). 
        Por ejemplo, el siguiente fragmento da como resultado los mismos 
        dos identificadores de artefacto que el anterior::

            hng = Coleccion(artefacto_altonivel, Coleccion('docs', doc_artefacto))

        Si se dan ``**kwargs'', las palabras clave se utilizan como 
        argumentos de nombre inicial para los valores respectivos::

            hng = Coleccion(
                artefacto_altonivel=algun_otro_artefacto,
                docs=Coleccion(doc_artefacto)
            )

        Eso es exactamente equivalente a::

            docs = Coleccion(doc_artefacto)
            hng = Coleccion()
            hng.ad_artefacto(algun_otro_artefacto, 'artefacto_altonivel')
            hng.ad_coleccion(docs, 'docs')

        Consulte los documentos de API de métodos individuales para obtener
        más detalles.
        """
        # Inicializar
        self.artefactos = Lexicon()
        self.colecciones = Lexicon()
        self.default = None
        self.nombre = None
        self._configuracion = {}
        # Kwargs específicos si corresponde
        self.cargado_de = kwargs.pop("cargado_de", None)
        self.nombre_auto_guion = kwargs.pop("nombre_auto_guion", None)
        # versión splat-kwargs del valor predeterminado (nombre_auto_guion=True)
        if self.nombre_auto_guion is None:
            self.nombre_auto_guion = True
        # Nombre si aplica
        args = list(args)
        if args and isinstance(args[0], six.string_types):
            self.nombre = self.transformar(args.pop(0))
        # Despacho args/kwargs
        for arg in args:
            self._ad_objecto(arg)
        # Despacho kwargs
        for nombre, obj in six.iteritems(kwargs):
            self._ad_objecto(obj, nombre)

    def _ad_objecto(self, obj, nombre=None):
        if isinstance(obj, Artefacto):
            method = self.ad_artefacto
        elif isinstance(obj, (Coleccion, types.ModuleType)):
            method = self.ad_coleccion
        else:
            raise TypeError("¡No tengo idea de cómo insertar {!r}!".format(type(obj)))
        return method(obj, nombre=nombre)

    def __repr__(self):
        nombres_de_artefactos = list(self.artefactos.claves())
        colecciones = ["{}...".format(x) for x in self.colecciones.claves()]
        return "<Coleccion {!r}: {}>".format(
            self.nombre, ", ".join(sorted(nombres_de_artefactos) + sorted(colecciones))
        )

    def __eq__(self, otro):
        return (
            self.nombre == otro.nombre
            and self.artefactos == otro.artefactos
            and self.colecciones == otro.colecciones
        )

    def __ne__(self, otro):
        return not self == otro

    def __nonzero__(self):
        return self.__bool__()

    def __bool__(self):
        return bool(self.nombres_de_artefactos)

    @classmethod
    def del_modulo(
        cls,
        modulo,
        nombre=None,
        config=None,
        cargado_de=None,
        nombre_auto_guion=None,
    ):
        """
        Devuelve una nueva `.Coleccion` creada a partir de ``modulo``.

        Inspecciona ``modulo`` en busca de instancias de `.Artefacto` y las 
        agrega a una nueva `.Coleccion`, devolviéndola. Si existe alguna 
        colección explícita de hangar (llamada ``en`` o ``hangar``), en su 
        lugar se carga preferentemente una copia de ese objeto colección.

        Cuando se genera la colección implícita/predeterminada, se le asignará
        el nombre del atributo ``__name__`` del módulo, o su última sección 
        punteada si es un submódulo. (Es decir, normalmente debería asignarse
        al nombre de archivo ``.py`` real).

        Las colecciones dadas explícitamente solo recibirán ese nombre 
        derivado del módulo si aún no tienen un atributo ``.nombre`` válido.

        Si el módulo tiene un textdocs (``__doc__``), se copia en la 
        `.Coleccion` resultante (y se usa para mostrarlo en la salida de 
        ayuda, lista, etc.)

        :param str nombre:
            Una cadena, que si se proporciona anulará cualquier nombre de 
            colección derivado automáticamente (o nombre establecido en la
            raíz del módulo hangar, si tiene uno).

        :param dict config:
            Se usa para establecer las opciones de configuración en la 
            `.Coleccion` recién creada antes de devolverla (lo que le ahorra
            una llamada a `.configurar`).

            Si el módulo importado tenía un objeto raíz hangar,
            ``config`` se fusiona sobre él (es decir, anula cualquier 
            conflicto).

        :param str cargado_de:
            Idéntico al kwarg del mismo nombre del constructor de clases
            regular - debe ser la ruta donde se encontró el módulo.

        :param bool nombre_auto_guion:
            Idéntico al kwarg del mismo nombre del constructor de la clase 
            regular - determina si los nombres emitidos tienen guiones 
            automáticos.

        .. versionadded:: 1.0 
        """
        nombre_de_modulo = modulo.__name__.split(".")[-1]

        def instanciar(nombre_de_obj=None):
            # El nombre dado explícitamente gana sobre el nombre raíz en 
            # (si corresponde), que gana sobre el nombre concreto del módulo.
            args = [nombre or nombre_de_obj or nombre_de_modulo]
            kwargs = dict(
                cargado_de=cargado_de, nombre_auto_guion=nombre_auto_guion
            )
            instancia = cls(*args, **kwargs)
            instancia.__doc__ = modulo.__doc__
            return instancia

        # Vea si el módulo proporciona un Hangar predeterminado para usar en lugar
        # de crear su propia colección.
        for candidato in ("hng", "hangar"):
            obj = getattr(modulo, candidato, None)
            if obj and isinstance(obj, Coleccion):
                #TODO: convertir esto en Coleccion.clonar() o similar?
                ret = instanciar(nombre_de_obj=obj.nombre)
                ret.artefactos = ret._transformar_con_lexicon(obj.artefactos)
                ret.colecciones = ret._transformar_con_lexicon(obj.colecciones)
                ret.default = ret.transformar(obj.default)
                # La configuración dada explícitamente gana sobre la 
                # configuración del espacio de nombres raíz
                obj_config = copiar_dic(obj._configuracion)
                if config:
                    fusionar_dics(obj_config, config)
                ret._configuracion = obj_config
                return ret
        # De lo contrario, haga su propia colección de los artefactos del módulo.
        artefactos = filter(lambda x: isinstance(x, Artefacto), vars(modulo).values())
        # Again, explicit name wins over implicit one from module path
        coleccion = instanciar()
        for artefacto in artefactos:
            coleccion.ad_artefacto(artefacto)
        if config:
            coleccion.configurar(config)
        return coleccion

    def ad_artefacto(self, artefacto, nombre=None, alias=None, default=None):
        """
        Agrega `.Artefacto` ``artefacto`` a esta colección.

        :param artefacto: El objeto `.Artefacto` para agregar a esta colección.

        :param nombre:
            Nombre de cadena opcional para enlazar (anula el atributo ``nombre``
            autodefinido del artefacto y/o cualquier identificador de Python
            (es decir, ``.nombre_de_func``).

        :param alias:
            Iterable opcional de nombres adicionales para vincular el artefacto 
            como, encima del nombre principal. Estos se utilizarán además de los
            alias que el propio artefacto declare internamente.

        :param default: Si este artefacto debería ser la colección por defecto.

        .. versionadded:: 1.0
        """
        if nombre is None:
            if artefacto.nombre:
                nombre = artefacto.nombre
            elif hasattr(artefacto.cuerpo, "nombre_de_func"):
                nombre = artefacto.cuerpo.nombre_de_func
            elif hasattr(artefacto.cuerpo, "__name__"):
                nombre = artefacto.__name__
            else:
                raise ValueError("¡No se pudo obtener un nombre para este artefacto!")  # noqa
        nombre = self.transformar(nombre)
        if nombre in self.colecciones:
            err = "Conflicto de nombre: esta colección ya tiene una subcolección llamada {!r}"  # noqa
            raise ValueError(err.format(nombre))
        self.artefactos[nombre] = artefacto
        for alias in list(artefacto.alias) + list(alias or []):
            self.artefactos.alias(self.transformar(alias), to=nombre)
        if default is True or (default is None and artefacto.es_predeterminado):
            if self.default:
                msj = "'{}' no puede ser el predeterminado porque '{}' ya lo es!"
                raise ValueError(msj.format(nombre, self.default))
            self.default = nombre

    def ad_coleccion(self, colecc, nombre=None):
        """
        Agrega `.Coleccion` ``colecc`` Como subcolección de ésta.

        :param colecc: La `.Coleccion` para añadir.

        :param str nombre:
            El nombre con el que vincular la colección. Por defecto 
            es el propio nombre interno de la colección.

        .. versionadded:: 1.0
        """
        # Manejar modulo-como-coleccion
        if isinstance(colecc, types.ModuleType):
            colecc = Coleccion.del_modulo(colecc)
        # Asegúrate de tener un nombre o muere en el intento
        nombre = nombre or colecc.nombre
        if not nombre:
            raise ValueError("¡Las colecciones sin-raiz deben tener un nombre!")
        nombre = self.transformar(nombre)
        # Prueba de conflicto
        if nombre in self.artefactos:
            err = (
                "Conflicto de nombre: esta colección ya tiene un artefacto llamado {!r}"
            )  # noqa
            raise ValueError(err.format(nombre))
        # Insertar
        self.colecciones[nombre] = colecc

    def _ruta_partida(self, ruta):
        """
        Obtener primera colección + el resto, de una ruta de artefacto.

        P.ej. para ``"subcoleccion.nombredeartefacto" ``, devuelve 
        ``("subcoleccion", "nombredeartefacto")``; para 
        ``"subcoleccion.anidado.nombredeartefacto"`` devuelve
        ``("subcoleccion", "anidado.nombredeartefacto")``, etc.

        Una ruta vacía se vuelve simplemente ``('', '')``.
        """
        partes = ruta.split(".")
        colecc = partes.pop(0)
        resto = ".".join(partes)
        return colecc, resto

    def subcoleccion_desde_ruta(self, ruta):
        """
        Dada una ``Ruta`` (Path) a una subcoleccion, retorna esa subcoleccion.

        .. versionadded:: 1.0
        """
        parts = ruta.split(".")
        coleccion = self
        while parts:
            coleccion = coleccion.colecciones[parts.pop(0)]
        return coleccion

    def __getitem__(self, nombre=None):
        """
        Retorna un artefacto llamado ``nombre``. Honra alias y subcolecciones.

        Si esta colección tiene un artefacto predeterminado, se devuelve 
        cuando ``nombre`` está vacío o ``None``. Si se proporciona una entrada
        vacía y no se ha seleccionado ningún artefacto como predeterminado, se
        generará ValueError.

        Los artefactos dentro de las subcolecciones deben presentarse en forma
        de puntos, p. Ej. 'foo.bar'. Los artefactos predeterminados de la
        subcolección se devolverán con el nombre de la subcolección'es.

        .. versionadded:: 1.0
        """
        return self.artefacto_con_config(nombre)[0]

    def _artefacto_con_config_fusionada(self, colecc, resto, nuestro):
        artefacto, config = self.colecciones[colecc].artefacto_con_config(resto)
        return artefacto, dict(config, **nuestro)

    def artefacto_con_config(self, nombre):
        """
        Devuelve el artefacto llamado ``nombre`` más su dic de configuración.

        P.ej. en un árbol anidado profundamente, este método devuelve el 
        `.Artefacto`, y un dic de configuración creado al combinar el de esta
        `.Coleccion` y cualquier `Colecciones <.Coleccion>` anidadas, hasta la
        que realmente contiene el `.Artefacto`.

        Ver `~.Coleccion.__getitem__` para conocer la semántica del arg 
        ``nombre``.

        :returns: Dos-tuplas de (`.Artefacto`, `dic`).

        .. versionadded:: 1.0
        """
        # Nuestra configuración de nivel superior
        nuestro = self.configuracion()
        # Artefacto predeterminado para esta colección en sí
        if not nombre:
            if self.default:
                return self[self.default], nuestro
            else:
                raise ValueError("Esta colección no tiene artefacto por defecto.")
        # Normalizar el nombre al formato que esperamos
        nombre = self.transformar(nombre)
        # Non-default artefactos dentro de subcoleciones -> recurse (sorta)
        if "." in nombre:
            colecc, resto = self._ruta_partida(nombre)
            return self._artefacto_con_config_fusionada(colecc, resto, nuestro)
        # Artefacto predeterminado para subcolecciones (via busquedad empty-nombre)
        if nombre in self.colecciones:
            return self._artefacto_con_config_fusionada(nombre, "", nuestro)
        # Búsqueda regular de artefacto 
        return self.artefactos[nombre], nuestro

    def __contains__(self, nombre):
        try:
            self[nombre]
            return True
        except KeyError:
            return False

    def a_contextos(self):
        """
        Devuelve todos los artefactos y subartefactos(acciones) contenidos 
        como una lista de contextos del analizador.
    
        .. versionadded:: 1.0
        """
        resultado = []
        for principal, alias in six.iteritems(self.nombres_de_artefactos):
            artefacto = self[principal]
            resultado.append(
                AnalizadorDeContexto(
                    nombre=principal, alias=alias, args=artefacto.obtener_argumentos()
                )
            )
        return resultado

    def nombre_del_subartefacto(self, nombre_de_coleccion, nombre_de_artefacto):
        return ".".join(
            [self.transformar(nombre_de_coleccion), self.transformar(nombre_de_artefacto)]
        )

    def transformar(self, nombre):
        """
        Transforma ``nombre`` con la configuración de comportamiento de
        auto-guiones.

        Si el atributo ``nombre_auto_guion`` de la colección es ``True``
        (predeterminado), todos los guiones bajos no iniciales/finales se 
        convierten en guiones. (Los guiones bajos iniciales/finales tienden
        a desaparecer en cualquier otra parte de la pila).

        Si es ``False``, se aplica lo inverso: todos los guiones se 
        convierten en guiones bajos.

        .. versionadded:: 1.0
        """
        # Cortocircuito en cualquier cosa non-aplicable, p. Ej. cadenas vacías, bools, None,
        # etc.
        if not nombre:
            return nombre
        from_, to = "_", "-"
        if not self.nombre_auto_guion:
            from_, to = "-", "_"
        reemplazo = []
        fin = len(nombre) - 1
        for i, char in enumerate(nombre):
            # No reemplace los guiones bajos iniciales o finales (+ teniendo en cuenta los
            # nombres con puntos)
            # TODO: no estoy 100% convencido de esto/puede estar exponiendo una 
            # discrepancia entre este nivel y los niveles más altos que tienden a eliminar
            # por completo los guiones bajos iniciales/finales.
            if (
                i not in (0, fin)
                and char == from_
                and nombre[i - 1] != "."
                and nombre[i + 1] != "."
            ):
                char = to
            reemplazo.append(char)
        return "".join(reemplazo)

    def _transformar_con_lexicon(self, viejo):
        """
        Toma un Lexicon y apliqua ".transformar" a sus claves y alias.

        :returns: Un nuevo Lexicon.
        """
        nuevo_ = Lexicon()
        # Los léxicos exhiben solo sus claves reales en la mayoría de los lugares, 
        # por lo que esto solo tomará esos, no los alias.
        for clave, valor in six.iteritems(viejo):
            # Realice una Deepcopy (copia profunda) del valor para que no solo estemos
            # copiando una referencia
            nuevo_[self.transformar(clave)] = copy.deepcopy(valor)
        # Copie también todos los alias, que son asignaciones de teclas de cadena_a_cadena
        for clave, valor in six.iteritems(viejo.alias):
            nuevo_.alias(from_=self.transformar(clave), to=self.transformar(valor))
        return nuevo_

    @property
    def nombres_de_artefactos(self):
        """
        Devuelve todos los identificadores de artefacto para esta colección 
        como un diccionario de un-nivel.

        Específicamente, un dic con los nombres de artefacto principal/"real" 
        como clave y cualquier alias como valor de lista.

        Básicamente, colapsa el árbol hangar en una única colección
        de cadenas de invocación facilmente-escaneable y, por lo tanto, es 
        adecuado para cosas como listados de artefactos de estilo-plano o 
        transformación en contextos de analizador.

        .. versionadded:: 1.0
        """
        ret = {}
        # Nuestros propios artefactos no tienen prefijo, solo ingresan 
        # como están: {nombre: [alias]}
        for nombre, artefacto in six.iteritems(self.artefactos):
            ret[nombre] = list(map(self.transformar, artefacto.alias))
        # Los artefactos de la subcolección obtienen el prefijo de nombre + alias
        for nombre_de_colecc, colecc in six.iteritems(self.colecciones):
            for nombre_de_artefacto, alias in six.iteritems(colecc.nombres_de_artefactos):
                # Transmitir a la lista para manejar el valor de retorno de Py3 map() 'map',
                # por lo que podemos agregarlo a continuación si es necesario.
                alias = list(
                    map(lambda x: self.nombre_del_subartefacto(nombre_de_colecc, x), alias)
                )
                # Marque el nombre de la colección en la lista de alias si este artefacto
                # es el predeterminado de la colección.
                if colecc.default == nombre_de_artefacto:
                    alias += (nombre_de_colecc,)
                ret[self.nombre_del_subartefacto(nombre_de_colecc, nombre_de_artefacto)] = alias
        return ret

    def configuracion(self, rutafact=None):
        """
        Obtenga valores de config. fusionado de la colección y los hijos.

        :param rutafact:
            (Opcional) Artefacto nombre/ruta, idéntico al usado para 
            `~.Coleccion.__ getitem__` (por ejemplo, puede estar punteado 
            para anidado de artefactos, etc.) Se usa para decidir qué ruta
            seguir en el árbol de colección al combinar valores de
            configuración.

        :returns: Un `dic` que contiene valores de configuración.

        .. versionadded:: 1.0
        """
        if rutafact is None:
            return copiar_dic(self._configuracion)
        return self.artefacto_con_config(rutafact)[1]

    def configurar(self, opciones):
        """
        (Recursivamente) fusiona ``opciones`` en la actual `.configuracion`.

        Las opciones configuradas de esta manera estarán disponibles para 
        todos los artefactos. Se recomienda utilizar claves únicas para 
        evitar posibles conflictos con otras opciones de configuración

        Por ejemplo, si estaba configurando un directorio de destino de 
        compilación de documentos de Sphinx, es mejor usar una clave como
         ``'sphinx.objetivo'`` que simplemente ``'objetivo'``.

        :param opciones: Objeto que implementa el protocolo del diccionario.
        :returns: ``None``.

        .. versionadded:: 1.0
        """
        fusionar_dics(self._configuracion, opciones)

    def serializado(self):
        """
        Devuelve una version-apropiada-para-la-serialización de este objeto.

        Consulte la documentación para `.Programa` y su formato de lista de
        artefactos ``json``; este método es el controlador de esa 
        funcionalidad.

        .. versionadded:: 1.0
        """
        return {
            "nombre": self.nombre,
            "help": lineadeayuda(self),
            "default": self.default,
            "artefactos": [
                {
                    "nombre": self.transformar(x.nombre),
                    "help": lineadeayuda(x),
                    "alias": [self.transformar(y) for y in x.alias],
                }
                for x in sorted(self.artefactos.valores(), key=lambda x: x.nombre)
            ],
            "colecciones": [
                x.serializado()
                for x in sorted(
                    self.colecciones.valores(), key=lambda x: x.nombre or ""
                )
            ],
        }
