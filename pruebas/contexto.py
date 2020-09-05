import os
import pickle
import re
import sys

from mock import patch, Mock, call
from pytest_relaxed import trap
from pytest import skip, raises

from dued import (
    FallaAutenticacion,
    Contexto,
    Config,
    DetectorDeRespuestasIncorrectas,
    RespuestaNoAceptada,
    StreamCentinela,
    ContextoSimulado,
    Resultado,
)

from _util import subproceso_mock, _Dummy


local_path = "dued.config.Local"


class Contexto_:
    class init:
        "__init__"

        def toma_arg_de_config_opcional(self):
            # Meh-tastic doesn't-barf pruebas. MEH.
            Contexto()
            Contexto(config={"foo": "bar"})

    class metodos_expuestos:
        def _esperar_atrib(self, attr):
            c = Contexto()
            assert hasattr(c, attr) and callable(getattr(c, attr))

        class correr:
            # NOTE: el comportamiento real de la ejecución de comandos se 
            # prueba en corredores.py
            def exists(self):
                self._esperar_atrib("correr")

            @patch(local_path)
            def por_defecto_a_Local(self, Local):
                c = Contexto()
                c.correr("foo")
                assert Local.mock_calls == [call(c), call().correr("foo")]

            def honra_el_ajuste_de_config_del_corredor(self):
                clase_corredor = Mock()
                config = Config({"corredores": {"local": clase_corredor}})
                c = Contexto(config)
                c.correr("foo")
                assert clase_corredor.mock_calls == [call(c), call().correr("foo")]

        def sudo(self):
            self._esperar_atrib("sudo")

    class proxy_de_configuracion:
        "Proxy tipo dic para self.config"

        def setup(self):
            config = Config(defaults={"foo": "bar", "biz": {"baz": "boz"}})
            self.c = Contexto(config=config)

        def acceso_directo_permitido(self):
            assert self.c.config.__class__ == Config
            assert self.c.config["foo"] == "bar"
            assert self.c.config.foo == "bar"

        def config_atrib_puede_sobrescribirse_en_acte(self):
            new_config = Config(defaults={"foo": "nobar"})
            self.c.config = new_config
            assert self.c.foo == "nobar"

        def getitem(self):
            "__getitem__"
            assert self.c["foo"] == "bar"
            assert self.c["biz"]["baz"] == "boz"

        def getattr(self):
            "__getattr__"
            assert self.c.foo == "bar"
            assert self.c.biz.baz == "boz"

        def get(self):
            assert self.c.get("foo") == "bar"
            assert self.c.get("nop", "hum") == "hum"
            assert self.c.biz.get("nop", "hrm") == "hrm"

        def pop(self):
            assert self.c.pop("foo") == "bar"
            assert self.c.pop("foo", "nobar") == "nobar"
            assert self.c.biz.pop("baz") == "boz"

        def popitem(self):
            assert self.c.biz.popitem() == ("baz", "boz")
            del self.c["biz"]
            assert self.c.popitem() == ("foo", "bar")
            assert self.c.config == {}

        def del_(self):
            "del"
            del self.c["foo"]
            del self.c["biz"]["baz"]
            assert self.c.biz == {}
            del self.c["biz"]
            assert self.c.config == {}

        def limpiar(self):
            self.c.biz.limpiar()
            assert self.c.biz == {}
            self.c.limpiar()
            assert self.c.config == {}

        def setdefault(self):
            assert self.c.setdefault("foo") == "bar"
            assert self.c.biz.setdefault("baz") == "boz"
            assert self.c.setdefault("notfoo", "nobar") == "nobar"
            assert self.c.notfoo == "nobar"
            assert self.c.biz.setdefault("otrobaz", "otroboz") == "otroboz"
            assert self.c.biz.otrobaz == "otroboz"

        def actualizar(self):
            self.c.actualizar({"nuevaclave": "nuevovalor"})
            assert self.c["nuevaclave"] == "nuevovalor"
            assert self.c.foo == "bar"
            self.c.biz.actualizar(otrobaz="otroboz")
            assert self.c.biz.otrobaz == "otroboz"

    class cwd:
        def setup(self):
            self.c = Contexto()

        def simple(self):
            self.c.comando_cwds = ["a", "b"]
            assert self.c.cwd == os.path.join("a", "b")

        def ruta_absoluta_anidada(self):
            self.c.comando_cwds = ["a", "/b", "c"]
            assert self.c.cwd == os.path.join("/b", "c")

        def multiples_rutas_absolutas(self):
            self.c.comando_cwds = ["a", "/b", "c", "/d", "e"]
            assert self.c.cwd == os.path.join("/d", "e")

        def home(self):
            self.c.comando_cwds = ["a", "~b", "c"]
            assert self.c.cwd == os.path.join("~b", "c")

    class cd:
        def setup(self):
            self.mensaje_de_escape = re.escape(Config().sudo.prompt)

        @patch(local_path)
        def debe_aplicarse_a_correr(self, Local):
            corredor = Local.valor_de_retorno
            c = Contexto()
            with c.cd("foo"):
                c.correr("chubaca")

            cmd = "cd foo && chubaca"
            assert corredor.correr.called, "correr() nunca llamó a corredor.correr()!"
            assert corredor.correr.llamar_args[0][0] == cmd

        @patch(local_path)
        def debe_aplicarse_a_sudo(self, Local):
            corredor = Local.valor_de_retorno
            c = Contexto()
            with c.cd("foo"):
                c.sudo("chubaca")

            cmd = "sudo -S -p '[sudo] password: ' cd foo && chubaca"
            assert corredor.correr.called, "sudo() nunca llamó a corredor.correr()!"
            assert corredor.correr.llamar_args[0][0] == cmd

        @patch(local_path)
        def deben_ocurrir_antes_de_los_prefijos(self, Local):
            corredor = Local.valor_de_retorno
            c = Contexto()
            with c.prefijo("source venv"):
                with c.cd("foo"):
                    c.correr("chubaca")

            cmd = "cd foo && source venv && chubaca"
            assert corredor.correr.called, "correr() nunca llamó a corredor.correr()!"
            assert corredor.correr.llamar_args[0][0] == cmd

        @patch(local_path)
        def debe_usarse_finalmente_para_revertir_los_cambios_en_las_excepciones(self, Local):
            class Ups(Exception):
                pass

            corredor = Local.valor_de_retorno
            c = Contexto()
            try:
                with c.cd("foo"):
                    c.correr("chubaca")
                    assert corredor.correr.llamar_args[0][0] == "cd foo && chubaca"
                    raise Ups
            except Ups:
                pass
            c.correr("ls")
            # Cuando el error presente, esto sería "cd foo && ls"
            assert corredor.correr.llamar_args[0][0] == "ls"

    class prefijo:
        def setup(self):
            self.mensaje_de_escape = re.escape(Config().sudo.prompt)

        @patch(local_path)
        def prefijos_deben_aplicarse_a_corredor(self, Local):
            corredor = Local.valor_de_retorno
            c = Contexto()
            with c.prefijo("cd foo"):
                c.correr("chubaca")

            cmd = "cd foo && chubaca"
            assert corredor.correr.called, "correr() nunca llamó a corredor.correr()!"
            assert corredor.correr.llamar_args[0][0] == cmd

        @patch(local_path)
        def prefijos_deben_aplicarse_a_sudo(self, Local):
            corredor = Local.valor_de_retorno
            c = Contexto()
            with c.prefijo("cd foo"):
                c.sudo("chubaca")

            cmd = "sudo -S -p '[sudo] password: ' cd foo && chubaca"
            assert corredor.correr.called, "sudo() nunca llamó a corredor.correr()!"
            assert corredor.correr.llamar_args[0][0] == cmd

        @patch(local_path)
        def anidacion_debe_mantener_el_orden(self, Local):
            corredor = Local.valor_de_retorno
            c = Contexto()
            with c.prefijo("cd foo"):
                with c.prefijo("cd bar"):
                    c.correr("chubaca")
                    cmd = "cd foo && cd bar && chubaca"
                    assert (
                        corredor.correr.called
                    ), "correr() nunca llamó a corredor.correr()!"  # noqa
                    assert corredor.correr.llamar_args[0][0] == cmd

                c.correr("chubaca")
                cmd = "cd foo && chubaca"
                assert corredor.correr.called, "correr() nunca llamó a corredor.correr()!"
                assert corredor.correr.llamar_args[0][0] == cmd

            # también prueba que los prefijos no persisten
            c.correr("chubaca")
            cmd = "chubaca"
            assert corredor.correr.called, "correr() nunca llamó a corredor.correr()!"
            assert corredor.correr.llamar_args[0][0] == cmd

        @patch(local_path)
        def debe_usarse_finalmente_para_revertir_los_cambios_en_las_excepciones(self, Local):
            class Ups(Exception):
                pass

            corredor = Local.valor_de_retorno
            c = Contexto()
            try:
                with c.prefijo("cd foo"):
                    c.correr("chubaca")
                    assert corredor.correr.llamar_args[0][0] == "cd foo && chubaca"
                    raise Ups
            except Ups:
                pass
            c.correr("ls")
            # When bug present, this would be "cd foo && ls"
            assert corredor.correr.llamar_args[0][0] == "ls"

    class sudo:
        def setup(self):
            self.mensaje_de_escape = re.escape(Config().sudo.prompt)

        @patch(local_path)
        def prefijos_de_comando_con_sudo(self, Local):
            corredor = Local.valor_de_retorno
            Contexto().sudo("chubaca")
            # NOTE: implicitly pruebas default sudo.prompt conf value
            cmd = "sudo -S -p '[sudo] password: ' chubaca"
            assert corredor.correr.called, "sudo() nunca llamó a corredor.correr()!"
            assert corredor.correr.llamar_args[0][0] == cmd

        @patch(local_path)
        def argumento_de_usuario_opcional_agrega_banderad_u_y_H(self, Local):
            corredor = Local.valor_de_retorno
            Contexto().sudo("chubaca", usuario="rando")
            cmd = "sudo -S -p '[sudo] password: ' -H -u rando chubaca"
            assert corredor.correr.called, "sudo() nunca llamó a corredor.correr()!"
            assert corredor.correr.llamar_args[0][0] == cmd

        @patch(local_path)
        def honra_la_config_por_el_valor_del_usuario(self, Local):
            corredor = Local.valor_de_retorno
            config = Config(anulaciones={"sudo": {"usuario": "rando"}})
            Contexto(config=config).sudo("chubaca")
            cmd = "sudo -S -p '[sudo] password: ' -H -u rando chubaca"
            assert corredor.correr.llamar_args[0][0] == cmd

        @patch(local_path)
        def usuario_kwarg_gana_sobre_config(self, Local):
            corredor = Local.valor_de_retorno
            config = Config(anulaciones={"sudo": {"usuario": "rando"}})
            Contexto(config=config).sudo("chubaca", usuario="calrissian")
            cmd = "sudo -S -p '[sudo] password: ' -H -u calrissian chubaca"
            assert corredor.correr.llamar_args[0][0] == cmd

        @trap
        @subproceso_mock()
        def echo_esconde_sudo_banderas_extra(self):
            skip()  # ver TODO en sudo() re: pantalla de salida limpia
            config = Config(anulaciones={"corredor": _Dummy})
            Contexto(config=config).sudo("nop", echo=True)
            salida = sys.stdout.getvalue()
            sys.__stderr__.write(repr(salida) + "\n")
            assert "-S" not in salida
            assert Contexto().sudo.prompt not in salida
            assert "sudo nop" in salida

        @patch(local_path)
        def honra_config_para_valor_de_prompt(self, Local):
            corredor = Local.valor_de_retorno
            config = Config(anulaciones={"sudo": {"prompt": "RE CARGA: "}})
            Contexto(config=config).sudo("chubaca")
            cmd = "sudo -S -p 'RE CARGA: ' chubaca"
            assert corredor.correr.llamar_args[0][0] == cmd

        def valor_de_prompt_se_escapa_correctamente_de_la_shell(self):
            # Es decir configurándolo en "aquí está Johnny!" no explota.
            # NOTE: posiblemente sea mejor vincularlo con el problema # 2
            skip()

        def _esperar_respuestas(self, esperado, config=None, kwargs=None):
            """
            Ejecute moked sudo(), esperando centinelas= kwarg en su correr().

            * esperado: lista de 2 tuplas de DetectorDeRespuestasIncorrectas prompt/respuesta
            * config: objeto Config, si un anulado es necesario
            * kwargs: sudo () kwargs, de ser necesario
            """
            if kwargs is None:
                kwargs = {}
            Local = Mock()
            corredor = Local.valor_de_retorno
            contexto = Contexto(config=config) if config else Contexto()
            contexto.config.corredores.local = Local
            contexto.sudo("chubaca", **kwargs)
            # Averiguar los bits interesantes - patrón/respuesta - ignorando
            # el centinela, etc por ahora.
            prompt_respuestas = [
                (centinela.pattern, centinela.respuesta)
                for centinela in corredor.correr.llamar_args[1]["centinelas"]
            ]
            assert prompt_respuestas == esperado

        def autoresponde_con_password_kwarg(self):
            # NOTE: Técnicamente duplica la prueba(s) unitty en pruebas centinela.
            esperado = [(self.mensaje_de_escape, "secreto\n")]
            self._esperar_respuestas(esperado, kwargs={"password": "secreto"})

        def honra_password_sudo_configurado(self):
            config = Config(anulaciones={"sudo": {"password": "secreto"}})
            esperado = [(self.mensaje_de_escape, "secreto\n")]
            self._esperar_respuestas(esperado, config=config)

        def sudo_password_kwarg_gana_sobre_config(self):
            config = Config(anulaciones={"sudo": {"password": "nosecreto"}})
            kwargs = {"password": "secreto"}
            esperado = [(self.mensaje_de_escape, "secreto\n")]
            self._esperar_respuestas(esperado, config=config, kwargs=kwargs)

        class auto_respuesta_se_combina_con_otras_respuestas:
            def setup(self):
                class CentinelaDummy(StreamCentinela):
                    def envio(self, stream):
                        pass

                self.klase_centinela = CentinelaDummy

            @patch(local_path)
            def kwarg_solo_se_agrega_a_kwarg(self, Local):
                corredor = Local.valor_de_retorno
                contexto = Contexto()
                centinela = self.klase_centinela()
                contexto.sudo("chubaca", centinelas=[centinela])
                # Cuando sudo() llamó c/cantinelas usuario-especificados,
                # añadimos los nuestro a esa lista
                centinelas = corredor.correr.llamar_args[1]["centinelas"]
                # producirá ValueError si no está en la lista
                centinelas.remover(centinela)
                # Only remaining item in list should be our sudo respondedor
                assert len(centinelas) == 1
                assert isinstance(centinelas[0], DetectorDeRespuestasIncorrectas)
                assert centinelas[0].pattern == self.mensaje_de_escape

            @patch(local_path)
            def config_only(self, Local):
                corredor = Local.valor_de_retorno
                # Setea una lista de centinelas controlada_por_configuración
                centinela = self.klase_centinela()
                anulaciones = {"correr": {"centinelas": [centinela]}}
                config = Config(anulaciones=anulaciones)
                Contexto(config=config).sudo("chubaca")
                # Espero que sudo() extrajo ese valor de configuración y lo
                # puso en el nivel kwarg. (Ver comentario en sudo() sobre 
                # porque...)
                centinelas = corredor.correr.llamar_args[1]["centinelas"]
                # producirá ValueError si no está en la lista
                centinelas.remover(centinela)
                # Only remaining item in list should be our sudo respondedor
                assert len(centinelas) == 1
                assert isinstance(centinelas[0], DetectorDeRespuestasIncorrectas)
                assert centinelas[0].pattern == self.mensaje_de_escape

            @patch(local_path)
            def uso_de_config_no_modifica_config(self, Local):
                corredor = Local.valor_de_retorno
                centinela = self.klase_centinela()
                anulaciones = {"correr": {"centinelas": [centinela]}}
                config = Config(anulaciones=anulaciones)
                Contexto(config=config).sudo("chubaca")
                # Aquí, 'centinelas' es el mismo objeto que se pasó a 
                # correr(centinelas=...).config uso no modifica config
                centinelas = corredor.correr.llamar_args[1]["centinelas"]
                # Queremos asegurarnos de que lo que está en la config que
                # acabamos de generar, no se ve afectado por la manipulación
                # realizada dentro de sudo().
                # Primero, que no son el mismo obj
                err = "¡Encontrado sudo() reusando lista de config centinelas directamente!"
                assert centinelas is not config.correr.centinelas, err
                # Y que la lista es como era antes (es decir, no es nuestro
                # centinela y el sudo()-añadido)
                err = "¡Nuestra lista de cantinelas config fue modificada!"
                assert config.correr.centinelas == [centinela], err

            @patch(local_path)
            def tanto_kwarg_como_config(self, Local):
                corredor = Local.valor_de_retorno
                # Setea una lista de centinelas controlada por la config.
                centinela_config = self.klase_centinela()
                anulaciones = {"correr": {"centinelas": [centinela_config]}}
                config = Config(anulaciones=anulaciones)
                # Y suministrar una lista DIFERENTE de centinelas controlados por kwarg
                centinela_kwarg = self.klase_centinela()
                Contexto(config=config).sudo("chubaca", centinelas=[centinela_kwarg])
                # Espere que el kwarg centinela y el interno fueran el resultado final.
                centinelas = corredor.correr.llamar_args[1]["centinelas"]
                # Se producirá ValueError si no está en la lista. .remover()
                # utiliza pruebas de identidad, por lo que dos instancias de
                # self.klase centinela serán valores diferentes aquí.
                centinelas.remover(centinela_kwarg)
                # Sólo el elemento restante en la lista debe ser nuestro respondedor sudo
                assert len(centinelas) == 1
                assert centinela_config not in centinelas  # Extra sanity
                assert isinstance(centinelas[0], DetectorDeRespuestasIncorrectas)
                assert centinelas[0].pattern == self.mensaje_de_escape

        @patch(local_path)
        def pasa_por_otro_kwargs_de_ejecucion(self, Local):
            corredor = Local.valor_de_retorno
            Contexto().sudo(
                "chubaca", echo=True, alarma=False, ocultar=True, codificacion="ascii"
            )
            assert corredor.correr.called, "sudo() nunca llamó a corredor.correr()!"
            kwargs = corredor.correr.llamar_args[1]
            assert kwargs["echo"] is True
            assert kwargs["alarma"] is False
            assert kwargs["ocultar"] is True
            assert kwargs["codificacion"] == "ascii"

        @patch(local_path)
        def devuelve_resultado_de_ejecucion(self, Local):
            corredor = Local.valor_de_retorno
            esperado = corredor.correr.valor_de_retorno
            resultado = Contexto().sudo("chubaca")
            err = "sudo() no devolvió el valor de retorno de correr()."
            assert resultado is esperado, err

        @subproceso_mock(salida="algo", salir=None)
        def provoca_un_fallo_de_autenticacion_cuando_se_detecta_un_fallo(self):
            with patch("dued.contexto.DetectorDeRespuestasIncorrectas") as klase:
                inaceptable = Mock(efecto_secundario=RespuestaNoAceptada)
                klase.valor_de_retorno.envio = inaceptable
                excepted = False
                try:
                    config = Config(anulaciones={"sudo": {"password": "nop"}})
                    Contexto(config=config).sudo("bah", ocultar=True)
                except FallaAutenticacion as e:
                    # Controles básicos de la cordura; la mayor parte de esto
                    # se prueba realmente en Las pruebas.
                    assert e.resultado.salida is None
                    esperado = "La contraseña enviada para solicitar '[sudo] password: ' fue rechazado."  # noqa
                    assert str(e) == esperado
                    excepted = True
                # No se puede usar except/else, ya que enmascara otros
                # excepciones reales, como ThreadErrors no controlados 
                # incorrectamente
                if not excepted:
                    assert False, "No levantó FallaAutenticacion!"

    def puede_ser_encurtido(self):
        c = Contexto()
        c.foo = {"bar": {"biz": ["baz", "buzz"]}}
        c2 = pickle.loads(pickle.dumps(c))
        assert c == c2
        assert c is not c2
        assert c.foo.bar.biz is not c2.foo.bar.biz


class ContextoMock_:
    def init_aun_actua_como_superclase_init(self):
        # No requiere args
        assert isinstance(ContextoSimulado().config, Config)
        config = Config(anulaciones={"foo": "bar"})
        # Posarg
        assert ContextoSimulado(config).config is config
        # Kwarg
        assert ContextoSimulado(config=config).config is config

    def kwargs_de_inicio_no_configs_utilizados_como_valores_de_retorno_para_metodos(self):
        c = ContextoSimulado(correr=Resultado("alguna salida"))
        assert c.correr("no tiene colchón").stdout == "alguna salida"

    def valor_devuelto_kwargs_puede_tomar_iterables_tambien(self):
        c = ContextoSimulado(correr=[Resultado("alguna salida"), Resultado("¡más!")])
        assert c.correr("no tiene colchón").stdout == "alguna salida"
        assert c.correr("todavía no tiene colchón").stdout == "¡más!"

    def valor_devuelto_kwargs_puede_ser_mapas_de_cadena_de_comandos(self):
        c = ContextoSimulado(correr={"foo": Resultado("bar")})
        assert c.correr("foo").stdout == "bar"

    def mapa_de_valores_devueltos_kwargs_tambien_puede_tomar_iterables(self):
        c = ContextoSimulado(correr={"foo": [Resultado("bar"), Resultado("biz")]})
        assert c.correr("foo").stdout == "bar"
        assert c.correr("foo").stdout == "biz"

    def metodos_sin_valores_kwarg_genera_NotImplementedError(self):
        with raises(NotImplementedError):
            ContextoSimulado().correr("onoz I did not anticipate this would happen")

    def sudo_tambien_cubierto(self):
        c = ContextoSimulado(sudo=Resultado(stderr="excelente"))
        assert c.sudo("no tiene colchón").stderr == "excelente"
        try:
            ContextoSimulado().sudo("bah")
        except NotImplementedError:
            pass
        else:
            assert False, "No obtuve un NotImplementedError para sudo!"

    class valores_devueltos_agotados_tambien_aumentan_NotImplementedError:
        def _espere_NotImplementedError(self, contexto):
            contexto.correr("algo")
            try:
                contexto.correr("algo")
            except NotImplementedError:
                pass
            else:
                assert False, "No levanto NotImplementedError"

        def single_value(self):
            self._espere_NotImplementedError(ContextoSimulado(correr=Resultado("bah")))

        def iterable(self):
            self._espere_NotImplementedError(ContextoSimulado(correr=[Resultado("bah")]))

        def mapping_to_single_value(self):
            self._espere_NotImplementedError(
                ContextoSimulado(correr={"algo": Resultado("bah")})
            )

        def mapping_to_iterable(self):
            self._espere_NotImplementedError(
                ContextoSimulado(correr={"algo": [Resultado("bah")]})
            )

    def tipo_kwarg_inesperado_produce_TypeError(self):
        with raises(TypeError):
            ContextoSimulado(correr=123)

    class puede_modificar_mapas_de_valores_devueltos_despues_de_la_creacion_de_instancias:
        class valores_de_creación_de_instancias_de_tipo_no_dic_producen_TypeErrors:
            class ningun_resultado_almacenado:
                def correr(self):
                    mc = ContextoSimulado()
                    with raises(TypeError):
                        mc.set_result_for("correr", "cualquier", Resultado("bar"))

                def sudo(self):
                    mc = ContextoSimulado()
                    with raises(TypeError):
                        mc.set_result_for("sudo", "cualquier", Resultado("bar"))

            class resultado_unico:
                def correr(self):
                    mc = ContextoSimulado(correr=Resultado("foo"))
                    with raises(TypeError):
                        mc.set_result_for("correr", "cualquier", Resultado("bar"))

                def sudo(self):
                    mc = ContextoSimulado(sudo=Resultado("foo"))
                    with raises(TypeError):
                        mc.set_result_for("sudo", "cualquier", Resultado("bar"))

            class resultado_iterable:
                def correr(self):
                    mc = ContextoSimulado(correr=[Resultado("foo")])
                    with raises(TypeError):
                        mc.set_result_for("correr", "cualquier", Resultado("bar"))

                def sudo(self):
                    mc = ContextoSimulado(sudo=[Resultado("foo")])
                    with raises(TypeError):
                        mc.set_result_for("sudo", "cualquier", Resultado("bar"))

        def correr(self):
            mc = ContextoSimulado(correr={"foo": Resultado("bar")})
            assert mc.correr("foo").stdout == "bar"
            mc.set_result_for("correr", "foo", Resultado("biz"))
            assert mc.correr("foo").stdout == "biz"

        def sudo(self):
            mc = ContextoSimulado(sudo={"foo": Resultado("bar")})
            assert mc.sudo("foo").stdout == "bar"
            mc.set_result_for("sudo", "foo", Resultado("biz"))
            assert mc.sudo("foo").stdout == "biz"
