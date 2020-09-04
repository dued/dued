from __future__ import unicode_literals, print_function

import getpass
import inspect
import json
import os
import sys
import textwrap
from importlib import import_module  # buffalo buffalo

from .util import six

from . import Coleccion, Config, Ejecutor, CargaDesdeElSitemaDeArchivos
from .completado.completar import completar, imprimir_script_de_completado
from .analizador import Analizador, AnalizadorDeContexto, Argumento
from .excepciones import SalidaInesperada, ColeccionNoEcontrada, ErrorDeAnalisis, Salida
from .terminales import pty_dimension
from .util import debug, habilita_logs, lineadeayuda


class Programa(object):
    """
    Administra la invocación de CLI de nivel superior, generalmente a través
    de puntos de entrada ``setup.py``.

    Diseñado para distribuir colecciones de artefactos Dued como programas
    independientes, pero también se usa internamente para implementar el
    programa ``dued``.

    .. seealso::
        :ref: `reusing-as-a-binary` para un tutorial/demostracion de esta
        funcionalidad

    .. versionadded:: 1.0
    """

    def args_nucleo(self):
        """
        Devuelve objetos nucleo predeterminados `.Argumento`, como una lista.

        .. versionadded:: 1.0
        """
        # Argumentos presentes siempre, incluso cuando se envuelve como un binario diferente
        return [
            Argumento(
                nombres=("tiempofuera", "T"),
                tipo=int,
                help="Especifique un tiempo de espera de ejecución \
                de comando global, en segundos.",
            ),
            Argumento(
                nombres=("completar",),
                tipo=bool,
                default=False,
                help="Imprime candidatos tab-completado para analizar el \
                resto dado.",  
            ),
            Argumento(
                nombres=("config", "f"),
                help="Archivo de config. de tiempo de ejecución para usar.", 
            ),
            Argumento(
                nombres=("depurar", "d"),
                tipo=bool,
                default=False,
                help="Habilitar salida de depuración.",
            ),
            Argumento(
                nombres=("seco", "S"),
                tipo=bool,
                default=False,
                help="Comandos echo en lugar de correr.",
            ),
            Argumento(
                nombres=("echo", "e"),
                tipo=bool,
                default=False,
                help="Echo ejecuta comandos antes de correr.",
            ),
            Argumento(
                nombres=("help", "h"),
                opcional=True,
                help="Mostrar ayuda principal o por artefecto y salir.",
            ),
            Argumento(
                nombres=("ocultar",),
                help="Establecer el valor predeterminado de correr()'s 'ocultar' kwarg.", # noqa
            ),
            Argumento(
                nombres=("lista", "l"),
                opcional=True,
                help="Lista artefactos disponibles, opcionalmente limitadas a un hangar.",  # noqa
            ),
            Argumento(
                nombres=("prof-de-lista", "P"),
                tipo=int,
                default=0,
                help="Al listar artefactos, solo muestra los primeros INT niveles.",
            ),
            Argumento(
                nombres=("formlista", "F"),
                help="Cambie el formato de visualización utilizado al enumerar artefactos. \
                Debe ser uno de: plano(default), anidado, json.",  # noqa
                default="plano",
            ),
            Argumento(
                nombres=("script-completado",),
                tipo=str,
                default="",
                help="Imprima el script de tab-completado para su shell preferido (bash|zsh|fish).",  # noqa
            ),
            Argumento(
                nombres=("prompt-sudo",),
                tipo=bool,
                default=False,
                help="Preguntar al usuario al iniciar sesión el valor de sudo.password config.",  # noqa
            ),
            Argumento(
                nombres=("pty", "p"),
                tipo=bool,
                default=False,
                help="Usar un pty al ejecutar comandos de shell.",
            ),
            Argumento(
                nombres=("version", "V"),
                tipo=bool,
                default=False,
                help="Muestra la versión y sale.",
            ),
            Argumento(
                nombres=("solo-alerta", "a"),
                tipo=bool,
                default=False,
                help="Advertir, en lugar de fallar, cuando los comandos de shell fallan.",
            ),
            Argumento(
                nombres=("generar-pyc",),
                tipo=bool,
                default=False,
                help="Habilitar la creación de archivos .pyc.",
            ),
        ]

    def artefacto_args(self):
        """
        Devuelve objetos `.Argumento` por defecto artefacto-relacionados, 
        como una lista.

        Estos solo se agregan a los argumentos centrales en el modo "corredor
        de artefactos" (el valor predeterminado para `` dued``) - se omiten 
        cuando el constructor recibe un argumento ``hangar`` no vacío (modo
        ""hangar incluido"" )

        .. versionadded:: 1.0
        """
        # Argumentos relacionados específicamente con la invocación como
        # 'dued' en sí (o como otros programas de ejecución de artefactos
        #  arbitrarias, como 'fab')
        return [
            Argumento(
                nombres=("coleccion", "c"),
                help="Especifique el nombre de la colección para cargar.",
            ),
            Argumento(
                nombres=("no-dedupe",),
                tipo=bool,
                default=False,
                help="Deshabilitar la deduplicación de tareas.",
            ),
            Argumento(
                nombres=("dir-raiz", "r"),
                help="Cambiar el directorio raíz utilizado para buscar módulos de tareas.", # noqa
            ),
        ]

    # ¿Otras variables globales de nivel de clase que una subclase podría
    # anular en algún momento?
    ancho_de_sangría_inicial = 2
    sangria_inicial = " " * ancho_de_sangría_inicial
    ancho_de_sangría = 4
    sangrar = " " * ancho_de_sangría
    relleno_col = 3

    def __init__(
        self,
        version=None,
        hangar=None,
        nombre=None,
        binario=None,
        clase_cargador=None,
        clase_ejecutor=None,
        clase_config=None,
        nombres_binarios=None,
    ):
        """
        Cree una nueva instancia parametrizada de `.Programa`.

        :param str version:
            La versión del programa, p.ej. ``"0.1.0"``. El valor
            predeterminado es ``"desconocida"``.

        :param hangar:
            Una `.Coleccion` para usar como subcomando's de este programa.

            Si ``None`` (el valor predeterminado), el programa se comportará
            como ``dued``, buscando un espacio de nombres de artefactos 
            cercano con un `.Cargador` y exponiendo argumentos como
            :option:`--coleccion` y :option:`--coleccion` para inspeccionar o
            seleccionar hangares específicos.

            Si se le da un objeto `.Coleccion`, lo usará como si hubiera sido
            entregado a :option:`--coleccion`. También actualizará el 
            analizador para eliminar referencias a artefactos y opciones 
            relacionadas con tareas, y mostrar los subcomandos en la salida
            ``--help``. El resultado será un programa que tiene un conjunto
            estático de subcomandos.

        :param str nombre:
            El nombre del programa(s), displayado en la salida ``--version``.

            Si ``None`` (default), es una versión en mayúscula de la primera
            palabra en el ``argv`` entregado a `.correr`. Por ejemplo, cuando
            se invoca desde un binstub instalado como ``foobar``, por defecto
            será ``Foobar``.

        :param str binario:
            Cadena descriptiva de nombre binario en minúscula utilizada en el
            texto de ayuda.

            Por ejemplo, el propio valor interno de Dued para esto es 
            ``du[ed]``, lo que indica que está instalado como ``du`` y
            ``dued``. Como se trata únicamente de texto destinado a la
            visualización de ayuda, puede estar en cualquier formato que 
            desee, aunque debe coincidir con lo que haya puesto en la entrada
            ``console_scripts`` de ``setup.py``.

            Si es ``None`` (predeterminado), usa la primera palabra en 
            ``argv`` palabra por palabra (como con ``nombre`` arriba, excepto
            que no está en mayúscula).

        :param nombres_binarios:
            Lista de cadenas de nombres binarios, para usar en scripts de
            completado.

            Esta lista asegura que los scripts de completado de shell 
            generados por: option: `--script-completado` instruyen al shell
            para que use ese completado para todos los nombres instalados de
            este programa.

            Por ejemplo, el valor predeterminado interno de Dued para esto
            es ``["du", "dued"]``.

            Si es ``None`` (por defecto), la primera palabra en ``argv`` (en
            la invocación de :option: `--script-completado`) se usa en una
            lista de un solo-elemento.

        :param clase_cargador:
            La subclase `.Cargador` a utilizar al cargar colecciones de 
            artefacto.

            El valor predeterminado es `.CargaDesdeElSitemaDeArchivos`.

        :param clase_ejecutor:
            La subclase `.Ejecutor` que se utilizará al ejecutar artefactos.

            Por defecto es `.Ejecutor`; también puede ser anulado en tiempoej
            por la :ref:`sistema de configuración <valores-predeterminados>` y
            su configuración ``artefactos.clase_ejecutor`` (siempre que esa
            configuración no sea ``None``).

        :param clase_config:
            The `.Config` subclass to use for the base config object.
            La subclase `.Config` que se utilizará para el objeto de 
            configuración base.

            El valor predeterminado es `.Config`.
            
        .. versionchanged:: 1.2

            Se agregó el argumento ``nombres_binarios``.
        """
        self.version = "desconocida" if version is None else version
        self.hangar = hangar
        self._nombre = nombre
        # TODO 2.0: rename binary to binary_help_name or similar. (Or write
        # code to autogenerate it from nombres_binarios.)
        self._binario = binario
        self._nombres_binarios = nombres_binarios
        self.argv = None
        self.clase_cargador = clase_cargador or CargaDesdeElSitemaDeArchivos
        self.clase_ejecutor = clase_ejecutor or Ejecutor
        self.clase_config = clase_config or Config

    def crear_config(self):
        """
        Crea una instancia de `.Config` (o subclase, según) para usar en ejec.
        de un artefacto.

        Esta configuración es totalmente utilizable pero carecerá de datos
        derivados del tiempo de ejecución, como archivos de configuración de
        proyecto y tiempo de ejecución, anulaciones de arg de CLI, etc. Esos
        datos se agregan más adelante en `actualizar_config`. Consulte la 
        cadena de documentos `.Config` para obtener detalles del ciclo de
        vida.

        :returns: ``None``; establece ``self.config`` en su lugar.

        .. versionadded:: 1.0
        """
        self.config = self.clase_config()

    def actualizar_config(self, combinar=True):
        """
        Actualiza el `.Config` previamente instanciado con datos analizados.

        Por ejemplo, así es como ``--echo`` puede anular el valor de
        configuración predeterminado para ``correr.echo``.

        :param bool combinar:
            Ya sea para combinar al final o diferir. Principalmente útil para
            subclasificadores. por defecto: ``True``.

        .. versionadded:: 1.0
        """
        # Ahora que tenemos el resultado de análisis a mano, podemos tomar los
        # bits de configuración restantes:
        # - configurar tiempoej, que depende de la bandera tiempoej/var entorno
        # - el nivel de configuración anula, ya que está compuesto por datos de
        #   la bandera tiempoej
        # NOTE: solo complete los valores que alterarían el comportamiento, 
        # de lo contrario quiero que se cumplan los valores predeterminados.
        correr = {}
        if self.args["solo-alerta"].valor:
            correr["alarma"] = True
        if self.args.pty.valor:
            correr["pty"] = True
        if self.args.ocultar.valor:
            correr["ocultar"] = self.args.ocultar.valor
        if self.args.echo.valor:
            correr["echo"] = True
        if self.args.seco.valor:
            correr["seco"] = True
        artefactos = {}
        if "no-dedupe" in self.args and self.args["no-dedupe"].valor:
            artefactos["dedupe"] = False
        tiempo_de_descanso = {}
        comando = self.args["tiempofuera"].valor
        if comando:
            tiempo_de_descanso["comando"] = comando
        # Manejar "completar los valores de configuración al inicio de tiempoej",
        # que por ahora es solo la contraseña de sudo
        sudo = {}
        if self.args["prompt-sudo"].valor:
            prompt = "Valor de configuración 'sudo.password' deseado:"
            sudo["password"] = getpass.getpass(prompt)
        anula = dict(correr=correr, artefactos=artefactos, sudo=sudo, tiempo_de_descanso=tiempo_de_descanso)
        self.config.cargar_anulaciones(anula, combinar=False)
        ruta_acte = self.args.config.valor
        if ruta_acte is None:
            ruta_acte = os.environ.get("DUED_CONFIG_TIEMPOEJ", None)
        self.config.setea_ruta_del_acte(ruta_acte)
        self.config.cargar_acte(combinar=False)
        if combinar:
            self.config.combinar()

    def correr(self, argv=None, salir=True):
        """
        Ejecute la lógica CLI principal, basada en ``argv``.

        :param argv:
            Los argumentos contra los que ejecutar. Puede ser ``None``, una
            lista de cadenas o una cadena. Consulte `.normalizar_argv` para
            obtener más detalles.

        :param bool salir:
            Cuando sea ``False`` (defaul: ``True``), ignorará las excepciones
            de `.ErrorDeAnalisis`, `.Salida` y `.Falla`, que de lo contrario
            activarán llamadas a `sys.exit`.

            .. note::
                Esto es principalmente una concesión a las pruebas. Si está
                configurando esto en ``False`` en un entorno de producción,
                probablemente debería usar `.Ejecutor` y amigos directamente
                en su lugar.

        .. versionadded:: 1.0
        """
        try:
            # Cree una configuración inicial, que contendrá los valores por 
            # defecto y los valores de la mayoría de las ubicaciones de los
            # archivos de config (todos menos tiempoej.) Se utiliza para 
            # informar el comportamiento de carga y análisis.
            self.crear_config()
            # Analizar el ARGV dado con nuestra maquinaria de análisis CLI, lo
            # que resulta en cosas como self.args (nucleo args/banderas), self.coleccion
            # (el hangar cargado, que puede verse afectado por las
            # banderas centrales) y self.artefactos (los artefactos solicitados
            # para ejec y sus propios args/banderas)
            self.analizar_core(argv)
            # Manejar lo concerniente de colección, incluida la configuración
            # del proyecto
            self.analizar_coleccion()
            # Analizar el resto de argv como entrada relacionada con artefacto
            self.analizar_artefactos()
            # Fin del análisis (típicamente cosas de rescate como --lista, --help)
            self.limpiar_analisis()
            # Actualice la config anterior con nuevos valores del paso de
            # análisis: contenido del archivo de configuración de tiempoej y
            # anulaciones derivadas de la bandera (por ejemplo, para las 
            # opciones de eco, alarma, etc. de correr()).
            self.actualizar_config()
            # Crea un Ejecutor, pasando los datos resultantes de los pasos
            # anteriores, luego dile que ejecute los artefactos.
            self.ejecutar()
        except (SalidaInesperada, Salida, ErrorDeAnalisis) as e:
            debug("Recibió una excepción posiblemente saltable: {!r}".format(e))
            # Imprime mensajes de error del analizador, corredor, etc si es 
            # necesario; previene el rastreo desordenado pero aún da pistas
            # al usuario interactivo sobre los problemas.
            if isinstance(e, ErrorDeAnalisis):
                print(e, file=sys.stderr)
            if isinstance(e, Salida) and e.mensaje:
                print(e.mensaje, file=sys.stderr)
            if isinstance(e, SalidaInesperada) and e.resultado.ocultar:
                print(e, file=sys.stderr, end="")
            # Poner fin a la ejecución a menos que nos hayan dicho que no lo hagamos.
            if salir:
                if isinstance(e, SalidaInesperada):
                    code = e.resultado.salida
                elif isinstance(e, Salida):
                    code = e.code
                elif isinstance(e, ErrorDeAnalisis):
                    code = 1
                sys.exit(code)
            else:
                debug("Se invoca como correr (..., salir=False), ignorando la excepción")
        except KeyboardInterrupt:
            sys.exit(1)  #Mismo comportamiento que el propio Python fuera de REPL

    def analizar_core(self, argv):
        debug("argv dado a Programa.correr: {!r}".format(argv))
        self.normalizar_argv(argv)

        # Obtener argumentos nucleo (setea self.nucleo)
        self.analizar_args_core()
        debug("Terminó de analizar los argumentos principales")

        # Setear la bandera de bytecode-writing del intérprete
        sys.dont_write_bytecode = not self.args["generar-pyc"].valor

        # Habilite la depuración de aquí en adelante, si se dio la bandera de
        # depuración. (Antes de este punto, la depuración requiere configurar
        # INVOKE_DEBUG).
        if self.args.debug.valor:
            habilita_logs()

        # Cortocircuito si --version
        if self.args.version.valor:
            debug("Corte --version, imprimir version & salir")
            self.imprimir_version()
            raise Salida

        # Imprimir (dinámico, no se requieren artefactos) script de completado
        # si se solicita
        if self.args["script-completado"].valor:
            imprimir_script_de_completado(
                shell=self.args["script-completado"].valor,
                nombres=self.nombres_binarios,
            )
            raise Salida

    def analizar_coleccion(self):
        """
        Carga una colección de artefactos y configura a nivel-proyecto.

        .. versionadded:: 1.0
        """
        # Carga una colección de artefactos a no ser que ya configuró uno.
        if self.hangar is not None:
            debug(
                "Al programa se asigno por defecto un hangar, sin cargar una colección"
            )  # noqa
            self.coleccion = self.hangar
        else:
            debug(
                "No se dió un hangar por defecto, intentando cargar uno desde el disco"
            )  # noqa
            # Si no se proporcionó ningún espacio de nombres incluido & --help,
            # simplemente imprímalo y salga. (Si tuviéramos un espacio de 
            # nombres empaquetado, nucleo --help se manejará *después* de que se
            # cargue la colección y se complete el análisis).
            if self.args.help.valor is True:
                debug(
                    "Sin hangar atado y sin --help; imprimiendo ayuda"
                )
                self.imprimir_ayuda()
                raise Salida
            self.cargar_coleccion()
        # Configúrelos para su uso potencial más adelante cuando enumere 
        # artefactos
        # TODO: ¡sé amable si estos vinieron de la configuración ...! A los
        # usuarios les encantaría decir que por defecto están anidado, 
        # por ejemplo. Fácil adición de funciones 2.x.
        self.raiz_de_lista = None
        self.profundidad_de_lista = None
        self.formato_de_lista = "plano"
        self.ambito_de_coleccion = self.coleccion

        # TODO: cargar el proyecto conf, si es posible, con gracia

    def limpiar_analisis(self):
        """
        Pasos posteriores al análisis, previos a la ejecución, como --help,
        --lista, etc.

        .. versionadded:: 1.0
        """
        halp = self.args.help.valor

        # Nucleo (sin valor dado): salida de --help (solo cuando se incluye el hangar)
        if halp is True:
            debug("Corte simple --help, imprimiendo help & salir")
            self.imprimir_ayuda()
            raise Salida

        # Imprimir ayuda por-artefacto, si es necesario
        if halp:
            if halp in self.analizador.contextos:
                msj = "Corte --help <nombredeartefacto>, imp ayuda por-artefacto & salir"
                debug(msj)
                self.imprimir_ayuda_de_artefacto(halp)
                raise Salida
            else:
                # TODO: se siente realmente tonto al factorizar esto de Analizador,
                # pero ... ¿deberíamos?
                raise ErrorDeAnalisis("No idea what '{}' is!".format(halp))

        # Imprime artefactos descubiertos si es necesario
        raiz_de_lista = self.args.lista.valor  # será True o cadena
        self.formato_de_lista = self.args["formlista"].valor
        self.profundidad_de_lista = self.args["prof-de-lista"].valor
        if raiz_de_lista:
            # No solo --lista, sino --lista alguna-raiz-origen - hacer más trabajo
            if isinstance(raiz_de_lista, six.string_types):
                self.raiz_de_lista = raiz_de_lista
                try:
                    sub = self.coleccion.subcoleccion_desde_ruta(raiz_de_lista)
                    self.ambito_de_coleccion = sub
                except KeyError:
                    msj = "Sub-coleccion '{}' extraviada!"
                    raise Salida(msj.format(raiz_de_lista))
            self.listar_artefactos()
            raise Salida

        # Imprimir ayudantes de completado si es necesario
        if self.args.completar.valor:
            completar(
                nombres=self.nombres_binarios,
                nucleo=self.nucleo,
                contexto_inicial=self.contexto_inicial,
                coleccion=self.coleccion,
            )

        # Comportamiento alternativo si no se proporcionaron artefactos y no se
        # especificó un valor predeterminado (principalmente una subrutina con
        # fines primordiales)
        # NOTA: cuando hay un artefacto predeterminado, Ejecutor lo seleccionará 
        # cuando no se encuentren artefactos en el análisis de CLI.
        if not self.artefactos and not self.coleccion.default:
            self.sin_artefactos_asignados()

    def sin_artefactos_asignados(self):
        debug(
            "No se especificó ningún artefacto para su ejecución y ningún artefacto predeterminado; \
            imprimiendo la ayuda global como respaldo" 
        ) # noqa
        self.imprimir_ayuda()
        raise Salida

    def ejecutar(self):
        """
        Entrega datos y especific. de artefactos-a-ejecutar a un `.Ejecutor`.

        .. note::
            El código cliente que solo quiere una subclase `.Ejecutor` dife-
            rente puede simplemente establecer` `clase_ejecutor`` en 
            `.__ init__`, o anular ``artefactos.clase_ejecutor`` en cualquier
            lugar del :ref:`config system <default-values>` (lo que puede per-
            mitirle evitar por completo el uso de un Programa personalizado).


        .. versionadded:: 1.0
        """
        klase = self.clase_ejecutor
        config_ruta = self.config.artefactos.clase_ejecutor
        if config_ruta is not None:
            # TODO: ¿por qué diablos esto no está integrado en importlib?
            ruta_del_modulo, _, nombre_de_clase = config_ruta.rpartition(".")
            # TODO: ¿vale la pena intentar envolver ambos y generar ImportError
            # para los casos en los que el módulo existe pero el nombre de la
            # clase no? Más "normal" pero también su propia fuente posible de 
            # errores / confusión ...
            modulo = import_module(ruta_del_modulo)
            klase = getattr(modulo, nombre_de_clase)
        ejecutor = klase(self.coleccion, self.config, self.nucleo)
        ejecutor.ejecutar(*self.artefactos)

    def normalizar_argv(self, argv):
        """
        Masajea ``argv`` en una útil lista de cadenas.

        **Si es None** (predeterminado), usa `sys.argv`.

        **Si no es una cadena iterable**, usa eso en lugar de `sys.argv`.

        **Si es una cadena**, realiza un `str.split` y luego se ejecuta con
        el resultado. (Esto es principalmente una conveniencia; en caso de 
        duda, use una lista).

        Setea ``self.argv`` en el resultado.

        .. versionadded:: 1.0
        """
        if argv is None:
            argv = sys.argv
            debug("argv era None; usando sys.argv: {!r}".format(argv))
        elif isinstance(argv, six.string_types):
            argv = argv.split()
            debug("argv era como-cadena; terrible: {!r}".format(argv))
        self.argv = argv

    @property
    def nombre(self):
        """
        Deriva del nombre legible por humanos del prog- basado en `.binario`.

        .. versionadded:: 1.0
        """
        return self._nombre or self.binario.capitalize()

    @property
    def llamado_de(self):
        """
        Devuelve el nombre del programa con el que fuimos llamados.

        Específicamente, este es el concepto (del módulo OS de Python de un) 
        nombre base del primer argumento en el vector de argumento analizado.

        .. versionadded:: 1.2
        """
        return os.path.basename(self.argv[0])

    @property
    def binario(self):
        """
        Derive el(los) nombre(s) binario(s) orientados-a-ayuda del programa(s)
        desde init args & argv.

        .. versionadded:: 1.0
        """
        return self._binario or self.llamado_de

    @property
    def nombres_binarios(self):
        """
        Derive el(los) nombre(s) binario(s) orientados-a-completado del 
        programa a partir de args y argv.

        .. versionadded:: 1.2
        """
        return self._nombres_binarios or [self.llamado_de]

    # TODO 2.0: ugh renombra esto o args_nucleo, son demasiado confusos
    @property
    def args(self):
        """
        Obtenga los argumentos del programa nucleo del resultado del análisis
        ``self.nucleo``.

        .. versionadded:: 1.0
        """
        return self.nucleo[0].args

    @property
    def contexto_inicial(self):
        """
        El contexto analizador inicial, también conocido como 
        **banderas centrales del programa**.

        Los argumentos específicos contenidos allí diferirán dependiendo de
        si se especificó un espacio de nombres empaquetado en `.__ init__`.

        .. versionadded:: 1.0
        """
        args = self.args_nucleo()
        if self.hangar is None:
            args += self.artefacto_args()
        return AnalizadorDeContexto(args=args)

    def imprimir_version(self):
        print("{} {}".format(self.nombre, self.version or "desconocida"))

    def imprimir_ayuda(self):
        sufijo_usado = "artf1 [--artf1-opcs] ... artfN [--artfN-opcs]"
        if self.hangar is not None:
            sufijo_usado = "<subcomando> [--subcomando-opcs] ..."
        print("Uso: {} [--opcs-nucleo] {}".format(self.binario, sufijo_usado))
        print("")
        print("Opciones principales:")
        print("")
        self.imprimir_columnas(self.contexto_inicial.help_tuplas())
        if self.hangar is not None:
            self.listar_artefactos()

    def analizar_args_core(self):
        """
        Filtra los argumentos centrales (nucleo) y deja los artefactos o sus
        argumentos para más adelante.

        Setea ``self.nucleo`` en el `.AnalizaResultado` de este paso.

        .. versionadded:: 1.0
        """
        debug("Analizando el contexto inicial (nucleo args)")
        analizador = Analizador(inicial=self.contexto_inicial, ignorar_desconocido=True)
        self.nucleo = analizador.analizar_args(self.argv[1:])
        msj = "Resultado del análisis de Core-args : {!r} & sin analizar : {!r}"
        debug(msj.format(self.nucleo, self.nucleo.sin_analizar))

    def cargar_coleccion(self):
        """
        Cargue una colección de artefacto basada en argumentos centrales 
        analizados, o muera en el intento.

        .. versionadded:: 1.0
        """
        # NOTE: inicia, nombre_de_colecc ambos recurren a los valores de configuración
        # dentro de Cargador (que, sin embargo, pueden obtenerlos de nuestra config).
        inicio = self.args["dir-raiz"].valor
        cargador = self.clase_cargador(config=self.config, inicio=inicio)
        nombre_de_colecc = self.args.coleccion.valor
        try:
            modulo, padre = cargador.cargar(nombre_de_colecc)
            # ¡Esta es la primera vez que podemos cargar la configuración del
            # proyecto, por lo que deberíamos -permitir que la configuración
            # del proyecto afecte el paso de análisis de artefacto! 
            # TODO: ¿vale la pena combinar estos métodos de configuración y
            # carga? Puede requerir más ajustes de cómo se comportan las 
            # cosas en / después de __init__.
            self.config.setea_ubic_del_py(padre)
            self.config.cargar_proyecto()
            self.coleccion = Coleccion.del_modulo(
                modulo,
                cargado_de=padre,
                nombre_auto_guion=self.config.artefactos.nombre_auto_guion,
            )
        except ColeccionNoEcontrada as e:
            raise Salida("No puedo encontrar ninguna colección con el nombre {!r}!".format(e.nombre))

    def _actualizar_contexto_core(self, contexto, nuevo_args):
        # Actualice contexto nucleo (principal) c/core_via_task args, si y solo
        # si la versión via-artefacto del arg realmente recibió un valor.
        # TODO: insertar esto en una subclase de Léxico Argumento-aware y
        # .actualizar()?
        for clave, arg in nuevo_args.items():
            if arg.obtuvo_valor:
                contexto.args[clave]._value = arg._value

    def analizar_artefactos(self):
        """
        Analiza los argumentos sobrantes, que suelen ser artefactos y arg por-artefacto.

        Setea ``self.analizador`` en el analizador usando, ``self.artefactos``
        en los contextos de por-artefacto analizados y ``self.nucleo_via_artefactos``
        en un contexto que contiene las banderas nucleo vistas dentro de los 
        contextos de artefacto.

        También modifica ``self.nucleo`` para incluir los datos de 
        ``nucleo_via_artefactos`` (para que refleje correctamente cualquier indicador
        principal proporcionado independientemente de dónde aparezcan).

        .. versionadded:: 1.0
        """
        self.analizador = Analizador(
            inicial=self.contexto_inicial,
            contextos=self.coleccion.a_contextos(),
        )
        debug("Analizando artefactos contra {!r}".format(self.coleccion))
        resultado = self.analizador.analizar_args(self.nucleo.sin_analizar)
        self.nucleo_via_artefactos = resultado.pop(0)
        self._actualizar_contexto_core(
            contexto=self.nucleo[0], nuevo_args=self.nucleo_via_artefactos.args
        )
        self.artefactos = resultado
        debug("Contextos de artefacto resultantes: {!r}".format(self.artefactos))

    def imprimir_ayuda_de_artefacto(self, nombre):
        """
        Imprimir ayuda para un artefacto específico, p. Ej. ``du --help <nombre artefacto>''.

        .. versionadded:: 1.0
        """
        # Setup
        ctx = self.analizador.contextos[nombre]
        tuplas = ctx.help_tuplas()
        textdocs = inspect.getdoc(self.coleccion[nombre])
        header = "Uso: {} [--opcs-nucleo] {} {}[otros artefactos aquí ...]"
        opcs = "[--opciones] " if tuplas else ""
        print(header.format(self.binario, nombre, opcs))
        print("")
        print("Textdocs:")
        if textdocs:
            # Really wish textwrap worked better for this.
            for line in textdocs.splitlines():
                if line.strip():
                    print(self.sangria_inicial + line)
                else:
                    print("")
            print("")
        else:
            print(self.sangria_inicial + "ninguno")
            print("")
        print("Opciones:")
        if tuplas:
            self.imprimir_columnas(tuplas)
        else:
            print(self.sangria_inicial + "ninguno")
            print("")

    def listar_artefactos(self):
        # Cortocircuito si no hay artefactos para mostrar (Coleccion ahora implementa bool)
        focus = self.ambito_de_coleccion
        if not focus:
            msj = "No se encontraron artefactos en la colección. '{}'!"
            raise Salida(msj.format(focus.nombre))
        # TODO: ahora que plano/anidado están casi 100% unificados,
        # ¿quizás reconsiderar esto un poco?
        getattr(self, "lista_{}".format(self.formato_de_lista))()

    def lista_plana(self):
        pares = self._hacer_parejas(self.ambito_de_coleccion)
        self.mostrar_con_columnas(pares=pares)

    def lista_anidada(self):
        pares = self._hacer_parejas(self.ambito_de_coleccion)
        extra = "'*' denota valores predeterminados de coleccion"
        self.mostrar_con_columnas(pares=pares, extra=extra)

    def _hacer_parejas(self, colecc, ancestros=None):
        if ancestros is None:
            ancestros = []
        pares = []
        sangrar = len(ancestros) * self.sangrar
        ruta_de_ancestros = ".".join(x for x in ancestros)
        for nombre, artefacto in sorted(six.iteritems(colecc.artefactos)):
            es_predeterminado = nombre == colecc.default
            # Empiece solo con el nombre y solo el alias, sin prefijos ni puntos.
            mostrarnombre = nombre
            alias = list(map(colecc.transformar, sorted(artefacto.alias)))
            # Si se muestra una subcolección (o si se muestra un espacio de 
            # nombres / raíz determinado), marque algunos puntos para dejar
            # en claro que estos nombres requieren rutas con puntos para dued.
            if ancestros or self.raiz_de_lista:
                mostrarnombre = ".{}".format(mostrarnombre)
                alias = [".{}".format(x) for x in alias]
            # ¿Anidado? Aplica sangría y agrega asteriscos a los default-artefactos
            if self.formato_de_lista == "anidado":
                prefijo = sangrar
                if es_predeterminado:
                    mostrarnombre += "*"
            # ¿Plano? Prefije nombres y alias con nombres de antepasados para
            # obtener una ruta completa con puntos; y dé a default-artefactos
            # su nombre de colección como primer alias.
            if self.formato_de_lista == "plano":
                prefijo = ruta_de_ancestros
                # Asegúrese de que los puntos iniciales estén presentes para
                # las subcolecciones si se muestra con alcance
                if prefijo and self.raiz_de_lista:
                    prefijo = "." + prefijo
                alias = [prefijo + alias for alias in alias]
                if es_predeterminado and ancestros:
                    alias.insert(0, prefijo)
            # Genere columnas de ayuda y nombre completo y agréguelas a los pares.
            alias_str = " ({})".format(", ".join(alias)) if alias else ""
            full = prefijo + mostrarnombre + alias_str
            pares.append((full, lineadeayuda(artefacto)))
        # Determina si estamos a máxima-profundidad o no
        truncar = self.profundidad_de_lista and (len(ancestros) + 1) >= self.profundidad_de_lista
        for nombre, subcolecc in sorted(six.iteritems(colecc.colecciones)):
            mostrarnombre = nombre
            if ancestros or self.raiz_de_lista:
                mostrarnombre = ".{}".format(mostrarnombre)
            if truncar:
                cuentas = [
                    "{} {}".format(len(getattr(subcolecc, attr)), attr)
                    for attr in ("artefactos", "colecciones")
                    if getattr(subcolecc, attr)
                ]
                mostrarnombre += " [{}]".format(", ".join(cuentas))
            if self.formato_de_lista == "anidado":
                pares.append((sangrar + mostrarnombre, lineadeayuda(subcolecc)))
            elif self.formato_de_lista == "plano" and truncar:
                # NOTE: solo se agrega un par orientado-a-colecc si se limita por profundidad
                pares.append((ruta_de_ancestros + mostrarnombre, lineadeayuda(subcolecc)))
            # Recurrir, si aún no está a la profundidad máxima
            if not truncar:
                pares_recurrentes = self._hacer_parejas(
                    colecc=subcolecc, ancestros=ancestros + [nombre]
                )
                pares.extend(pares_recurrentes)
        return pares

    def list_json(self):
        # Cordura: no podemos honrar limpiamente el argumento --prof-de-lista
        # sin cambiar el esquema de datos o actuar de manera extraña; y 
        # tampoco tiene mucho sentido limitar la profundidad cuando la salida
        # es para que la maneje un script. Así que nos negamos, por ahora. 
        # TODO: encuentra una mejor manera
        if self.profundidad_de_lista:
            raise Salida(
                "¡La opción --prof-de-lista no es compatible con el formato JSON!"
            )  # noqa
        # TODO: considere usar algo más formal re: el formato que emite, por 
        # ejemplo, json-schema o lo que sea. Simplificaría los documentos 
        # relativamente concisos pero solo humanos que actualmente describen esto.
        colecc = self.ambito_de_coleccion
        datos = colecc.serializado()
        print(json.dumps(datos))

    def abridor_de_lista_de_artefacto(self, extra=""):
        raiz = self.raiz_de_lista
        profundidad = self.profundidad_de_lista
        especificador = " '{}'".format(raiz) if raiz else ""
        cola = ""
        if profundidad or extra:
            cadena_de_profundidad = "profundidad={}".format(profundidad) if profundidad else ""
            ensamblador = "; " if (profundidad and extra) else ""
            cola = " ({}{}{})".format(cadena_de_profundidad, ensamblador, extra)
        texto = "Disponible{} artefactos{}".format(especificador, cola)
        # TODO: ¿los casos de uso con espacio de nombres incluido también
        # quieren mostrar cosas como la raíz y la profundidad? Dejando fuera
        # por ahora ...
        if self.hangar is not None:
            texto = "Subcomandos"
        return texto

    def mostrar_con_columnas(self, pares, extra=""):
        raiz = self.raiz_de_lista
        print("{}:\n".format(self.abridor_de_lista_de_artefacto(extra=extra)))
        self.imprimir_columnas(pares)
        # TODO: ¿vale la pena quitar esto por anidado? ya que se indica con un
        # asterisco allí? ugggh
        default = self.ambito_de_coleccion.default
        if default:
            specific = ""
            if raiz:
                specific = " '{}'".format(raiz)
                default = ".{}".format(default)
            # TODO: recortar/prefijo puntos
            print("Default{} artefacto: {}\n".format(specific, default))

    def imprimir_columnas(self, tuplas):
        """
        Imprimir columnas con pestañas de (nombre, ayuda) ``tuplas``.

        Útil para enumerar artefactos + textdocs:, banderas + cadenas de 
        ayuda, etc.

        .. versionadded:: 1.0
        """
        # Calcule el tamaño de las columnas: no ajuste las especificaciones
        # de la bandera, dé lo que queda a las descripciones.
        ancho_de_nombre = max(len(x[0]) for x in tuplas)
        ancho_de_desc = (
            pty_dimension()[0]
            - ancho_de_nombre
            - self.ancho_de_sangría_inicial
            - self.relleno_col
            - 1
        )
        envoltura = textwrap.TextWrapper(width=ancho_de_desc)
        for nombre, cad_de_ayuda in tuplas:
            if cad_de_ayuda is None:
                cad_de_ayuda = ""
            # Ajustar descripciones/texto de ayuda
            trozos_de_ayuda = envoltura.wrap(cad_de_ayuda)
            # Imprimir especificaciones de bandera + relleno
            relleno_de_nombre = ancho_de_nombre - len(nombre)
            spec = "".join(
                (
                    self.sangria_inicial,
                    nombre,
                    relleno_de_nombre * " ",
                    self.relleno_col * " ",
                )
            )
            # Print help text as needed
            if trozos_de_ayuda:
                print(spec + trozos_de_ayuda[0])
                for chunk in trozos_de_ayuda[1:]:
                    print((" " * len(spec)) + chunk)
            else:
                print(spec.rstrip())
        print("")
