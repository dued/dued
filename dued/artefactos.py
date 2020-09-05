"""
Este módulo contiene los decoradores básicos de clase & conveniencia `.Artefacto`
utilizados para generar nuevos artefactos.
"""

from copy import deepcopy
import inspect
import types

from .contexto import Contexto
from .analizador import Argumento, traducir_guionesbajos
from .util import six

if six.PY3:
    from itertools import zip_longest
else:
    from itertools import izip_longest as zip_longest


#: Objeto centinela que representa un valor verdaderamente en blanco (vs`` None``).
NO_DEFAULT = object()


class Artefacto(object):
    """
    Objeto nucleo que representa un artefacto ejecutable y su 
    especificación de argumento.

    En su mayor parte, este objeto es una cámara de compensación para todos
    los datos que se pueden suministrar al decorador
    `@artefacto <dued.artefactos.artefacto>`, como ``nombre``, ``alias``,
    ``posicional``, etc., que aparecen como atributos.

    Además, la creación de instancias copia algunos metadatos amigables con
    la introspección/documentación del objeto ``cuerpo`` suministrado, como 
    ``__doc__``, ``__name__`` y ``__module__``, lo que le permite "aparecer
    como" ``cuerpo`` para la mayoría de las intenciones y propósitos.

    .. versionadded:: 1.0
    """

    # TODO: almacene estos valores predeterminados de kwarg en el centro,
    # consulte esos valores tanto aquí como en @artefacto.
    # TODO: permitir el control central del módulo por-sesión/por-moduloaretefacto
    # sobre algunos de ellos, p. Ej. (auto_)posicional, auto_banderascortas.
    # NOTE: sombreamos __builtins__.help aquí a propósito - ofuscar para evitarlo se
    # siente mal, dado que el builtin nunca estará realmente en juego en ningún
    # lugar excepto en un shell de depuración cuyo marco está exactamente
    # dentro de esta clase.
    def __init__(
        self,
        cuerpo,
        nombre=None,
        alias=(),
        posicional=None,
        opcional=(),
        default=False,
        auto_banderascortas=True,
        help=None,
        pre=None,
        post=None,
        autoimpresion=False,
        iterable=None,
        incremento=None,
    ):
        # Real invocable
        self.cuerpo = cuerpo
        # Copie un montón de metodos especiales del cuerpo en beneficio de Sphinx
        # autodoc u otros introspectores.
        self.__doc__ = getattr(cuerpo, "__doc__", "")
        self.__name__ = getattr(cuerpo, "__name__", "")
        self.__module__ = getattr(cuerpo, "__module__", "")
        # Nombre predeterminado, nombres alternativos y si debe actuar como
        # predeterminado para su colección padre
        self._nombre = nombre
        self.alias = alias
        self.es_predeterminado = default
        # Arg/bandera/analizador pistas
        self.posicional = self.llenar_posiciones_implicitas(posicional)
        self.opcional = opcional
        self.iterable = iterable or []
        self.incremento = incremento or []
        self.auto_banderascortas = auto_banderascortas
        self.help = help or {}
        # Llamar chain bidness
        self.pre = pre or []
        self.post = post or []
        self.veces_de_llamado = 0
        # Ya sea para imprimir el valor de retorno después de la ejecución
        self.autoimpresion = autoimpresion

    @property
    def nombre(self):
        return self._nombre or self.__name__

    def __repr__(self):
        alias = ""
        if self.alias:
            alias = " ({})".format(", ".join(self.alias))
        return "<Artefacto {!r}{}>".format(self.nombre, alias)

    def __eq__(self, otro):
        if self.nombre != otro.nombre:
            return False
        # Las funciones no definen __eq__ pero los objetos func_code aparentemente
        # sí. (Si estamos envolviendo algún otro invocable, serán responsables 
        # de definir la igualdad en su extremo).
        if self.cuerpo == otro.cuerpo:
            return True
        else:
            try:
                return six.get_function_code(
                    self.cuerpo
                ) == six.get_function_code(otro.cuerpo)
            except AttributeError:
                return False

    def __hash__(self):
        # Presume que el nombre y el cuerpo nunca se cambiarán. Hrm.
        # Potencialmente más limpio para no usar Artefactos como claves hash,
        # pero hagámoslo por ahora.
        return hash(self.nombre) + hash(self.cuerpo)

    def __call__(self, *args, **kwargs):
        # Protéjase de llamar artefactos sin contexto.
        if not isinstance(args[0], Contexto):
            err = "Artefacto esperaba un Contexto como su primer argumento, ¡obtuvo {} en su lugar!"
            # TODO: generar una subclase personalizada _de_ TypeError en su lugar
            raise TypeError(err.format(type(args[0])))
        resultado = self.cuerpo(*args, **kwargs)
        self.veces_de_llamado += 1
        return resultado

    @property
    def llamados(self):
        return self.veces_de_llamado > 0

    def argspec(self, cuerpo):
        """
        Devuelve dos tuplas:

        * El primer elemento es la lista de nombres de arg, en el orden definido.

            * Es decir no podemos * simplemente usar el método ``claves()``
              de un diccionario's aquí.

        * El segundo elemento es la asignación de nombres de arg a valores 
          predeterminados o `.NO_DEFAULT` (un valor 'vacío' distinto de None,
          ya que None es un valor válido por sí solo).

        .. versionadded:: 1.0
        """
        # Manejar objetos invocables-pero-no-funciones
        # TODO: __call__ exhibe el arg 'self'; ¿Nivelamos manualmente el primer resultado
        # en argspec, o hay alguna manera de obtener la especificación "realmente invocable"?
        func = cuerpo if isinstance(cuerpo, types.FunctionType) else cuerpo.__call__
        spec = inspect.getargspec(func)
        nombres_de_arg = spec.args[:]
        args_coincidentes = [reversed(x) for x in [spec.args, spec.defaults or []]]
        spec_dic = dict(zip_longest(*args_coincidentes, fillvalue=NO_DEFAULT))
        # Pop contexto argumento
        try:
            arg_de_contexto = nombres_de_arg.pop(0)
        except IndexError:
            # TODO: ver TODO dentro de __call__, esto debería ser del mismo tipo
            raise TypeError("¡Los artefactos debe tener un argumento de contexto inicial!")
        del spec_dic[arg_de_contexto]
        return nombres_de_arg, spec_dic

    def llenar_posiciones_implicitas(self, posicional):
        args, spec_dic = self.argspec(self.cuerpo)
        # Si posicional es None, todo lo que carezca de un valor
        # predeterminado se considerará automáticamente posicional.
        if posicional is None:
            posicional = []
            for nombre in args:  # # Ir en orden definido, no dictar, no dict "order"
                default = spec_dic[nombre]
                if default is NO_DEFAULT:
                    posicional.append(nombre)
        return posicional

    def arg_opts(self, nombre, default, nombres_tomados):
        opcs = {}
        # Ya sea posicional o no
        opcs["posicional"] = nombre in self.posicional
        # Si es una bandera de valor opcional
        opcs["opcional"] = nombre in self.opcional
        # Si debe ser de tipo iterable (lista)
        if nombre in self.iterable:
            opcs["tipo"] = list
            # Si el usuario dio un valor por default que no-es-None, es de 
            # esperar que sepa mejor que nosotros lo que quiere aquí
            # (y con suerte ofrece el protocolo de lista ...); de lo contrario,
            # proporcione un valor por default útil
            opcs["default"] = default if default is not None else []
        # Si debería incrementar su valor o no
        if nombre in self.incremento:
            opcs["incremento"] = True
        # Argumento nombre(s) (reemplace c/versión discontinua si hay guiones
        # bajos y mueva la versión subrayada para que sea nombre_de_atributo en su lugar).
        if "_" in nombre:
            opcs["nombre_de_atributo"] = nombre
            nombre = traducir_guionesbajos(nombre)
        nombres = [nombre]
        if self.auto_banderascortas:
            # Debe saber qué nombres cortos están disponibles
            for char in nombre:
                if not (char == nombre or char in nombres_tomados):
                    nombres.append(char)
                    break
        opcs["nombres"] = nombres
        # Manejar el valor y tipo default si es posible
        if default not in (None, NO_DEFAULT):
            # TODO: permite configurar 'tipo' explícitamente.
            # NOTE: omitir la configuración 'tipo' si opcional es Verdadero + el
            # tipo(default) es bool; que resulta en un Argumento sin sentido que
            # da dolor al analizador de varias formas.
            tipo = type(default)
            if not (opcs["opcional"] and tipo is bool):
                opcs["tipo"] = tipo
            opcs["default"] = default
        # Ayuda
        if nombre in self.help:
            opcs["help"] = self.help[nombre]
        return opcs

    def obtener_argumentos(self):
        """
        Devuelve una lista de objetos Argumento que representan la firma de
        este(os) artefacto(s).

        .. versionadded:: 1.0
        """
        # Core argspec
        nombres_de_arg, spec_dic = self.argspec(self.cuerpo)
        # Obtenga una lista de argumentos + sus valores predeterminados 
        # (si los hay) en el orden de declaración/definición (es decir, según
        # getargspec() )
        tuplas = [(x, spec_dic[x]) for x in nombres_de_arg]
        # Prepara la lista de todos los nombres ya-tomados (principalmente
        # para ayudar a elegir las banderas cortas automáticas)
        nombres_tomados = {x[0] for x in tuplas}
        # Crear lista de argumentos (arg_opts se encargará de configurar
        # nombres cortos, etc.)
        args = []
        for nombre, default in tuplas:
            nuevo_arg = Argumento(**self.arg_opts(nombre, default, nombres_tomados))
            args.append(nuevo_arg)
            # Actualizar la lista de nombres_tomados con la lista completa de
            # nombres del nuevo argumento(s) (que puede incluir nuevas 
            # banderas cortas) para que la creación posterior de Argumento sepa
            # qué se tomó.
            nombres_tomados.update(set(nuevo_arg.nombres))
        # Ahora necesitamos asegurarnos de que los posicionales terminen al 
        # principio de la lista, en el orden dado en self.positional, de modo
        # que cuando Contexto los consuma, este orden se conserve.
        for posarg in reversed(self.posicional):
            for i, arg in enumerate(args):
                if arg.nombre == posarg:
                    args.insert(0, args.pop(i))
                    break
        return args


def artefacto(*args, **kwargs):
    """
    Marca el objeto invocable envuelto como un artefacto dued válido.

    Se puede llamar sin paréntesis si no es necesario especificar opciones
    adicionales. De lo contrario, se permiten los siguientes argumentos de
    palabras clave entre paréntesis:

    * ``nombre``: Nombre predeterminado para usar cuando se vincula a una
      `.Coleccion`. Útil para evitar problemas de namespace de Python
      (es decir, cuando el nombre de nivel de CLI deseado no puede o no debe
      usarse como nombre de nivel de Python).
    * ``alias``: Especifique uno o más alias para este artefacto, lo que 
      permite invocarlo con varios nombres diferentes. Por ejemplo, un 
      artefacto llamado ``miartefacto`` con una envoltura simple 
      ``@artefacto`` solo puede invocarse como ``"miartefacto"``. Cambiar el
      decorador a ``@artefacto (alias=['miotroartefacto'])`` permite la
      invocación como  ``"miartefacto"`` *o* ``"miotroartefacto"``.
    * ``posicional``: Iterable anulación del auto-comportamiento del 
      analizador(es) "que arg sin valor default se consideran posicionales".
      Si hay una lista  de nombres de arg, no se considerará posicional ningún
      arg además de los nombrados en este iterable. (Esto significa que una 
      lista vacía obligará a que todos los argumentos se proporcionen como 
      banderas explícitas).
    * ``opcional``: Iterable de nombres de argumentos, declarando que esos 
      args tienen :ref:`valores opcionales <valores-opcionales>`. Tales
      argumentos  pueden darse como opciones toma-de-valor (por ejemplo,
      ``--mi-arg=mivalor``, donde se da artefacto ``"mivalor"``) o como 
      banderas booleanas (``--mi-arg``, resultando en ``True``).
    * ``iterable``: Iterable de nombres de argumentos, declarandolas para 
      :ref:`construir valores iterables <valores-de-bandera-iterables>`.
    * ``incremento``: Iterable de nombres de argumentos, declarandolas para 
      :ref:`incrementar sus valalores <valores-de-bandera-incrementos>`.
    * ``default``: Opción booleana que especifica si este artefacto debe ser
      el artefacto predeterminado de su colección (es decir, se llama si se 
      da el nombre de la colección).
    * ``auto_banderascortas``: Ya sea para crear automáticamente banderas 
      cortas a partir de opciones de artefacto; por defecto es True.
    * ``help``: Dicc mapeando nombres de argumentos a sus cadenas de ayuda. 
      Se mostrará en la salida de ``--help``.
    * ``pre``, ``post``: Listas de objetos artefacto para ejecutar antes o
       después del artefacto envuelto siempre que se ejecuta.
    * ``autoimpresion``: Booleano que determina si se imprime automáticamente
      el valor de retorno de este artefacto en la salida estándar cuando se
      invoca directamente a través de la CLI. El valor predeterminado es 
      Falso.
    * ``klase``: Clase para instanciar/devolver. El valor predeterminado es
      `.Artefacto`.

    Si se dan argumentos que no sean palabras clave, se toman como el valor
    del kwarg ``pre`` por conveniencia. (Es un error dar tanto ``*args`` como
    ``pre`` al mismo tiempo).

    .. versionadded:: 1.0
    .. versionchanged:: 1.1
        Se agregó el argumento de palabra clave ``klase``.
    """
    klase = kwargs.pop("klase", Artefacto)
    # @artefacto -- (probablemente) no se dieron opciones.
    if len(args) == 1 and callable(args[0]) and not isinstance(args[0], Artefacto):
        return klase(args[0], **kwargs)
    # @artefacto(pre, artefactos, aquí)
    if args:
        if "pre" in kwargs:
            raise TypeError(
                "¡No puede dar * args y 'pre' kwarg simultáneamente!"
            )
        kwargs["pre"] = args
    # @artefacto(opciones)
    # TODO: ¿por qué diablos hicimos esto originalmente de esta manera en lugar
    #  de simplemente delegar en Artefacto? Eliminemos todo esto en algún 
    # momento y veamos qué se rompe, si es que hay algo.
    nombre = kwargs.pop("nombre", None)
    alias = kwargs.pop("alias", ())
    posicional = kwargs.pop("posicional", None)
    opcional = tuple(kwargs.pop("opcional", ()))
    iterable = kwargs.pop("iterable", None)
    incremento = kwargs.pop("incremento", None)
    default = kwargs.pop("default", False)
    auto_banderascortas = kwargs.pop("auto_banderascortas", True)
    help = kwargs.pop("help", {})
    pre = kwargs.pop("pre", [])
    post = kwargs.pop("post", [])
    autoimpresion = kwargs.pop("autoimpresion", False)

    def interior(obj):
        obj = klase(
            obj,
            nombre=nombre,
            alias=alias,
            posicional=posicional,
            opcional=opcional,
            iterable=iterable,
            incremento=incremento,
            default=default,
            auto_banderascortas=auto_banderascortas,
            help=help,
            pre=pre,
            post=post,
            autoimpresion=autoimpresion,
            # Pass in any remaining kwargs as-is.
            **kwargs
        )
        return obj

    return interior


class Llamar(object):
    """
    Representa una llamada/ejecución de un `.Artefacto` con (kw)args dados.

    Similar a `~functools.partial` con algunas funciones adicionales (como la 
    delegación al artefacto interno y el seguimiento opcional del nombre por
    el que se llama).

    .. versionadded:: 1.0
    """

    def __init__(self, artefacto, llamado_de=None, args=None, kwargs=None):
        """
        Crea un nuevo objeto `.Llamar`.

        :param artefacto: El objeto `.Artefacto` a ejecutar.

        :param str llamado_de:
            El nombre con el que se llama al artefacto, p. Ej. si fue llamado por
            un alias u otro enlace. El valor predeterminado es ``None``, también 
            conocido como se hacía referencia al artefacto por su nombre
            predeterminado.

        :param tuple args:
            Positional arguments to llamar with, if any. Default: ``None``.
            Argumentos posicionales con los que llamar, si los hay.
            Predeterminado: ``None``.

        :param dict kwargs:
            Argumentos de palabras-clave (keyword) con los que llamar, si los
            hay. Predeterminado: ``None``.
        """
        self.artefacto = artefacto
        self.llamado_de = llamado_de
        self.args = args or tuple()
        self.kwargs = kwargs or dict()

    # TODO: ¿Qué tan útil es esto? se siente como una magia exagerada
    def __getattr__(self, nombre):
        return getattr(self.artefacto, nombre)

    def __deepcopy__(self, memo):
        return self.clonar()

    def __repr__(self):
        # Abreviatura sajona de "nambien conocido como"
        aka = ""
        if self.llamado_de is not None and self.llamado_de != self.artefacto.nombre:
            aka = " (llamado por: {!r})".format(self.llamado_de)
        return "<{} {!r}{}, args: {!r}, kwargs: {!r}>".format(
            self.__class__.__name__,
            self.artefacto.nombre,
            aka,
            self.args,
            self.kwargs,
        )

    def __eq__(self, otro):
        # NOTE: No comparando 'llamado_de'; un llamar con nombre de un Artefacto dado
        # con los mismos args/kwargs debe considerarse igual que un llamar sin nombre
        # del mismo Artefacto con los mismos args/kwargs (por ejemplo, pre/post artefacto
        # especificado sin nombre). Lo mismo ocurre con artefactos con múltiples alias.
        for attr in "artefacto args kwargs".split():
            if getattr(self, attr) != getattr(otro, attr):
                return False
        return True

    def crear_contexto(self, config):
        """
        Genere un `.Contexto` apropiado para esta llamada, con la 
        configuración dada.

        .. versionadded:: 1.0
        """
        return Contexto(config=config)

    def clonar_datos(self):
        """
        Devuelve argumentos de palabra clave adecuados para clonar esta 
        llamada en otra.

        .. versionadded:: 1.1
        """
        return dict(
            artefacto=self.artefacto,
            llamado_de=self.llamado_de,
            args=deepcopy(self.args),
            kwargs=deepcopy(self.kwargs),
        )

    def clonar(self, dentro=None, with_=None):
        """
        Devuelve una copia independiente de esta Llamada.

        Útil para parametrizar la ejecucion de artefactos.

        :param dentro:
            Una subclase para generar en lugar de la clase actual. Opcional.

        :param dict with_:
            Un dicc de argumentos de palabras clave adicionales para usar al
            crear el nuevo clon; Normalmente se usa cuando se clona ``dentro``
            de una subclase que tiene argumentos adicionales sobre la clase base.
            Opcional.

            .. note::
                Este dicc se usa para ``.update()`` los datos del objeto(s) 
                original (el valor de retorno de su `clonar_datos`), por lo que
                en caso de conflicto, los valores en ``with_`` ganarán.

        .. versionadded:: 1.0
        .. versionchanged:: 1.1
            Agregamos el kwarg ``with_``.
        """
        klase = dentro if dentro is not None else self.__class__
        datos = self.clonar_datos()
        if with_ is not None:
            datos.update(with_)
        return klase(**datos)


def llamar(artefacto, *args, **kwargs):
    """
    Describe la ejecución de un `.Artefacto`, normalmente con argumentos 
    pre-suministrados.

    Útil para configurar :ref:`invocaciones de pre/post artefacto
    <_parametetrizando-pre-post-artefactos>`. En realidad, es solo una
    envoltura conveniente alrededor de la clase `.Llamar`, que puede usarse
    directamente en su lugar si se desea.

    Por ejemplo, aquí hay dos artefactos de tipo *compilar* que se refieren 
    a un  pre-artefacto de ``configuracion``, uno sin valores de argumento
    incorporados (y por lo tanto no es necesario usar `.llamar`),y uno que
    alterna un booleano bandera::

        @artefacto
        def configuracion(c, limpiar=False):
            if limpiar:
                c.correr("rm -rf objetivo")
            # ... configura las cosas aquí ...
            c.correr("tar czvf objetivo.tgz objetivo")

        @artefacto(pre=[configuracion])
        def compilar(c):
            c.correr("compilar, teniendo en cuenta archivos sobrantes...")

        @artefacto(pre=[llamar(configuracion, limpiar=True)])
        def clean_build(c):
            c.correr("compilar, asumiendo el estado de limpieza...")

    Consulte los documentos del constructor para `.Llamar` para obtener
    más detalles: los ``args`` y los ``kwargs`` de esta función se asignan
    directamente a los mismos argumentos que en ese método.

    .. versionadded:: 1.0
    """
    return Llamar(artefacto=artefacto, args=args, kwargs=kwargs)
