import os
import signal
import struct
import sys
import termios
import threading
import types

from io import BytesIO
from itertools import chain, repeat

from dued.vendor.six import StringIO, b, PY2, iteritems

from pytest import raises, skip
from pytest_relaxed import trap
from mock import patch, Mock, call

from dued import (
    CaducoComando,
    Config,
    Contexto,
    Falla,
    Local,
    Promesa,
    Respondedor,
    Resultado,
    Corredor,
    StreamCentinela,
    ErrorEnTuberiaDeSubP,
    ExcepcionDeHilo,
    SalidaInesperada,
    ErrorDeCentinela,
)
from dued.corredores import codificacion_por_defecto
from dued.terminales import WINDOWS

from _util import (
    subproceso_mock,
    mock_pty,
    saltar_si_es_windows,
    _Dummy,
    __CorredorDeInterrupcionDeTeclado,
    OhNoz,
    _,
)


class _LevantandoCentinela(StreamCentinela):
    def envio(self, stream):
        raise ErrorDeCentinela("bah")


class _ExcepcionGenerica(Exception):
    pass


class _CorredorDeExcepcionGenerica(_Dummy):
    def esperar(self):
        raise _ExcepcionGenerica


def _corre(*args, **kwargs):
    klase = kwargs.pop("klase", _Dummy)
    settings = kwargs.pop("settings", {})
    contexto = Contexto(config=Config(anula=settings))
    return klase(contexto).correr(*args, **kwargs)


def _corredor(salida="", err="", **kwargs):
    klase = kwargs.pop("klase", _Dummy)
    corredor = klase(Contexto(config=Config(anula=kwargs)))
    if "salidas" in kwargs:
        corredor.cod_de_retorno = Mock(valor_de_retorno=kwargs.pop("salidas"))
    out_file = BytesIO(b(salida))
    err_file = BytesIO(b(err))
    corredor.leer_proc_stdout = out_file.read
    corredor.leer_proc_stderr = err_file.read
    return corredor


def esperar_shell_de_plataforma(shell):
    if WINDOWS:
        assert shell.endswith("cmd.exe")
    else:
        assert shell == "/bin/bash"


def crear_atributos_tc(cc_is_ints=True, echo=False):
    # Configure la submatriz de caracteres de control; técnicamente depende
    # de la plataforma, por lo que debemos ser dinámicos.
    # NOTE: configurando esto para que podamos usar ambos valores potenciales
    # para los miembros 'cc' ... los documentos dicen ints, la realidad 
    # dice cadenas de bytes de un byte ...
    cc_base = [None] * (max(termios.VMIN, termios.VTIME) + 1)
    cc_ints, cc_bytes = cc_base[:], cc_base[:]
    cc_ints[termios.VMIN], cc_ints[termios.VTIME] = 1, 0
    cc_bytes[termios.VMIN], cc_bytes[termios.VTIME] = b"\x01", b"\x00"
    # Set tcgetattr to look like it's already cbroken...
    attrs = [
        # ibandera, obandera, cbandera - don't care
        None,
        None,
        None,
        # lbandera needs to have ECHO and ICANON unset
        ~(termios.ECHO | termios.ICANON),
        # ispeed, ospeed - don't care
        None,
        None,
        # cc - care about its VMIN and VTIME members.
        cc_ints if cc_is_ints else cc_bytes,
    ]
    # Undo the ECHO unset if caller wants this to look like a non-cbroken term
    if echo:
        attrs[3] = attrs[3] | termios.ECHO
    return attrs


class _CronometrandoAUnCorredor(_Dummy):
    @property
    def tiempo_fuera(self):
        return True


class Corredor_:
    _metodos_de_parada = ["generar_resultado", "parar", "parar_el_temporizador"]

    # NOTE: these copies of _corre and _corredor form the base case of "prueba Corredor
    # subclasses via self._corre/_corredor helpers" functionality. See how e.g.
    # Local_ uses the same approach but bakes in the dummy class used.
    def _corre(self, *args, **kwargs):
        return _corre(*args, **kwargs)

    def _corredor(self, *args, **kwargs):
        return _corredor(*args, **kwargs)

    def _escribir_stdin_mock(self):
        """
        Devuelve la nueva subclase _Dummy cuyo método escribir_proc_stdin()
        es un mock.
        """

        class MockearStdin(_Dummy):
            pass

        MockearStdin.escribir_proc_stdin = Mock()
        return MockearStdin

    class init:
        "__init__"

        def toma_una_instancia_de_contexto(self):
            c = Contexto()
            assert Corredor(c).contexto == c

        def instancia_de_contexto_es_requerida(self):
            with raises(TypeError):
                Corredor()

    class correr:
        def maneja_kwargs_no_valido_como_cualquier_otra_funcion(self):
            try:
                self._corre(_, nope_noway_nohow="as if")
            except TypeError as e:
                assert "tiene una palabra clave inesperada de argumento" in str(e)
            else:
                assert False, "El kwarg no válido de correr() no generó TypeError"

    class alarma:
        def honrar_config(self):
            corredor = self._corredor(correr={"alarma": True}, salidas=1)
            # No levanta Falla -> todo bien
            corredor.correr(_)

        def kwarg_supera_la_config(self):
            corredor = self._corredor(correr={"alarma": False}, salidas=1)
            # No levanta Falla -> todo bien
            corredor.correr(_, alarma=True)

        def no_se_aplica_a_los_errores_de_centinela(self):
            corredor = self._corredor(salida="cosas")
            try:
                centinela = _LevantandoCentinela()
                corredor.correr(_, centinelas=[centinela], alarma=True, ocultar=True)
            except Falla as e:
                assert isinstance(e.motivo, ErrorDeCentinela)
            else:
                assert False, "No levantó a Falla para ErrorDeCentinela!"

        def no_se_aplica_a_los_errores_de_tiempo_de_espera(self):
            with raises(CaducoComando):
                self._corredor(klase=_CronometrandoAUnCorredor).correr(
                    _, tiempofuera=1, alarma=True
                )

    class ocultar:
        @trap
        def honrar_config(self):
            corredor = self._corredor(salida="cosas", correr={"ocultar": True})
            r = corredor.correr(_)
            assert r.stdout == "cosas"
            assert sys.stdout.getvalue() == ""

        @trap
        def kwarg_supera_la_config(self):
            corredor = self._corredor(salida="cosas")
            r = corredor.correr(_, ocultar=True)
            assert r.stdout == "cosas"
            assert sys.stdout.getvalue() == ""

    class pty:
        def pty_pordefecto_a_apagado(self):
            assert self._corre(_).pty is False

        def honrar_config(self):
            corredor = self._corredor(correr={"pty": True})
            assert corredor.correr(_).pty is True

        def kwarg_supera_la_config(self):
            corredor = self._corredor(correr={"pty": False})
            assert corredor.correr(_, pty=True).pty is True

    class shell:
        def pordefecto_a_bash_o_cmdexe_cuando_pty_True(self):
            esperar_shell_de_plataforma(self._corre(_, pty=True).shell)

        def pordefecto_a_bash_o_cmdexe_cuando_pty_False(self):
            esperar_shell_de_plataforma(self._corre(_, pty=False).shell)

        def puede_ser_reemplazado(self):
            assert self._corre(_, shell="/bin/zsh").shell == "/bin/zsh"

        def puede_ser_configurado(self):
            corredor = self._corredor(correr={"shell": "/bin/tcsh"})
            assert corredor.correr(_).shell == "/bin/tcsh"

        def kwarg_supera_la_config(self):
            corredor = self._corredor(correr={"shell": "/bin/tcsh"})
            assert corredor.correr(_, shell="/bin/zsh").shell == "/bin/zsh"

    class entorno:
        def pordefecto_a_entorno_os(self):
            assert self._corre(_).entorno == os.environ

        def actualizaciones_cuando_dic_dado(self):
            esperado = dict(os.environ, FOO="BAR")
            assert self._corre(_, entorno={"FOO": "BAR"}).entorno == esperado

        def reemplaza_cuando_reemplazar_ent_True(self):
            entorno = self._corre(_, entorno={"JUST": "ME"}, reemplazar_ent=True).entorno
            assert entorno == {"JUST": "ME"}

        def puede_usar_la_config(self):
            entorno = self._corre(_, settings={"correr": {"entorno": {"FOO": "BAR"}}}).entorno
            assert entorno == dict(os.environ, FOO="BAR")

        def kwarg_gana_sobre_config(self):
            settings = {"correr": {"entorno": {"FOO": "BAR"}}}
            kwarg = {"FOO": "NOBAR"}
            foo = self._corre(_, settings=settings, entorno=kwarg).entorno["FOO"]
            assert foo == "NOBAR"

    class valor_de_retorno:
        def codigo_devuelto(self):
            """
            Resultado como .codigo_devuelto (y .salida)que contiene el entero
            (int) de código de salida
            """
            corredor = self._corredor(salidas=17)
            r = corredor.correr(_, alarma=True)
            assert r.codigo_devuelto == 17
            assert r.salida == 17

        def atrib_ok_indica_exito(self):
            corredor = self._corredor()
            assert corredor.correr(_).ok is True  # valret pordefault dummy es 0

        def atrib_ok_indica_falla(self):
            corredor = self._corredor(salidas=1)
            assert corredor.correr(_, alarma=True).ok is False

        def atrib_falla_indica_exito(self):
            corredor = self._corredor()
            assert corredor.correr(_).failed is False  # valret pordefault dummy es 0

        def atrib_falla_indica_falla(self):
            corredor = self._corredor(salidas=1)
            assert corredor.correr(_, alarma=True).failed is True

        @trap
        def atrib_stdout_contiene_stdout(self):
            corredor = self._corredor(salida="foo")
            assert corredor.correr(_).stdout == "foo"
            assert sys.stdout.getvalue() == "foo"

        @trap
        def atrib_stderr_contiene_stderr(self):
            corredor = self._corredor(err="foo")
            assert corredor.correr(_).stderr == "foo"
            assert sys.stderr.getvalue() == "foo"

        def si_pty_fue_usado(self):
            assert self._corre(_).pty is False
            assert self._corre(_, pty=True).pty is True

        def comando_ejecutado(self):
            assert self._corre(_).comando == _

        def shell_usada(self):
            esperar_shell_de_plataforma(self._corre(_).shell)

        def ocultar_param_expuesto_y_normalizado(self):
            assert self._corre(_, ocultar=True).ocultar, "stdout" == "stderr"
            assert self._corre(_, ocultar=False).ocultar == tuple()
            assert self._corre(_, ocultar="stderr").ocultar == ("stderr",)

    class ecos_de_comando:
        @trap
        def apagado_pordefecto(self):
            self._corre("mi comando")
            assert sys.stdout.getvalue() == ""

        @trap
        def activable_via_kwarg(self):
            self._corre("mi comando", echo=True)
            assert "mi comando" in sys.stdout.getvalue()

        @trap
        def activable_via_config(self):
            self._corre("yup", settings={"correr": {"echo": True}})
            assert "yup" in sys.stdout.getvalue()

        @trap
        def kwarg_supera_la_config(self):
            self._corre("yup", echo=True, settings={"correr": {"echo": False}})
            assert "yup" in sys.stdout.getvalue()

        @trap
        def utiliza_negrita_ansi(self):
            self._corre("mi comando", echo=True)
            # TODO: vendor & use a color module
            assert sys.stdout.getvalue() == "\x1b[1;37mmy comando\x1b[0m\n"

    class corriendo_en_seco:
        @trap
        def setea_echo_a_True(self):
            self._corre("que pasa", settings={"correr": {"seco": True}})
            assert "que pasa" in sys.stdout.getvalue()

        @trap
        def cortocircuitos_con_resultados_dummy(self):
            corredor = self._corredor(correr={"seco": True})
            # Usar el llamar a self.iniciar() en una _correr_cuerpo()
            # como centinela para todo el trabajo que hay más allá.
            corredor.start = Mock()
            resultado = corredor.correr(_)
            assert not corredor.start.called
            assert isinstance(resultado, Resultado)
            assert resultado.comando == _
            assert resultado.stdout == ""
            assert resultado.stderr == ""
            assert resultado.salida == 0
            assert resultado.pty is False

    class codificacion:
        # NOTE: estas pruebas solo verifican como termina Corredor.codificacion;
        # es difícil/imposible burlarse de los objetos de cadena para ver qué
        # se está dando .decodificar() :(
        # TODO: considere usar secuencias de bytes codificadas verdaderamente
        # "no estándar" como accesorios, codificadas con algo que no sea 
        # compatible con UTF-8
        # UTF-7 lo es, entonces ...) por lo que podemos afirmar que la cadena 
        # decodificada es igual a su equivalente Unicode.
        # Use UTF-7 como una codificación válida, es poco probable que sea un
        # valor predeterminado real derivado de locale.getpreferredencoding()
        # de prueba-corredor
        def pordefecto_es_el_resultado_del_metodo_de_codificación(self):
            # Setup
            corredor = self._corredor()
            codificacion = "UTF-7"
            corredor.codificacion_por_defecto = Mock(valor_de_retorno=codificacion)
            # Execution & assertion
            corredor.correr(_)
            corredor.codificacion_por_defecto.assert_called_with()
            assert corredor.codificacion == "UTF-7"

        def honrar_config(self):
            c = Contexto(Config(anula={"correr": {"codificacion": "UTF-7"}}))
            corredor = _Dummy(c)
            corredor.codificacion_por_defecto = Mock(valor_de_retorno="UTF-not-7")
            corredor.correr(_)
            assert corredor.codificacion == "UTF-7"

        def honrar_kwarg(self):
            skip()

        def usa_modulo_locale_pordefecto_para_codificacion(self):
            # En realidad, probar este material altamente específico del 
            # SO/entorno es muy propenso a errores; así que nos degradamos
            # a solo probar las llamadas de función esperadas por ahora :(
            with patch("dued.corredores.locale") as fake_locale:
                fake_locale.getdefaultlocale.valor_de_retorno = ("bah", "UHF-8")
                fake_locale.getpreferredencoding.valor_de_retorno = "PLANB"
                esperado = "UHF-8" if (PY2 and not WINDOWS) else "PLANB"
                assert self._corredor().codificacion_por_defecto() == esperado

        def vuelve_a_la_config_local_pordefecto_cuando_preferredencoding_es_None(self):
            if PY2:
                skip()
            with patch("dued.corredores.locale") as fake_locale:
                fake_locale.getdefaultlocale.valor_de_retorno = (None, None)
                fake_locale.getpreferredencoding.valor_de_retorno = "PLANB"
                assert self._corredor().codificacion_por_defecto() == "PLANB"

    class ocultando_la_salida:
        @trap
        def _esperar_oculto(self, ocultar, esperar_salida="", esperar_error=""):
            self._corredor(salida="foo", err="bar").correr(_, ocultar=ocultar)
            assert sys.stdout.getvalue() == esperar_salida
            assert sys.stderr.getvalue() == esperar_error

        def ambos_lo_esconden_todo(self):
            self._esperar_oculto("ambos")

        def True_lo_oculta_todo(self):
            self._esperar_oculto(True)

        def salida_solo_oculta_el_stadout(self):
            self._esperar_oculto("salida", esperar_salida="", esperar_error="bar")

        def error_solo_oculta_el_staderr(self):
            self._esperar_oculto("error", esperar_salida="foo", esperar_error="")

        def acepta_alias_stdout_para_salida(self):
            self._esperar_oculto("stdout", esperar_salida="", esperar_error="bar")

        def acepta_alias_stderr_para_error(self):
            self._esperar_oculto("stderr", esperar_salida="foo", esperar_error="")

        def None_oculta_nada(self):
            self._esperar_oculto(None, esperar_salida="foo", esperar_error="bar")

        def False_no_oculta_nada(self):
            self._esperar_oculto(False, esperar_salida="foo", esperar_error="bar")

        def valores_desconocidos_genera_ValueError(self):
            with raises(ValueError):
                self._corre(_, ocultar="¿Qué?")

        def vals_desconocidos_mencionan_el_valor_dado_por_error(self):
            valor = "fulminatrix"
            try:
                self._corre(_, ocultar=valor)
            except ValueError as e:
                msj = "Error de correr(ocultar=xxx) no le dijo al usuario cuál era valor!"  # noqa
                msj += "\nException msj: {}".format(e)
                assert valor in str(e), msj
            else:
                assert (
                    False
                ), "correr() no genero ValueError por mal ocultar= valor"  # noqa

        def no_afecta_a_la_captura(self):
            assert self._corredor(salida="foo").correr(_, ocultar=True).stdout == "foo"

        @trap
        def anula_ecos(self):
            self._corredor().correr("invisible", ocultar=True, echo=True)
            assert "invisible" not in sys.stdout.getvalue()

    class anulaciones_de_flujo_de_salida:
        @trap
        def salida_pordefecto_en_sys_stdout(self):
            "sal_stream pordefecto a sys.stdout"
            self._corredor(salida="que onda").correr(_)
            assert sys.stdout.getvalue() == "que onda"

        @trap
        def err_pordefecto_en_sys_stderr(self):
            "err_stream pordefecto a sys.stderr"
            self._corredor(err="que onda").correr(_)
            assert sys.stderr.getvalue() == "que onda"

        @trap
        def salida_se_puede_anular(self):
            "sal_stream puede ser anulada"
            salida = StringIO()
            self._corredor(salida="que onda").correr(_, sal_stream=salida)
            assert salida.getvalue() == "que onda"
            assert sys.stdout.getvalue() == ""

        @trap
        def salida_anulada_nunca_se_oculta(self):
            salida = StringIO()
            self._corredor(salida="que onda").correr(_, sal_stream=salida, ocultar=True)
            assert salida.getvalue() == "que onda"
            assert sys.stdout.getvalue() == ""

        @trap
        def err_puede_ser_anulado(self):
            "err_stream puede se anulado"
            err = StringIO()
            self._corredor(err="que onda").correr(_, err_stream=err)
            assert err.getvalue() == "que onda"
            assert sys.stderr.getvalue() == ""

        @trap
        def err_anulado_nunca_se_oculta(self):
            err = StringIO()
            self._corredor(err="que onda").correr(_, err_stream=err, ocultar=True)
            assert err.getvalue() == "que onda"
            assert sys.stderr.getvalue() == ""

        @trap
        def pty_pordefecto_a_sys(self):
            self._corredor(salida="que onda").correr(_, pty=True)
            assert sys.stdout.getvalue() == "que onda"

        @trap
        def salida_pty_puede_ser_anulado(self):
            salida = StringIO()
            self._corredor(salida="yo").correr(_, pty=True, sal_stream=salida)
            assert salida.getvalue() == "yo"
            assert sys.stdout.getvalue() == ""

    class manejo_de_flujos_de_salida:
        # En su mayoría casos de esquina, el comportamiento genérico se cubre arriba
        def escribe_y_se_vacia_a_stdout(self):
            salida = Mock(spec=StringIO)
            self._corredor(salida="bah").correr(_, sal_stream=salida)
            salida.write.asercion_llamado_una_vez_con("bah")
            salida.flush.asercion_llamado_una_vez_con()

        def escribe_y_se_vacia_a_stderr(self):
            err = Mock(spec=StringIO)
            self._corredor(err="cualquier").correr(_, err_stream=err)
            err.write.asercion_llamado_una_vez_con("cualquier")
            err.flush.asercion_llamado_una_vez_con()

    class manejo_de_flujos_de_entrada:
        # NOTE: las pruebas de respuesta automática reales están en otro 
        # lugar. Estas sólo prueban que stdin funciona normalmente y puede
        # ser anulado.
        @patch("dued.corredores.sys.stdin", StringIO("Texto!"))
        def pordefecto_a_sys_stdin(self):
            # Ejecutar c/clase corredor que tiene un escritor stdin mockeado
            klase = self._escribir_stdin_mock()
            self._corredor(klase=klase).correr(_, sal_stream=StringIO())
            # Compruebe que se llamó al escritor simulado con los datos de
            # nuestro sys.stdin parcheado.
            # NOTE: esto también prueba que los flujos que no contienen 
            # archivos leen/escriben 1 byte a la vez. Ver prueba más abajo
            # para stdin sin archivo
            llamadas = list(map(lambda x: call(x), "Texto!"))
            klase.escribir_proc_stdin.assert_has_calls(llamadas, ningun_orden=False)

        def puede_ser_anulado(self):
            klase = self._escribir_stdin_mock()
            ing_stream = StringIO("¡oye, escucha!")
            self._corredor(klase=klase).correr(
                _, ing_stream=ing_stream, sal_stream=StringIO()
            )
            # La duplicación stdin se produce char-by-char
            llamadas = list(map(lambda x: call(x), "¡oye, escucha!"))
            klase.escribir_proc_stdin.assert_has_calls(llamadas, ningun_orden=False)

        def se_puede_desactivar_por_completo(self):
            # Mock maneja stdin por tanto podemos afirmar que ni siquiera
            # es llamado
            class ManejoDeStdinMockeado(_Dummy):
                pass

            ManejoDeStdinMockeado.manejar_stdin = Mock()
            self._corredor(klase=ManejoDeStdinMockeado).correr(
                _, ing_stream=False  # vs None o un stream
            )
            assert not ManejoDeStdinMockeado.manejar_stdin.called

        @patch("dued.util.debug")
        def las_excepciones_son_logeadas(self, mock_debug):
            # Hacen escribir proc stdin asplode
            klase = self._escribir_stdin_mock()
            klase.escribir_proc_stdin.efecto_secundario = OhNoz("oh dios por qué")
            # Ejecutar con un poco de stdin para desencadenar ese asplode
            # (pero saltar el real bubbled-up de él para que podamos 
            # comprobar la salida de cosas)
            try:
                stdin = StringIO("no-vacio")
                self._corredor(klase=klase).correr(_, ing_stream=stdin)
            except ExcepcionDeHilo:
                pass
            # Assert debug() se llamó con formato esperado
            # TODO: hacer que la depuración llame a un método en 
            # hilo_de_manejo_de_excepciones, luego hacer que la clase de hilo
            # sea configurable en algún lugar de Corredor, y pasar un 
            # hilo_de_manejo_de_excepciones personalizado que tenga un
            # Mock para ese método?
            # NOTE: dividir en unas pocas afirmaciones para solucionar el
            # cambio de python 3.7 re: coma final, lo que elimina la 
            # capacidad de afirmar estáticamente toda la cadena. Suspiro.
            # También soy demasiado vago para regex.
            msj = mock_debug.llamar_args[0][0]
            assert "Excepción encontrada OhNoz" in msj
            assert "'oh dios por qué'" in msj
            assert "en hilo para 'manejar_stdin'" in msj

        def EOF_desencadena_el_cierre_de_proc_stdin(self):
            class Fake(_Dummy):
                pass

            Fake.cerrar_proc_stdin = Mock()
            self._corredor(klase=Fake).correr(_, ing_stream=StringIO("¿qué?"))
            Fake.cerrar_proc_stdin.asercion_llamado_una_vez_con()

        def EOF_no_cierra_proc_stdin_cuando_pty_True(self):
            class Fake(_Dummy):
                pass

            Fake.cerrar_proc_stdin = Mock()
            self._corredor(klase=Fake).correr(
                _, ing_stream=StringIO("¿qué?"), pty=True
            )
            assert not Fake.cerrar_proc_stdin.called

    class manejo_de_fallos:
        def fallas_rapidas(self):
            with raises(SalidaInesperada):
                self._corredor(salidas=1).correr(_)

        def cod_de_retorno_distintos_de_1_siguen_actuando_como_un_error(self):
            r = self._corredor(salidas=17).correr(_, alarma=True)
            assert r.failed is True

        class SalidaInesperada_repr:
            def similar_a_la_repr_de_resultados(self):
                try:
                    self._corredor(salidas=23).correr(_)
                except SalidaInesperada as e:
                    esperado = "<SalidaInesperada: cmd='{}' salida=23>"
                    assert repr(e) == esperado.format(_)

        class SalidaInesperada_cadena:
            def setup(self):
                def lines(prefijo):
                    prefixed = "\n".join(
                        "{} {}".format(prefijo, x) for x in range(1, 26)
                    )
                    return prefixed + "\n"

                self._stdout = lines("stdout")
                self._stderr = lines("stderr")

            @trap
            def muestra_el_cod_de_comando_y_salida_por_defecto(self):
                try:
                    self._corredor(
                        salidas=23, salida=self._stdout, err=self._stderr
                    ).correr(_)
                except SalidaInesperada as e:
                    esperado = """¡Se encontró con un código de salida de comando malo!

Comando: '{}'

Código de salida: 23

Stdout: ya impresa

Stderr: ya impresa

"""
                    assert str(e) == esperado.format(_)
                else:
                    assert False, "¡no se pudo levantar SalidaInesperada!"

            @trap
            def no_muestra_stderr_cuando_pty_True(self):
                try:
                    self._corredor(
                        salidas=13, salida=self._stdout, err=self._stderr
                    ).correr(_, pty=True)
                except SalidaInesperada as e:
                    esperado = """¡Se encontró con un código de salida de comando malo!

Comando: '{}'

Código de salida: 23

Stdout: ya impresa

Stderr: n/a (los PTYs no tienen stderr)

"""
                    assert str(e) == esperado.format(_)

            @trap
            def pty_stderr_mensaje_gana_sobre_stderr_oculto(self):
                try:
                    self._corredor(
                        salidas=1, salida=self._stdout, err=self._stderr
                    ).correr(_, pty=True, ocultar=True)
                except SalidaInesperada as e:
                    r = str(e)
                    assert "Stderr: n/a (los PTYs no tienen stderr)" in r
                    assert "Stderr: ya impresa" not in r

            @trap
            def explicit_hidding_stream_tail_display(self):
                # All the permutations of what's displayed when, are in
                # subsequent prueba, which does 'x in y' assertions; this one
                # here ensures the actual format of the display (newlines, etc)
                # is as desired.
                try:
                    self._corredor(
                        salidas=77, salida=self._stdout, err=self._stderr
                    ).correr(_, ocultar=True)
                except SalidaInesperada as e:
                    esperado = """¡Se encontró con un código de salida de comando malo!

Comando: '{}'

Código de salida: 23

Stdout:

stdout 16
stdout 17
stdout 18
stdout 19
stdout 20
stdout 21
stdout 22
stdout 23
stdout 24
stdout 25

Stderr:

stderr 16
stderr 17
stderr 18
stderr 19
stderr 20
stderr 21
stderr 22
stderr 23
stderr 24
stderr 25

"""
                    assert str(e) == esperado.format(_)

            @trap
            def muestra_colas_de_streams_solo_cuando_se_oculta(self):
                def ups(msj, r, ocultar):
                    return "{}! ocultar={}; cadena de salida:\n\n{}".format(
                        msj, ocultar, r
                    )

                for ocultar, esperar_salida, esperar_error in (
                    (False, False, False),
                    (True, True, True),
                    ("stdout", True, False),
                    ("stderr", False, True),
                    ("ambos", True, True),
                ):
                    try:
                        self._corredor(
                            salidas=1, salida=self._stdout, err=self._stderr
                        ).correr(_, ocultar=ocultar)
                    except SalidaInesperada as e:
                        r = str(e)
                        # Espere que la parte superior de la salida nunca
                        # se muestre
                        err = ups("Se encontró demasiado stdout", r, ocultar)
                        assert "stdout 15" not in r, err
                        err = ups("Se encontró demasiado stderr", r, ocultar)
                        assert "stderr 15" not in r, err
                        # Espere ver la cola de stdout si lo esperamos
                        if esperar_salida:
                            err = ups("No vi stdout", r, ocultar)
                            assert "stdout 16" in r, err
                        # Espera ver la cola de stderr si lo esperamos
                        if esperar_error:
                            err = ups("No vi stderr", r, ocultar)
                            assert "stderr 16" in r, err
                    else:
                        assert False, "No pudo elevar SalidaInesperada!"

        def _error_normal(self):
            self._corredor(salidas=1).correr(_)

        def _error_de_centinela(self):
            klase = self._escribir_stdin_mock()
            # Exited=None because real procs will have no useful .cod_de_retorno()
            # resultado if they're aborted partway via an exception.
            corredor = self._corredor(klase=klase, salida="stuff", salidas=None)
            corredor.correr(_, centinelas=[_LevantandoCentinela()], ocultar=True)

        # TODO: may eventually turn into having Corredor raise distinct Falla
        # subclasses itself, at which point `motivo` would probably go away.
        class motivo:
            def es_None_para_salidas_normales_que_no_dan_cero(self):
                try:
                    self._error_normal()
                except Falla as e:
                    assert e.motivo is None
                else:
                    assert False, "¡No pudo producir la Falla!"

            def es_None_para_salidas_de_comandos_personalizados(self):
                # TODO: cuando ponemos en práctica 'exitcodes 1 y 2 están
                # realmente BIEN'
                skip()

            def es_excepcion_cuando_ErrorDeCentinela_se_genero_internamente(self):
                try:
                    self._error_de_centinela()
                except Falla as e:
                    assert isinstance(e.motivo, ErrorDeCentinela)
                else:
                    assert False, "¡No pudo producir la Falla!"

        # TODO: ¿deberían moverse a otro lugar, por ejemplo, al archivo de
        # prueba específico de Resultado?
        # TODO: * ¿* hay * una buena manera de dividir en múltiples subclases
        # de Respuesta y/o Falla? Dada la división entre "devuelto como un 
        # valor cuando no hay problema" y "planteado como/adjunto a una 
        # excepción cuando hay problema", posiblemente no, complica la forma
        # en que se deben cumplir las API.
        class resultado_envuelto:
            def mayoria_de__atribs_siempre_estan_presentes(self):
                attrs = ("comando", "shell", "entorno", "stdout", "stderr", "pty")
                for method in (self._error_normal, self._error_de_centinela):
                    try:
                        method()
                    except Falla as e:
                        for attr in attrs:
                            assert getattr(e.resultado, attr) is not None
                    else:
                        assert False, "¡No pudo producir la Falla!"

            class fallo_de_salida_del_shell:
                def salido_es_entero(self):
                    try:
                        self._error_normal()
                    except Falla as e:
                        assert isinstance(e.resultado.salida, int)
                    else:
                        assert False, "¡No pudo producir la Falla!"

                def ok_bool_etc_son_falsos(self):
                    try:
                        self._error_normal()
                    except Falla as e:
                        assert e.resultado.ok is False
                        assert e.resultado.failed is True
                        assert not bool(e.resultado)
                        assert not e.resultado
                    else:
                        assert False, "¡No pudo producir la Falla!"

                def estado_de_salida_de_las_notas_repcadena(self):
                    try:
                        self._error_normal()
                    except Falla as e:
                        assert "Salió con estatus 1" in str(e.resultado)
                    else:
                        assert False, "¡No pudo producir la Falla!"

            class fallo_de_centinela:
                def salido_es_Ninguno(self):
                    try:
                        self._error_de_centinela()
                    except Falla as e:
                        salida = e.resultado.salida
                        err = "No previsto None, consiguió {!r}".format(salida)
                        assert salida is None, err

                def ok_y_bool_todavia_son_falsos(self):
                    try:
                        self._error_de_centinela()
                    except Falla as e:
                        assert e.resultado.ok is False
                        assert e.resultado.failed is True
                        assert not bool(e.resultado)
                        assert not e.resultado
                    else:
                        assert False, "¡No pudo producir la Falla!"

                def repcadena_carece_de_estado_de_salida(self):
                    try:
                        self._error_de_centinela()
                    except Falla as e:
                        assert "salió con el estado" not in str(e.resultado)
                        esperado = "no totalmente ejecutado debido a error de la cantinela"
                        assert esperado in str(e.resultado)
                    else:
                        assert False, "¡No pudo producir la Falla!"

    class threading:
        # NOTE: ver también las pruebas más genéricas en concurrencia.py
        def hacer_brotarUP_errores_dentro_de_cuerpo_del_hilo_io(self): # brotarUP = bubble Up
            class Ups(_Dummy):
                def manejar_stdout(self, **kwargs):
                    raise OhNoz()

                def manejar_stderr(self, **kwargs):
                    raise OhNoz()

            corredor = Ups(Contexto())
            try:
                corredor.correr("nopi")
            except ExcepcionDeHilo as e:
                # Esperamos dos objetos OhNoz separados en 'e'
                assert len(e.excepciones) == 2
                for tup in e.excepciones:
                    assert isinstance(tup.valor, OhNoz)
                    assert isinstance(tup.traceback, types.TracebackType)
                    assert tup.type == OhNoz
                # TODO: prueba también los argumentos que forman parte de la
                # tupla. Sin embargo, es bastante específico de la 
                # implementación, por lo que posiblemente no valga la pena.
            else:
                assert False, "No levanto ExcepcionDeHilo como esperaba!"

        def io_thread_errors_str_has_details(self):
            class Ups(_Dummy):
                def manejar_stdout(self, **kwargs):
                    raise OhNoz()

            corredor = Ups(Contexto())
            try:
                corredor.correr("nopi")
            except ExcepcionDeHilo as e:
                mensaje = str(e)
                # Solo asegúrese de que aparezcan los bits destacados, frente
                # a p. Ej. representación pordefault que ocurre en su lugar.
                assert "Vio 1 excepciones dentro de los hilos" in mensaje
                assert "{'kwargs': " in mensaje
                assert "Seguimiento (la última llamada más reciente):\n\n" in mensaje
                assert "OhNoz" in mensaje
            else:
                assert False, "No levanto ExcepcionDeHilo como esperaba!"

    class centinelas:
        # NOTE: inicialmente es tentador considerar el uso de mocks simulacros
        # o instancias stub de Respondedor para muchos de estos, pero 
        # realmente no ahorra tiempoej o tiempo de lectura/escritura de
        # código apreciable.
        # NOTE: estas interacciones estrictamente de prueba entre 
        # StreamCentinela/Respondedor y su anfitrión Corredor; Las pruebas
        # solo respondedor están en pruebas/centinelas.py.

        def nada_esta_escrito_a_stdin_pordefecto(self):
            # NOTE: técnicamente, si algún idiota ejecuta las pruebas a mano
            # y machaca las claves mientras lo hace ... esto fallaría. LOL?
            # NOTE: esta prueba no parece muy útil pero es a) una prueba de
            # cordura y b) protege contra p. Ej. rompiendo el autoRespondedor
            # de manera que responda a "" o "\n" o etc.
            klase = self._escribir_stdin_mock()
            self._corredor(klase=klase).correr(_)
            assert not klase.escribir_proc_stdin.called

        def _esperar_respuesta(self, **kwargs):
            """
            Ejecute un conjunto correr() con ``centinelas`` de ``respuestas``.

            Cualquier otro ``** kwargs`` dado se pasa directamente a ``_corredor()``.

            :returns: El método simulado ``escribir_proc_stdin`` del corredor.
            """
            centinelas = [
                Respondedor(patron=clave, respuesta=valor)
                for clave, valor in iteritems(kwargs.pop("responses"))
            ]
            kwargs["klase"] = klase = self._escribir_stdin_mock()
            corredor = self._corredor(**kwargs)
            corredor.correr(_, centinelas=centinelas, ocultar=True)
            return klase.escribir_proc_stdin

        def respuestas_de_los_centinelas_se_escriben_a_proc_stdin(self):
            self._esperar_respuesta(
                salida="la casa estaba vacía", responses={"vacio": "entregado"}
            ).asercion_llamado_una_vez_con("entregado")

        def multiple_hits_yields_multiple_responses(self):
            holla = call("¿a qué altura?")
            self._esperar_respuesta(
                salida="saltar, esperar, saltar, esperar", responses={"saltar": "¿a qué altura?"}
            ).assert_has_calls([holla, holla])

        def tallas_de_trozos_mas_small_que_los_patrones_todavia_funcionan_bien(self):
            klase = self._escribir_stdin_mock()
            klase.leer_tam_del_fragmento = 1  # < len('saltar')
            respondedor = Respondedor("saltar", "¿a qué altura?")
            corredor = self._corredor(klase=klase, salida="saltar, esperar, saltar, esperar")
            corredor.correr(_, centinelas=[respondedor], ocultar=True)
            holla = call("¿a qué altura?")
            # Responses happened, period.
            klase.escribir_proc_stdin.assert_has_calls([holla, holla])
            # And there weren't duplicates!
            assert len(klase.escribir_proc_stdin.llamada_a_lista_de_args) == 2

        def tanto_salida_como_err_se_escanean(self):
            bye = call("adiós")
            # Sería sólo un 'adiós' si sólo escanearia stdout

            self._esperar_respuesta(
                salida="hola mi nombre es luke",
                err="Hola como estas",
                responses={"hola": "adiós"},
            ).assert_has_calls([bye, bye])

        def patrones_multiples_funciona_segun_lo_esperado(self):
            llamadas = [call("Rose"), call("Padme")]
            # Técnicamente, esperaría que se llamara a 'Rose' antes de 
            # 'carnaval', pero en Python 3 es confiablemente al revés de
            # Python 2. En situaciones del mundo real donde cada mensaje se
            # sienta y espera su respuesta, esto probablemente no sería un
            # problema, por lo que usar ningun_orden = True por ahora. Gracias
            # de nuevo Python 3.
            self._esperar_respuesta(
                salida="Bien Tico yo soy Amidala",
                responses={"Tico": "Rose", "Amidala": "Padme"},
            ).assert_has_calls(llamadas, ningun_orden=True)

        def multiple_patterns_across_both_streams(self):
            responses = {
                "Tico": "Rose",
                "Amidala": "Padme",
                "Nave": "Halcon",
                "Robot": "BB-8",
            }
            llamadas = map(lambda x: call(x), responses.values())
            # NO PUEDE asumir el orden debido a transmisiones simultáneas.
            # Si no dijéramos ningun_orden=True, podríamos obtener una falla
            # en la condición de carrera
            self._esperar_respuesta(
                salida="Bien Tico, yo soy Amidala",
                err="Nave mejor que Robot!",
                responses=responses,
            ).assert_has_calls(llamadas, ningun_orden=True)

        def honra_opcion_de_config_de_los_centinelas(self):
            klase = self._escribir_stdin_mock()
            respondedor = Respondedor("mi stdout", "¿Quién es más loco?")
            corredor = self._corredor(
                salida="este es mi stdout",  # stdout producido
                klase=klase,  # stdin mockeado  escrito
                correr={"centinelas": [respondedor]},  # termina como anulación de configuración
            )
            corredor.correr(_, ocultar=True)
            klase.escribir_proc_stdin.asercion_llamado_una_vez_con("¿Quién es más loco?")

        def kwarg_anula_la_config(self):
            # TODO: ¿cómo manejar los casos de uso donde combinar, no anular,
            # es el valor por defecto esperado/no sorprendente? probablemente
            # otra config-only(no kwarg), por ejemplo correr.merge_responses?
            # TODO: ahora que estas cosas están basadas en listas, no en dic,
            # debería ser más fácil ... PERO ¿cómo manejar la eliminación de
            # valores predeterminados de la config? ¿Quizás solo documente 
            # para tener cuidado al usar la config, ya que no _ser_ anulada?
            # (Los usuarios siempre pueden establecer explícitamente la config
            # para que sea una lista vacía si quieren que los kwargs sean el
            # conjunto completo de centinelas ... ¿verdad?)
            klase = self._escribir_stdin_mock()
            conf = Respondedor("mi stdout", "¿Quién es más loco?")
            kwarg = Respondedor("mi stdout", "tu enfoque tu realidad")
            corredor = self._corredor(
                salida="este es mi stdout", # stdout producido
                klase=klase,  # stdin mockeado escrito
                correr={"centinelas": [conf]},  # termina como anulación de configuración
            )
            corredor.correr(_, ocultar=True, centinelas=[kwarg])
            klase.escribir_proc_stdin.asercion_llamado_una_vez_con("tu enfoque tu realidad")

    class io_suspension:
        # NOTE: hay una prueba explícita de medición de CPU en la suite de 
        # integración que asegura que el *punto* de sueño - evitando el 
        # acaparamiento de CPU - esté realmente funcionando. Estas pruebas a 
        # continuación solo prueban unitariamente los mecanismos alrededor de
        # la funcionalidad de suspensión (asegurándose de que sean visibles
        # y puedan modificarse según sea necesario).
        def atrib_de_entrada_a_suspension_pordefecto_a_centesima_de_segundo(self):
            assert Corredor(Contexto()).entrada_en_reposo == 0.01

        @subproceso_mock()
        def subclases_pueden_anular_la_entrada_en_suspension(self):
            class MiCorredor(_Dummy):
                entrada_en_reposo = 0.007

            with patch("dued.corredores.time") as mock_time:
                MiCorredor(Contexto()).correr(
                    _,
                    ing_stream=StringIO("foo"),
                    sal_stream=StringIO(),  # producción nula para no contaminar las pruebas
                )
            # Solo asegúrate de que las primeras suspensiones se vean bien.
            # No se puede saber la longitud exacta de la lista debido a que 
            # el trabajador estándar cuelga la salida hasta el final del 
            # proceso. Todavía vale la pena probar más que el primero.
            assert mock_time.sleep.llamada_a_lista_de_args[:3] == [call(0.007)] * 3

    class duplicando_stdin:
        def _prueba_mirrorig(self, reflejo_esperado, **kwargs):
            # preparando mirroring
            fingir_en = "¡Estoy escribiendo!"
            salida = Mock()
            entrada_ = StringIO(fingir_en)
            entrada_es_pty = kwargs.pop("en_pty", None)

            class MiCorredor(_Dummy):
                def deberia_hacer_echo_de_stdin(self, entrada_, salida):
                    # Resultado falso de esuntty() prueba aquí y solo aquí; 
                    # si hacemos esto más arriba, afectará a las cosas que
                    # intentan ejecutar termios & tal, que es más difícil 
                    # de mock con éxito.
                    if entrada_es_pty is not None:
                        entrada_.esuntty = lambda: entrada_es_pty
                    return super(MiCorredor, self).deberia_hacer_echo_de_stdin(
                        entrada_, salida
                    )

            # Ejecutar comando básico con los parámetros dados
            self._corre(
                _,
                klase=MiCorredor,
                ing_stream=entrada_,
                sal_stream=salida,
                **kwargs
            )
            # Examine el flujo de salida simulado para ver si se reflejó en
            if reflejo_esperado:
                llamadas = salida.write.llamada_a_lista_de_args
                assert llamadas == list(map(lambda x: call(x), fingir_en))
                assert len(salida.flush.llamada_a_lista_de_args) == len(fingir_en)
            # Or not mirrored to
            else:
                assert salida.write.llamada_a_lista_de_args == []

        def cuando_pty_es_True_no_se_produce_duplicacion(self):
            self._prueba_mirrorig(pty=True, reflejo_esperado=False)

        def cuando_pty_es_False_escribimos_en_flujo_de_nuevo_al_stream_de_salida(self):
            self._prueba_mirrorig(pty=False, en_pty=True, reflejo_esperado=True)

        def lla_duplicacion_se_omite_cuando_nuestra_entrada_no_es_un_tty(self):
            self._prueba_mirrorig(en_pty=False, reflejo_esperado=False)

        def reflejo_puede_ser_forzado_en(self):
            self._prueba_mirrorig(
                # El subproceso pty normalmente deshabilita el eco
                pty=True,
                # Pero luego lo habilitamos a la fuerza
                echo_stdin=True,
                # Y espera que suceda
                reflejo_esperado=True,
            )

        def duplicacion_se_puede_forzar_a_desactivar(self):
            # Hacer que el subproceso pty sea False, stdin tty True, 
            # echo_stdin False, probar que no hay duplicación
            self._prueba_mirrorig(
                # La falta de subproceso de pty normalmente permite hacer eco
                pty=False,
                # Siempre que el terminal de control _es_ un tty
                en_pty=True,
                # Pero luego lo desactivamos a la fuerza
                echo_stdin=False,
                # Y espera que no suceda
                reflejo_esperado=False,
            )

        def la_duplicacion_respeta_la_configuracion(self):
            self._prueba_mirrorig(
                pty=False,
                en_pty=True,
                settings={"correr": {"echo_stdin": False}},
                reflejo_esperado=False,
            )

        @trap
        @saltar_si_es_windows
        @patch("dued.corredores.sys.stdin")
        @patch("dued.terminales.fcntl.ioctl")
        @patch("dued.terminales.os")
        @patch("dued.terminales.termios")
        @patch("dued.terminales.tty")
        @patch("dued.terminales.select")
        # NOTE: la edición no-fileno se maneja en la parte superior de esta 
        # clase de prueba local, en el caso base prueba.
        def lee_bytes_FIONREAD_de_stdin_cuando_fileno(
            self, select, tty, termios, mock_os, ioctl, stdin
        ):
            # Configurar stdin como un búfer como-archivo que pasa tiene fileno
            stdin.fileno.valor_de_retorno = 17  # arbitrario
            stdin_data = list("boo!")

            def leeimitacion(n):
                # ¿Por qué no hay una versión de corte de pop ()?
                datos = stdin_data[:n]
                del stdin_data[:n]
                return "".join(datos)

            stdin.read.efecto_secundario = leeimitacion
            # Sin burlarse de esto, siempre obtendremos errores al verificar
            # el falso fileno () anterior
            mock_os.tcgetpgrp.valor_de_retorno = None
            # Asegúrese de que select() solo escupe stdin una vez, a pesar 
            # de que hay varios bytes para leer (esto al menos en parte 
            # falsifica el comportamiento del problema # 58)
            select.select.efecto_secundario = chain(
                [([stdin], [], [])], repeat(([], [], []))
            )
            # Hacer que ioctl produzca nuestro número múltiple de bytes
            # cuando se llama con FIONREAD
            def imitacion_ioctl(fd, cmd, buf):
                # Esto funciona ya que cada atributo simulado seguirá siendo
                # su propio objeto simulado con una identidad "is" distinta.
                if cmd is termios.FIONREAD:
                    return struct.pack("h", len(stdin_data))

            ioctl.efecto_secundario = imitacion_ioctl
            # Configure nuestro corredor como uno con escritura stdin 
            # simulada (la forma más sencilla de afirmar cómo están 
            # sucediendo las lecturas y escrituras)
            klase = self._escribir_stdin_mock()
            self._corredor(klase=klase).correr(_)
            klase.escribir_proc_stdin.asercion_llamado_una_vez_con("boo!")

    class stdin_de_caracteres_en_buffer:
        @saltar_si_es_windows
        @patch("dued.terminales.tty")
        def setcbreak_llamado_en_tty_stdins(self, mock_tty, mock_termios):
            mock_termios.tcgetattr.valor_de_retorno = crear_atributos_tc(echo=True)
            self._corre(_)
            mock_tty.setcbreak.assert_called_with(sys.stdin)

        @saltar_si_es_windows
        @patch("dued.terminales.tty")
        def setcbreak_no_llamado_en_stdin_no_tty(self, mock_tty):
            self._corre(_, ing_stream=StringIO())
            assert not mock_tty.setcbreak.called

        @saltar_si_es_windows
        @patch("dued.terminales.tty")
        @patch("dued.terminales.os")
        def setcbreak_no_llamado_si_el_proceso_no_esta_en_primer_plano(
            self, mock_os, mock_tty
        ):
            # Re issue #439.
            mock_os.getpgrp.valor_de_retorno = 1337
            mock_os.tcgetpgrp.valor_de_retorno = 1338
            self._corre(_)
            assert not mock_tty.setcbreak.called
            # Sanity
            mock_os.tcgetpgrp.asercion_llamado_una_vez_con(sys.stdin.fileno())

        @saltar_si_es_windows
        @patch("dued.terminales.tty")
        def tty_stdins_tienen_ajustes_restaurados_por_defecto(
            self, mock_tty, mock_termios
        ):
            # Obtenga atribs ya rotos, ya que es una manera fácil de obtener
            # el formato/diseño correcto
            attrs = crear_atributos_tc(echo=True)
            mock_termios.tcgetattr.valor_de_retorno = attrs
            self._corre(_)
            # Asegúrese de que se restauren las configuraciones antiguas
            mock_termios.tcsetattr.asercion_llamado_una_vez_con(
                sys.stdin, mock_termios.TCSADRAIN, attrs
            )

        @saltar_si_es_windows
        @patch("dued.terminales.tty")  # stub
        def tty_stdins_tienen_ajustes_restaurados_en_KeyboardInterrupt(
            self, mock_tty, mock_termios
        ):
            # Esta prueba es re: número de GH # 303
            centinela = crear_atributos_tc(echo=True)
            mock_termios.tcgetattr.valor_de_retorno = centinela
            # No haga burbujear el KeyboardInterrupt ...
            try:
                self._corre(_, klase=__CorredorDeInterrupcionDeTeclado)
            except KeyboardInterrupt:
                pass
            # ¡¿Restauramos la configuración ?!
            mock_termios.tcsetattr.asercion_llamado_una_vez_con(
                sys.stdin, mock_termios.TCSADRAIN, centinela
            )

        @saltar_si_es_windows
        @patch("dued.terminales.tty")
        def setcbreak_no_se_llama_si_terminal_parece_ya_roto(
            self, mock_tty, mock_termios
        ):
            # Demuestra # 559, sorta, en la medida en que solo pasa cuando
            # el comportamiento fijo está en su lugar. (Probar el error
            # anterior es difícil, ya que depende de la condición de carrera;
            # el nuevo comportamiento lo elude por completo). Pruebe las 
            # versiones de bytes e ints de los valores CC, ya que los
            #  documentos no están de acuerdo con al menos la realidad 
            # de algunas plataformas al respecto.
            for is_ints in (True, False):
                mock_termios.tcgetattr.valor_de_retorno = crear_atributos_tc(
                    cc_is_ints=is_ints
                )
                self._corre(_)
                # Asegúrese de que tcsetattr y setcbreak nunca hayan llamado a
                assert not mock_tty.setcbreak.called
                assert not mock_termios.tcsetattr.called

    class enviar_interrupcion:
        def _correr_con_interrupción_mockeada(self, klase):
            corredor = klase(Contexto())
            corredor.enviar_interrupcion = Mock()
            try:
                corredor.correr(_)
            except _ExcepcionGenerica:
                pass
            return corredor

        def llamado_en_KeyboardInterrupt(self):
            corredor = self._correr_con_interrupción_mockeada(
                __CorredorDeInterrupcionDeTeclado
            )
            assert corredor.enviar_interrupcion.called

        def no_llamado_por_otras_excepciones(self):
            corredor = self._correr_con_interrupción_mockeada(_CorredorDeExcepcionGenerica)
            assert not corredor.enviar_interrupcion.called

        def envia_secuencia_de_bytes_de_escape(self):
            for pty in (True, False):
                corredor = __CorredorDeInterrupcionDeTeclado(Contexto())
                mock_stdin = Mock()
                corredor.escribir_proc_stdin = mock_stdin
                corredor.correr(_, pty=pty)
                mock_stdin.asercion_llamado_una_vez_con(u"\x03")

    class tiempofuera:
        def temporizador_de_inicio_llamado_con_valor_de_config(self):
            corredor = self._corredor(tiempo_de_descanso={"comando": 7})
            corredor.iniciar_tmp = Mock()
            assert corredor.contexto.config.tiempo_de_descanso.comando == 7
            corredor.correr(_)
            corredor.iniciar_tmp.asercion_llamado_una_vez_con(7)

        def correr_kwarg_honrado(self):
            corredor = self._corredor()
            corredor.iniciar_tmp = Mock()
            assert corredor.contexto.config.tiempo_de_descanso.comando is None
            corredor.correr(_, tiempofuera=3)
            corredor.iniciar_tmp.asercion_llamado_una_vez_con(3)

        def kwarg_gana_sobre_config(self):
            corredor = self._corredor(tiempo_de_descanso={"comando": 7})
            corredor.iniciar_tmp = Mock()
            assert corredor.contexto.config.tiempo_de_descanso.comando == 7
            corredor.correr(_, tiempofuera=3)
            corredor.iniciar_tmp.asercion_llamado_una_vez_con(3)

        def aumenta_CommandTimedOut_con_informacion_de_tiempo_de_espera(self):
            corredor = self._corredor(
                klase=_CronometrandoAUnCorredor, tiempo_de_descanso={"comando": 7}
            )
            with raises(CaducoComando) as info:
                corredor.correr(_)
            assert info.valor.tiempofuera == 7
            _repr = "<CaducoComando: cmd='nop' tiempofuera=7>"
            assert repr(info.valor) == _repr
            esperado = """
¡El comando no se completó en 7 segundos!

Comando: 'nop'

Stdout: ya impreso

Stderr: ya impreso

""".lstrip()
            assert str(info.valor) == esperado

        @patch("dued.corredores.threading.Timer")
        def temporizador_de_inicio_da_a_su_temporizador_el_metodo_matar(self, Timer):
            corredor = self._corredor()
            corredor.iniciar_tmp(30)
            Timer.asercion_llamado_una_vez_con(30, corredor.matar)

        def _timer_mockeado(self):
            corredor = self._corredor()
            corredor._timer = Mock()
            return corredor

        def corre_siempre_detiene_el_temporizador(self):
            corredor = _CorredorDeExcepcionGenerica(Contexto())
            corredor.parar_el_temporizador = Mock()
            with raises(_ExcepcionGenerica):
                corredor.correr(_)
            corredor.parar_el_temporizador.asercion_llamado_una_vez_con()

        def temporizador_de_parada_cancela_el_temporizador(self):
            corredor = self._timer_mockeado()
            corredor.parar_el_temporizador()
            corredor._timer.cancel.asercion_llamado_una_vez_con()

        def la_vida_del_temporizador_es_la_prueba_de_tiempo_fuera(self):
            # Puede ser redundante, pero lo suficientemente fácil como para
            # la unidad de prueba
            corredor = Corredor(Contexto())
            corredor._timer = Mock()
            corredor._timer.is_alive.valor_de_retorno = False
            assert corredor.tiempo_fuera
            corredor._timer.is_alive.valor_de_retorno = True
            assert not corredor.tiempo_fuera

        def tiempo_de_espera_especificado_pero_ningun_temporizador_significa_que_no_hay_excepcion(self):
            # Extraño caso de esquina, pero vale la pena probar
            corredor = Corredor(Contexto())
            corredor._timer = None
            assert not corredor.tiempo_fuera

    class parar:
        def siempre_corre_sin_importar_lo_que_pase(self):
            corredor = _CorredorDeExcepcionGenerica(contexto=Contexto())
            corredor.parar = Mock()
            with raises(_ExcepcionGenerica):
                corredor.correr(_)
            corredor.parar.asercion_llamado_una_vez_con()

    class asincrono:
        def devuelve_Promesa_inmediatamente_y_termina_en_unirse(self):
            # subclase Dummy con proceso_esta_terminado bandera controlable 
            class _Finisher(_Dummy):
                _finished = False

                @property
                def proceso_esta_terminado(self):
                    return self._finished

            corredor = _Finisher(Contexto())
            # Set up mocks and go
            corredor.start = Mock()
            for method in self._metodos_de_parada:
                setattr(corredor, method, Mock())
            resultado = corredor.correr(_, asincrono=True)
            # Got a Promesa (its attrs etc are in its own prueba subsuite)
            assert isinstance(resultado, Promesa)
            # Started, but did not stop (as would've happened for rechazado)
            assert corredor.start.called
            for method in self._metodos_de_parada:
                assert not getattr(corredor, method).called
            # Set proc completion bandera to esverdad and join()
            corredor._finished = True
            resultado.join()
            for method in self._metodos_de_parada:
                assert getattr(corredor, method).called

        @trap
        def oculta_salida(self):
            # Correr c/faux subproc stdout/err datos, pero async
            self._corredor(salida="foo", err="bar").correr(_, asincrono=True).join()
            # Espera que los flujos de salida/err predeterminados no se impriman.
            assert sys.stdout.getvalue() == ""
            assert sys.stderr.getvalue() == ""

        def no_reevia_stdin(self):
            class ManejoDeStdinMockeado(_Dummy):
                pass

            ManejoDeStdinMockeado.manejar_stdin = Mock()
            corredor = self._corredor(klase=ManejoDeStdinMockeado)
            corredor.correr(_, asincrono=True).join()
            # Al igual que con la prueba principal para establecer esto en
            # False, sabemos que cuando stdin está deshabilitado, ni 
            # siquiera se llama al controlador (no se crea ningún hilo para él).
            assert not ManejoDeStdinMockeado.manejar_stdin.called

        def deja_solo_streams_anulados(self):
            # NOTE: técnicamente una prueba duplicada de las pruebas 
            # genéricas para # 637 re: intersección de las secuencias 
            # ocultas y anuladas. Pero ese es un detalle de implementación,
            # por lo que sigue siendo valioso.
            klase = self._escribir_stdin_mock()
            salida, err, in_ = StringIO(), StringIO(), StringIO("Bueno")
            corredor = self._corredor(salida="foo", err="bar", klase=klase)
            corredor.correr(
                _,
                asincrono=True,
                sal_stream=salida,
                err_stream=err,
                ing_stream=in_,
            ).join()
            assert salida.getvalue() == "foo"
            assert err.getvalue() == "bar"
            assert klase.escribir_proc_stdin.called  # lento

    class rechazado:
        @patch.object(threading.Thread, "start")
        def inicia_y_devuelve_None_pero_no_hace_nada_mas(self, thread_start):
            corredor = Corredor(Contexto())
            corredor.iniciar = Mock()
            not_called = self._metodos_de_parada + ["esperar"]
            for method in not_called:
                setattr(corredor, method, Mock())
            resultado = corredor.correr(_, rechazado=True)
            # No Resultado object!
            assert resultado is None
            # Subprocess kicked off
            assert corredor.iniciar.called
            # No timer or IO threads started
            assert not thread_start.called
            # No esperar or shutdown related Corredor methods called
            for method in not_called:
                assert not getattr(corredor, method).called

        def no_se_puede_dar_junto_con_asincrono(self):
            with raises(ValueError) as info:
                self._corredor().correr(_, asincrono=True, rechazado=True)
            centinela = "No se puede dar ambos 'asincrono' y 'rechazado'"
            assert centinela in str(info.valor)

class _LocalVeloz(Local):
    # Neutro esto por la misma razón que en _Dummy arriba
    entrada_en_reposo = 0


class Local_:
    def _corre(self, *args, **kwargs):
        return _corre(*args, **dict(kwargs, klase=_LocalVeloz))

    def _corredor(self, *args, **kwargs):
        return _corredor(*args, **dict(kwargs, klase=_LocalVeloz))

    class pty:
        @mock_pty()
        def cuando_pty_True_usamos_pty_fork_y_os_exec(self):
            "when pty=True, we use pty.fork and os.exec*"
            self._corre(_, pty=True)
            # Ls aserciones de @mock_pty comprueban las llamadas os/pty
            # por nosotros.

        @mock_pty(insert_os=True)
        def _espera_check_de_salida(self, salida, mock_os):
            if salida:
                expected_check = mock_os.WIFEXITED
                expected_get = mock_os.WEXITSTATUS
                unexpected_check = mock_os.WIFSIGNALED
                unexpected_get = mock_os.WTERMSIG
            else:
                expected_check = mock_os.WIFSIGNALED
                expected_get = mock_os.WTERMSIG
                unexpected_check = mock_os.WIFEXITED
                unexpected_get = mock_os.WEXITSTATUS
            expected_check.valor_de_retorno = True
            unexpected_check.valor_de_retorno = False
            self._corre(_, pty=True)
            exitstatus = mock_os.waitpid.valor_de_retorno[1]
            expected_get.asercion_llamado_una_vez_con(exitstatus)
            assert not unexpected_get.called

        def pty_usa_WEXITSTATUS_si_WIFEXITED(self):
            self._espera_check_de_salida(True)

        def pty_usa_WTERMSIG_si_WIFSIGNALED(self):
            self._espera_check_de_salida(False)

        @mock_pty(insert_os=True)
        def resultado_WTERMSIG_se_volvio_negativo_para_coincidir_con_el_subproceso(self, mock_os):
            mock_os.WIFEXITED.valor_de_retorno = False
            mock_os.WIFSIGNALED.valor_de_retorno = True
            mock_os.WTERMSIG.valor_de_retorno = 2
            assert self._corre(_, pty=True, alarma=True).salida == -2

        @mock_pty()
        def pty_esta_config_para_controlar_la_tamano_del_terminal(self):
            self._corre(_, pty=True)
            # @ mock_pty's afirma verificar las llamadas de 
            # TIOC [GS] WINSZ para nosotros

        def advertencia_solo_incendios_una_vez(self):
            # Es decir si la implementación comprueba pty-ness> 1 vez,
            # solo se emite una advertencia. Esto es algo específico de la
            # implementación, pero ...
            skip()

        @patch("dued.corredores.sys")
        def objetos_stdin_reemplazados_no_explotan(self, mock_sys):
            # Reemplace sys.stdin por un objeto que carezca de .esuntty(),
            # lo que normalmente causa un AttributeError a menos que estemos
            # siendo cuidadosos.
            mock_sys.stdin = object()
            # Test. If bug is present, this will error.
            corredor = Local(Contexto())
            assert corredor.deberia_usar_pty(pty=True, retroceder=True) is False

        @mock_pty(trailing_error=OSError("Input/salida error"))
        def OSErrors_espurios_manejados_con_gracia(self):
            # Doesn't-blow-up prueba.
            self._corre(_, pty=True)

        @mock_pty(trailing_error=OSError("I/O error"))
        def otros_OSErrors_espurios_manejados_con_gracia(self):
            # Doesn't-blow-up prueba.
            self._corre(_, pty=True)

        @mock_pty(trailing_error=OSError("wat"))
        def OSErrors_no_espurios_brotanUP(self):
            try:
                self._corre(_, pty=True)
            except ExcepcionDeHilo as e:
                e = e.excepciones[0]
                assert e.type == OSError
                assert str(e.valor) == "wat"

        @mock_pty(os_close_error=True)
        def detener_silencia_los_errores_en_pty_cierra(self):
            # Otra prueba no explosiva, esta vez alrededor de os.close() del pty
            # en sí (debido a os_close_error = True)
            self._corre(_, pty=True)

        class retroceder:
            @mock_pty(esuntty=False)
            def puede_ser_anulado_por_kwarg(self):
                self._corre(_, pty=True, retroceder=False)
                # Las aserciones de @ mock_pty se volverán locas si las
                # llamadas a os/pty relacionadas con pty no se activaron,
                # así que hemos terminado.

            @mock_pty(esuntty=False)
            def puede_ser_anulado_por_config(self):
                self._corredor(correr={"retroceder": False}).correr(_, pty=True)
                # Las aserciones de @ mock_pty se volverán locas si las
                # llamadas a os/pty relacionadas con pty no se activaron,
                # así que hemos terminado.

            @trap
            @subproceso_mock(esuntty=False)
            def afecta_al_valor_de_pty_resultado(self, *mocks):
                assert self._corre(_, pty=True).pty is False

            @mock_pty(esuntty=False)
            def anulada_reserva_afecta_al_valor_de_pty_resultado(self):
                assert self._corre(_, pty=True, retroceder=False).pty is True

    class shell:
        @mock_pty(insert_os=True)
        def pordefecto_a_bash_o_cmdexe_cuando_pty_True(self, mock_os):
            # NOTE: sí, windows no puede correr pty es cierto, pero esto 
            # realmente está probando el comportamiento de configuración,
            # así que ... bah
            self._corre(_, pty=True)
            esperar_shell_de_plataforma(mock_os.execve.llamada_a_lista_de_args[0][0][0])

        @subproceso_mock(insert_Popen=True)
        def pordefecto_a_bash_o_cmdexe_cuando_pty_False(self, mock_Popen):
            self._corre(_, pty=False)
            esperar_shell_de_plataforma(
                mock_Popen.llamada_a_lista_de_args[0][1]["executable"]
            )

        @mock_pty(insert_os=True)
        def puede_ser_anulado_cuando_pty_True(self, mock_os):
            self._corre(_, pty=True, shell="/bin/zsh")
            assert mock_os.execve.llamada_a_lista_de_args[0][0][0] == "/bin/zsh"

        @subproceso_mock(insert_Popen=True)
        def puede_ser_anulado_cuando_pty_False(self, mock_Popen):
            self._corre(_, pty=False, shell="/bin/zsh")
            assert mock_Popen.llamada_a_lista_de_args[0][1]["executable"] == "/bin/zsh"

    class entorno:
        # NOTE: la semántica de actualizar vs reemplazar se prueba 
        # 'puramente' arriba en las pruebas regulares de Corredor.

        @subproceso_mock(insert_Popen=True)
        def utiliza_Popen_kwarg_para_pty_False(self, mock_Popen):
            self._corre(_, pty=False, entorno={"FOO": "BAR"})
            esperado = dict(os.environ, FOO="BAR")
            entorno = mock_Popen.llamada_a_lista_de_args[0][1]["entorno"]
            assert entorno == esperado

        @mock_pty(insert_os=True)
        def utiliza_execve_para_pty_True(self, mock_os):
            type(mock_os).environ = {"OTRAVAR": "OTROVAL"}
            self._corre(_, pty=True, entorno={"FOO": "BAR"})
            esperado = {"OTRAVAR": "OTROVAL", "FOO": "BAR"}
            entorno = mock_os.execve.llamada_a_lista_de_args[0][0][2]
            assert entorno == esperado

    class cerrar_proc_stdin:
        def provoca_SubprocessPipeError_cuando_pty_en_uso(self):
            with raises(ErrorEnTuberiaDeSubP):
                corredor = Local(Contexto())
                corredor.usando_pty = True
                corredor.cerrar_proc_stdin()

        def cierra_el_proceso_stdin(self):
            corredor = Local(Contexto())
            corredor.process = Mock()
            corredor.usando_pty = False
            corredor.cerrar_proc_stdin()
            corredor.process.stdin.close.asercion_llamado_una_vez_con()

    class tiempofuera:
        @patch("dued.corredores.os")
        def matar_usa_self_pid_cuando_pty(self, mock_os):
            corredor = self._corredor()
            corredor.usando_pty = True
            corredor.pid = 50
            corredor.matar()
            mock_os.matar.asercion_llamado_una_vez_con(50, signal.SIGKILL)

        @patch("dued.corredores.os")
        def matar_utiliza_proceso_pid_cuando_no_pty(self, mock_os):
            corredor = self._corredor()
            corredor.usando_pty = False
            corredor.process = Mock(pid=30)
            corredor.matar()
            mock_os.matar.asercion_llamado_una_vez_con(30, signal.SIGKILL)


class Resultado_:
    def no_se_requiere_nada(self):
        Resultado()

    def primer_posarg_es_stdout(self):
        assert Resultado("foo").stdout == "foo"

    def comando_por_defecto_a_cadena_vacía(self):
        assert Resultado().comando == ""

    def shell_por_defecto_a_cadena_vacía(self):
        assert Resultado().shell == ""

    def codificacion_pordefecto_a_codificacion_predeterminada_local(self):
        assert Resultado().codificacion == codificacion_por_defecto()

    def env_por_defecto_a_dic_vacío(self):
        assert Resultado().entorno == {}

    def stdout_por_defecto_es_cadena_vacia(self):
        assert Resultado().stdout == u""

    def stderr_por_defecto_es_cadena_vacia(self):
        assert Resultado().stderr == u""

    def salida_pordefecto_a_cero(self):
        assert Resultado().salida == 0

    def pty_pordefecto_a_False(self):
        assert Resultado().pty is False

    def repr_contiene_info_util(self):
        assert repr(Resultado(comando="foo")) == "<Resultado cmd='foo' salida=0>"

    class cola:
        def setup(self):
            self.sample = "\n".join(str(x) for x in range(25))

        def devuelve_las_ultimas_10_líneas_de_flujo_dado_más_espacio_en_blanco(self):
            esperado = """

15
16
17
18
19
20
21
22
23
24"""
            assert Resultado(stdout=self.sample).cola("stdout") == esperado

        def el_recuento_de_lineas_es_configurable(self):
            esperado = """

23
24"""
            cola = Resultado(stdout=self.sample).cola("stdout", contar=2)
            assert cola == esperado

        def funciona_para_stderr_también(self):
            # Dumb prueba is dumb, but cualquier
            esperado = """

23
24"""
            cola = Resultado(stderr=self.sample).cola("stderr", contar=2)
            assert cola == esperado

        @patch("dued.corredores.codificar_salida")
        def codifica_con_codificacion_de_resultados(self, encode):
            Resultado(stdout="foo", codificacion="utf-16").cola("stdout")
            encode.asercion_llamado_una_vez_con("\n\nfoo", "utf-16")


class Promesa_:
    def expone_params_de_ejecucion_solo_lectura(self):
        corredor = _corredor()
        promesa = corredor.correr(
            _, pty=True, codificacion="utf-17", shell="sea", asincrono=True
        )
        assert promesa.comando == _
        assert promesa.pty is True
        assert promesa.codificacion == "utf-17"
        assert promesa.shell == "sea"
        assert not hasattr(promesa, "stdout")
        assert not hasattr(promesa, "stderr")

    class join:
        # NOTE: la mecánica del ciclo de vida de Corredor de alto nivel de 
        # join() (re: esperar(), proceso_esta_terminado() etc) se prueba
        # en la suite principal.

        def devuelve_Resultado_en_el_exito(self):
            resultado = _corredor().correr(_, asincrono=True).join()
            assert isinstance(resultado, Resultado)
            # Sanity
            assert resultado.comando == _
            assert resultado.salida == 0

        def genera_la_excepcion_de_hilo_principal_en_kaboom(self):
            corredor = _corredor(klase=_CorredorDeExcepcionGenerica)
            with raises(_ExcepcionGenerica):
                corredor.correr(_, asincrono=True).join()

        def genera_la_excepción_de_subproceso_en_su_kaboom(self):
            class Kaboom(_Dummy):
                def manejar_stdout(self, **kwargs):
                    raise OhNoz()

            corredor = _corredor(klase=Kaboom)
            promesa = corredor.correr(_, asincrono=True)
            with raises(ExcepcionDeHilo) as info:
                promesa.join()
            assert isinstance(info.valor.excepciones[0].valor, OhNoz)

        def provoca_el_Falla_en_el_fracaso(self):
            corredor = _corredor(salidas=1)
            promesa = corredor.correr(_, asincrono=True)
            with raises(Falla):
                promesa.join()

    class gestor_de_contexto:
        def llamadas_se_unen_o_esperan_en_el_cierre_de_bloque(self):
            promesa = _corredor().correr(_, asincrono=True)
            promesa.join = Mock()
            with promesa:
                pass
            promesa.join.asercion_llamado_una_vez_con()

        def cede_a_si_mismo(self):
            promesa = _corredor().correr(_, asincrono=True)
            with promesa as valor:
                assert valor is promesa
