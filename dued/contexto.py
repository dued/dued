import os
import re
from contextlib import contextmanager

try:
    from dued.vendor.six import raise_from, iteritems
except ImportError:
    from six import raise_from, iteritems

from .config import Config, DataProxy
from .excepciones import Falla, FallaAutenticacion, RespuestaNoAceptada
from .corredores import Resultado
from .centinelas import DetectorDeRespuestasIncorrectas


class Contexto(DataProxy):
    """
    Contexto API contenedor y objeto de paso de estado.

    Los objetos `.Contexto` se crean durante el análisis de la línea de 
    comandos (o, si se desea, a mano) y se utilizan para compartir el estado 
    de análisis y configuración con artefactos ejecutados 
    (ver :ref:`porque-contexto`).

    Específicamente, la clase ofrece envoltorios para llamadas de API 
    centrales(como `.correr`) que toman en cuenta las banderas del analizador
    CLI, archivos de configuración y/o cambios realizados en tiempo de 
    ejecución. También actúa como un proxy para su atributo 
    `~.Contexto.config`; consulte la documentación de ese atributo para
    obtener más detalles.

    Las instancias de `.Contexto` pueden ser compartidas entre artefactos al
    ejecutar sub-artefactos - ya sea el mismo contexto que se le dio al 
    llamador, o una copia alterada del mismo (o, teóricamente, uno nuevo).

    .. versionadded:: 1.0
    """

    def __init__(self, config=None):
        """
        :param config:
            `.Config` objeto para utilizar como configuración base.

            Por defecto es una instancia anónima/predeterminada ".Config".
        """
        #: El objeto `.Config` completamente fusionado apropiado para este contexto.
        #:
        #: Se puede acceder a la configuración de `.Config` (consulte su 
        #: documentación para obtener más detalles) como claves de diccionario 
        #:  (``c.config['foo']``) o atributos de objeto (``c.config.foo``).
        #:
        #: Como forma abreviada de conveniencia, el objeto `.Contexto` se convierte 
        #: en proxy de su atributo ``config`` de la misma manera, p. Ej. c['foo'] o
        #:  ``c.foo`` devuelve el mismo valor que ``c.config['foo']``.
        config = config if config is not None else Config()
        self._set(_config=config)
        #: Una lista de comandos para ejecutar (a través de "&&") antes del argumento
        #: principal de cualquier llamada a `correr` o `sudo`. Tenga en cuenta que
        #: la API principal para manipular esta lista es "prefijo"; consulte sus
        #:  documentos para obtener más detalles.
        prefijos_de_comando = list()
        self._set(prefijos_de_comando=prefijos_de_comando)
        #: Una lista de directorios en los que 'cd' antes de ejecutar comandos con
        #: `correr` o `sudo`; destinado a la gestión a través de 'cd', consulte sus
        #: documentos para obtener más detalles.
        comando_cwds = list()
        self._set(comando_cwds=comando_cwds)

    @property
    def config(self):
        # Permite que Contexto exponga un atributo .config aunque DataProxy lo considere
        # una clave de configuración.
        return self._config

    @config.setter
    def config(self, valor):
        # NOTE: utilizado principalmente por bibliotecas cliente que necesitan 
        # modificar la configuración de un Contexto en tiempo de ejecución; es 
        # decir, una subclase de Contexto que tiene sus propios datos únicos 
        # puede querer estar parada al parametrizar/expandir una lista de 
        # llamadas al inicio de una sesión, con la configuración final 
        # completada en tiempo de ejecución.
        self._set(_config=valor)

    def correr(self, comando, **kwargs):
        """
        Ejecute un comando de shell local, respetando las opciones de config.

        Específicamente, este método crea una instancia de una subclase 
        `.Corredor` (de acuerdo con la opción de configuración ``corredor``; 
        el predeterminado es `.Local`) y llama a su método ``.correr`` con 
        ``comando``  y ``kwargs``.

        Consulte `.Corredor.correr` para obtener detalles sobre ``comando`` y
        los argumentos de palabras clave disponibles.

        .. versionadded:: 1.0
        """
        corredor = self.config.corredores.local(self)
        return self._corre(corredor, comando, **kwargs)

    # NOTE: dividido en correr() para permitir la inyección de clases de corredor 
    # en Fabric/etc, que necesita hacer malabares con múltiples tipos de clases
    # de corredor (local y remoto).
    def _corre(self, corredor, comando, **kwargs):
        comando = self._comandos_de_prefijo(comando)
        return corredor.correr(comando, **kwargs)

    def sudo(self, comando, **kwargs):
        """
        Ejecute un comando de shell a través de ``sudo`` con respuesta 
        automática de contraseña.

        **Lo esencial**

        Este método es idéntico a `correr` pero agrega un puñado de 
        comportamientos convenientes para invocar el programa ``sudo``. No
        hace nada que los usuarios no puedan hacer ellos mismos envolviendo
        `correr`, pero el caso de uso es demasiado común para hacer que los
        usuarios reinventen estas ruedas.

        .. note::
            Si tiene la intención de responder manualmente a la solicitud de
            contraseña de sudo, simplemente use ``correr ("comando sudo")``
            en su lugar! Las funciones de respuesta automática de este método
            se interpondrán en su camino.

        Específicamente, `sudo`:

        * Coloca un `.DetectorDeRespuestasIncorrectas` en kwarg ``centinelas``
        ver :doc:`/concepts/centinelas`) que:

            * busca la solicitud de contraseña configurada ``sudo``;
            * responde con la contraseña sudo configurada (``sudo.password``
              de :doc: `configuración </conceptos/configuración>`);
            * puede decir cuándo esa respuesta causa una falla de 
              autenticación (por ejemplo, si el sistema requiere una 
              contraseña y no se configuró una), y genera una 
              `.FallaAutenticacion` si es así.

        * Construye una cadena de comando ``sudo`` usando el argumento 
          ``comando`` provisto, precedido por varios indicadores (ver más
          abajo);
        * Ejecuta ese comando a través de una llamada a `correr`, devolviendo
          el resultado.

        **Banderas utilizadas**

        ``sudo`` utiliza banderas debajo del capó que incluyen::

        - ``-S`` para permitir la respuesta automática de la contraseña a
          través de stdin;
          para indicar explícitamente el mensaje que se debe usar, de modo que
          podamos asegurar de que nuestro auto-Respondedor sabe qué buscar
        - ``-u <usuario>`` si ``usuario`` no es ``None``, ejecuta el comando
          distinto de ``raiz``
        - Cuando ``-u`` está presente, también se agrega ``-H``, p' garantizar
          que el subproceso tenga el ``$HOME`` del usuario solicitado 
          configurado correctamente.

        **Configurar comportamiento**

        Hay un par de formas de cambiar el comportamiento de este método:

        - Debido a que envuelve `correr`, respeta todos los parámetros de 
          config y argumentos de palabras clave de `correr`, de la misma 
          manera que lo hace `correr`.

            - Por lo tanto, invocaciones como ``c.sudo('comando', echo=True)``
              son posibles, y si una capa de configuración (como un archivo de
              configuración o una var entorno) especifica que, p. ej. 
              ``correr.alarma = True``, eso también tendrá efecto en `sudo`.

         - `sudo` tiene su propio conjunto de argumentos de palabras clave 
           (ver más abajo) y también son controlables a través del sistema de
           configuración, bajo el árbol ``sudo.*``.

            - Por lo tanto, podría, por ejemplo, preestablecer un usuario sudo
              en un archivo de configuración; como un ``dued.json`` que 
              contenga ``{"sudo": {"usuario": "someuser"}}``.

        :param str password: Anulación del Tiempoej para ``sudo.password``.
        :param str usuario: Anulación del Tiempoej para ``sudo.usuario``.

        .. versionadded:: 1.0
        """
        corredor = self.config.corredores.local(self)
        return self._sudo(corredor, comando, **kwargs)

    # NOTE: esto es para inyección corredor; vea la NOTA arriba de _corre().
    def _sudo(self, corredor, comando, **kwargs):
        prompt = self.config.sudo.prompt
        password = kwargs.pop("password", self.config.sudo.password)
        usuario = kwargs.pop("usuario", self.config.sudo.usuario)
        # TODO: permitir subclases para 'obtener la contraseña' para que los
        # usuarios que REALMENTE quieran mensajes perezosos de tiempoej puedan
        # implementarlo fácilmente.
        # TODO: desea imprimir un echo "más limpio" con solo 'sudo <comando>';
        # pero es difícil de hacer como está, obtener datos de configuración desde
        # fuera de un Corredor que uno tiene actualmente es complicado (podría
        # solucionarlo), si en su lugar inspeccionamos manualmente la 
        # configuración que duplica la lógica. NOTE: una vez que nos damos cuenta
        # de eso, hay una prueba existente que fallaría-si-no-se-omite para este
        # comportamiento en prueba/contexto.py.
        # TODO: una vez hecho esto, sin embargo: ¿cómo manejar la salida de 
        # "depuración completa" exactamente (visualización del comando sudo completo
        # real, w/ -S y -p), en términos de API / config? Impl es fácil, solo vuelve
        # a pasar echo a 'correr' ...
        user_banderas = ""
        if usuario is not None:
            user_banderas = "-H -u {} ".format(usuario)
        comando = self._comandos_de_prefijo(comando)
        cadena_cmd = "sudo -S -p '{}' {}{}".format(prompt, user_banderas, comando)
        centinela = DetectorDeRespuestasIncorrectas(
            patron=re.escape(prompt),
            respuesta="{}\n".format(password),
            centinela="Perdón intente de nuevo.\n",
        )
        # Asegúrese de combinar cualquier centinelas especificado-por-ususario
        # con el nuestro.
        # NOTE: Si hay centinelas controladas-por-configuración, los subimos al
        # nivel kwarg; que nos permite combinar limpiamente sin necesidad de una
        # semántica compleja basada en configuraciones de "anulación vs fusión".
        # TODO: si/cuando se implemente esa semántica, úsela en su lugar.
        # NOTE: el valor de config para centinelas por defecto es una lista vacía;
        # y queremos clonarlo para evitar mutar realmente la configuración.
        centinelas = kwargs.pop("centinelas", list(self.config.correr.centinelas))
        centinelas.agregar(centinela)
        try:
            return corredor.correr(cadena_cmd, centinelas=centinelas, **kwargs)
        except Falla as falla:
            # Transmutar fallas producidas por nuestro detectorDeRespuestasIncorrectas, 
            # en auth
            # fallos: el comando ni siquiera se ejecutó.
            # TODO: quiere ser un gancho aquí para los usuarios que desean "anular un valor
            # de config incorrecto para sudo.password" entrada manual
            # NOTE: como se indica en los comentarios # 294, PODRÍAMOS que en el futuro 
            # deseemos actualizar esto para que correr() tenga la capacidad de generar
            # FallaAutenticacion por sí solo.
            # Por ahora eso se ha juzgado como una complejidad innecesaria.
            if isinstance(falla.motivo, RespuestaNoAceptada):
                # NOTE: no preocuparse por la 'razón' aquí, no tiene sentido.
                # NOTE: usar raise_from (..., None) para suprimir la salida "útil" de 
                # múltiples excepciones de Python 3. Es confuso aquí.
                error = FallaAutenticacion(resultado=falla.resultado, prompt=prompt)
                raise_from(error, None)
            # Vuelva a levantar por cualquier otro error para que corra normalmente.
            else:
                raise

    # TODO: me pregunto si tiene sentido mover esta parte de las cosas dentro de
    # Corredor, lo que haría crecer un `prefijos` y `cwd` init kwargs o similar.
    # Cuanto menos esté metido en Contexto, probablemente mejor.
    def _comandos_de_prefijo(self, comando):
        """
        Prefijos de ``comando`` con todos los prefijos que se encuentran en
        ``prefijos_de_comando``.

        ``prefijos_de_comando`` es una lista de cadenas que es modificada por
        el administrador de contexto `prefijo`.
        """
        prefijos = list(self.prefijos_de_comando)
        dir_actual = self.cwd
        if dir_actual:
            prefijos.insert(0, "cd {}".format(dir_actual))

        return " && ".join(prefijos + [comando])

    @contextmanager
    def prefijo(self, comando):
        """
        Prefije todos los comandos anidados `correr`/` sudo` con el comando
        dado más ``&&``.

        La mayoría de veces, querrá usar esto junto con un script de shell
        que altera el estado del shell, como los que exportan o alteran las
        variables de entorno del shell.

        Por ejemplo, uno de los usos más comunes de esta herramienta es con el
        comando ``workon`` comando `virtualenvwrapper
        <https://virtualenvwrapper.readthedocs.io/en/latest/>`_::

            with c.prefijo('workon mienv'):
                c.correr('./admin.py migrar')

        En el fragmento anterior, el comando correr del shell real sería 
        este::

            $ workon mienv && ./admin.py migrar

        Este administrador de contexto es compatible con `cd`, por lo que si 
        su virtualenv no tiene ``cd`` en su script ``postactivate``, 
        puede hacer lo siguiente::

            with c.cd('/ruta/a/mi/app'):
                with c.prefijo('workon mienv'):
                    c.correr('./admin.py migrar')
                    c.correr('./admin.py cargardatos ensayo')

        Lo que daría lugar a ejecuciones como esta::

            $ cd /ruta/a/mi/app && workon mienv && ./admin.py migrar
            $ cd /ruta/a/mi/app && workon mienv && ./admin.py cargardatos ensayo

        Finalmente, como se mencionó anteriormente, `prefijo` se puede anidar
        si se desea, por ejemplo::

            with c.prefijo('workon mienv'):
                c.correr('ls')
                with c.prefijo('source /algunos/script'):
                    c.correr('touch un_archivo')

        El resultado::

            $ workon myenv && ls
            $ workon myenv && source /algunos/script && touch un_archivo

        Artificial, pero espero que sea ilustrativo.

        .. versionadded:: 1.0
        """
        self.prefijos_de_comando.agregar(comando)
        try:
            yield
        finally:
            self.prefijos_de_comando.pop()

    @property
    def cwd(self):
        """
        Devuelve el dir actual de trabajo, teniendo en cuenta el uso de `cd`.

        .. versionadded:: 1.0
        """
        if not self.comando_cwds:
            # TODO: ¿debería ser Ninguno? Se siente más limpio, aunque puede haber
            # beneficios al ser una cadena vacía, como confiar en un `cd` sin
            # argumentos que normalmente es la abreviatura de "ir al user $HOME".
            return ""

        # obtener el índice para el subconjunto de rutas que comienzan con el último / o ~
        for i, ruta in reversed(list(enumerate(self.comando_cwds))):
            if ruta.startswith("~") or ruta.startswith("/"):
                break

        # TODO: ver si hay una función "escapar de esta ruta" más fuerte en algún
        # lugar que podamos reutilizar. por ejemplo, escapar de tildes o barras en
        # los nombres de archivo.
        rutas = [ruta.replace(" ", r"\ ") for ruta in self.comando_cwds[i:]]
        return os.path.join(*rutas)

    @contextmanager
    def cd(self, ruta):
        """
        Administrador de contexto que mantiene el estado del directorio al
        ejecutar comandos.

        Cualquier llamada a `correr`,`sudo`, dentro del bloque encapsulado
        tendrá implícitamente una cadena similar a ``"cd <ruta> &&"`` 
        prefijada para dar la sensación de que realmente hay estado envuelto.

        Dado que el uso de `cd` afecta a todas estas invocaciones, cualquier
        código que haga uso de la propiedad `cwd` también se verá afectado
        por el uso de `cd`.

        Al igual que el intérprete de shell 'cd' real, se puede llamar a `cd`
        con rutas relativas (tenga en cuenta que su directorio de inicio 
        predeterminado es el ``$ HOME`` de su usuario) y también se puede 
        anidar.

        A continuación se muestra un intento "normal" de usar el shell 'cd',
        que no funciona ya que todos los comandos se ejecutan en subprocesos
        individuales; -- el estado **no** se mantiene entre las invocaciones
        de `correr` o `sudo` ::

            c.correr('cd /var/www')
            c.correr('ls')

        El fragmento anterior enumerará el contenido del usuario ``$ HOME`` en
        lugar de ``/var/www`` Con `cd`, sin embargo, funcionará como se 
        esperaba::

            with c.cd('/var/www'):
                c.correr('ls')  # Se convierte en "cd /var/www && ls"

        Finalmente, una demostración (ver comentarios en línea) de 
        anidamiento::

            with c.cd('/var/www'):
                c.correr('ls') # cd /var/www && ls
                with c.cd('website1'):
                    c.correr('ls')  # cd /var/www/website1 && ls

        .. note::
            Los caracteres de espacio se escaparán automáticamente para 
            facilitar el manejo de dichos nombres de directorio.

        .. versionadded:: 1.0
        """
        self.comando_cwds.agregar(ruta)
        try:
            yield
        finally:
            self.comando_cwds.pop()


class ContextoSimulado(Contexto):
    """
    Un `.Contexto` cuyos valores de retorno de métodos pueden ser
    predeterminados.

    Principalmente útil para probar bases de código que utilizan Dued..

    .. note::
        Los métodos no dados a `Resultado <.Resultado>` para ceder generarán 
        ``NotImplementedError`` si se llaman (ya que la alternativa es llamar
        al método subyacente real, generalmente indeseable cuando se hace una
        burla).

        .. versionadded:: 1.0
    """

    def __init__(self, config=None, **kwargs):
        """
        Cree un objeto similar a un ``Contexto``-cuyos métodos produzcan 
        objetos `.Resultado`.

        :param config:
            Un objeto de configuración para usar. Idéntico en comportamiento a
            `.Contexto`.

        :param correr:
            Una estructura de datos de `Resultados <.Resultado>`, para retorono
            de las llamadas al método `~.Contexto.correr` del objeto
            instanciado (en lugar de ejecutar realmente el comando de shell 
            solicitado).

            Específicamente, este kwarg acepta:

            - A single `.Resultado` object, which will be returned once.
            - An iterable of `Results <.Resultado>`, which will be returned on
              each subsequent llamar to ``.correr``.
            - A map of comando strings to either of the above, allowing
              specific llamar-and-respuesta semantics instead of assuming a 
              llamar order.
            - Un único objeto `.Resultado`, que se devolverá una vez.
            - Un iterable de `Resultado <.Resultado>`, que se devolverá en 
              cada llamada posterior a ``.correr``.
            - Un mapa de cadenas de comandos para cualquiera de los anteriores,
              lo que permite una semántica específica de llamada y respuesta en
              lugar de asumir un orden de llamada.

        :param sudo:
            Idéntico a ``correr``, pero cuyos valores se obtienen de llamadas a
            `~ .Contexto.sudo`.

        :raises:
            ``TypeError``, si los valores dados a ``correr`` u otros kwargs no
            son objetos o iterables `.Resultado` individuales.
        """
        # TODO: sería bueno permitir regexen en lugar de coincidencias de cadenas exactas
        super(ContextoSimulado, self).__init__(config)
        for method, resultado in iteritems(kwargs):
            # Caso de conveniencia especial: Resultado individual -> lista de un elemento
            if (
                not hasattr(resultado, "__iter__")
                and not isinstance(resultado, Resultado)
                # No es necesario un dicc de prueba explícito; tienen __iter__
            ):
                err = "No estoy seguro de cómo dar resultados de un {!r}"
                raise TypeError(err.format(type(resultado)))
            self._set("__{}".format(method), resultado)

    # TODO: _maybe_ ¿hacer esto más metaprogramado/flexible (usando __call__ etc)?
    # Me preocupa mucho que cause más problemas de depuración de los que vale
    # actualmente. Tal vez en situaciones en las que Contexto desarrolla una
    # cantidad de métodos (por ejemplo, en Fabric 2; aunque Fabric podría hacer
    # su propia sub-subclase en ese caso ...)

    def _resultado_de_rendimiento(self, attname, comando):
        # NOTE: originalmente tenía esto con un montón de explícitos
         # NotImplementedErrors, pero duplicó el tamaño del método y la 
         # posibilidad de errores inesperados de índice / etc. parece baja aquí.
        try:
            valor = getattr(self, attname)
            # TODO: pensé que había un DictType 2x3 'mejor' o w/e, pero no puedo
            # encontrar uno de inmediato
            if isinstance(valor, dict):
                if hasattr(valor[comando], "__iter__"):
                    resultado = valor[comando].pop(0)
                elif isinstance(valor[comando], Resultado):
                    resultado = valor.pop(comando)
            elif hasattr(valor, "__iter__"):
                resultado = valor.pop(0)
            elif isinstance(valor, Resultado):
                resultado = valor
                delattr(self, attname)
            return resultado
        except (AttributeError, IndexError, KeyError):
            raise_from(NotImplementedError, None)

    def correr(self, comando, *args, **kwargs):
        # TODO: ¿realizar más cosas de conveniencia asociando args/kwargs con
        # el resultado? P.ej. rellenando .comando, etc? Posiblemente útil para
        # depurar si uno encuentra problemas de orden inesperado con lo que
        # pasaron a __init__.
        return self._resultado_de_rendimiento("__run", comando)

    def sudo(self, comando, *args, **kwargs):
        # TODO: esto destruye completamente el comportamiento de nivel superior
        # de sudo(), que podría ser bueno o malo, dependiendo. La mayor parte 
        # del tiempo creo que es bueno.
        # No es necesario proporcionar una configuración de contraseña ficticia, etc.
        # TODO: ver el TODO de correr() re: inyectar valores arg/kwarg
        return self._resultado_de_rendimiento("__sudo", comando)

    def set_result_for(self, attname, comando, resultado):
        """
        Modifica los resultados simulados almacenados para un ``attname`` dado
        (por ejemplo, ``correr``).

        Esto es similar a cómo se crea una instancia de `ContextoSimulado` con un dict
        kwarg` `correr` o ``sudo``. Por ejemplo, esto::

            mc = ContextoSimulado(correr={'micomando': Resultado("mistdout")})
            assert mc.correr('micomando').stdout == "mistdout"

        es funcionalmente equivalente a esto::

            mc = ContextoSimulado()
            mc.set_result_for('correr', 'micomando', Resultado("mistdout"))
            assert mc.correr('micomando').stdout == "mistdout"

        `set_result_for` es sobre todo útil para modificar una instancia
        ya-instanciada `ContextoSimulado`, como uno creado por la configuración
        de prueba o los métodos auxiliares.

        .. versionadded:: 1.0
        """
        attname = "__{}".format(attname)
        heck = TypeError(
            "¡No se pueden actualizar los resultados de los resultados simulados non-dict o inexistentes!"
        )
        # Obtenga valor y quéjese si no es un dict.
        # TODO: ¿deberíamos permitir que esto también establezca valores no
        # dictados? Parece vagamente inútil, en ese punto, solo hacer un nuevo
        # ContextoSimulado, ¿eh?
        try:
            valor = getattr(self, attname)
        except AttributeError:
            raise heck
        if not isinstance(valor, dict):
            raise heck
        # Bien, estamos bien para modificar, así que hágalo.
        valor[comando] = resultado
