# -*- coding: utf-8 -*-

import locale
import os
import struct
from subprocess import Popen, PIPE
import sys
import threading
import time
import signal

from .util import six

# Importe algunas cosas específicas de la plataforma en el nivel superior
# para que se puedan burlar de las pruebas.
try:
    import pty
except ImportError:
    pty = None
try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import termios
except ImportError:
    termios = None

from .excepciones import (
    SalidaInesperada,
    Falla,
    ExcepcionDeHilo,
    ErrorDeCentinela,
    ErrorEnTuberiaDeSubP,
    CaducoComando,
)
from .terminales import (
    WINDOWS,
    pty_dimension,
    caracter_buffereado,
    listo_para_leer,
    bytes_a_leer,
)
from .util import tiene_fileno, esuntty, hilo_de_manejo_de_excepciones, codificar_salida


class Corredor(object):
    """
    API de ejecución-de-comandos de núcleo parcialmente-abstracto.

    Esta clase no es utilizable por sí misma y debe ser subclasificada,
    implementando una serie de métodos como `start`,`esperar` y 
    `cod_de_retorno`. Para ver un ejemplo de implementación de una subclase,
    consulte el código fuente de `.Local`.

    .. versionadded:: 1.0
    """

    leer_tam_del_fragmento = 1000
    entrada_en_reposo = 0.01

    def __init__(self, contexto):
        """
        Crea un nuevo corredor con un identificador en algún `.Contexto`.

        :param contexto:
            una instancia de `.Contexto`, utilizada para transmitir opciones 
            predeterminadas y proporcionar acceso a otra información 
            contextualizada (por ejemplo, un `.Corredor` orientado a 
            distancia podría querer una subclase `.Contexto` que contenga 
            información sobre nombres de host y puertos).

            .. note::
                El `.Contexto` dado a las instancias`.Corredor` **debe** 
                contener valores de configuración predeterminados para la 
                clase `.Corredor` en cuestión. Como mínimo, esto significa 
                valores para cada uno de los argumentos de la palabra key
                predeterminada `.Corredor.correr` como ``echo`` y ``alarma``.

        :raises excepciones.ValueError:
            si no todos los valores default esperados se encuentran en 
            ``contexto``
        """
        #: El `.Contexto` dado al argumento del mismo nombre de` __init__`.
        self.contexto = contexto
        #: Un `threading.Event` que indica la finalización del programa.
        #:
        #: Normalmente se establece después de que regrese `esperar`. Algunos mecanismos 
        #: IO se basan en esto para saber cuándo salir de un ciclo de lectura infinito.
        self.programa_terminado = threading.Event()
        # Desearía que Sphinx organizara todos los atributos de clase/instancia
        # en el mismo lugar. Si no hago esto aquí, va 'class vars -> __init__
        # textdocs -> instance vars ':( TODO: considere combinar class y 
        # __init__ docstrings, aunque eso también es molesto.
        #: Cuántos bytes (como máximo) leer por iteración de lecturas de flujo.
        self.leer_tam_del_fragmento = self.__class__.leer_tam_del_fragmento
        # Ídem re: declarar esto en 2 lugares por razones de documentación.
        #: Cuántos segundos para reposo en cada iteración del bucle de lectura
        #: stdin y otros bucles que de otro modo serían rápidos.
        self.entrada_en_reposo = self.__class__.entrada_en_reposo
        #: Si se ha emitido una advertencia pty fallback.
        self.aviso_sobre_repligue_pty = False
        #: Una lista de instancias de `.StreamCentinela` para su uso por
        #: `responder`. Se rellena en tiempoej con `correr`.
        self.centinelas = []
        # Marcador de posición del temporizador de tiempo de espera opcional
        self._timer = None
        # Indicadores asíncronos (inicializados para hacer referencia 'finalmente' 
        # en caso de que algo salga REALMENTE mal durante el análisis de opciones) 
        self._asincrono = False
        self._rechazado = False

    def correr(self, comando, **kwargs):
        """
        Ejecute ``comando``, devolviendo una instancia de `Resultado` una vez
        que esté completo.

        De forma predeterminada, este método es síncrono (solo regresa una vez
        que se ha completado el subproceso) y permite la comunicación
        interactiva del teclado con el subproceso.

        En su lugar, puede comportarse de forma asincrónica (regresando pronto
        y requiriendo interacción con el objeto resultante para administrar el
        ciclo de vida del subproceso) si especifica ``asincrono = True``.
        Además, puede disociar completamente el subproceso del control de Dued
        (lo que le permite persistir por sí solo después de que Python sale)
        diciendo ``rechazado = True``. Consulte los documentos de per-kwarg a
        continuación para obtener detalles sobre ambos.

        .. note::
            Todos los kwargs tendrán por defecto los valores encontrados en el
            atributo `~.Corredor.contexto` de esta instancia, específicamente
            en el subárbol ``correr`` de su configuración (por ejemplo,
            ``correr.echo`` proporciona el valor predeterminado para la 
            palabra key ``echo`` , etc.). Los valores predeterminados 
            básicos se describen en la lista de parámetros a continuación.

        :param str comando: El comando de shell para ejecutar.

        :param str shell:
            Qué binario de shell usar. Predeterminado: ``/bin/bash``(en Unix;
            ``COMSPEC`` o ``cmd.exe`` en Windows).

        :param bool alarma:
            ya sea para advertir y continuar, en lugar de generar 
            `.SalidaInesperada`, cuando el comando ejecutado sale con un
            status distinto de cero. Default: ``False``

            .. note::
                Esta configuración no tiene ningún efecto sobre las 
                excepciones, que aún se generarán, generalmente agrupadas en
                objetos `.ExcepcionDeHilo` si fueron generadas por los 
                hilos de trabajo de IO.

                De manera similar, las excepciones de `.ErrorDeCentinela` 
                generadas por instancias de `.StreamCentinela` también 
                ignorarán esta configuración, y normalmente se incluirán
                dentro de los objetos de `.Falla` (para preservar el contexto
                de ejecución).

                Ídem `.CaducoComando` - Básicamente, cualquier cosa que evite
                que un comando llegue a "salir con un código de salida" ignora
                esta bandera.   

        :param ocultar:
            Permite al llamador deshabilitar el comportamiento predeterminado
            de ``correr`` de copiar el subproceso stdout y stderr al terminal
            de control.
            Especifique ``ocultar='salida'`` (o ``'stdout'``) para ocultar solo 
            el stream stdout, ``ocultar='err'`` (o ``'stderr'``) para ocultar
            solo stderr, o ``ocultar='ambos'`` (o ``True``) para ocultar ambos
            streams.

            El valor predeterminado es ``None``, lo que significa imprimir 
            todo; ``False`` también desactivará la ocultación.

            .. note::
                Stdout y stderr siempre se capturan y almacenan en el objeto
                ``Resultado``, independientemente del valor de `` ocultar``.

            .. note::
                ``ocultar=True`` también anulará ``echo=True`` si se dan ambos
                (ya sea como kwargs o mediante config/CLI).

        :param bool pty:
            Por defecto, ``correr`` se conecta directamente al proceso 
            invocado y lee sus streams stdout/stderr. Algunos programas 
            almacenarán en búfer (o incluso se comportarán) de manera
            diferente en esta situación en comparación con el uso de una
            terminal real o pseudoterminal(pty). Para usar un pty en lugar
            del comportamiento predeterminado, especifique ``pty=True``.

            .. warning::
                Debido a su naturaleza, los ptys tienen un único flujo 
                (stream) de salida, por lo que la capacidad de diferenciar
                stdout de stderr **no es posible** cuando ``pty=True``. Como
                tal, toda la salida aparecerá en ``sal_stream`` (ver más abajo)
                y se capturará en el atributo de resultado ``stdout``.
                ``err_stream`` y ``stderr`` siempre estarán vacíos cuando
                ``pty=True``.

        :param bool retroceder:
            Controls auto-fallback behavior re: problems offering a pty when
            ``pty=True``. Whether this has any effect depends on the specific
            `Corredor` subclass being invoked. Default: ``True``.
            Controla el comportamiento de retroceso automático con respecto a:
            problemas al ofrecer un pty cuando ``pty=True``. Si esto tiene
            algún efecto depende de la subclase específica de `Corredor` que
            se invoque. Predeterminado: `True`.

        :param bool asincrono:
            Cuando se establece en ``True`` (predeterminado ``False``), 
            habilita un comportamiento asincrono, de esta manera:

            - Las conexiones al terminal de control están deshabilitadas, lo
              que significa que no verá la salida del subproceso y no 
              responderá a la entrada de su teclado, similar a 
              ``ocultar=True`` y ``ing_stream=False`` (aunque se da 
              explícitamente ``(salida|err|in)_stream`` los objetos 
              similares-a-archivos se seguirán respetando como de costumbre).
            - `.correr` regresa inmediatamente después de iniciar el 
              subproceso, y su valor de retorno se convierte en una instancia
              de `Promesa` en lugar de `Resultado`.
            - Los objetos `Promesa` son principalmente útiles para su método 
              `~Promesa.join`, que se bloquea hasta que el subproceso sale 
              (similar a las API de subprocesos) y devuelve un `~Resultado`
              final o genera una excepción, como un síncrono ``correr`` lo
              haría.

                - Al igual que con las API de subprocesos y similares, los
                  usuarios de ``asincrono=True`` deben asegurarse de ``join``
                  a sus objetos `Promesa` para evitar problemas con el cierre
                  del intérprete.
                - Una manera fácil de manejar tal limpieza es usar la 
                  `Promesa` como administrador de contexto - automáticamente
                  se ``join`` a la salida del bloque de contexto.

            .. versionadded:: 1.4

        :param bool rechazado:
            Cuando se establece en ``True`` (predeterminado ``False``), 
            devuelve inmediatamente como ``asincrono=True``, pero no realiza
            ningún rabajo en segundo plano relacionado con ese subproceso (se
            ignora por completo). Esto permite que los subprocesos que 
            utilizan el fondo de shell o técnicas similares (por ejemplo 
            ``&``, ``nohup``) persistan más allá de la vida útil del proceso
            de Python que ejecuta Dued.

            .. note::
                Si no está seguro de si quiere esto o ``asincrono``, 
                probablemente quiera ``asincrono``

            Específicamente, ``rechazado=True`` tiene los siguientes 
            comportamientos:

            - El valor de retorno es ``None`` en lugar de una subclase 
              `Resultado`.
            - No se activan subprocesos de trabajo de I/O, por lo que no
              tendrá acceso al subproceso stdout/stderr, su stdin no se 
              reenviará, ``(salida|err|in)_stream`` se ignorará y las
              características como ``centinelas`` no funcionará.
            - No se comprueba ningún código de salida, por lo que no recibirá
              ningún error si el subproceso no se cierra correctamente.
            - ``pty=True`` puede no funcionar correctamente (es posible que
              los subprocesos no se ejecuten en absoluto; esto parece ser un
               error potencial en ``pty.fork`` de Python) a menos que su línea
               de comando incluya herramientas como ``nohup`` o (la shell
               incorporada) ``rechazado``.

            .. versionadded:: 1.4

        :param bool echo:
            Controla si `.correr` imprime la cadena de comando en la salida 
            estándar local antes de ejecutarla. Predeterminado: ``False``.

            .. note::
                ``ocultar=True`` anulará ``echo=True`` si ambos se dan.

        :param dict entorno:
            De forma predeterminada, los subprocesos reciben una copia del
            propio entorno de Dued (es decir, ``os.environ``). Proporcione 
            un dicc aquí para actualizar ese entorno secundario.

            Por ejemplo, ``correr('comando', entorno={'PYTHONPATH':
            '/algun/entorno/virtual/talves'})`` modificaría el entorno var de
            ``PYTHONPATH``, con el resto del entorno del hijo pareciendo
            idéntico al padre.

            .. seealso:: ``reemplazar_ent`` para cambiar 'update' o 'replace'.

        :param bool reemplazar_ent:
            Cuando es ``True``, hace que el subproceso reciba el diccionario
            dado a ``entorno`` como su entorno de shell completo, en lugar de
            actualizar una copia de ``os.environ`` (que es el comportamiento
            predeterminado). Predeterminado:``False``.

        :param str codificacion:
            Anula la detección automática de la codificación que utiliza el
            subproceso para sus flujos stdout/stderr (que por defecto es el
            valor de retorno de `codificacion_por_defecto`).

        :param sal_stream:
            Un objeto stream como-archivo en el que se debe escribir
            la salida estándar del subproceso. Si es ``None`` (por defecto), 
            se utilizará ``sys.stdout``.

        :param err_stream:
            Igual que ``sal_stream``, excepto por el error estándar, y por
            defecto es ``sys.stderr``.

        :param ing_stream:
            Un objeto stream como-archivo que se usara como entrada estándar
            del subproceso. Si es ``None`` (por defecto), se utilizará
            ``sys.stdin``.

            Si es ``False``, deshabilitará la duplicación de stdin por completo
            (aunque otras funciones que escriben en el subproceso 'stdin, como
            la respuesta automática, seguirán funcionando). Deshabilitar la 
            duplicación de stdin puede ayudar cuando ``sys.stdin`` es un objeto
            non-stream que se comporta mal, como los arneses de prueba o los 
            corredores de comandos sin cabeza.

        :param centinelas:
            Una lista de instancias de `.StreamCentinela` que se usarán para
            escanear el ``stdout`` o ``stderr`` del programa y pueden escribir
            en su ``stdin`` (típicamente objetos ``str`` o ``bytes`` según la
            versión de Python) en respuesta a patrones u otras heurísticas.

            Consulte :doc:`/concepts/centinelas` para obtener detalles sobre
            esta funcionalidad..

            Default: ``[]``.

        :param bool echo_stdin:
            Ya sea para escribir datos de ``ing_stream`` de nuevo a
            ``sal_stream``.

            En otras palabras, en el uso interactivo normal, este parámetro
            controla si Dued refleja lo que escribe en su terminal.

            De forma predeterminada (cuando es ``None``), este comportamiento
            se desencadena por lo siguiente:

                * No usar un pty para ejecutar el subcomando (es decir, 
                  ``pty=False``), ya que ptys hace eco (echo) de forma nativa
                  de stdin a stdout por sí mismos;
                * Y cuando el terminal de control de Dued en sí (según 
                  ``ing_stream``) parece ser un dispositivo de terminal válido o
                  TTY. (Específicamente, cuando `~dued.util.esuntty` arroja un 
                  resultado ``True`` cuando se le da ``ing_stream``).

                  .. note::
                      Esta propiedad tiende a ser ``False`` cuando se canaliza
                      la salida de otro programa a una sesión Dued, o cuando
                      se ejecuta Dued dentro de otro programa (por ejemplo, 
                      ejecutar Dued desde sí mismo)

            Si ambas propiedades son verdaderas, se producirá un echo; si 
            alguno es falso, no se realizará ningún echo.

            Cuando no es ``None``, este parámetro anulará la aito-detección y
            forzará o deshabilitará el eco.

        :param tiempofuera:
            Hacer que el corredor envíe una interrupción al subproceso y 
            genere `.CaducoComando`, si el comando tarda más de ``tiempofuera``
            segundos en ejecutarse. El valor predeterminado es ``None``, lo
            que significa que no hay tiempo de espera.

            .. versionadded:: 1.3

        :returns:
            `Resultado`, or a subclass thereof.

        :raises:
            `.SalidaInesperada`, if the comando exited nonzero and
            ``alarma`` was ``False``.

        :raises:
            `.Falla`, if the comando didn't even exit cleanly, e.g. if a
            `.StreamCentinela` raised `.ErrorDeCentinela`.

        :raises:
            `.ExcepcionDeHilo` (if the background I/O threads encountered
            excepciones other than `.ErrorDeCentinela`).

        .. versionadded:: 1.0
        """
        try:
            return self._correr_cuerpo(comando, **kwargs)
        finally:
            if not (self._asincrono or self._rechazado):
                self._parar_todo()

    def _parar_todo(self):
        # TODO 2.0: as probably noted elsewhere, parar_el_temporizador should become part
        # of parar() and then we can nix this. Ugh!
        self.parar()
        self.parar_el_temporizador()

    def _setup(self, comando, kwargs):
        """
        Prepara datos en ``self`` (si mismo) para que estemos listos para
        comenzar a ejecutar
        """
        # Normalizar kwargs c/config; setea self.opcs, self.streams
        self._unificar_kwargs_con_config(kwargs)
        # Prepara entorno
        self.entorno = self.generar_ent(
            self.opcs["entorno"], self.opcs["reemplazar_ent"]
        )
        # Llegar a la codificación final si ni config ni kwargs tenían una
        self.codificacion = self.opcs["codificacion"] or self.codificacion_por_defecto()
        # Eco ejecutando comando (quiere llegar temprano para ser incluido en seco-correr)
        if self.opcs["echo"]:
            print("\033[1;37m{}\033[0m".format(comando))
        # Preparar argumentos de resultado comunes.
        # TODO: Odio esto. Necesita una reflexión más profunda sobre la modificación
        # de Corredor.generar_resultado de una manera que no sea literalmente el mismo
        # proceso de dos pasos, y que también funcione en sentido descendente.
        self.kwargs_resultado = dict(
            comando=comando,
            shell=self.opcs["shell"],
            entorno=self.entorno,
            pty=self.usando_pty,
            ocultar=self.opcs["ocultar"],
            codificacion=self.codificacion,
        )

    def _correr_cuerpo(self, comando, **kwargs):
        # Prepare todos los bits n bobs.
        self._setup(comando, kwargs)
        # Si seco-correr, detente aquí.
        if self.opcs["seco"]:
            return self.generar_resultado(
                **dict(self.kwargs_resultado, stdout="", stderr="", salida=0)
            )
        # Comience a ejecutar el comando real (se ejecuta en segundo plano)
        self.iniciar(comando, self.opcs["shell"], self.entorno)
        # Si es rechazado, simplemente nos detenemos aquí: sin hilos, sin 
        # temporizador, sin verificación de errores, nada.
        if self._rechazado:
            return
        # Levántese y comience IO, hilos de temporizador
        self.iniciar_tmp(self.opcs["tiempofuera"])
        self.hilos, self.stdout, self.stderr = self.crear_hilos_io()
        for hilo in self.hilos.values():
            hilo.iniciar()
        # Envoltura o promesa de que lo haremos, dependiendo
        return self.hacer_promesa() if self._asincrono else self._terminar()

    def hacer_promesa(self):
        """
        Devuelve una `Promesa` que permite el control asincrono del resto 
        del ciclo de vida.

        .. versionadded:: 1.4
        """
        return Promesa(self)

    def _terminar(self):
        # Esperar a que se ejecute el subproceso, reenviando las señales a
        # medida que las recibimos.
        try:
            while True:
                try:
                    self.esperar()
                    break  # ¡Listo esperando!
                # No se detenga localmente en ^ C, solo reenvíelo:
                # - si el extremo remoto realmente se detiene, naturalmente 
                #   nos detendremos después
                # - si el extremo remoto no se detiene (por ejemplo, REPL,
                #   editor), no queremos detenernos prematuramente
                except KeyboardInterrupt as e:
                    self.enviar_interrupcion(e)
                # TODO: respetar otras señales enviadas a nuestro propio proceso
                # y transmitirlas al subproceso antes de manejarlas 'normalmente'.
        # Asegúrese de atar nuestros hilos de trabajo, incluso si algo explotó.
        # Cualquier excepción que haya surgido durante self.esperar() anterior
        # aparecerá después de este bloque.
        finally:
            # Informar al worker stdin-mirroring para detener su eterno bucle
            self.programa_terminado.set()
            # Úna hilos, almacene excepciones internas y establezca un tiempo
            # de espera si es necesario. (Segregar ErroresDeCentinela, ya que son
            # "errores anticipados" que quieren aparecer al final durante la
            # creación de objetos Falla).
            errores_de_centinela = []
            excepciones_de_hilo = []
            for objetivo, hilo in six.iteritems(self.hilos):
                hilo.join(self._tiempofuera_para_unir_hilos(objetivo))
                excepcion = hilo.excepcion()
                if excepcion is not None:
                    real = excepcion.valor
                    if isinstance(real, ErrorDeCentinela):
                        errores_de_centinela.append(real)
                    else:
                        excepciones_de_hilo.append(excepcion)
        # Si aparecieron excepciones dentro de los hilos, créalas ahora como 
        # un objeto de excepción agregado.
        # NOTE: esto se mantiene fuera del 'finally' para que las excepciones
        # del hilo principal se generen antes que las excepciones del 
        # worker-thread; es más probable que sean problemas muy graves.
        if excepciones_de_hilo:
            raise ExcepcionDeHilo(excepciones_de_hilo)
        # Intercalar stdout/err, calcular salir y obtener el obj resultado final 
        resultado = self._cotejar_resultado(errores_de_centinela)
        # Cualquier presencia de ErrorDeCentinela en los hilos indica que un
        # centinela estaba alterado y abortó la ejecución; hacer una Falla
        # genérica y plantear eso.
        if errores_de_centinela:
            # TODO: existe ambigüedad si de alguna manera obtenemos 
            # ErrorDeCentinela en *ambos* hilos ... tan improbable como sería
            # normalmente.
            raise Falla(resultado, motivo=errores_de_centinela[0])
        # Si se solicitó un tiempo de espera y el subproceso se agotó, grite.
        tiempofuera = self.opcs["tiempofuera"]
        if tiempofuera is not None and self.tiempo_fuera:
            raise CaducoComando(resultado, tiempofuera=tiempofuera)
        if not (resultado or self.opcs["alarma"]):
            raise SalidaInesperada(resultado)
        return resultado

    def _unificar_kwargs_con_config(self, kwargs):
        """
        Unifique los kwargs `correr` con las opciones de config para llegar
        a las opciones locales.

        Sets:

        - ``self.opcs`` - opcs dict
        - ``self.streams`` - mapa de nombres de stream para transmitir valores
          objetivo
        """
        opcs = {}
        for key, valor in six.iteritems(self.contexto.config.correr):
            acte = kwargs.pop(key, None)
            opcs[key] = valor if acte is None else acte
        # Extraiga el tiempo de espera de ejecución del comando, que almacena
        # la config en otro lugar, pero solo úselo si realmente está config
        # (compatibilidad con versiones anteriores)
        config_timeout = self.contexto.config.tiempo_de_descanso.comando
        opcs["tiempofuera"] = kwargs.pop("tiempofuera", config_timeout)
        # Manejar keys kwarg inválidas (cualquier cosa que quede en kwargs).
        # Actuar como lo haría una función normal, es decir, TypeError
        if kwargs:
            err = "correr() obtuvo un arg de palabra key inesperado '{}'"
            raise TypeError(err.format(list(kwargs.keys())[0]))
        # Actualización de banderas asincrónas, rechazadas
        self._asincrono = opcs["asincrono"]
        self._rechazado = opcs["rechazado"]
        if self._asincrono and self._rechazado:
            err = "¡No se puede dar 'asincrono' y 'rechazado' al mismo tiempo!"  # noqa
            raise ValueError(err)
        # Si ocultar era True, apaga el eco
        if opcs["ocultar"] is True:
            opcs["echo"] = False
        # Por el contrario, asegúrese de que el eco esté siempre
        #  activado cuando se ejecuta-en-seco
        if opcs["seco"] is True:
            opcs["echo"] = True
        # Ocultar siempre si es asincrono
        if self._asincrono:
            opcs["ocultar"] = True
        # Luego normalice 'ocultar' de uno de los varios valores de entrada
        # válidos, en una tupla de nombres-de-stream. También tenga en 
        # cuenta los streams .
        sal_stream, err_stream = opcs["sal_stream"], opcs["err_stream"]
        opcs["ocultar"] = normalizar_ocultar(opcs["ocultar"], sal_stream, err_stream)
        # Deriva objetos stream
        if sal_stream is None:
            sal_stream = sys.stdout
        if err_stream is None:
            err_stream = sys.stderr
        ing_stream = opcs["ing_stream"]
        if ing_stream is None:
            # Si ing_stream no se ha anulado y somos asíncronos, no queremos
            # leer de sys.stdin (de lo contrario, el valor predeterminado),
            # así que establezca False en su lugar.
            ing_stream = False if self._asincrono else sys.stdin
        # Determinar pty o no
        self.usando_pty = self.deberia_usar_pty(opcs["pty"], opcs["retroceder"])
        if opcs["centinelas"]:
            self.centinelas = opcs["centinelas"]
        # Set datos
        self.opcs = opcs
        self.streams = {"salida": sal_stream, "err": err_stream, "in": ing_stream}

    def _cotejar_resultado(self, errores_de_centinela):
        # En este punto, tuvimos suficiente éxito como para que quisiéramos regresar 
        # o generar informa detallada sobre nuestra ejecución; entonces generamos un Resultado.
        stdout = "".join(self.stdout)
        stderr = "".join(self.stderr)
        if WINDOWS:
            # "Nuevas líneas universales": reemplace todas las formas estándar de 
            # nueva línea con \n. Esto no está técnicamente relacionado con
            # Windows (\r ya que la nueva línea es una antigua convención
            # de Mac) pero solo aplicamos la traducción para Windows, ya que
            # es la única plataforma en la que es probable que importe en 
            # estos días.
            stdout = stdout.replace("\r\n", "\n").replace("\r", "\n")
            stderr = stderr.replace("\r\n", "\n").replace("\r", "\n")
        # Obtener el código de retorno/salida, a menos que haya ErroresDeCentinela
        # que manejar. NOTE: En ese caso, cod_de_retorno() puede bloquear la espera
        # en el proceso (que puede estar esperando la entrada del usuario). Dado
        # que la mayoría de las situaciones de ErrorDeCentinela carecen de un 
        # código de salida útil de todos modos, omitir esto no hace daño a nadie.
        salida = None if errores_de_centinela else self.cod_de_retorno()
        # TODO: como se señaló en otra parte, odio esto. Considere cambiar la API
        # de generar_resultado() en la próxima revolución importante para que podamos
        # poner orden.
        resultado = self.generar_resultado(
            **dict(
                self.kwargs_resultado, stdout=stdout, stderr=stderr, salida=salida
            )
        )
        return resultado

    def _tiempofuera_para_unir_hilos(self, objetivo):
        # Agregue un tiempofuera a las uniones de subprocesos salida/err cuando
        # parezca que no están muertas pero su contraparte está muerta; esto indica 
        # el problema # 351 (solucionado por # 432) donde el subproc puede 
        # bloquearse porque su stdout (o stderr) ya no está siendo consumido 
        # por el hilo muerto (y una tubería se está llenando). En ese caso, 
        # el hilo no-muerto es probable que se bloquee para siempre en un 
        # `recv` a menos que agreguemos este tiempo de espera.
        if objetivo == self.manejar_stdin:
            return None
        opuesto = self.manejar_stderr
        if objetivo == self.manejar_stderr:
            opuesto = self.manejar_stdout
        if opuesto in self.hilos and self.hilos[opuesto].esta_muerto:
            return 1
        return None

    def crear_hilos_io(self):
        """
        Crea y devuelve un diccionario de objetos de trabajo de subprocesos IO.

        Se espera que el Llamador maneje la persistencia y/o el inicio de los
        hilos envueltos.
        """
        stdout, stderr = [], []
        # Configure los parámetros del hilo IO (formato - body_func: {kwargs})
        args_de_hilo = {
            self.manejar_stdout: {
                "buffer_": stdout,
                "ocultar": "stdout" in self.opcs["ocultar"],
                "salida": self.streams["salida"],
            }
        }
        # Después de optar por el procesamiento anterior, ing_stream será un obj
        # de flujo real o False, por lo que podemos probarlo de verdad. Ni siquiera
        # creamos un hilo de manejo de stdin si es Falso, lo que significa que el
        #  usuario indicó que stdin no existe o es problemático.
        if self.streams["in"]:
            args_de_hilo[self.manejar_stdin] = {
                "entrada_": self.streams["in"],
                "salida": self.streams["salida"],
                "echo": self.opcs["echo_stdin"],
            }
        if not self.usando_pty:
            args_de_hilo[self.manejar_stderr] = {
                "buffer_": stderr,
                "ocultar": "stderr" in self.opcs["ocultar"],
                "salida": self.streams["err"],
            }
        # Inicie los hilos IO
        hilos = {}
        for objetivo, kwargs in six.iteritems(args_de_hilo):
            t = hilo_de_manejo_de_excepciones(objetivo=objetivo, kwargs=kwargs)
            hilos[objetivo] = t
        return hilos, stdout, stderr

    def generar_resultado(self, **kwargs):
        """
        Crea y devuelve una instancia de `Resultado` adecuada a partir de los
        ``kwargs`` dados.

        Las subclases pueden desear anular esto para manipular cosas o generar
        una subclase `Resultado` (por ejemplo, las que contienen metadatos 
        adicionales además de los predeterminados).

        .. versionadded:: 1.0
        """
        return Resultado(**kwargs)

    def leer_la_salida_del_proceso(self, lector):
        """
        Leer y decodificar de forma iterativa bytes de un subproceso salida/err.

        :param lector:
            Una función/parcial literal de lectura, que envuelve el objeto 
            stream actual en cuestión, que requiere una número de bytes para
            leer y devuelve esa cantidad de bytes (o ``None``).

             ``lector`` debe ser una referencia a `leer_proc_stdout` o 
             `leer_proc_stderr`, que realizan las llamadas de lectura 
             específicas de la plataforma/libreria.

        :returns:
            Un generador que produce cadenas Unicode (`unicode` en Python 2;
            `str` en Python 3)

            Específicamente, cada cadena resultante es el resultado de 
            decodificar los bytes `leer_tam_del_fragmento` leídos del 
            subproceso salida/err.

        .. versionadded:: 1.0
        """
        # NOTE: Normalmente, la lectura de cualquier stdout/err (local, remoto
        # o de otro tipo) puede considerarse como "leer hasta que no obtenga
        # nada a cambio". Esto es preferible a "esperar hasta que una señal
        # fuera de banda afirme que el proceso ha terminado de ejecutarse" 
        # porque a veces esa señal aparecerá antes de que hayamos leído todos
        # los datos en la transmisión (es decir, una condición de carrera).
        while True:
            datos = lector(self.leer_tam_del_fragmento)
            if not datos:
                break
            yield self.decodificar(datos)

    def escribe_nuestra_salida(self, stream, cadena):
        """
        Escribe una ``cadena`` al ``stream``.

        También llama a ``.flush()`` en ``stream`` para garantizar que los
        streams de terminales reales no se almacenan en búfer.

        :param stream:
            Un objeto stream de como-archivo, mapeado a los parámetros 
            ``sal_stream`` o ``err_stream`` de `correr`.

        :param cadena: Un objeto string Unicode.

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        stream.write(codificar_salida(cadena, self.codificacion))
        stream.flush()

    def _manejar_la_salida(self, buffer_, ocultar, salida, lector):
        # TODO: almacenar bytes en de-codificación/raw en algún lugar también ...
        for datos in self.leer_la_salida_del_proceso(lector):
            # Eco a la salida estándar local si es necesario
            # TODO: ¿Deberíamos reformular esto como "si quieres ocultar, dame un
            # flujo de salida ficticio, por ejemplo, algo como /dev/null"? De lo
            # contrario, una combinación de 'ocultar = stdout' + 'aquí es un 
            # sal_stream explícito' significa que nunca se escribe sal_stream, y
            # eso parece ... extraño.
            if not ocultar:
                self.escribe_nuestra_salida(stream=salida, cadena=datos)
            # Almacenar en búfer compartido para que el hilo principal pueda hacer
            # cosas con el resultado después de que se complete la ejecución.
            # NOTE: this is threadsafe insofar as no reading occurs until after
            # the thread is join()'d.
            # NOTE: esto es seguro para subprocesos en la medida en que no ocurra
            # ninguna lectura hasta que join()'d el subproceso.
            buffer_.append(datos)
            # Correr nuestro búfer específico a través del framework autorespondedor
            self.responder(buffer_)

    def manejar_stdout(self, buffer_, ocultar, salida):
        """
        Leer el proceso stdout, almacenarlo en un búfer e imprimir/analizar.

        Diseñado para usarse como objetivo de hilo. Solo termina cuando se han
        leído todas las salidas estándar del subproceso.

        :param buffer_: El búfer de captura compartido con el hilo principal.
        :param bool ocultar: Si reproducir o no los datos en ``salida``.
        :param salida:
            Output stream (como-archivo object) to write data into when not
            hiding.
            Flujo de salida (objeto como-archivo) para escribir datos cuando
            no se esconden.

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        self._manejar_la_salida(
            buffer_, ocultar, salida, lector=self.leer_proc_stdout
        )

    def manejar_stderr(self, buffer_, ocultar, salida):
        """
        Read process' stderr, storing into a buffer & printing/analizando.

        Identical to `manejar_stdout` except for the stream read from; see its
        textdocs for API details.
        Lee el stderr del proceso, lo almacenar en un búfer e imprime/analiza.

        Idéntico a `manejar_stdout` excepto por el flujo leído; consulte
        su textdocs para obtener detalles de la API.

        .. versionadded:: 1.0
        """
        self._manejar_la_salida(
            buffer_, ocultar, salida, lector=self.leer_proc_stderr
        )

    def leer_nuestro_stdin(self, entrada_):
        """
        Lee y decodifica bytes de una secuencia stdin local.

        :param entrada_:
            Objeto stream actual para leer. Se asigna a ``ing_stream`` en 
            `correr`, por lo que a menudo será ``sys.stdin``, pero puede ser
            cualquier objeto stream-like.

        :returns:
            Una cadena Unicode, el resultado de decodificar los bytes leídos
            (podría ser la cadena vacía si la tubería se ha cerrado/alcanzado
            EOF); o ``None`` si stdin aún no estaba listo para leer

        .. versionadded:: 1.0
        """
        # TODO: considere mover el administrador de contexto con búfer de caracteres
        # llamar aquí? La desventaja es que cambiaría esos interruptores por cada
        # byte leído en lugar de una vez por sesión, lo que podría ser costoso (?).
        bytes_ = None
        if listo_para_leer(entrada_):
            bytes_ = entrada_.read(bytes_a_leer(entrada_))
            # Decodificar si parece ser de tipo-binario. (De stream de terminal 
            # reales, generalmente sí; de objetos como-archivo, a menudo no).
            if bytes_ and isinstance(bytes_, six.binary_type):
                # TODO: ¿la decodificación de 1 byte a la vez romperá las 
                # codificaciones de caracteres multibyte? ¿Cómo cuadrar la 
                # interactividad con eso?
                bytes_ = self.decodificar(bytes_)
        return bytes_

    def manejar_stdin(self, entrada_, salida, echo):
        """
        Lea el stdin local, copie en el proceso(s) stdin según sea necesario.

        Diseñado para usarse como objetivo de hilo.

        .. note::
            Debido a que los streams stdin del terminal real no tienen un
            "final" bien-definido, si se detecta un stream de este tipo
            (basado en la existencia de un ``.fileno()``) este método esperará
            hasta que se establezca `programa_terminado`, antes de terminar.

            Cuando la secuencia no parece ser de una terminal, se usa la misma
            semántica que `manejar_stdout` - la secuencia es simplemente`
            `read()` desde que devuelve un valor vacío.

        :param entrada_: Stream (object como-archivo) de donde leer.
        :param salida: Stream (object como-archivo) al que puede producir eco.
        :param bool echo: Opción de anulación del usuario para eco stdin-stdout.

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        # TODO: restablecer el bloqueo/cualquier lógica de hilo de fab v1 que 
        # evita la lectura de stdin mientras otras partes del código solicitan
        # contraseñas de tiempoej. (busque 'input_enabled')
        # TODO: fabric # 1339 está fuertemente relacionado con esto, si no está 
        # exponiendo literalmente alguna regresión en Fabric 1.x mismo.
        cerrar_stdin = False
        with caracter_buffereado(entrada_):
            while True:
                datos = self.leer_nuestro_stdin(entrada_)
                if datos:
                    # Refleje lo que acabamos de leer para procesar 'stdin.
                    # Realizamos una codificación para que Python 3 obtenga bytes
                    # (streams + str's en Python 3 == no bueno) pero omitimos el 
                    # paso de decodificación, ya que presumiblemente no es necesario 
                    # (nadie interactúa con estos datos programáticamente).
                    self.escribir_proc_stdin(datos)
                    # También repítelo a la salida estándar local (o lo que sea que
                    # sal_stream esté configurado) cuando sea necesario.
                    if echo is None:
                        echo = self.deberia_hacer_echo_de_stdin(entrada_, salida)
                    if echo:
                        self.escribe_nuestra_salida(stream=salida, cadena=datos)
                # Cadena vacia /char/byte != None. No se puede usar simplemente "más" aquí.
                elif datos is not None:
                    # When reading from como-archivo objects that aren't "real"
                    # terminal streams, an empty byte signals EOF.
                    # Al leer desde objetos como-archivo que no son flujos de terminal
                    # "reales", un byte vacío indica EOF.
                    if not self.usando_pty and not cerrar_stdin:
                        self.cerrar_proc_stdin()
                        cerrar_stdin = True
                # Señales duales de todo-listo: el programa que se está ejecutando se
                # termina de ejecutar, *y* no parece que estemos leyendo nada de stdin.
                # (NOTE: Si solo probamos el primero, podemos encontrar condiciones de
                # carrera re: stdin no leído).
                if self.programa_terminado.is_set() and not datos:
                    break
                # Duerme la siesta para no masticar CPU.
                time.sleep(self.entrada_en_reposo)

    def deberia_hacer_echo_de_stdin(self, entrada_, salida):
        """
        Determine si los datos leídos desde ``entrada_`` deben hacerse eco en
        `` salida``.

         Utilizado por `manejar_stdin`; prueba atributos de ``entrada_`` y ``salida``.

        :param entrada_: Flujo de entrada (objeto como-archivo).
        :param salida: Flujo de salida (objeto como-archivo).
        :returns: A ``bool``.

        .. versionadded:: 1.0
        """
        return (not self.usando_pty) and esuntty(entrada_)

    def responder(self, buffer_):
        """

        The patterns and responses are driven by the `.StreamCentinela` instances
        from the ``centinelas`` kwarg of `correr` - see :doc:`/concepts/centinelas`
        for a conceptual overview.
        Escriba en el stdin del programa en rpta a los patrones en `` buffer_``.

        Los patrones y las respuestas son impulsados por las instancias 
        `.StreamCentinela` del kwarg ``centinelas`` de `correr` - ver
        :doc: `/concept/centinelas` para una descripción general conceptual.

        :param buffer:
            El búfer de captura para el flujo de IO particular de este hilo.

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        # Unir el contenido del búfer en una sola cadena; sin esto, las subclases
        # de StreamCentinela no pueden hacer cosas como buscar iterativamente
        # coincidencias de patrones.
        # NOTE: el uso de string.join debería ser "suficientemente eficiente" por
        # ahora, re: velocidad y uso de memoria. Si eso se vuelve falso, considere
        # usar StringIO o cStringIO (aunque este último no funciona bien con
        # Unicode), que aparentemente es aún más eficiente.
        stream = u"".join(buffer_)
        for centinela in self.centinelas:
            for respuesta in centinela.envio(stream):
                self.escribir_proc_stdin(respuesta)

    def generar_ent(self, entorno, reemplazar_ent):
        """
        Retorna un dicc de entorno adecuado basado en la entrada y el 
        comportamiento del usuario.

        :param dict entorno: 
            Dicc sunimistro de anulac. o entorno completo, según.
        :param bool reemplazar_ent:
            Si actualiza ``entorno``, o se usa en lugar de, el valor de 
            `os.environ`.

        :returns: Un diccionario de variables de entorno de shell.

        .. versionadded:: 1.0
        """
        return entorno if reemplazar_ent else dict(os.environ, **entorno)

    def deberia_usar_pty(self, pty, retroceder):
        """
        ¿Debería la ejecución intentar utilizar un pseudo-terminal?

        :param bool pty:
            Si el usuario pidió explícitamente una pty.
        :param bool retroceder:
            Si se debe permitir volver a la ejecución no-pty, en situaciones
            en las que ``pty=True`` pero no se pudo asignar una pty.

        .. versionadded:: 1.0
        """
        # NOTE: respaldo no utilizado: sin retroceso implementado por defecto.
        return pty

    @property
    def tiene_hilos_muertos(self):
        """
        Used during process-completion waiting (in `esperar`) to ensure we don't
        deadlock our child process if our IO processing threads have
        errored/died.
        Detecte si algún subproceso IO parece haber terminado inesperadamente.

        Se utiliza durante la espera de finalización del proceso (en `esperar`)
        para garantizar que no bloqueemos nuestro proceso hijo si nuestros
        subprocesos de procesamiento de E/S (IO) tienen-errores/murieron.

        :returns:
            ``True`` si alguno de los hilos parece haber terminado con una 
            excepción, ``Falso`` en caso contrario.

        .. versionadded:: 1.0
        """
        return any(x.esta_muerto for x in self.hilos.values())

    def esperar(self):
        """
        Bloquear hasta que el comando en ejecución parezca haber salido.

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        while True:
            proc_terminado = self.proceso_esta_terminado
            hilos_muertos = self.tiene_hilos_muertos
            if proc_terminado or hilos_muertos:
                break
            time.sleep(self.entrada_en_reposo)

    def escribir_proc_stdin(self, datos):
        """
        Escriba ``datos`` codificados en el proceso(s) en ejecución 'stdin.

        :param datos: una cadena Unicode.

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        # Codifique siempre, luego solicite la subclase de implementación
        # para realizar la escritura real en el subproceso 'stdin.
        self._escribir_proc_stdin(datos.encode(self.codificacion))

    def decodificar(self, datos):
        """
        Decodifica algunos bytes de ``datos`` y devuelve Unicode.

        .. versionadded:: 1.0
        """
        # NOTE: sí, este es un 1-liner. El punto es hacer que sea mucho más 
        # difícil olvidar usar 'reemplazar' al decodificar :)
        return datos.decodificar(self.codificacion, "reemplazar")

    @property
    def proceso_esta_terminado(self):
        """
        Determine si nuestro subproceso ha terminado.

        .. note::
            La implementación de este método debe ser no bloqueante, ya que se
            usa dentro de un ciclo de consulta / sondeo.

        :returns:
            ``True`` si el subproceso ha terminado de ejecutarse, ``False`` de
            lo contrario

        .. versionadded:: 1.0
        """
        raise NotImplementedError

    def iniciar(self, comando, shell, entorno):
        """
        Iniciar ejecución de ``comando`` (vía ``shell``, con ``entorno``).

        Normalmente, esto significa el uso de un subproceso bifurcado o
        solicitar el inicio de la ejecución en un sistema remoto.

        En la mayoría de los casos, este método también establecerá variables
        de miembro específicas de la subclase que se utilizan en otros métodos
        como `esperar` y/o `cod_de_retorno`.

        :param str comando:
            Cadena de comando para ejecutar.

        :param str shell:
            Shell para usar al ejecutar ``comando``.

        :param dict entorno:
            Dicc de Entorno utilizado para preparar el entorno de shell
            
        .. versionadded:: 1.0
        """
        raise NotImplementedError

    def iniciar_tmp(self, tiempofuera):
        """
        Inicie un temporizador para `matar` nuestro subproceso después de 
        ``tiempofuera`` segundos.
        """
        if tiempofuera is not None:
            self._timer = threading.Timer(tiempofuera, self.matar)
            self._timer.start()

    def leer_proc_stdout(self, num_bytes):
        """
        Lea ``num_bytes`` del stdout del proceso en ejecución.

        :param int num_bytes: Número máximo de bytes para leer.

        :returns: Un objeto cadena/bytes.

        .. versionadded:: 1.0
        """
        raise NotImplementedError

    def leer_proc_stderr(self, num_bytes):
        """
        Leer ``num_bytes`` del stream stderr del proceso(s) en ejecución

        :param int num_bytes: Número máximo de bytes para leer.

        :returns: Un objeto cadena/bytes.

        .. versionadded:: 1.0
        """
        raise NotImplementedError

    def _escribir_proc_stdin(self, datos):
        """
        Escriba ``datos`` en el proceso(s) en ejecución stdin.

        Esto nunca debe llamarse directamente; es para que las subclases
        implementen. Consulte `escribir_proc_stdin` para llamar la API 
        pública.

        :param datos: Datos de bytes ya codificados aptos para escritura.

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        raise NotImplementedError

    def cerrar_proc_stdin(self):
        """
        Cierre el proceso en ejecución 'stdin.

        :returns: ``None``.

        .. versionadded:: 1.3
        """
        raise NotImplementedError

    def codificacion_por_defecto(self):
        """
        Devuelve una cadena que nombra la codificación esperada de los 
        subprocesos.

        Este valor de retorno debe ser adecuado para su uso por métodos de
        codificación/decodificación.

        .. versionadded:: 1.0
        """
        # TODO: probablemente quiera ser 2 métodos, uno para local y otro 
        # para subproceso. Por ahora, es suficiente asumir que ambos son iguales.
        return codificacion_por_defecto()

    def enviar_interrupcion(self, interrumpir):
        """
        Envíe una señal de interrupción al subproceso en ejecución.

        En casi todas las implementaciones, el comportamiento predeterminado
        es el que se desea: enviar ``\x03`` a la tuberia de subproceso(s)
        stdin. Sin embargo, dejamos esto como un método público en caso de que
        sea necesario aumentar o reemplazar este valor predeterminado.

        :param interrumpir:
            El ``KeyboardInterrupt`` de origen local que provoca el método llamar.

        :returns: ``None``.

        .. versionadded:: 1.0
        """
        self.escribir_proc_stdin(u"\x03")

    def cod_de_retorno(self):
        """
        Devuelve el código numérico de retorno/salida resultante de la 
        ejecución del comando.

        :returns: `int`

        .. versionadded:: 1.0
        """
        raise NotImplementedError

    def parar(self):
        """
        Realice la limpieza final, si es necesario.

        Este método se llama dentro de una cláusula ``finalmente`` dentro del
        método principal `correr`. Dependiendo de la subclase, puede ser una
        operación no operativa o puede hacer cosas como cerrar conexiones de
        red o abrir archivos.

        :returns: ``None``

        .. versionadded:: 1.0
        """
        raise NotImplementedError

    def parar_el_temporizador(self):
        """
        Cancelar un temporizador de tiempofuera abierto, si es necesario.
        """
        # TODO 2.0: combinar con parar() (es decir, hacer parar() algo que los
        # usuarios extiendan y llamar a super(), en lugar de anularlo por
        # completo, luego simplemente mueva esto a la implementación 
        # predeterminada de parar().
        if self._timer:
            self._timer.cancel()

    def matar(self):
        """
        Terminar forzosamente el subproceso.

        Normalmente solo lo utiliza la funcionalidad tiempofuera.

        Suele ser un intento de "mejor esfuerzo", p. Ej. Los subprocesos
        remotos a menudo deben conformarse con simplemente apagar el lado
        local de la conexión de red y esperar que el extremo remoto finalmente
        reciba el mensaje.
        """
        raise NotImplementedError

    @property
    def tiempo_fuera(self):
        """
        Devuelve ``True`` si el subproceso se detuvo porque se agotó el 
        tiempo de espera.

        .. versionadded:: 1.3
        """
        # La expiración del temporizador implica que hicimos el tiempo de
        # espera. (El temporizador en sí habrá matado el subproceso, 
        # permitiéndonos incluso llegar a este punto).
        return self._timer and not self._timer.is_alive()


class Local(Corredor):
    """
    Ejecute un comando en el sistema local en un subproceso.

    .. note::
        Cuando Dued en sí se ejecuta sin una terminal de control (por ejemplo,
        cuando ``sys.stdin`` carece de un ``fileno`` útil), no es posible
        presentar un identificador en nuestro PTY a los subprocesos locales.
        En tales situaciones, `Local` volverá a comportarse como si 
        ``pty=False`` (en la teoría de que la ejecución degradada es mejor que
        ninguna), además de imprimir una advertencia en stderr.

        Para deshabilitar este comportamiento, diga ``retroceder=False``.

    .. versionadded:: 1.0
    """

    def __init__(self, contexto):
        super(Local, self).__init__(contexto)
        # Variable de contabilidad para el caso de uso de pty
        self.status = None

    def deberia_usar_pty(self, pty=False, retroceder=True):
        usar_pty = False
        if pty:
            usar_pty = True
            # TODO: pasa & prueba ing_stream, no sys.stdin
            if not tiene_fileno(sys.stdin) and retroceder:
                if not self.aviso_sobre_repligue_pty:
                    err = "ADVERTENCIA: stdin no tiene fileno; recurriendo a una ejecución no pty!\n"  # noqa
                    sys.stderr.write(err)
                    self.aviso_sobre_repligue_pty = True
                usar_pty = False
        return usar_pty

    def leer_proc_stdout(self, num_bytes):
        # Obtenga la función útil de lectura de algunos bytes
        if self.usando_pty:
            # Necesidad de manejar errores de SO falsos en algunas plataformas
            # Linux.
            try:
                datos = os.read(self.parent_fd, num_bytes)
            except OSError as e:
                # Solo come OSError'es específicos de IO para no ocultar otros
                stringified = str(e)
                io_errors = (
                    # El típico defecto
                    "Entrada/salida error",
                    # Algunas plataformas menos comunes lo expresan de esta manera
                    "I/O error",
                )
                if not any(error in stringified for error in io_errors):
                    raise
                # Los OSErrors incorrectos ocurren después de que han aparecido
                # todas las salidas esperadas, por lo que devolvemos un valor
                #  falso, que activa la lógica de "fin de salida" en el código
                #  usando funciones de lector.
                datos = None
        else:
            datos = os.read(self.process.stdout.fileno(), num_bytes)
        return datos

    def leer_proc_stderr(self, num_bytes):
        # NOTE: cuando se usa un pty, nunca se llamará.
        # TODO: ¿alguna vez obtenemos esos OSErrors en stderr? 
        # ¿Se siente como si pudiéramos?
        return os.read(self.process.stderr.fileno(), num_bytes)

    def _escribir_proc_stdin(self, datos):
        # NOTE: parent_fd de os.fork() es una tubería de lectura/escritura 
        # adjunta a nuestro proceso bifurcado 'stdout / stdin, respectivamente.
        fd = self.parent_fd if self.usando_pty else self.process.stdin.fileno()
        # Intente escribir, ignorando las tuberías rotas si se encuentran 
        # (implica que el proceso hijo salió antes de que terminara la tubería 
        # del proceso; no hay nada que podamos hacer al respecto).
        try:
            return os.write(fd, datos)
        except OSError as e:
            if "Tuberia rota" not in str(e):
                raise

    def cerrar_proc_stdin(self):
        if self.usando_pty:
            # no hay un escenario de trabajo para decirle al proceso que
            # está incluido cuando se usa pty
            raise ErrorEnTuberiaDeSubP("No se puede cerrar stdin cuando pty=True")
        self.process.stdin.close()

    def iniciar(self, comando, shell, entorno):
        if self.usando_pty:
            if pty is None:  # Encountered ImportError
                err = "¡Indicó pty=True, pero su plataforma no es compatible con el módulo 'pty'!"  # noqa
                sys.exit(err)
            columnas, filas = pty_dimension()
            self.pid, self.parent_fd = pty.fork()
            # Si somos el proceso hijo, cargue el comando real en un shell, tal
            # como lo hace el subproceso; esto reemplaza nuestro proceso, cuyas
            # tuberías están todas conectadas al PTY, por el "real".
            if self.pid == 0:
                # TODO: both pty.spawn() and pexpect.spawn() do a lot of
                # setup/desmontaje involving tty.setraw, getrlimit, signal.
                # Ostensibly we'll want some of that eventually, but if
                # possible write pruebas - integration-level if necessary -
                # before adding it!
                #
                # Set pty window size based on what our own controlling
                # terminal's window size appears to be.
                # TODO: make subroutine?
                # TODO: tanto pty.spawn() como pexpect.spawn() realizan muchas
                # configuraciones/desmontajes que involucran tty.setraw, getrlimit,
                # signal. Aparentemente, eventualmente querremos algo de eso, pero
                # si es posible, escriba pruebas (nivel de integración si es 
                # necesario) antes de agregarlo.
                #
                # Establezca el tamaño de la ventana pty según lo que parezca
                # ser el tamaño de la ventana de nuestra propia terminal de control.
                # TODO: hacer subrutina?
                winsize = struct.pack("HHHH", filas, columnas, 0, 0)
                fcntl.ioctl(sys.stdout.fileno(), termios.TIOCSWINSZ, winsize)
                # Utilice execve para un comportamiento mínimo "exec con 
                # variable # args + entorno". No es necesario la 'p' (use PATH
                # para encontrar el ejecutable) por ahora.
                # NOTE: el subproceso stdlib (en realidad su sabor posix, que está
                # escrito en C) usa execve o execv, dependiendo.
                os.execve(shell, [shell, "-c", comando], entorno)
        else:
            self.process = Popen(
                comando,
                shell=True,
                executable=shell,
                env=entorno,
                stdout=PIPE,
                stderr=PIPE,
                stdin=PIPE,
            )

    def matar(self):
        pid = self.pid if self.usando_pty else self.process.pid
        os.kill(pid, signal.SIGKILL)

    @property
    def proceso_esta_terminado(self):
        if self.usando_pty:
            # NOTE:
            # https://github.com/pexpect/ptyprocess/blob/4058faa05e2940662ab6da1330aa0586c6f9cd9c/ptyprocess/ptyprocess.py#L680-L687
            # implica que Linux "requiere" el uso de la versión de bloqueo, 
            # no-WNOHANG, de este llamado. Sin embargo, nuestras pruebas no
            # verifican esto, así que ...
            # NOTE: Parece que se bloquea totalmente en Windows, por lo que 
            # nuestro problema # 351 puede ser totalmente irresoluble allí. Poco claro.
            pid_val, self.status = os.waitpid(self.pid, os.WNOHANG)
            return pid_val != 0
        else:
            return self.process.poll() is not None

    def cod_de_retorno(self):
        if self.usando_pty:
            # No hay subprocess.cod_de_retorno disponible; utilice 
            # WIFEXITED/WIFSIGNALED para determinar qué de WEXITSTATUS/WTERMSIG
            # utilizar.
            # TODO: ¿es seguro simplemente decir "llamar a todos WEXITSTATUS/WTERMSIG
            # y devolver el que no sea predeterminado"? ¿Probablemente no?
            # NOTE: hacer esto en un orden arbitrario debería ser seguro ya que
            # solo uno de los métodos WIF * debería devolver True.
            
            code = None
            if os.WIFEXITED(self.status):
                code = os.WEXITSTATUS(self.status)
            elif os.WIFSIGNALED(self.status):
                code = os.WTERMSIG(self.status)
                # Haga coincidir subprocess.cod_de_retorno convirtiendo las señales
                # en números enteros negativos de 'código de salida'.
                code = -1 * code
            return code
            # TODO: ¿nos preocupamos por WIFSTOPPED? ¿Tal vez algún día?
        else:
            return self.process.returncode

    def parar(self):
        # Si abrimos un PTY para comunicaciones secundarias, asegúrese de 
        # cerrarlo(); de lo contrario, los procesos de larga ejecución que
        # utilizan Dued agotan sus descriptores de archivo eventualmente.
        if self.usando_pty:
            try:
                os.close(self.parent_fd)
            except Exception:
                # Si sucedió algo extraño que impidió el cierre, no hay nada
                #  que hacer al respecto ahora ...
                pass


class Resultado(object):
    """
    Un contenedor de información sobre el resultado de la ejecución de un comando.

    Todos los parámetros se exponen como atributos del mismo nombre y tipo.

    :param str stdout:
        Los subproceso(s) estándar de salida.

    :param str stderr:
        Igual que ``stdout`` pero contiene un error estándar (a menos que el
        proceso se haya invocado mediante un pty, en cuyo caso estará vacío;
        consulte `.Corredor.correr`).

    :param str codificacion:
        La codificación de cadenas utilizada por el entorno de shell local.

    :param str comando:
        El comando que fue ejecutado.

    :param str shell:                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              
        El binario de shell utilizado para la ejecución.

    :param dict entorno:
        El entorno de shell utilizado para la ejecución. (El valor por defecto
        es el dicc vacío, ``{}``, no ``None`` como se muestra en la firma).

    :param int salida:
        Un entero que representa el código de salida/retorno del subproceso.

        .. note::
            Esto puede ser ``None`` en situaciones en las que el subproceso no
            se ejecutó hasta su finalización, como cuando la respuesta 
            automática falló o se alcanzó un tiempo fuera.

    :param bool pty:
        Un booleano que describe si el subproceso se invocó con un pty o no;
        ver `.Corredor.correr`.

    :param tuple ocultar:
        Una tupla de nombres de stream (ninguno, uno o ambos de 
        ``('stdout', 'stderr')`` que estaban ocultos al usuario cuando se 
        ejecutó el comando de generación; este es un valor normalizado 
        derivado del parámetro ``ocultar`` de `.Corredor.correr`.

        Por ejemplo, ``correr('comando', ocultar='stdout')`` producirá un
        `Resultado` donde ``resultado.ocultar == ('stdout',)``; 
        ``ocultar=True`` o ``ocultar='ambos'`` da como resultado
        ``resultado.ocultar == ('stdout', 'stderr')``; y ``ocultar=False``
        (el default) genera ``resultado.ocultar == ()`` (la tupla vacía).

    .. note::
        La evaluación de la verdad de los objetos `Resultado` es equivalente
        al valor de su atributo `.ok`. Por lo tanto, son posibles expresiones
        rápidas y sucias como las siguientes::

            if correr("algun comando shell"):
                do_algo()
            else:
                handle_problem()

        Sin embargo, recuerda `Zen de Python #2
        <http://zen-of-python.info/explicit-is-better-than-implicit.html#2>`_.

    .. versionadded:: 1.0
    """

    # TODO: heredar de namedtuple en su lugar? heh (o: usa attrs de pypi)
    def __init__(
        self,
        stdout="",
        stderr="",
        codificacion=None,
        comando="",
        shell="",
        entorno=None,
        salida=0,
        pty=False,
        ocultar=tuple(),
    ):
        self.stdout = stdout
        self.stderr = stderr
        if codificacion is None:
            codificacion = codificacion_por_defecto()
        self.codificacion = codificacion
        self.comando = comando
        self.shell = shell
        self.entorno = {} if entorno is None else entorno
        self.salida = salida
        self.pty = pty
        self.ocultar = ocultar

    @property
    def codigo_devuelto(self):
        """
        Un alias para ``.salida``.

        .. versionadded:: 1.0
        """
        return self.salida

    def __nonzero__(self):
        # NOTE: Este es el método que (en Python 2) determina el comportamiento
        # booleano de los objetos.
        return self.ok

    def __bool__(self):
        # NOTE: Y este es el equivalente en Python 3 de __nonzero__. un nombre
        # Mucho mejor ...
        return self.__nonzero__()

    def __str__(self):
        if self.salida is not None:
            desc = "Comando salido con estatus {}.".format(self.salida)
        else:
            desc = "El comando no se ejecutó completamente debido a un error de centinela."
        ret = [desc]
        for x in ("stdout", "stderr"):
            val = getattr(self, x)
            ret.append(
                u"""=== {} ===
{}
""".format(
                    x, val.rstrip()
                )
                if val
                else u"(no {})".format(x)
            )
        return u"\n".join(ret)

    def __repr__(self):
        # TODO: ¿Hacer más? p.ej. len de stdout/err? (¿Cómo representar 
        # limpiamente en un formato 'x = y' como este? Por ejemplo, '4b' es
        # ambiguo en cuanto a lo que representa
        plantilla = "<Resultado cmd={!r} salida={}>"
        return plantilla.format(self.comando, self.salida)

    @property
    def ok(self):
        """
        Un equivalente booleano a ``salida == 0``.

        .. versionadded:: 1.0
        """
        return self.salida == 0

    @property
    def failed(self):
        """
        El inverso de ``ok``.

        I.e., ``True`` if the programa exited with a nonzero return code, and
        ``False`` otherwise.
        Es decir, ``True`` si el programa salió con un código de retorno
        distinto de cero y ``False`` en caso contrario.

        .. versionadded:: 1.0
        """
        return not self.ok

    def cola(self, stream, contar=10):
        """
        Devuelve las últimas líneas (cola) de ``contar`` de ``stream``, 
        más los espacios en blanco iniciales.

        :param str stream:
            Nombre de algún atributo de flujo capturado, 
            por ejemplo, ``"stdout"``.

        :param int contar:
            Número de líneas a conservar.

        .. versionadded:: 1.3
        """
        # TODO: ¿conservar finales de línea alternativos? Mehhhh
        # NOTE: sin conservación \n final; más fácil para la pantalla
        # inferior si está normalizado
        texto = "\n\n" + "\n".join(getattr(self, stream).splitlines()[-contar:])
        return codificar_salida(texto, self.codificacion)


class Promesa(Resultado):
    """
    Una promesa de algún "Resultado" futuro, producto de una ejecución
    asincrono.

    El miembro principal de la API de esta clase es "join"; Las instancias
    también se pueden usar como administradores de contexto, que llamarán
    automáticamente `join` cuando el bloque salga. En tales casos, el 
    administrador de contexto cede el ``yo``.

    `Promesa` también expone copias de muchos atributos de `Resultado`,
    específicamente aquellos que derivan de kwargs `~Corredor.correr`
    y no el resultado de la ejecución del comando. Por ejemplo, aquí
    se replica ``comando``, pero no ``stdout``.

    .. versionadded:: 1.4
    """

    def __init__(self, corredor):
        """
        Crea una nueva promesa.

        :param corredor:
            Una instancia en-vuelo del `Corredor` que hace esta promesa.

            Ya debe haber iniciado el subproceso y haber generado subprocesos
            de E/S (IO).
        """
        self.corredor = corredor
        # Básicamente solo quiero exactamente este (recientemente 
        # refactorizado) dict de kwargs.
        # TODO: considere usar proxy frente a copiar, pero probablemente
        # espere a que se refactorice
        for key, valor in self.corredor.kwargs_resultado.items():
            setattr(self, key, valor)

    def join(self):
        """
        Bloquear hasta que salga el subproceso asociado, devolviendo/elevando
        el resultado.

        Esto actúa de manera idéntica al final de un ``correr`` ejecutado
        sincrónicamente, es decir que:

         - se unen varios subprocesos en segundo plano (como los workers de
           IO);
         - si el subproceso salió normalmente, se devuelve un `Resultado`;
         - en cualquier otro caso (excepciones imprevistas, subproceso IO
           `.ExcepcionDeHilo` , `.Falla`, `.ErrorDeCentinela`) aquí se 
           plantea la excepción relevante.

        Consulte los documentos `~ Corredor.correr`, o los de las clases 
        relevantes, para obtener más detalles.
        """
        try:
            return self.corredor._terminar()
        finally:
            self.corredor._parar_todo()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.join()


def normalizar_ocultar(val, sal_stream=None, err_stream=None):
    # Normalizar a lista-de-nombres-de-flujo
    vals_ocultos = (None, False, "salida", "stdout", "err", "stderr", "ambos", True)
    if val not in vals_ocultos:
        err = "'ocultar' tiene {!r} que no esta en {!r}"
        raise ValueError(err.format(val, vals_ocultos))
    if val in (None, False):
        ocultar = []
    elif val in ("ambos", True):
        ocultar = ["stdout", "stderr"]
    elif val == "salida":
        ocultar = ["stdout"]
    elif val == "err":
        ocultar = ["stderr"]
    else:
        ocultar = [val]
    # Revertir cualquier flujo que se haya anulado del valor predeterminado
    if sal_stream is not None and "stdout" in ocultar:
        ocultar.remove("stdout")
    if err_stream is not None and "stderr" in ocultar:
        ocultar.remove("stderr")
    return tuple(ocultar)


def codificacion_por_defecto():
    """
    Obtener codificación de texto por defecto del intérprete-local aparente.

    A menudo se usa como línea de base en situaciones en las que debemos usar
    ALGUNA codificación para bytes desconocidos pero presumiblemente de texto,
    y el usuario no ha especificado una anulación.
    """
    # Según algunos experimentos, existe un problema con
    # `locale.getpreferredencoding(do_setlocale=False)` en Python 2.x en Linux
    # y OS X, y `locale.getpreferredencoding (do_setlocale = True)` 
    # desencadena algunos cambios de estado global. (Ver # 274 para discusión).
    codificacion = locale.getpreferredencoding(False)
    if six.PY2 and not WINDOWS:
        default = locale.getdefaultlocale()[1]
        if default is not None:
            codificacion = default
    return codificacion
