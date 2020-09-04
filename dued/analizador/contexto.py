import itertools

try:
    from ..vendor.lexicon import Lexicon
except ImportError:
    from lexicon import Lexicon

from .argumento import Argumento


def traducir_guionesbajos(nombre):
    return nombre.lstrip("_").rstrip("_").replace("_", "-")


def a_bandera(nombre):
    nombre = traducir_guionesbajos(nombre)
    if len(nombre) == 1:
        return "-" + nombre
    return "--" + nombre


def sort_candidate(arg):
    nombres = arg.nombres
    # TODO: is there no "split into two buckets on predicate" builtin?
    shorts = {x for x in nombres if len(x.strip("-")) == 1}
    longs = {x for x in nombres if x not in shorts}
    return sorted(shorts if shorts else longs)[0]


def bandera_clave(x):
    """
    Obtenga útiles listas-de-entradas clave para clasificar las banderas de 
    la CLI.

    .. versionadded:: 1.0
    """
    # Setup
    ret = []
    x = sort_candidate(x)
    # Las banderas de estilo largo triunfan sobre las de estilo corto, por lo
    # que el primer elemento de comparación es simplemente si la bandera tiene
    # un solo carácter de longitud (con banderas que no son de longitud 1 como
    # "primero" [número inferior])
    ret.append(1 if len(x) == 1 else 0)
    # El siguiente elemento de comparación son simplemente las cadenas en sí
    # mismas, sin distinción entre mayúsculas y minúsculas. Se compararán
    # alfabéticamente si se comparan en esta etapa.
    ret.append(x.lower())
    # Finalmente, si la prueba que no distingue entre mayúsculas y minúsculas
    # también coincidió, compare la que distingue entre mayúsculas y 
    # minúsculas, pero a la inversa (primero las letras minúsculas)
    invertido = ""
    for char in x:
        invertido += char.lower() if char.isupper() else char.upper()
    ret.append(invertido)
    return ret

# Nombrado un poco más detallado, por lo que las referencias a Sphinx
# pueden ser inequívocas. Me cansé de los caminos totalmente calificados.
class AnalizadorDeContexto(object):
    """
    Analizando contexto con conocimiento de banderas y su formato.

    Generalmente asociado con el programa central o un artefacto.

    Cuando se ejecuta a través de un analizador, también se mantendrán los 
    valores de tiempoej rellenados por el analizador.
    
    .. versionadded:: 1.0
    """

    def __init__(self, nombre=None, alias=(), args=()):
        """
        Crea un nuevo `` AnalizadorDeContexto llamado ``nombre``, 
        con ``alias``.

        ``nombre`` es opcional y debería ser una cadena si se proporciona.
        Se usa para diferenciar los objetos AnalizadorDeContexto, y para
        usarlos en un Analizador al determinar qué porción de entrada podría
        pertenecer a un AnalizadorDeContexto dado.

        ``alias`` también es opcional y debería ser un iterable que contenga
        cadenas. El análisis respetará cualquier alias cuando intente 
        "encontrar" un contexto dado en su entrada.

        Puede dar uno o más ``args``, que es una alternativa rápida a llamar a
        ``para arg en args: self.agregar_arg (arg)`` después de la inicialización.

        """
        self.args = Lexicon()
        self.args_posicionales = []
        self.banderas = Lexicon()
        self.banderas_inversas = {}  # No need for Lexicon here
        self.nombre = nombre
        self.alias = alias
        for arg in args:
            self.agregar_arg(arg)

    def __repr__(self):
        alias = ""
        if self.alias:
            alias = " ({})".format(", ".join(self.alias))
        nombre = (" {!r}{}".format(self.nombre, alias)) if self.nombre else ""
        args = (": {!r}".format(self.args)) if self.args else ""
        return "<analizador/Contexto{}{}>".format(nombre, args)

    def agregar_arg(self, *args, **kwargs):
        """
        Adds given ``Argumento`` (or constructor args for one) to this contexto.
        Agrega el ``Argumento`` dado (o los argumentos del constructor para 
        uno) a este contexto.

        El Argumento en cuestión se agrega a los siguientes atributos de dict:

        * ``args``: acceso "normal", es decir, los nombres dados se exponen
          directamente como claves.
        * ``banderas``: acceso "banderalike", es decir, los nombres dados se
          traducen a banderas CLI, p. ej. Se puede acceder a ``"foo"`` a 
          través de ``banderas['--foo']``.
        * ``banderas_inversas``: similar a ``banderas`` pero que contiene solo
          las versiones "inversas" de las banderas booleanas que por defecto 
          son True. Esto permite que el analizador rasarbol, por ejemplo, 
          ``--no-mibandera`` y convertirlo en un valor False para el Argumento
          ``mibandera``.

        .. versionadded:: 1.0
        """
        # Normalize
        if len(args) == 1 and isinstance(args[0], Argumento):
            arg = args[0]
        else:
            arg = Argumento(*args, **kwargs)
        # Restricción de unicidad: sin colisiones de nombres
        for nombre in arg.nombres:
            if nombre in self.args:
                msj = "Intenté agregar un argumento llamado {!r} pero uno ya existe!"  # noqa
                raise ValueError(msj.format(nombre))
        # Nombre utilizado como nombre "principal" para fines de alias
        principal = arg.nombres[0]  # NOT arg.nombre
        self.args[principal] = arg
        # Observe las posiciones en un atributo de lista ordenada y distinta
        if arg.posicional:
            self.args_posicionales.append(arg)        # Agregar nombres y nicknombres a banderas, args
        self.banderas[a_bandera(principal)] = arg
        for nombre in arg.nicknombres:
            self.args.alias(nombre, to=principal)
            self.banderas.alias(a_bandera(nombre), to=a_bandera(principal))
        # Agregar nombre_de_atributo a args, pero no a banderas
        if arg.nombre_de_atributo:
            self.args.alias(arg.nombre_de_atributo, to=principal)
        # Agregar a banderas_inversas si es necesario
        if arg.tipo == bool and arg.default is True:
            # Invierta aquí el nombre de la bandera 'principal', que será
            # una versión discontinua del nombre del argumento principal si
            # se produjo una transformación de guión bajo a guión.
            nombre_inverso = a_bandera("no-{}".format(principal))
            self.banderas_inversas[nombre_inverso] = a_bandera(principal)

    @property
    def faltan_argumentos_posicionales(self):
        return [x for x in self.args_posicionales if x.valor is None]

    @property
    def como_kwargs(self):
        """
        This contexto's arguments' values keyed by their ``.nombre`` attribute.
        como kwargs

        Los valores de los argumentos de este contexto codificados por su
        atributo ``.nombre``.

        Da como resultado un dicc adecuado para su uso en contextos de Python,
        donde p. Ej. un argumento llamado ``foo-bar`` se vuelve accesible como
        ``foo_bar``.

        .. versionadded:: 1.0
        """
        ret = {}
        for arg in self.args.valores():
            ret[arg.nombre] = arg.valor
        return ret

    def nombres_para(self, bandera):
        # TODO: probablemente debería ser un método en Lexicon/AliasDict
        return list(set([bandera] + self.banderas.aliases_of(bandera)))

    def ayuda_para(self, bandera):
        """
        Devuelve 2-tuplas de ``(bandera-spec, help-string)`` para la ``bandera`` dada.

        ..versionadded:: 1.0
        """
        # Obtener arg obj
        if bandera not in self.banderas:
            err = "{!r} ¡No es una bandera válida para este contexto! Las banderas válidas son: {!r}"  # noqa
            raise ValueError(err.format(bandera, self.banderas.claves()))
        arg = self.banderas[bandera]
        # Determine el tipo de valor esperado, si lo hubiera
        valor = {str: "CADENA", int: "INT"}.get(arg.tipo)
        # Formatear y listo
        full_nombres = []
        for nombre in self.nombres_para(bandera):
            if valor:
                # Las banderas cortas son -f VAL, largos son --foo=VAL
                # Cuando es opcional, también, -f [VAL] y --foo[=VAL]
                if len(nombre.strip("-")) == 1:
                    valor_ = ("[{}]".format(valor)) if arg.opcional else valor
                    valorcadena = " {}".format(valor_)
                else:
                    valorcadena = "={}".format(valor)
                    if arg.opcional:
                        valorcadena = "[{}]".format(valorcadena)
            else:
                # sin valor => booleano
                # comprobar la inversa
                if nombre in self.banderas_inversas.values():
                    nombre = "--[no-]{}".format(nombre[2:])

                valorcadena = ""
            # virar juntos
            full_nombres.append(nombre + valorcadena)
        nombrecadena = ", ".join(sorted(full_nombres, key=len))
        helpcadena = arg.help or ""
        return nombrecadena, helpcadena

    def help_tuplas(self):
        """
        Devuelve el iterable ordenado de las tuplas de ayuda para 
        todos los Argumentos miembro.

        Clasifica así:

        * La clasificación general es alfanumérica
        * Banderas cortas triunfan sobre banderas largas
        * Los argumentos con banderas *only* largas y banderas *no* cortas
          vendrán primero.
        * Cuando un Argumento tiene varias banderas largas o cortas, se
          clasificará utilizando el candidato más favorable (el más bajo
          alfabéticamente).

         Esto resultará en una lista de ayuda como la siguiente::

            --alfa, --zeta # 'alfa' gana
            --beta
            -a, --query # bandera corta gana
            -b, --argh
            -c

        .. versionadded:: 1.0
        """
        # TODO: argumento/bandera API debe cambiar :(
        # tener que llamar a una_bandera en el primer nombre de un argumento
        # es una tontería.
        # ¿Pasar un objeto Argumento a ayuda_para puede requerir cambios 
        # moderados?
        # Transmitir a la lista para garantizar que no sea generador en 
        # Python 3.
        return list(
            map(
                lambda x: self.ayuda_para(a_bandera(x.nombre)),
                sorted(self.banderas.valores(), key=bandera_clave),
            )
        )

    def nombres_de_banderas(self):
        """
        Similar a `help_tuplas` pero solo devuelve los nombres de las 
        banderas, no helpcadena.

        Específicamente, todos los nombres de las banderas, aplanados, en
        orden aproximado.

        .. versionadded:: 1.0
        """
        # Regular bandera nombres
        banderas = sorted(self.banderas.valores(), key=bandera_clave)
        nombres = [self.nombres_para(a_bandera(x.nombre)) for x in banderas]
        # Los nombres de las banderas inversas se venden por separado
        nombres.append(self.banderas_inversas.keys())
        return tuple(itertools.chain.from_iterable(nombres))
