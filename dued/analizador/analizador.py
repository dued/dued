import copy

try:
    from ..vendor.lexicon import Lexicon
    from ..vendor.fluidity import StateMachine, state, transition
except ImportError:
    from lexicon import Lexicon
    from fluidity import StateMachine, state, transition

from ..util import debug
from ..excepciones import ErrorDeAnalisis


def es_bandera(valor):
    return valor.startswith("-")


def es_bandera_larga(valor):
    return valor.startswith("--")


class Analizador(object):
    """
    Crear un analizador consciente de ``contextos`` y un contexto opcional
    ``inicial``.

    ``contextos`` debe ser un iterable de instancias de ``Contexto`` que se
    buscarán cuando se encuentren nuevos nombres de contexto durante un 
    análisis. Estos contextos determinan qué banderas pueden seguirlos, así
    como si las banderas dadas toman valores.

    ``inicial`` es opcional y se usará para determinar la validez de las 
    opciones/banderas del "núcleo" al inicio de la ejecución del análisis,
    si se encuentran.

    ``ignorar_desconocido`` determina qué hacer cuando se encuentran contextos
    que no se asignan a ningún miembro de ``contextos``. Por defecto es
    ``False``, lo que significa que cualquier contexto desconocido resulta en
    una excepción de error de análisis. Si es ``True``, encontrar un contexto
    desconocido detiene el análisis y llena el atributo ``.sin_analizar`` del
    valor de retorno con los tokens de análisis restantes.

    .. versionadded:: 1.0
    """

    def __init__(self, contextos=(), inicial=None, ignorar_desconocido=False):
        self.inicial = inicial
        self.contextos = Lexicon()
        self.ignorar_desconocido = ignorar_desconocido
        for contexto in contextos:
            debug("Añadiendo {}".format(contexto))
            if not contexto.nombre:
                raise ValueError("Los contextos no-iniciales deben tener nombres.")
            exists = "Un contexto llamado/alias {!r} ya esta en este analizador!"
            if contexto.nombre in self.contextos:
                raise ValueError(exists.format(contexto.nombre))
            self.contextos[contexto.nombre] = contexto
            for alias in contexto.alias:
                if alias in self.contextos:
                    raise ValueError(exists.format(alias))
                self.contextos.alias(alias, to=contexto.nombre)

    def analizar_args(self, argv):
        """
        Analiza una lista de tokens de estilo argv ``argv``.

        Devuelve una lista (en realidad una subclase, `.AnalizaResultado`) de
        objetos `.AnalizadorDeContexto` que coinciden con el orden en que se
        encontraron en el ``argv`` y que contienen objetos `.Argumento` con
        valores actualizados basados en cualquier bandera dada.

        Supone que ya se ha eliminado cualquier nombre de programa. Bueno::

            Analizador(...).analizar_args(['--nucleo-opc', 'artefacto', '--artefacto-opc'])

        Bad::

            Analizador(...).analizar_args(['dued', '--nucleo-opc', ...])


        :param argv: Lista de tokens de cadenas de argumentos.
        :returns:
            Un `.AnalizaResultado` (una subclase de ``list`` que contiene 
            cierto número de objetos `.AnalizadorDeContexto`)

        .. versionadded:: 1.0
        """
        machine = AnalizarLaMaquina(
            inicial=self.inicial,
            contextos=self.contextos,
            ignorar_desconocido=self.ignorar_desconocido,
        )
        # FIXME: ¿Por qué no hay str.partition para las listas? Debe haber
        # una mejor manera de hacer esto. Divida argv alrededor del centinela
        # restante de dos guiones.
        debug("Arrancando argv: {!r}".format(argv))
        try:
            guion = argv.indice("--")
        except ValueError:
            guion = len(argv)  # Sin resto == cuerpo se queda todo
        cuerpo = argv[:guion]
        remanente = argv[guion:][1:]  # [1:] para quitarse el resto
        if remanente:
            debug(
                "Remanente[{!r}:][1:] => {!r}".format(guion, remanente)
            )
        for indice, token in enumerate(cuerpo):
            # Manejar formularios no-delimitados-por-espacios, si no espera
            # actualmente un valor de bandera y aún se encuentra en un 
            # territorio de análisis válido (es decir, no en un estado 
            # "desconocido" que implica solo-almacenar)
            # NOTE: hacemos esto en unos pocos pasos para poder dividir-y
            # luego-verificar-la-validez; necesaria para cosas como cuando
            # la bandera vista anteriormente toma opcionalmente un valor.
            mutaciones = []
            orig = token
            if es_bandera(token) and not machine.resultado.sin_analizar:
                # Banderas delimitadas por signo igual, por ejemplo,
                # --foo=bar o -f=bar
                if "=" in token:
                    token, _, valor = token.partition("=")
                    msj = "Dividiendo x=y expr {!r} en los tokens {!r} y {!r}"
                    debug(msj.format(orig, token, valor))
                    mutaciones.append((indice + 1, valor))
                # Contiguous booleano short banderas, e.g. -qv
                elif not es_bandera_larga(token) and len(token) > 2:
                    full_token = token[:]
                    resto, token = token[2:], token[:2]
                    err = "Dividiendo {!r} en el token {!r} y resto {!r}"
                    debug(err.format(full_token, token, resto))
                    # Manejar bloque de bandera booleana vs valor + bandera
                    # corta. Asegúrese de no probar el token como una bandera
                    # de contexto si hemos pasado al territorio de 'almacenar
                    # cosas desconocidas' (por ejemplo, en un pase de 
                    # args-nucleo, manejando lo que van a ser argumentos de 
                    # artefacto)
                    tiene_bandera = (
                        token in machine.contexto.banderas
                        and machine.current_state != "desconocido"
                    )
                    if tiene_bandera and machine.contexto.banderas[token].toma_valor:
                        msj = "{!r} es una bandera para el contexto actual y toma un valor, dándole {!r}"  # noqa
                        debug(msj.format(token, resto))
                        mutaciones.append((indice + 1, resto))
                    else:
                        resto = ["-{}".format(x) for x in resto]
                        msj = (
                            "Didicion global multi-banderas {!r} en {!r} y {!r}"
                        )  # noqa
                        debug(msj.format(orig, token, resto))
                        for item in reversed(resto):
                            mutaciones.append((indice + 1, item))
            # Aquí, tenemos algunas posibles mutaciones en cola, y es posible
            # que 'token' también se haya sobrescrito. Si los aplicamos y 
            # continuamos tal como están, o lo revertimos, depende de:
            # - Si el analizador no estaba esperando un valor de bandera,
            #   ya estamos en el camino correcto, así que aplique mutaciones
            #   y muévase al paso manejar().
            # - Si ESTAMOS esperando un valor, y la bandera que lo espera
            #   SIEMPRE quiere un valor (no es opcional), volvemos a usar el
            #   token original. (TODO: podría reorganizar esto para evitar el
            #   subanálisis en este caso, pero la optimización para la 
            #   ejecución dirigida a humanos no es fundamental).
            # - Finalmente, si estamos esperando un valor Y es opcional, 
            #   inspeccionamos el primer sub-token/mutación para ver si de
            #   otra manera hubiera sido un indicador válido, y dejamos que
            #   eso determine lo que hacemos (si es válido, aplicamos las 
            #   mutaciones; si no es válido, restablecemos el token original).
            if machine.esperando_valor_de_bandera:
                opcional = machine.bandera and machine.bandera.opcional
                subtoken_es_una_bandera_valida = token in machine.contexto.banderas
                if not (opcional and subtoken_es_una_bandera_valida):
                    token = orig
                    mutaciones = []
            for indice, valor in mutaciones:
                cuerpo.insert(indice, valor)
            machine.manejar(token)
        machine.finish()
        resultado = machine.resultado
        resultado.remanente = " ".join(remanente)
        return resultado


class AnalizarLaMaquina(StateMachine):
    initial_state = "contexto"

    state("contexto", enter=["completar_bandera", "completar_contexto"])
    state("desconocido", enter=["completar_bandera", "completar_contexto"])
    state("fin", enter=["completar_bandera", "completar_contexto"])

    transition(from_=("contexto", "desconocido"), event="finish", to="fin")
    transition(
        from_="contexto",
        event="ver_contexto",
        action="cambiar_al_contexto",
        to="contexto",
    )
    transition(
        from_=("contexto", "desconocido"),
        event="ver_desconocido",
        action="solo_almacenar",
        to="desconocido",
    )

    def cambiando_estado(self, from_, to):
        debug("AnalizarLaMaquina: {!r} => {!r}".format(from_, to))

    def __init__(self, inicial, contextos, ignorar_desconocido):
        # Inicializar
        self.ignorar_desconocido = ignorar_desconocido
        self.inicial = self.contexto = copy.deepcopy(inicial)
        debug("Inicializar con contexto: {!r}".format(self.contexto))
        self.bandera = None
        self.bandera_tiene_valor = False
        self.resultado = AnalizaResultado()
        self.contextos = copy.deepcopy(contextos)
        debug("Contextos disponibles: {!r}".format(self.contextos))
        # En caso de que StateMachine haga algo en __init__
        super(AnalizarLaMaquina, self).__init__()

    @property
    def esperando_valor_de_bandera(self):
        # ¿Tenemos una bandera actual y espera un valor (en lugar de ser un
        # bool/palanca)?
        toma_valor = self.bandera and self.bandera.toma_valor
        if not toma_valor:
            return False
        # OK, esta bandera es una que toma valores.
        # ¿Es un tipo de lista (al que se acaba de cambiar)? Entonces siempre
        # aceptará más valores.
        # TODO: ¿cómo manejar a alguien que quiere que sea otro iterable como
        # tupla o clase personalizada? ¿O simplemente decimos sin soporte?
        if self.bandera.tipo is list and not self.bandera_tiene_valor:
            return True
        # No es una lista, está bien. ¿Ya tiene valor?
        tiene_valor = self.bandera.valor_bruto is not None
        # Si no tiene uno, estamos esperando uno (que le dice al analizador
        # cómo proceder y, por lo general, almacenar el siguiente token).
        # TODO: en el caso negativo aquí, deberíamos hacer otra cosa en su
        # lugar:
        # - Excepto, "oye la cagaste, ¡ya le diste esa bandera!"
        # - Sobrescribir, "oh, ¿cambiaste de opinión?" - que también requiere
        #   más trabajo en otros lugares, lamentablemente. (¿Quizás propiedades
        #   adicionales en Argumento que se pueden consultar, por ejemplo, 
        #   "arg.es_iterable"?)
        return not tiene_valor

    def manejar(self, token):
        debug("Token de manejo: {!r}".format(token))
        # Manejar el estado desconocido en la parte superior: no nos
        # importa ni siquiera la entrada posiblemente válida si hemos
        # encontrado una entrada desconocida.
        if self.current_state == "desconocido":
            debug("Parte-superior-de-manejar() ver_desconocido({!r})".format(token))
            self.ver_desconocido(token)
            return
        # Bandera
        if self.contexto and token in self.contexto.banderas:
            debug("vio bandera {!r}".format(token))
            self.cambiar_a_bandera(token)
        elif self.contexto and token in self.contexto.banderas_inversas:
            debug("vio bandera inversa {!r}".format(token))
            self.cambiar_a_bandera(token, inversas=True)
        # Valor para la  bandera
        elif self.esperando_valor_de_bandera:
            debug(
                "Estamos esperando un valor de bandera {!r} debe ser eso?".format(
                    token
                )
            )  # noqa
            self.ver_valor(token)
        # Args posicionales (deben ir por encima de la comprobación de 
        # contexto-nombre en caso de que aún necesitemos un posarg y el 
        # usuario quiera legítimamente darle un valor que resulte ser un
        # nombre de contexto válido).
        elif self.contexto and self.contexto.faltan_argumentos_posicionales:
            msj = "Contexto {!r} requiere argumentos posicionales, comiendo {!r}"
            debug(msj.format(self.contexto, token))
            self.ver_arg_posicional(token)
        # Nuevi contexto
        elif token in self.contextos:
            self.ver_contexto(token)
        # La bandera de contexto inicial se da como por-artefacto bandera 
        # (por ejemplo, --help)
        elif self.inicial and token in self.inicial.banderas:
            debug("Vio (inicial-contexto) bandera {!r}".format(token))
            bandera = self.inicial.banderas[token]
            # Caso especial para nucleo --help bandera: el nombre de contexto se usa como valor.
            if bandera.nombre == "help":
                bandera.valor = self.contexto.nombre
                msj = "Vio --help en un  contexto por-artefacto, seteando artefacto nombre ({!r}) como su valor"  # noqa
                debug(msj.format(bandera.valor))
            # Todos los demás: basta con entrar en el estado analizador 'cambiar a bandera'
            else:
                # TODO: ¿manejar también banderas de núcleo inverso? No hay 
                # ninguno en este momento (por ejemplo, --no-dedupe es en 
                # realidad 'no_dedupe', no un 'dedupe' predeterminado-Falso) y
                # depende de nosotros si realmente ponemos alguno en su lugar.
                self.cambiar_a_bandera(token)
        # Desconocido
        else:
            if not self.ignorar_desconocido:
                debug("No se puede encontrar el contexto con el nombre {!r}, errando".format(token))   # noqa
                self.error("No tengo idea de que {!r} es!".format(token))
            else:
                debug("Parte-baja-de-manejar() ver_desconocido({!r})".format(token))
                self.ver_desconocido(token)

    def solo_almacenar(self, token):
        # Empezar la lista sin_analizar
        debug("Almacenando token desconocido {!r}".format(token))
        self.resultado.sin_analizar.append(token)

    def completar_contexto(self):
        debug(
            "Envase contexto arriba {!r}".format(
                self.contexto.nombre if self.contexto else self.contexto
            )
        )
        # Asegúrese de que se hayan dado todos los argumentos posicionales
        # del contexto.
        if self.contexto and self.contexto.faltan_argumentos_posicionales:
            err = "'{}' no recibió los argumentos posicionales requeridos: {}"
            nombres = ", ".join(
                "'{}'".format(x.nombre)
                for x in self.contexto.faltan_argumentos_posicionales
            )
            self.error(err.format(self.contexto.nombre, nombres))
        if self.contexto and self.contexto not in self.resultado:
            self.resultado.append(self.contexto)

    def cambiar_al_contexto(self, nombre):
        self.contexto = copy.deepcopy(self.contextos[nombre])
        debug("Moviéndose al contexto {!r}".format(nombre))
        debug("Contexto args: {!r}".format(self.contexto.args))
        debug("Contexto banderas: {!r}".format(self.contexto.banderas))
        debug("Contexto banderas_inversas: {!r}".format(self.contexto.banderas_inversas))

    def completar_bandera(self):
        if self.bandera:
            msj = "Completando bandera actual {} antes de seguir adelante"
            debug(msj.format(self.bandera))
        # Barf si necesitáramos un valor y no obtuvimos uno
        if (
            self.bandera
            and self.bandera.toma_valor
            and self.bandera.valor_bruto is None
            and not self.bandera.opcional
        ):
            err = "La bandera {!r} necesitaba un valor y no se le dio uno!"
            self.error(err.format(self.bandera))
        # Manejar banderas de valor opcional; en este punto no se les dio un 
        # valor explícito, pero fueron vistos, ergo deberían ser tratados
        # como bools.
        if self.bandera and self.bandera.valor_bruto is None and self.bandera.opcional:
            msj = "Vio bandera opcional {!r} pasar con/sin valor; ajuste a verdadero"
            debug(msj.format(self.bandera.nombre))
            # Salta el casting para que el bool se conserve
            self.bandera.asigna_valor(True, cast=False)

    def comprobar_la_ambiguedad(self, valor):
        """
        Protéjase de la ambigüedad cuando la bandera actual toma un valor
        opcional.

        .. versionadded:: 1.0
        """
        # ¿Actualmente no se está examinando ninguna bandera, o se está 
        # examinando una pero no toma un valor opcional? La ambigüedad no es
        # posible.
        if not (self.bandera and self.bandera.opcional):
            return False
        # Estamos * tratando con una bandera de valor opcional, pero ¿ya 
        # recibió un valor? Aquí tampoco puede haber ambigüedad.
        if self.bandera.valor_bruto is not None:
            return False
        # De lo contrario, *puede* haber ambigüedad si una o más de las
        # siguientes pruebas fallan.
        pruebas = []
        # ¿Aún existen posargs sin completar?
        pruebas.append(self.contexto and self.contexto.faltan_argumentos_posicionales)
        # ¿El valor coincide con otro artefacto / contexto nombre válido?
        pruebas.append(valor in self.contextos)
        if any(pruebas):
            msj = "{!r} es ambiguo cuando se da después de una bandera de valor opcional"
            raise ErrorDeAnalisis(msj.format(valor))

    def cambiar_a_bandera(self, bandera, inversas=False):
        # Verificación de cordura para detectar ambigüedad con bandera de
        # valor opcional previa
        self.comprobar_la_ambiguedad(bandera)
        # También átelo, en caso de que el anterior tuviera un valor opcional,
        # etc. Parece ser inofensivo para otros tipos de banderas. 
        # (TODO: este es un indicador serio de que necesitamos mover parte de
        # esta contabilidad bandera-por-bandera a los bits de la máquina de 
        # estado, si es posible, ya que era REAL y confuso: ¡por qué esto se
        # requería manualmente!)
        self.completar_bandera()
        # Setear obj bandera/arg
        bandera = self.contexto.banderas_inversas[bandera] if inversas else bandera
        # Actualiza estado
        try:
            self.bandera = self.contexto.banderas[bandera]
        except KeyError as e:
            # Intente retroceder a inicial/nucleo bandera
            try:
                self.bandera = self.inicial.banderas[bandera]
            except KeyError:
                # Si no estaba en ninguno de los dos, plantee la excepción
                # del contexto original, ya que es más útil / correcto.
                raise e
        debug("Moviéndose a bandera {!r}".format(self.bandera))
        # Contabilidad para banderas de tipo iterable (donde el típico 'valor
        # no vacío / no predeterminado -> claramente ya obtuvo su valor' 
        # prueba es insuficiente)
        self.bandera_tiene_valor = False
        # Manejar banderas booleanas (que se pueden actualizar inmediatamente)
        if not self.bandera.toma_valor:
            val = not inversas
            debug("Marcando bandera vista {!r} como {}".format(self.bandera, val))
            self.bandera.valor = val

    def ver_valor(self, valor):
        self.comprobar_la_ambiguedad(valor)
        if self.bandera.toma_valor:
            debug("Seteando bandera {!r} al valor {!r}".format(self.bandera, valor))
            self.bandera.valor = valor
            self.bandera_tiene_valor = True
        else:
            self.error("La bandera {!r} no requiere valor!".format(self.bandera))

    def ver_arg_posicional(self, valor):
        for arg in self.contexto.args_posicionales:
            if arg.valor is None:
                arg.valor = valor
                break

    def error(self, msj):
        raise ErrorDeAnalisis(msj, self.contexto)


class AnalizaResultado(list):
    """
    Objeto tipo-lista con algunos atributos extra relacionados con el análisis.

    Específicamente, un atributo ``.remanente``, que es la cadena que se 
    encuentra después de un ``-`` en cualquier lista argv analizada; y un
    atributo ``.sin_analizar``, una lista de tokens que no se pudieron 
    analizar.

    .. versionadded:: 1.0
    """

    def __init__(self, *args, **kwargs):
        super(AnalizaResultado, self).__init__(*args, **kwargs)
        self.remanente = ""
        self.sin_analizar = []
