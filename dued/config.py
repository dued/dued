import copy
import json
import os
import types
from os.path import join, splitext, expanduser

from .entorno import Entorno
from .excepciones import TipoDeArchivoDesconocido, MiembroDeConfigNoSeleccionable
from .corredores import Local
from .terminales import WINDOWS
from .util import debug, six, yaml


if six.PY3:
    try:
        from importlib.machinery import SourceFileLoader
    except ImportError:  # PyPy3
        from importlib._bootstrap import _SourceFileLoader as SourceFileLoader

    def load_source(nombre, ruta):
        if not os.path.exists(ruta):
            return {}
        return vars(SourceFileLoader("mod", ruta).load_module())


else:
    import imp

    def load_source(nombre, ruta):
        if not os.path.exists(ruta):
            return {}
        return vars(imp.load_source("mod", ruta))


class DataProxy(object):
    """
    Clase de ayuda que implementa el acceso anidado dic+atrib para `.Config`.

    Específicamente, se usa tanto para `.Config` como para envolver cualquier
    otro dicc asignado como valores de configuración (recursivamente).

    .. warning::
        Todos los métodos (de este objeto o en subclases) deben tener cuidado 
        de inicializar nuevos atributos a través de
        ``self._set(nombre='valor')``, ¡o se producirán errores de 
        recursividad!

    .. versionadded:: 1.0
    """

    # Atributos que se proxean (transfieren) a través del obj de config interno de dicc-fusionado.
    _proxies = (
        tuple(
            """
        get
        has_key
        items
        iteritems
        iterkeys
        itervalues
        claves
        valores
    """.split()
        )
        + tuple(
            "__{}__".format(x)
            for x in """
        cmp
        contains
        iter
        sizeof
    """.split()
        )
    )

    @classmethod
    def datos_desde(cls, datos, raiz=None, rutaclave=tuple()):
        """
        Constructor alternativo para DataProxies 'baby' usado como valores de
        sub-dicc.

        Permite la creación de objetos DataProxy independientes y también
        permite que las subclases como `.Config` definan su propio 
        ``__init__`` sin confundir las dos.

        :param dict datos:
            Los datos personales de este DataProxy en particular. Requerido,
            son los datos que se están transfiriendo (proxeando).

        :param raiz:
            Manejador opcional en un DataProxy/Config raíz que 
            necesita notificación sobre actualizaciones de datos.

        :param tuple rutaclave:
            Tupla opcional que describe la ruta de las claves que conducen a
            la ubicación de este DataProxy dentro de la estructura ``raíz``
            (raiz) Requerido si se dio ``raiz`` (y viceversa).

        .. versionadded:: 1.0
        """
        obj = cls()
        obj._set(_config=datos)
        obj._set(_raiz=raiz)
        obj._set(_rutaclave=rutaclave)
        return obj

    def __getattr__(self, clave):
        # NOTE: debido a la semántica predeterminada de búsqueda de atributos
        # de Python, los atributos "reales" siempre se mostrarán en el acceso
        # a los atributos y este método se omite. Ese comportamiento es bueno 
        # para nosotros (es más intuitivo que tener una clave de configuración q
        # que sombree accidentalmente un atributo o método real).
        try:
            return self._get(clave)
        except KeyError:
            # Proxy las vars más especiales para configurar el protocolo dict.
            if clave in self._proxies:
                return getattr(self._config, clave)
            # De lo contrario, genere AttributeError útil para seguir getattr proto.
            err = "No attribute or config clave found for {!r}".format(clave)
            attrs = [x for x in dir(self.__class__) if not x.startswith("_")]
            err += "\n\nValid claves: {!r}".format(
                sorted(list(self._config.keys()))
            )
            err += "\n\nValid real attributes: {!r}".format(attrs)
            raise AttributeError(err)

    def __setattr__(self, clave, valor):
        # Convierta los conjuntos-de-atributos en actualizaciones de config siempre
        # que no tengamos un atributo real con el nombre/clave dado.
        tiene_atributo_real = clave in dir(self)
        if not tiene_atributo_real:
            # Asegúrese de activar nuestro propio __setitem__ en lugar de ir 
            # directamente a nuestro dict/cache interno
            self[clave] = valor
        else:
            super(DataProxy, self).__setattr__(clave, valor)

    def __iter__(self):
        # Por alguna razón, Python ignora nuestro __hasattr__ al determinar 
        # si admitimos __iter__. QUE MAL
        return iter(self._config)

    def __eq__(self, otro):
        # NOTE: No se puede usar el proxy __eq__ porque el RHS siempre será un 
        # obj de la clase actual, no la clase de proxy, y eso causa NotImplemented. 
        # Intente comparar con otros objetos como nosotros, recurriendo a un valor
        # no muy comparable (None) para que la comparación falle.
        otro_val = getattr(otro, "_config", None)
        # But we can compare to vanilla dicts just fine, since our _config is
        # itself just a dict.
        if isinstance(otro, dict):
            otro_val = otro
        return self._config == otro_val

    # Hacer imposible, porque toda nuestra razón de ser es ser algo mutable. 
    # Las subclases con atributos mutables pueden anular esto.
    # NOTE: esto es principalmente una concesión a Python 2, v3 lo hace automáticamente.
    __hash__ = None

    def __len__(self):
        return len(self._config)

    def __setitem__(self, clave, valor):
        self._config[clave] = valor
        self._trazar_modificacion_de(clave, valor)

    def __getitem__(self, clave):
        return self._get(clave)

    def _get(self, clave):
        # Cortocircuito si los mecanismos de pickling/copia preguntan si
        # tenemos __setstate__ etc; preguntarán esto sin llamar a nuestro
        #  __init__ primero, por lo que, de lo contrario, estaríamos en un
        #  catch-22 que causa RecursionError.
        if clave in ("__setstate__",):
            raise AttributeError(clave)
        # En este punto deberíamos poder asumir un self._config ...
        valor = self._config[clave]
        if isinstance(valor, dict):
            # La ruta clave del nuevo objeto es simplemente la clave, precedida 
            # por nuestra propia ruta clave si tenemos una.
            rutaclave = (clave,)
            if hasattr(self, "_rutaclave"):
                rutaclave = self._rutaclave + rutaclave
            # Si no tenemos _raiz, debemos ser la raiz, entonces somos nosotros. 
            # De lo contrario, pase nuestro manejador por la raiz.
            raiz = getattr(self, "_raiz", self)
            valor = DataProxy.datos_desde(datos=valor, raiz=raiz, rutaclave=rutaclave)
        return valor

    def _set(self, *args, **kwargs):
        """
        Solución alternativa de conveniencia del comportamiento predeterminado
        de 'atributos son claves de configuración'.

        Utiliza `object .__ setattr__` para evitar el comportamiento normal de 
        proxy de la clase, pero es menos verboso que usarlo directamente.

        Tiene dos modos (que pueden combinarse si realmente lo desea):

        - ``self._set('attrname', valor)``, al igual que ``__setattr__``
        - ``self._set(attname=valor)`` (es decir, kwargs), incluso escribiendo 
           menos.
        """
        if args:
            object.__setattr__(self, *args)
        for clave, valor in six.iteritems(kwargs):
            object.__setattr__(self, clave, valor)

    def __repr__(self):
        return "<{}: {}>".format(self.__class__.__name__, self._config)

    def __contains__(self, clave):
        return clave in self._config

    @property
    def _es_hoja(self):
        return hasattr(self, "_raiz")

    @property
    def _es_raiz(self):
        return hasattr(self, "_modificar")

    def _trazar_eliminacion_de(self, clave):
        # Agarrar el objeto raiz responsable de rastrear las remociones; ya
        # sea la raiz referenciada (si somos una hoja) o nosotros mismos 
        # (si no lo somos). (Los nodos intermedios nunca tienen nada más
        # que __getitem__ invocados, de lo contrario, por definición, se
        # tratan como una hoja).
        objetivo = None
        if self._es_hoja:
            objetivo = self._raiz
        elif self._es_raiz:
            objetivo = self
        if objetivo is not None:
            objetivo._eliminar(getattr(self, "_rutaclave", tuple()), clave)

    def _trazar_modificacion_de(self, clave, valor):
        objetivo = None
        if self._es_hoja:
            objetivo = self._raiz
        elif self._es_raiz:
            objetivo = self
        if objetivo is not None:
            objetivo._modificar(getattr(self, "_rutaclave", tuple()), clave, valor)

    def __delitem__(self, clave):
        del self._config[clave]
        self._trazar_eliminacion_de(clave)

    def __delattr__(self, nombre):
        # Asegúrese de no estropear la eliminación de atributos verdaderos 
        # para las situaciones que realmente lo desean. (Poco común, pero no raro).
        if nombre in self:
            del self[nombre]
        else:
            object.__delattr__(self, nombre)

    def limpiar(self):
        claves = list(self.claves())
        for clave in claves:
            del self[clave]

    def pop(self, *args):
        # Debe probar esto antes de (posiblemente) mutar self._config
        clave_existio = args and args[0] in self._config
        # Siempre tenemos un _config (ya sea un dict real o un caché de niveles 
        # combinados) para que podamos recurrir a él para todos los casos de
        # esquina que manejan re: args (arity, manejo de un valor predeterminado,
        # aumento de KeyError, etc.)
        ret = self._config.pop(*args)
        # Si parece que no se produjo ningún estallido (la clave no estaba allí), 
        # presumiblemente el usuario dio el valor predeterminado, por lo que
        # podemos hacer un corto para regresar aquí, no es necesario rastrear 
        # una eliminación que no sucedió.
        if not clave_existio:
            return ret
        # Aquí, podemos suponer que existió al menos la primera posarg (clave).
        self._trazar_eliminacion_de(args[0])
        # En todos los casos, devuelve el valor explotado.
        return ret

    def popitem(self):
        ret = self._config.popitem()
        self._trazar_eliminacion_de(ret[0])
        return ret

    def setdefault(self, *args):
        # Debe probar por adelantado si la clave existió de antemano
        clave_existio = args and args[0] in self._config
        # Correr localmente
        ret = self._config.setdefault(*args)
        # La clave ya existía -> nada había mutado, cortocircuito
        if clave_existio:
            return ret
        # Aquí, podemos suponer que la clave no existía y, por lo tanto, el 
        # usuario debe haber proporcionado un 'default' (si no lo hubiera hecho,
        # se habría exceptuado el setdefault() real anterior).
        clave, default = args
        self._trazar_modificacion_de(clave, default)
        return ret

    def actualizar(self, *args, **kwargs):
        if kwargs:
            for clave, valor in six.iteritems(kwargs):
                self[clave] = valor
        elif args:
            # TODO: quejarse si arity>1
            arg = args[0]
            if isinstance(arg, dict):
                for clave in arg:
                    self[clave] = arg[clave]
            else:
                # TODO: Ser más estricto sobre la entrada en este caso
                for pair in arg:
                    self[pair[0]] = pair[1]


class Config(DataProxy):
    """
    la clase de manejo de configuración principal de dued.

    Ver: doc: `/kh_general/configuracion` para detalles sobre el sistema de
    configuración que implementa esta clase, incluyendo :ref:`jerarquía de 
    configuración <jerarquía-de-config> `. El resto de la documentación de 
    esta lase asume familiaridad con ese documento.

    **Acceso**

    Se puede acceder y/o actualizar los valores de configuración usando la
    sintaxis dict::

        config['foo']

    o sintaxis de atributo::

        config.foo

    El anidamiento funciona de la misma manera: los valores de configuración
    del dict se convierten en objetos que respetan tanto el protocolo de 
    diccionario como el método de acceso a atributos::

       config['foo']['bar']
       config.foo.bar

    **Una nota sobre métodos y acceso a atributos**

    Esta clase implementa todo el protocolo del diccionario: métodos como
    ``claves``, ``valores``, ``items``, ``pop``, etc., deberían funcionar
    como lo hacen en los dicc regulares. También implementa nuevos métodos
    específicos de configuración como `cargar_sistema`,`cargar_coleccion`,
    `combinar`,`clonar`, etc.

    .. warning::
        En consecuencia, esto significa que si tiene opciones de configuración
        compartiendo nombres con estos métodos, **debe** usar sintaxis de 
        diccionario (por ejemplo, ``miconfig['claves']``) para acceder a los
        datos de configuración.

    **Coclo de Vida**

    En el momento de la inicialización, `.Config`:

    - crea estructuras de datos por-nivel;
    - almacena los niveles suministrados a `__init__`, como defaults o
      anulaciones, así como las diversos patrones rutas/nombredearchivo;
    - y carga archivos de configuración, si los encuentra (aunque normalmente
      esto solo significa archivos de nivel de usuario y de sistema, ya que
      los archivos de proyecto y tiempo de ejecución necesitan más información
      antes de que se puedan encontrar y cargar).

        - Este paso se puede omitir especificando ``lento=True``.

    En este punto, `.Config` es completamente utilizable - y debido a que 
    carga preventivamente algunos archivos de configuración, esos archivos de
    config pueden afectar cualquier cosa que venga después, como el análisis
    CLI o la carga de colecciones de artefacto.

    En el caso de uso de CLI, el procesamiento adicional se realiza después de
    la instanciación, utilizando los métodos ``load_*`` como 
    `cargar_anulaciones`, `cargar_proyecto`, etc.

    - el resultado del análisis de argumento/opción se aplica al nivel de
      anulaciones;
    - se carga un archivo de configuración a nivel de proyecto, ya que depende
      de una colección de artefactos cargada;
    - se carga un archivo de configuración en tiempo de ejecución, si se 
      proporcionó su bandera;
    - luego, para cada artefacto que se esté ejecutando:

        - se cargan los datos per-coleccion (solo es posible ahora que tenemos
          coleccion & artefacto en la mano);
        - Se cargan los datos del entorno de shell (debe hacerse al final del
          proceso debido a que se usa el resto de la configuración como guía
          para interpretar los nombres de var de entorno).

    En este punto, el objeto de configuración se entrega al artefacto que se
    está ejecutando, como parte de su ejecución `.Contexto`.

    Cualquier modificación realizada directamente en el propio `.Config`
    después de este punto terminará almacenada en su propio nivel de
    configuración (superior), lo que facilita la depuración de los valores
    finales.

    Finalmente, cualquier *eliminación* realizada en el `.Config` (por 
    ejemplo, aplicaciones de mutadores de dict-style como ``pop``, 
    ``limpiar``, etc.) también se rastrea en su propia estructura, lo que
    permite que el objeto de configuración respete tales llamadas a métodos
    sin mutar los datos fuente subyacentes.

    **Atributos de clase especiales**

    Los siguientes atributos de nivel-de-clase se utilizan para la 
    configuración de bajo-nivel del propio sistema de configuración, como qué
    rutas de archivo cargar. Están destinados principalmente a ser 
    reemplazados por subclases.

    - ``prefijo``: proporciona el valor predeterminado para 
      ``prefijo_de_archivo`` (directamente) y ``entorno_prefijo`` (en 
      mayúsculas). Consulte sus  descripciones para obtener más detalles. Su 
      valor por default es ``"dued"``.
    - ``prefijo_de_archivo``: el archivo de configuración 'basename' 
      predeterminado (aunque no es un literal basename; puede contener partes
      de ruta si se desea) que se agrege a los valores configurados de 
      ``sistema_prefijo``, ``ususario_prefijo``, etc, para llegar a las
      rutas de archivo finales (pre-extension).

      Por lo tanto, de forma predeterminada, una ruta de archivo de 
      configuración a nivel del sistema concatena el ``sistema_prefijo`` de
      ``/etc/`` con el ``prefijo_de_archivo`` de ``dued`` para llegar a rutas 
      como ``/etc/dued.json``.

      Por defecto es ``None``, lo que significa utilizar el valor de 
      ``prefijo``.

    - ``entorno_prefijo``: Un prefijo usado (junto con un guión bajo de 
      unión) para determinar qué variables de entorno se cargan como nivel de 
      configuración de var de entorno. Dado que su default es el valor de
      ``prefijo`` en mayúsculas, esto significa que se buscan por defecto
      vars de entorno como ``DUED_CORRER_ECHO``.

      Por defecto es ``None``, lo que significa utilizar el valor de
      ``prefijo``.

    .. versionadded:: 1.0
    """

    prefijo = "dued"
    prefijo_de_archivo = None
    entorno_prefijo = None

    @staticmethod
    def global_defaults():
        """
        Devuelve la configuración básica predeterminada de Dued.

        Generalmente solo para uso por parte interna de `.Config`. Para
        obtener descripciones de estos valores, consulte 
        :ref:`valores-predeterminados`.

        Las subclases pueden optar por anular este método, llamando a 
        ``Config.global_defaults`` y aplicando `.fusionar_dics` al
        resultado, para agregar o modificar estos valores.

        .. versionadded:: 1.0
        """

        # En Windows, no tendrá /bin/bash, busque un COMSPEC entorno var configurado
        # (https://en.wikipedia.org/wiki/COMSPEC) o, de lo contrario, recurra
        # a un cmd.exe no calificado.
        if WINDOWS:
            shell = os.environ.get("COMSPEC", "cmd.exe")
        # De lo contrario, suponga Unix, la mayoría de las distribuciones tienen
        # /bin/bash disponible.
        # TODO: considere una alternativa automática a /bin/sh para sistemas que
        # carecen de /bin/bash; sin embargo, los usuarios pueden configurar 
        # correr.shell con bastante facilidad, así que ...
        else:
            shell = "/bin/bash"

        return {
            # TODO: documentamos 'debug' pero no está realmente implementado
            # fuera de entorno var y bandera CLI. Si lo respetamos, tenemos que
            # ir y averiguar en qué puntos podríamos querer llamar a
            # `util.habilita_logs`:
            # - usarlo como un default de respaldo para el análisis de arg no
            #   es de mucha utilidad, ya que en ese momento la config no 
            #   contiene nada más que defaults y valores de bandera CLI
            # - hacerlo en el momento de la carga del archivo puede ser algo útil,
            #   aunque cuando esto sucede puede estar sujeto a cambios pronto
            # - hacerlo en el tiempo de carga de entorno var parece un poco
            #   tonto dado el soporte existente para las pruebas al inicio de
            #   DUED_DEBUG 'debug': False,
            # TODO: Siento que queremos que estos sean más consistentes re: valores
            # predeterminados almacenados aquí vs 'almacenados' como lógica 
            # donde se hace referencia, probablemente hay algunos bits que son todos
            # "si Ninguno -> predeterminado" que podrían ir aquí. Alternativamente,
            # ¿_más_ de estos valores predeterminados son Ninguno?
            "correr": {
                "asincrono": False,
                "rechazado": False,
                "seco": False,
                "echo": False,
                "echo_stdin": None,
                "codificacion": None,
                "entorno": {},
                "err_stream": None,
                "retroceder": True,
                "ocultar": None,
                "ing_stream": None,
                "sal_stream": None,
                "pty": False,
                "reemplazar_ent": False,
                "shell": shell,
                "alarma": False,
                "centinelas": [],
            },
            # Esto no vive dentro del árbol 'correr'; de lo contrario, sería algo
            # más difícil extender/anular en Fabric 2, que tiene una situación de
            # corredor local/remoto dividido. "corredores": {"local": Local},
            "corredores": {"local": Local},
            "sudo": {
                "password": None,
                "prompt": "[sudo] password: ",
                "usuario": None,
            },
            "artefactos": {
                "nombre_auto_guion": True,
                "nombre_de_coleccion": "artefactos",
                "dedupe": True,
                "clase_ejecutor": None,
                "dir_raiz": None,
            },
            "tiempo_de_descanso": {"comando": None},
        }

    def __init__(
        self,
        anulaciones=None,
        defaults=None,
        sistema_prefijo=None,
        ususario_prefijo=None,
        dir_de_py=None,
        acte_ruta=None,
        lento=False,
    ):
        """
        Crea un nuevo objeto de configuración.

        :param dict defaults:
            Un dicc que contiene datos de configuración predeterminados (nivel
            más bajo). Por defecto: global_defaults`.

        :param dict anulaciones:
            A dict containing nivel-de-anulacion config datos. Default: ``{}``.
            Un dicc que contiene los datos de configuración de 
            nivel-de-anulacion. Predeterminado: ``{}``.

        :param str sistema_prefijo:
            Ruta base para la ubicación del archivo de configuración global;
            combinado con el prefijo y los sufijos de archivo para llegar a
            los candidatos de ruta de archivo final.

            Default: ``/etc/`` (por ejemplo, `/etc/dued.yaml`` o 
            ``/etc/dued.json``).

        :param str ususario_prefijo:
            Como ``sistema_prefijo`` pero para el archivo config 
            por-usuario. Estas variables se unen como cadenas, no mediante
            uniones de estilo-ruta, por lo que pueden contener rutas de 
            archivo parciales; para el archivo config por-usuario, esto a
            menudo significa un punto inicial, para hacer que el resultado
            final sea un archivo oculto en la mayoría de los sistemas.

            Default: ``~/.`` (por ejemplo, ``~/.dued.yaml``).

        :param str dir_de_py:
            Opcional, ruta de directorio de la `.Coleccion` cargado 
            actualmente 8como lo carga` .Cargador`). Cuando no está vacío,
            activará la búsqueda de arch. config por proyecto en este dir.

        :param str acte_ruta:
            Opcional ruta a un archivo de configuración en tiempo de
            ejecución.

            Se usa para ocupar el penúltimo espacio en la jerarquía de config.
            Debe ser una ruta de archivo completa a un archivo existente, no
            una ruta de directorio o un prefijo.

        :param bool lento:
            para cargar automáticamente algunos de los niveles de 
            configuración inferiores.

            Por defecto es (``lento=False``), ``__init__`` llama automáticamente
            a `cargar_sistema` y `cargar_usuario` para cargar los archivos de
            config del sistema y del usuario, respectivamente.

            Para tener más control sobre qué se carga y cuándo, puede decir
            ``lento=True`` y no se realiza ninguna carga automática.
            
            .. note::
                Si da ``default`` y/o ``anulaciones`` como kwargs ``__init__`` en
                lugar de esperar a usar después `cargar_defaults` o 
                `cargar_anulaciones`, esos *terminarán* cargados inmediatamente.

        """
        # Técnicamente, un detalle de implementación: no exponer en API pública.
        # Almacena configuraciones fusionadas y se accede a través de DataProxy.
        self._set(_config={})

        # Sufijos de archivos de configuración para buscar, en orden de preferencia.
        self._set(_sufijos_de_archivo=("yaml", "yml", "json", "py"))

        # Valores de configuración predeterminados, normalmente una copia de `global_defaults`.
        if defaults is None:
            defaults = copiar_dic(self.global_defaults())
        self._set(_defaults=defaults)

        # Datos de configuración controlados por colección, recopilados del 
        # árbol de colección que contiene el artefacto en ejecución.
        self._set(_coleccion={})

        # Prefijo de ruta buscado para el archivo de configuración del sistema.
        # NOTE: No hay un prefijo de sistema predeterminado en Windows.
        if sistema_prefijo is None and not WINDOWS:
            sistema_prefijo = "/etc/"
        self._set(_sistema_prefijo=sistema_prefijo)
        # Ruta al archivo de configuración del sistema cargado, si lo hubiera.
        self._set(_sistema_ruta=None)
        # Si el archivo de configuración del sistema se ha cargado o no (o 
        # ``None`` si aún no se ha intentado cargar).
        self._set(_sistema_seteado=None)
        # Data loaded from the system config file.
        self._set(_sistema={})

        # Prefijo de ruta buscado para archivos de configuración por usuario.
        if ususario_prefijo is None:
            ususario_prefijo = "~/."
        self._set(_ususario_prefijo=ususario_prefijo)
        # Ruta al archivo de configuración de usuario cargado, si lo hubiera.
        self._set(_ususario_ruta=None)
        # Whether the user config file has been loaded or not (or ``None`` if
        # no loading has been attempted yet.)
        # Si el archivo de configuración del usuario se ha cargado o no (o 
        # ``None`` si aún no se ha intentado cargar).
        self._set(_ususario_seteado=None)
        # Datos cargados desde el archivo de configuración por usuario.
        self._set(_ususario={})

        # Como es posible que desee setealo post-inicialización, los 
        # atributos relacionados con el archivo conf del proyecto se
        # inicializan o sobrescriben mediante un método específico.
        self.setea_ubic_del_py(dir_de_py)

        # Entorno variable nombre prefix
        entorno_prefijo = self.entorno_prefijo
        if entorno_prefijo is None:
            entorno_prefijo = self.prefijo
        entorno_prefijo = "{}_".format(entorno_prefijo.upper())
        self._set(_entorno_prefijo=entorno_prefijo)
        # Config datos loaded from the shell environment.
        self._set(_entorno={})

        # Como es posible que desee configurarlo post-inicialización, los 
        # atributos relacionados con el archivo de conf en tiempo de 
        # ejecución(acte) se inicializan o sobrescriben con un método específico.
        self.setea_ruta_del_acte(acte_ruta)

        # anulaciones - nivel de configuración normal más alto. Normalmente
        # se rellena con banderas de línea de comando.
        if anulaciones is None:
            anulaciones = {}
        self._set(_anula=anulaciones)

        # Nivel más alto absoluto: modificaciones del usuario.
        self._set(_modificaciones={})
        # Y su hermano: eliminaciones de usuarios. (almacenado como un dicc plano
        # de claves de ruta clave-valor ficticios (dummy), para pruebas/eliminación
        # de miembros en tiempo constante sin recursividad desordenada. 
        # TODO: ¿tal vez rehacer _everything_ de esa manera? en _modificaciones
        # y otros niveles, los valores por supuesto serían importantes y no solo None)
        self._set(_eliminaciones={})

        # Carga conveniente de archivos de usuario y sistema, ya
        # que no requieren otros niveles para funcionar.
        if not lento:
            self._cargar_archivo_de_conf_base()

        # Combinar siempre; de lo contrario, los valores predeterminados, etc.
        # no se pueden utilizar hasta que el creador o una subrutina lo haga.
        self.combinar()

    def _cargar_archivo_de_conf_base(self):
        # Solo una refactorización de algo hecho en init unlazy o en clonar()
        self.cargar_sistema(combinar=False)
        self.cargar_usuario(combinar=False)

    def cargar_defaults(self, datos, combinar=True):
        """
        Setea o reemplaza el nivel de configuración 'defaults', desde 
        ``datos``.

        :param dict datos: Los datos de config se cargarán como nivel por
        defecto.

        :param bool combinar:
            Ya sea para combinar los datos cargados en la config. central.
            por Defecto:``True``

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        self._set(_defaults=datos)
        if combinar:
            self.combinar()

    def cargar_anulaciones(self, datos, combinar=True):
        """
        Setea o reemplaza el nivel de configuración 'anulaciones', desde ``datos``.

        :param dict datos: Los datos de config se carga como nivel de
            anulaciones

        :param bool combinar:
            Ya sea para combinar los datos cargados en la config. central.
            por Defecto:``True``

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        self._set(_anula=datos)
        if combinar:
            self.combinar()

    def cargar_sistema(self, combinar=True):
        """
        Carga un archivo de config a nivel-sistema, si es posible.

        Chequea la ruta configurada ``_sistema_prefijo``, que por 
        defecto es ``/etc``, entonc. cargará archivos como ``/etc/dued.yml``.

        :param bool combinar:
            Ya sea para combinar los datos cargados en la config. central.
            por Defecto:``True``

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        self._cargar_archivo(prefijo="sistema", combinar=combinar)

    def cargar_usuario(self, combinar=True):
        """
        Carga un archivo de config a nivel-ususario, si es posible.

        Chequea la ruta configurada ``_prefijo_del_ususario``, que por 
        defecto es ``~/.``, entonc. cargará archivos como ``~/.dued.yml``.

        :param bool combinar:
            Ya sea para combinar los datos cargados en la config. central.
            por Defecto:``True``

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        self._cargar_archivo(prefijo="usuario", combinar=combinar)

    def cargar_proyecto(self, combinar=True):
        """
        Carga un archivo de config a nivel-proyecto, si es posible.

        Comprueba el valor de ``_proyecto_prefijo`` configurado derivado 
        de la ruta dada a `setea_ubic_del_py`, que normalmente se establece en
        el directorio que contiene la colección de artefacto cargada.

        Por lo tanto, si se ejecutara la herramienta CLI para una colección de
        artefactos ``/home/myuser/code/dued.yml``, `cargar_proyecto` buscaría
        archivos como ``/home/myuser/code/dued.yml``.

        :param bool combinar:
            Ya sea para combinar los datos cargados en la config. central.
            por Defecto:``True``

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        self._cargar_archivo(prefijo="proyecto", combinar=combinar)

    def setea_ruta_del_acte(self, ruta):
        """
        Establece la ruta del archivo de configuración en tiempo de ejecución.

        .. versionadded:: 1.0
        """
        # Ruta al archivo de configuración de tiempo de ejecución 
        # especificado por el usuario.
        self._set(_ruta_al_acte=ruta)
        # Datos cargados desde el archivo de configuración en tiempo de ejecución.
        self._set(_acte={})
        # Si el archivo de configuración de tiempo de ejecución se ha cargado
        # o no (o ``None`` si aún no se ha intentado cargar).
        self._set(_acte_seteado=None)

    def cargar_acte(self, combinar=True):
        """
        Carga un archivo de configuración a nivel-acte, si se especificó uno.

        When the CLI framework creates a `Config`, it sets ``_ruta_al_acte``,
        which is a full ruta to the requested config file. This method 
        attempts to load that file.

        Cuando el framework CLI crea una `Config`, establece 
        ``_ruta_al_acte``, que es una ruta completa al archivo de configuración
        solicitado. Este método intenta cargar ese archivo.

        :param bool combinar:
            Ya sea para combinar los datos cargados en la config. central.
            por Defecto:``True``

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        self._cargar_archivo(prefijo="acte", absoluto=True, combinar=combinar)

    def cargar_entorno_shell(self):
        """
        Cargar valores del entorno de shell.

        `.cargar_entorno_shell` está diseñado para ejecutarse tarde en el ciclo
        de vida de un objeto `.Config`, una vez que se hayan cargado todas las
        demás fuentes (como un archivo de config en tiempo de ejecución o 
        config por-colección). La carga desde el shell no es tremendamente 
        costoso, pero debe realizarse en un momento específico para garantizar
        que el comportamiento de "las únicas claves de config conocidas se 
        cargan desde el entorno" funcione correctamente.

        Consulte :ref:`entorno-vars` para obtener detalles sobre esta decisión
        de diseño y otra información sobre cómo se escanean y cargan las
        variables de entorno.

        .. versionadded:: 1.0
        """
        # Forzar la fusión de datos existentes para garantizar que tengamos
        # una imagen actualizada
        debug("Ejecutando pre-combinar para carga de entorno shell...")
        self.combinar()
        debug("Hecho con pre-combinar.")
        cargador = Entorno(config=self._config, prefijo=self._entorno_prefijo)
        self._set(_varent=cargador.cargar())
        debug("Entorno shell cargado, desencadena la fusión final")
        self.combinar()

    def cargar_coleccion(self, datos, combinar=True):
        """
        Actualice los datos de config controlados por coleccion.

        `.cargar_coleccion` está destinado a ser utilizado por la maquinaria
        de ejecución principal de artefactos, que es responsable de obtener
        datos basados en la colección.

        Ver :ref: `coleccion-configuration` para más detalles.

        .. versionadded:: 1.0
        """
        debug("Cargando configuración de coleccion")
        self._set(_coleccion=datos)
        if combinar:
            self.combinar()

    def setea_ubic_del_py(self, ruta):
        """
        Setea la ruta del dir donde se puede encontrar un archivo de conf a
        nivel-de-proyecto.

        No carga ningún archivo por sí solo; para eso, ver `cargar_proyecto`.

        .. versionadded:: 1.0
        """
        # 'Prefijo' para que coincida con los otros conjuntos de atributos
        proyecto_prefijo = None
        if ruta is not None:
            # Asegúrese de que el prefijo esté normalizado a una cadena de
            # ruta similar a un directorio
            proyecto_prefijo = join(ruta, "")
        self._set(_proyecto_prefijo=proyecto_prefijo)
        # Ruta al archivo de config por-proyecto cargado, si lo hubiera.
        self._set(_proyecto_ruta=None)
        # Si el archivo de configuración del proyecto se ha cargado
        # o no (o ``None`` si aún no se ha intentado cargar).
        self._set(_py_seteado=None)
        # Datos cargados desde el archivo de config por proyecto.
        self._set(_py={})

    def _cargar_archivo(self, prefijo, absoluto=False, combinar=True):
        # Preparar
        ubicado = "_{}_ubicado".format(prefijo)
        ruta = "_{}_ruta".format(prefijo)
        datos = "_{}".format(prefijo)
        arreglo = self.prefijo_de_archivo
        if arreglo is None:
            arreglo = self.prefijo
        # Cortocircuito si la carga parece haber ocurrido ya
        if getattr(self, ubicado) is not None:
            return
        # Moar configuracion (mas config!!)
        if absoluto:
            ruta_absoluta = getattr(self, ruta)
            # None -> ruta absoluta esperada pero ninguna establecida, cortocircuito
            if ruta_absoluta is None:
                return
            rutas = [ruta_absoluta]
        else:
            prefijo_de_ruta = getattr(self, "_{}_prefijo".format(prefijo))
            # Cortocircuito si la carga parece innecesaria (por ejemplo, para archivos
            # de config del py cuando no se está quedando sin un proyecto)
            if prefijo_de_ruta is None:
                return
            rutas = [
                ".".join((prefijo_de_ruta + arreglo, x))
                for x in self._sufijos_de_archivo
            ]
        # Empujandolos
        for rutadearchivo in rutas:
            # Normalize
            rutadearchivo = expanduser(rutadearchivo)
            try:
                try:
                    tipo_ = splitext(rutadearchivo)[1].lstrip(".")
                    cargador = getattr(self, "_load_{}".format(tipo_))
                except AttributeError:
                    msj = "Los archivod de config tipo {!r} (del arch. {!r}) no son compatibles! Use uno de: {!r}"  # noqa
                    raise TipoDeArchivoDesconocido(
                        msj.format(tipo_, rutadearchivo, self._sufijos_de_archivo)
                    )
                # Almacenar datos, la ruta en la que se encontró y el hecho de 
                # por que se encontró
                self._set(datos, cargador(rutadearchivo))
                self._set(ruta, rutadearchivo)
                self._set(ubicado, True)
                break
            # Normalmente significa 'no existe tal archivo', así que solo anótelo y salte.
            except IOError as e:
                if e.errno == 2:
                    err = "No vi ninguno {}, ignorando!."
                    debug(err.format(rutadearchivo))
                else:
                    raise
        # Aún ninguna -> ninguna ruta con sufijo fue ubicado, registre este hecho
        if getattr(self, ruta) is None:
            self._set(ubicado, False)
        # Fusionar datos cargados en si se encontró alguno
        elif combinar:
            self.combinar()

    def _cargar_yaml(self, ruta):
        with open(ruta) as fd:
            return yaml.load(fd)

    def _cargar_yml(self, ruta):
        return self._cargar_yaml(ruta)

    def _cargar_json(self, ruta):
        with open(ruta) as fd:
            return json.load(fd)

    def _cargar_py(self, ruta):
        datos = {}
        for clave, valor in six.iteritems(load_source("mod", ruta)):
            # Elimine miembros especiales, ya que siempre serán incorporados
            # y otras cosas especiales que un usuario no querrá en su configuración.
            if clave.startswith("__"):
                continue
            # Generar excepciones en los valores del módulo; son imposibles de cortar.
            # TODO: ¿succionarlo y volver a implementar copy() sin decapado? 
            # Por otra parte, un usuario que intenta introducir un módulo en su
            # configuración probablemente está haciendo algo mejor en el acte/library
            # y no en un "archivo de configuración" ... ¿verdad?
            if isinstance(valor, types.ModuleType):
                err = "'{}' es un módulo, que no se puede utilizar como valor de config. (¿Quizás está dando un archivo de artefactos en lugar de un archivo de configuración por error??)"  # noqa
                raise MiembroDeConfigNoSeleccionable(err.format(clave))
            datos[clave] = valor
        return datos

    def combinar(self):
        """
        Fusiona todas las fuentes de configuración, en orden.

        .. versionadded:: 1.0
        """
        debug("Fusionando fuentes de config en orden en un nuevo config_vacio...")
        self._set(_config={})
        debug("Defaults: {!r}".format(self._defaults))
        fusionar_dics(self._config, self._defaults)
        debug("Coleccion-conducida: {!r}".format(self._coleccion))
        fusionar_dics(self._config, self._coleccion)
        self._fusionar_archivo("sistema", "Sistema-completo")
        self._fusionar_archivo("ususario", "Por-usuario")
        self._fusionar_archivo("proyecto", "Por-proyecto")
        debug("Configuración de variable de entorno: {!r}".format(self._varent))
        fusionar_dics(self._config, self._varent)
        self._fusionar_archivo("acte", "Tiempoej")
        debug("Anulaciones: {!r}".format(self._anula))
        fusionar_dics(self._config, self._anula)
        debug("Modificaciones: {!r}".format(self._modificaciones))
        fusionar_dics(self._config, self._modificaciones)
        debug("Eliminaciones: {!r}".format(self._eliminaciones))
        aniquilar(self._config, self._eliminaciones)

    def _fusionar_archivo(self, nombre, desc):
        # Preparar
        desc += " archivo de configuración"  # yup
        _ubicado = getattr(self, "_{}_ubicado".format(nombre))
        ruta = getattr(self, "_{}_ruta".format(nombre))
        datos = getattr(self, "_{}".format(nombre))
        # None -> todavía no se ha cargado
        if _ubicado is None:
            debug("{} aún no se ha cargado, omitiendo".format(desc))
        # True -> hurra
        elif ubicado:
            debug("{} ({}): {!r}".format(desc, ruta, datos))
            fusionar_dics(self._config, datos)
        # False -> lo intentó, no tuvo éxito
        else:
            # TODO: ¿cómo conservar lo que se intentó para cada caso pero solo
            # para el negativo? ¿Solo una rama aquí basada en 'nombre'?
            debug("{} no encontrado, saltando".format(desc))

    def clonar(self, dentro=None):
        """
        Devuelve una copia de este objeto de configuración.

        El nuevo objeto será idéntico en términos de fuentes configuradas y 
        cualquier dato cargado (o manipulado por el usuario), pero será un 
        objeto distinto con el menor estado mutable compartido posible.

        Específicamente, todos los valores de `dict` dentro de la config se
        recrean recursivamente, con valores de hoja non-dict sujetos a 
        `copy.copy` (nota: *no* `copy.deepcopy`, ya que esto puede causar 
        problemas con varios objetos como compilado regexen o bloqueos de 
        subprocesos, que a menudo se encuentran enterrados en agregados ricos
        como API o clientes de BD).

        Los únicos valores de config restantes que pueden terminar compartidos
        entre una config y su clon son, por lo tanto, aquellos objetos 'ricos'
        que nomm'copian.copy' limpiamente, o componen objetos non-dict (como 
        listas o tuplas).

        :param dentro:
            Una subclase `.Config` a la que debería "actualizarse" el nuevo 
            clon.

            Usado por bibliotecas cliente que tienen sus propias subclases 
            `.Config` que p. Ej. definen valores predeterminados adicionales;
            clonando "en" una de estas subclases asegura que las 
            claves/subarboles nuevos se agreguen con elegancia, sin 
            sobrescribir nada que pueda haber sido predefinido.

            default: ``None`` (simplemente clone en otro `.Config` regular).

        :returns:
            Un `.Config`, o una instancia de la clase dada a ``dentro``.

        :raises:
            ``TypeError``, si se le da un valor a ``dentro`` y ese valor no es
            una subclase `.Config`.

        .. versionadded:: 1.0
        """
        # Verificación de cordura para 'dentro'
        if dentro is not None and not issubclass(dentro, self.__class__):
            err = "'dentro' debe ser una subclase de {}!"
            raise TypeError(err.format(self.__class__.__name__))
        # Construir nuevo objeto
        klase = self.__class__ if dentro is None else dentro
        # También permite kwargs de constructores arbitrarios, para subclases 
        # donde se desea pasar (algunos) datos en el tiempo de inicio (vs copia post-init)
        # TODO: ¿probablemente quieras hacer pivotar a toda la clase de esta 
        # manera eventualmente ...?. Ya no recuerdo exactamente por qué optamos
        # originalmente por el enfoque 'nueva configuración de atributo init +'
        # ... aunque claramente hay una discrepancia de impedancia entre "Quiero que
        # sucedan cosas en la instanciación de mi configuración" y "Quiero que la
        # clonación no se active ciertas cosas como la carga de fuentes de datos
        # externas ".
        # NOTE: esto incluirá lento=True, vea el final del método
        nuevo = klase(**self._clona_kwargs_inic(dentro=dentro))
        # Copy/combinar/etc all 'private' datos sources and attributes
        for nombre in """
            coleccion
            sistema_prefijo
            sistema_ruta
            sistema_ubicado
            sistema
            ususario_prefijo
            ususario_ruta
            ususario_ubicado
            usuario
            proyecto_prefijo
            proyecto_ruta
            proyecto_ubicado
            proyecto
            entorno_prefijo
            entorno
            acte_ruta
            acte_ubicado
            acte
            anulaciones
            modificaciones
        """.split():
            nombre = "_{}".format(nombre)
            mis_datos = getattr(self, nombre)
            # Los datos Non-dict se transfieren directamente (via un copy())
            # NOTA: presumiblemente alguien realmente podría arruinar y 
            # cambiar los tipos de estos valores, pero en ese momento está en ellos ...
            if not isinstance(mis_datos, dict):
                nuevo._set(nombre, copy.copy(mis_datos))
            # DLos Diccs de datos se fusiona (lo que también implica una
            # copy.copy eventualmente)
            else:
                fusionar_dics(getattr(nuevo, nombre), mis_datos)
        # Haga lo que hubiera hecho __init__ si no fuera lento, es decir, cargar
        # archivos de conf usuario/sistema.
        nuevo._cargar_archivo_de_conf_base()
        # Finalmente, combinar() para reales (_load_base_conf_files no lo hace
        # internamente, por lo que los datos no aparecerían de otra manera).
        nuevo.combinar()
        return nuevo

    def _clona_kwargs_inic(self, dentro=None):
        """
        Suministre kwargs adecuados para inicializar un nuevo clon de este 
        objeto.

        Tenga en cuenta que la mayor parte del proceso `.clonar` implica 
        copiar datos entre dos instancias en lugar de pasar init kwargs; sin
        embargo, a veces realmente quieres init kwargs, razón por la cual 
        existe este método.

        :param dentro: El valor de ``dentro`` como se pasó a la llamada
        `.clonar`.

        :returns: un `dict`.
        """
        # NOTE: debe pasar los valores predeterminados frescos o de lo contrario
        # se usará global_defaults() en su lugar. Excepto cuando 'dentro' está en
        # juego, en cuyo caso realmente queremos la unión de los dos.
        nuevos_defaults = copiar_dic(self._defaults)
        if dentro is not None:
            fusionar_dics(nuevos_defaults, dentro.global_defaults())
        # Los kwargs.
        return dict(
            defaults=nuevos_defaults,
            # TODO: considere hacer esto 'codificado' en el extremo de la 
            # llamada (es decir, dentro de clonar()) para asegurarse de que
            # nadie lo bombardee accidentalmente a través de subclases.
            lento=True,
        )

    def _modificar(self, rutaclave, clave, valor):
        """
        Actualiza nuestro nivel de configuración de modificaciones-de-usuario
        con nuevos datos.

        :param tuple rutaclave:
            La ruta de clave que identifica el sub-dict que se actualiza. 
            Puede ser una tupla vacía si la actualización ocurre en el nivel
            superior.

        :param str clave:
            La clave actual recibe una actualización.

        :param valor:
            El valor que se escribe.
        """
        # Primero, asegúrese de borrar la ruta-clave de _eliminaciones, en caso
        # de que se haya eliminado previamente.
        extirpar(self._eliminaciones, rutaclave + (clave,))
        # Ahora podemos agregarlo a la estructura de modificaciones.
        datos = self._modificaciones
        rutaclave = list(rutaclave)
        while rutaclave:
            subclave = rutaclave.pop(0)
            # TODO: podría usar defaultdict aquí, pero ... ¿meh?
            if subclave not in datos:
                # TODO: genera esta y las siguientes 3 líneas ...
                datos[subclave] = {}
            datos = datos[subclave]
        datos[clave] = valor
        self.combinar()

    def _eliminar(self, rutaclave, clave):
        """
        Como `._modificar`, pero para eliminar.
        """
        # NOTE: debido a que las eliminaciones se procesan en combinar() en último
        # lugar, no necesitamos eliminar cosas de _modificaciones al eliminarlas;
        # pero nosotros *hacemos* lo inverso - eliminar de _eliminaciones al modificar.
         # TODO: ¿sería sensato impulsar este paso a los llamadores?
        datos = self._eliminaciones
        rutaclave = list(rutaclave)
        while rutaclave:
            subclave = rutaclave.pop(0)
            if subclave in datos:
                datos = datos[subclave]
                # Si encontramos None, significa que algo más alto que nuestra
                # ruta de clave solicitada ya está marcado como eliminado; para
                # que no tengamos que hacer nada ni ir más lejos.
                if datos is None:
                    return
                # De lo contrario, es presumiblemente otro dict, así que sigue repitiendo ...
            else:
                # Clave no encontrada -> nadie ha marcado nada a lo largo de esta parte
                # del camino para su eliminación, así que comenzaremos a construirlo.
                datos[subclave] = {}
                # Luego prepárate para la próxima iteración
                datos = datos[subclave]
        # Bucle salido -> los datos deben ser el dict de más hojas, por lo que ahora
        # podemos establecer nuestra clave eliminada en None
        datos[clave] = None
        self.combinar()


class ErrorDeFusionAmbiguo(ValueError):
    pass


def fusionar_dics(base, updates):
    """
    Recursivamente combina dic ``updates`` en dic ``base`` (mutando ``base``.)

    * Se recurrirá a los valores que son en sí mismos dicccionarios.
    * Valores que son un dic en una entrada y *no* un dic en la otra entrada
      (por ejemplo, si nuestras entradas fueran 
      ``{'foo': 5}`` and ``{'foo': {'bar': 5}}``) son irreconciliables y
      generará una excepción.
    * Los valores de hoja no-dic se ejecutan a través de `copy.copy` para 
      evitar el sangrado de estado.

    .. note::
        Esto es efectivamente un "copy.deepcopy" ligero que ofrece protección
        contra tipos no coincidentes (dic vs non-dic) y evita algunos 
        problemas centrales de deepcopy (como la forma en que explota en
        ciertos tipos de objetos).

    :returns:
        El valor de ``base``, que es más útil para funciones de envoltura
        como `copiar_dic`.

    .. versionadded:: 1.0
    """
    # TODO: for chrissakes just make it return instead of mutating?
    for clave, valor in (updates or {}).items():
        # Dict values whose claves also exist in 'base' -> recurse
        # (But only if both types are dicts.)
        if clave in base:
            if isinstance(valor, dict):
                if isinstance(base[clave], dict):
                    fusionar_dics(base[clave], valor)
                else:
                    raise _merge_error(base[clave], valor)
            else:
                if isinstance(base[clave], dict):
                    raise _merge_error(base[clave], valor)
                # Fileno-bearing objects are probably 'real' files which do not
                # copy well & must be passed by reference. Meh.
                elif hasattr(valor, "fileno"):
                    base[clave] = valor
                else:
                    base[clave] = copy.copy(valor)
        # New values get set anew
        else:
            # Dict values get reconstructed to avoid being references to the
            # updates dict, which can lead to nasty state-bleed bugs otherwise
            if isinstance(valor, dict):
                base[clave] = copiar_dic(valor)
            # Fileno-bearing objects are probably 'real' files which do not
            # copy well & must be passed by reference. Meh.
            elif hasattr(valor, "fileno"):
                base[clave] = valor
            # Non-dict values just get set straight
            else:
                base[clave] = copy.copy(valor)
    return base


def _merge_error(orig, new_):
    return ErrorDeFusionAmbiguo(
        "Can't cleanly merge {} with {}".format(
            _format_mismatch(orig), _format_mismatch(new_)
        )
    )


def _format_mismatch(x):
    return "{} ({!r})".format(type(x), x)


def copiar_dic(fuente):
    """
    Devuelve una copia nueva de ``fuente`` con el menor estado compartido 
    posible.

    Utiliza `fusionar_dics` debajo del capó, con un dict ``base`` vacío; 
    consulte su documentación para obtener detalles sobre el comportamiento.

    .. versionadded:: 1.0
    """
    return fusionar_dics({}, fuente)


def extirpar(dic_, rutaclave):
    """
    Quita la clave apuntada por ``rutaclave`` del dic anidado ``dic_``, si
    existe.

    .. versionadded:: 1.0
    """
    datos = dic_
    rutaclave = list(rutaclave)
    hoja_key = rutaclave.pop()
    while rutaclave:
        clave = rutaclave.pop(0)
        if clave not in datos:
            # No ahí, nada que extirpar
            return
        datos = datos[clave]
    if hoja_key in datos:
        del datos[hoja_key]


def aniquilar(base, eliminaciones):
    """
    Eliminar todas las claves (anidado) mencionadas en ''eliminaciones'', de
    ``base``.

    .. versionadded:: 1.0
    """
    for clave, valor in six.iteritems(eliminaciones):
        if isinstance(valor, dict):
            # NOTE: no probar si la clave [clave] existe; si algo está 
            # listado en una estructura de eliminaciones, debe existir en
            # alguna fuente en algún lugar y, por lo tanto, también en la
            # caché que se borra.
            aniquilar(base[clave], eliminaciones[clave])
        else:  # implicitly None
            del base[clave]
