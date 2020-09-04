class Argumento(object):
    """
    Un argumento/bandera de línea de comando.

    :param nombre:
        Azúcar sintáctico para ``nombres=[<nombre>]``. Dar tanto ``nombre``
        como ``nombres`` no es válido.
    :param nombres:
        Lista de identificadores válidos para este argumento. Por ejemplo,
        un argumento de "ayuda" puede definirse con una lista de nombres de
        ``['-h', '--help']``.
    :param tipo:
        Tipo analisis de fabrica y sugerencia del analizador. P.ej. ``int`` 
        convertirá el valor de texto predeterminado analizado en un entero de 
        Python; y ``bool`` le dirán al analizador que no espere un valor real
        sino que trate el argumento como un toggle/bandera.
    :param default:
        Valor por defecto puesto a disposición del analizador si no se da 
        ningún valor en la línea de comando.
    :param help:
        Texto de ayuda, diseñado para usarse con ``--help``.
    :param posicional:
        Si el valor de este argumento se puede dar posicionalmente. Cuando los
        argumentos ``False`` (predeterminado) deben nombrarse explícitamente.
    :param opcional:
        Si este argumento (no ``bool``) requiere un valor o no.
    :param incremento:
        Si este argumento (``int``) se incrementará o no en lugar de
        sobrescribir/asignar.
    :param nombre_de_atributo:
        Un nombre descriptivo de identificador/atributo de Python, normalmente
        completado con la versión subrayada cuando ``nombre`` / ``nombres```
        contienen guiones.

    .. versionadded:: 1.0
    """

    def __init__(
        self,
        nombre=None,
        nombres=(),
        tipo=str,
        default=None,
        help=None,
        posicional=False,
        opcional=False,
        incremento=False,
        nombre_de_atributo=None,
    ):
        if nombre and nombres:
            msj = "¡No se pueden dar argumentos 'nombre' y 'nombres'! Elegir uno."
            raise TypeError(msj)
        if not (nombre or nombres):
            raise TypeError("Un Argumento debe tener al menos un nombre.")
        self.nombres = tuple(nombres if nombres else (nombre,))
        self.tipo = tipo
        valor_inicial = None
        # Caso especial: los argumentos de tipo lista comienzan como una lista
        # vacía, no como None.
        if tipo is list:
            valor_inicial = []
        # Otro: los argumentos incrementables comienzan con su valor 
        # predeterminado.
        if incremento:
            valor_inicial = default
        self.valor_bruto = self._value = valor_inicial
        self.default = default
        self.help = help
        self.posicional = posicional
        self.opcional = opcional
        self.incremento = incremento
        self.nombre_de_atributo = nombre_de_atributo

    def __repr__(self):
        nicks = ""
        if self.nicknombres:
            nicks = " ({})".format(", ".join(self.nicknombres))
        banderas = ""
        if self.posicional or self.opcional:
            banderas = " "
        if self.posicional:
            banderas += "*"
        if self.opcional:
            banderas += "?"
        # TODO: almacena este valor predeterminado en otro lugar que no sea
        # la firma de Argumento .__ init__?
        tipo = ""
        if self.tipo != str:
            tipo = " [{}]".format(self.tipo.__name__)
        return "<{}: {}{}{}{}>".format(
            self.__class__.__name__, self.nombre, nicks, tipo, banderas
        )

    @property
    def nombre(self):
        """
        El nombre canónico compatible-con-atributos para este argumento.

        Será ``nombre_de_atributo`` (si se le da al constructor) o el primer 
        nombre en ``nombres`` en caso contrario.

        .. versionadded:: 1.0
        """
        return self.nombre_de_atributo or self.nombres[0]

    @property
    def nicknombres(self):
        return self.nombres[1:]

    @property
    def toma_valor(self):
        if self.tipo is bool:
            return False
        if self.incremento:
            return False
        return True

    @property
    def valor(self):
        return self._value if self._value is not None else self.default

    @valor.setter
    def valor(self, arg):
        self.asigna_valor(arg, cast=True)

    def asigna_valor(self, valor, cast=True):
        """
        Llamada a API de establecimiento de valor explícito real.


        Asigna ``self.valor_bruto`` en ``valor`` directamente.

        Asigna ``self.valor`` en ``self.tipo(valor)``, a menos que:

        - ``cast= False``, en cuyo caso también se utiliza el valor bruto.
        - ``self.tipo==lista``, en cuyo caso el valor se agrega a 
          ``self.valor`` en lugar de emitir y sobrescribir.
        - ``self.incremento==True``, en cuyo caso el valor se ignora y el
          valor actual (asumido int) simplemente se incrementa.

        .. versionadded:: 1.0
        """
        self.valor_bruto = valor
        # Función predeterminada para no-hacer-nada/identidad
        func = lambda x: x
        # Si está lanzado, configúrelo en self.tipo, que debería ser str/int/etc
        if cast:
            func = self.tipo
        # Si self.tipo es una lista, agregue en lugar de usar cast func.
        if self.tipo is list:
            func = lambda x: self._value + [x]
        # Si es incremento, simplemente incremente.
        if self.incremento:
            # TODO: explotar bien si self._value no era un int para empezar
            func = lambda x: self._value + 1
        self._value = func(valor)

    @property
    def obtuvo_valor(self):
        """
        Devuelve si el argumento alguna vez recibió un valor (no
        predeterminado).

        Para la mayoría de los tipos de argumentos, esto simplemente verifica
        si el valor almacenado internamente no es ``None``; para otros, como
        los tipos de ``lista``, se pueden usar diferentes controles.

        .. versionadded:: 1.3
        """
        if self.tipo is list:
            return bool(self._value)
        return self._value is not None
