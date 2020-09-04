from mock import Mock
import pytest

from dued import Coleccion, Config, Contexto, Ejecutor, Artefacto, llamar, artefacto
from dued.analizador import AnalizadorDeContexto, AnalizaResultado

from _util import confirmar


# TODO: porque does this not work as a decorator? probably relaxed's fault - but
# how?
marcapytest = pytest.mark.usefixtures("integracion")


class Ejecutor_:
    def setup(self):
        self.artefacto1 = Artefacto(Mock(valor_de_retorno=7))
        self.artefacto2 = Artefacto(Mock(valor_de_retorno=10), pre=[self.artefacto1])
        self.artefacto3 = Artefacto(Mock(), pre=[self.artefacto1])
        self.artefacto4 = Artefacto(Mock(valor_de_retorno=15), post=[self.artefacto1])
        self.contextualizado = Artefacto(Mock())
        colecc = Coleccion()
        colecc.ad_artefacto(self.artefacto1, nombre="artefacto1")
        colecc.ad_artefacto(self.artefacto2, nombre="artefacto2")
        colecc.ad_artefacto(self.artefacto3, nombre="artefacto3")
        colecc.ad_artefacto(self.artefacto4, nombre="artefacto4")
        colecc.ad_artefacto(self.contextualizado, nombre="contextualizado")
        self.ejecutor = Ejecutor(coleccion=colecc)

    class init:
        "__init__"

        def reconocer_coleccion_y_config(self):
            colecc = Coleccion()
            conf = Config()
            e = Ejecutor(coleccion=colecc, config=conf)
            assert e.coleccion is colecc
            assert e.config is conf

        def usa_config_en_blanco_de_forma_predeterminada(self):
            e = Ejecutor(coleccion=Coleccion())
            assert isinstance(e.config, Config)

        def puede_conceder_acceso_al_resultado_delanalisis_del_arg_principal(self):
            c = AnalizaResultado([AnalizadorDeContexto(nombre="miartefacto")])
            e = Ejecutor(coleccion=Coleccion(), nucleo=c)
            assert e.nucleo is c
            # prueba de consistenacia del acceso/uso del mundo real
            assert len(e.nucleo) == 1
            assert e.nucleo[0].nombre == "miartefacto"
            assert len(e.nucleo[0].args) == 0

        def el_resultado_del_análisis_del_arg_nucleo_establece_pordefecto_None(self):
            assert Ejecutor(coleccion=Coleccion()).nucleo is None

    class ejecutar:
        def caso_base(self):
            self.ejecutor.ejecutar("artefacto1")
            assert self.artefacto1.cuerpo.called

        def kwargs(self):
            k = {"foo": "bar"}
            self.ejecutor.ejecutar(("artefacto1", k))
            args = self.artefacto1.cuerpo.llamar_args[0]
            kwargs = self.artefacto1.cuerpo.llamar_args[1]
            assert isinstance(args[0], Contexto)
            assert len(args) == 1
            assert kwargs["foo"] == "bar"

        def artefactos_contextualizados_se_tregan_como_arg_al_analizador_de_contexto(self):
            self.ejecutor.ejecutar("contextualizado")
            args = self.contextualizado.cuerpo.llamar_args[0]
            assert len(args) == 1
            assert isinstance(args[0], Contexto)

        def artefactos_pordefecto_llamados_cuando_no_se_especifican_artefactos(self):
            # NOTE: cuando no hay artefactos Y no predeterminado, Programa imprimirá
            # la ayuda global. Simplemente no haremos nada en absoluto, lo cual está
            # bien por ahora.
            artefacto = Artefacto(Mock("default-artefacto"))
            colecc = Coleccion()
            colecc.ad_artefacto(artefacto, nombre="miartefacto", default=True)
            ejecutor = Ejecutor(coleccion=colecc)
            ejecutor.ejecutar()
            args = artefacto.cuerpo.llamar_args[0]
            assert isinstance(args[0], Contexto)
            assert len(args) == 1

    class pre_post_basico:
        "funcionalidad básica pre/post artefacto"

        def acciones_previas(self):
            self.ejecutor.ejecutar("artefacto2")
            assert self.artefacto1.cuerpo.call_count == 1

        def acciones_posteriores(self):
            self.ejecutor.ejecutar("artefacto4")
            assert self.artefacto1.cuerpo.call_count == 1

        def llamadas_pordefecto_a_args_vacios_siempre(self):
            pre_cuerpo, post_cuerpo = Mock(), Mock()
            t1 = Artefacto(pre_cuerpo)
            t2 = Artefacto(post_cuerpo)
            t3 = Artefacto(Mock(), pre=[t1], post=[t2])
            e = Ejecutor(coleccion=Coleccion(t1=t1, t2=t2, t3=t3))
            e.ejecutar(("t3", {"algo": "bah"}))
            for cuerpo in (pre_cuerpo, post_cuerpo):
                args = cuerpo.llamar_args[0]
                assert len(args) == 1
                assert isinstance(args[0], Contexto)

        def _llamar_objs(self):
            # Setup
            pre_cuerpo, post_cuerpo = Mock(), Mock()
            t1 = Artefacto(pre_cuerpo)
            t2 = Artefacto(post_cuerpo)
            t3 = Artefacto(
                Mock(),
                pre=[llamar(t1, 5, foo="bar")],
                post=[llamar(t2, 7, biz="baz")],
            )
            c = Coleccion(t1=t1, t2=t2, t3=t3)
            e = Ejecutor(coleccion=c)
            e.ejecutar("t3")
            # Pre-artefacto asserts
            args, kwargs = pre_cuerpo.llamar_args
            assert kwargs == {"foo": "bar"}
            assert isinstance(args[0], Contexto)
            assert args[1] == 5
            # Post-artefacto asserts
            args, kwargs = post_cuerpo.llamar_args
            assert kwargs == {"biz": "baz"}
            assert isinstance(args[0], Contexto)
            assert args[1] == 7

        def llamar_objs_jugar_bien_con_args_de_contexto(self):
            self._llamar_objs()

    class deduplicacion_y_encadenamiento:
        def encadenamiento_primero_en_profundidad(self):
            confirmar(
                "-c profundo_primero desplegar",
                salida="""
Limpieza HTML
Limpieza de archivos .tar.gz
Limpio todo
Creando directorios
Construyendo
Desplegando
Preparando para pruebas
Pruebas
""".lstrip(),
            )

        def _confirmar(self, args, esperado):
            confirmar("-c integracion {}".format(args), salida=esperado.lstrip())

        class ganchos_adyacentes:
            def deduping(self):
                self._confirmar(
                    "biz",
                    """
foo
bar
biz
post1
post2
""",
                )

            def no_deduping(self):
                self._confirmar(
                    "--no-dedupe biz",
                    """
foo
foo
bar
biz
post1
post2
post2
""",
                )

        class ganchos_no_adyacentes:
            def deduping(self):
                self._confirmar(
                    "boz",
                    """
foo
bar
boz
post2
post1
""",
                )

            def no_deduping(self):
                self._confirmar(
                    "--no-dedupe boz",
                    """
foo
bar
foo
boz
post2
post1
post2
""",
                )

        # AKA, a (foo) (foo -> bar) scenario arising from foo + bar
        class artefactos_adyacentes_de_nivel_superior:
            def deduping(self):
                self._confirmar(
                    "foo bar",
                    """
foo
bar
""",
                )

            def no_deduping(self):
                self._confirmar(
                    "--no-dedupe foo bar",
                    """
foo
foo
bar
""",
                )

        # AKA (foo -> bar) (foo)
        class artefactos_de_nivel_superior_no_adyacentes:
            def deduping(self):
                self._confirmar(
                    "foo bar",
                    """
foo
bar
""",
                )

            def no_deduping(self):
                self._confirmar(
                    "--no-dedupe foo bar",
                    """
foo
foo
bar
""",
                )

        def desduplicacion_trata_diferentes_llamadas_al_mismo_artefacto_de_manera_diferente(self):
            cuerpo = Mock()
            t1 = Artefacto(cuerpo)
            pre = [llamar(t1, 5), llamar(t1, 7), llamar(t1, 5)]
            t2 = Artefacto(Mock(), pre=pre)
            c = Coleccion(t1=t1, t2=t2)
            e = Ejecutor(coleccion=c)
            e.ejecutar("t2")
            # No llama al segundo t1(5)
            lista_de_parametros = []
            for llamada_al_cuerpo in cuerpo.llamada_a_lista_de_args:
                assert isinstance(llamada_al_cuerpo[0][0], Contexto)
                lista_de_parametros.append(llamada_al_cuerpo[0][1])
            assert set(lista_de_parametros) == {5, 7}

    class coleccion_conducida_por_config:
        "concerniente a Coleccion controlada desde la configuración"

        def config_de_la_colección_de_manos_al_contexto(self):
            @artefacto
            def miartefacto(c):
                assert c.mi_clave == "valor"

            c = Coleccion(miartefacto)
            c.configurar({"mi_clave": "valor"})
            Ejecutor(coleccion=c).ejecutar("miartefacto")

        def artefacto_de_la_mano_con_config_especifica_al_contexto(self):
            @artefacto
            def miartefacto(c):
                assert c.mi_clave == "valor"

            @artefacto
            def otroartefacto(c):
                assert c.mi_clave == "otrovalor"

            interior1 = Coleccion("interior1", miartefacto)
            interior1.configurar({"mi_clave": "valor"})
            interios2 = Coleccion("interios2", otroartefacto)
            interios2.configurar({"mi_clave": "otrovalor"})
            c = Coleccion(interior1, interios2)
            e = Ejecutor(coleccion=c)
            e.ejecutar("interior1.miartefacto", "interios2.otroartefacto")

        def config_de_subcoleccion_funciona_con_artefactos_pordefecto(self):
            @artefacto(default=True)
            def miartefacto(c):
                assert c.mi_clave == "valor"

            # Configura un artefacto "conocido como" sub.artefacto que puede
            # ser llamado simplemente 'sub' debido a que es predeterminado.
            sub = Coleccion("sub", miartefacto=miartefacto)
            sub.configurar({"mi_clave": "valor"})
            principal = Coleccion(sub=sub)
            # Ejecutar a través de coleccion nombre por defecto 'artefacto'.
            Ejecutor(coleccion=principal).ejecutar("sub")

    class retorna_el_valor_devuelto_del_artefacto_especificado:
        def caso_base(self):
            assert self.ejecutor.ejecutar("artefacto1") == {self.artefacto1: 7}

        def con_pre_artefactos(self):
            resultado = self.ejecutor.ejecutar("artefacto2")
            assert resultado == {self.artefacto1: 7, self.artefacto2: 10}

        def con_post_artefactos(self):
            resultado = self.ejecutor.ejecutar("artefacto4")
            assert resultado == {self.artefacto1: 7, self.artefacto4: 15}

    class autoimprimiendo:
        def pordefecto_esta_apagado_y_no_hay_salida(self):
            confirmar("-c autoimpresion nop", salida="")

        def las_impresiones_devuelven_el_valor_a_stdout_cuando_esta_prendido(self):
            confirmar("-c autoimpresion yup", salida="¡es la fuerza!\n")

        def las_impresiones_devuelven_el_valor_a_stdout_cuando_esta_prendido_y_en_la_coleccion(self):
            confirmar("-c autoimpresion sub.yup", salida="¡es la fuerza!\n")

        def no_dispara_en_pre_artefactos(self):
            confirmar("-c autoimpresion pre-chequeo", salida="")

        def no_dispara_en_post_artefactos(self):
            confirmar("-c autoimpresion post-chequeo", salida="")

    class contexto_entre_artefactos_y_uso_compartido_de_config:
        def contexto_es_nuevo_pero_la_config_es_la_misma(self):
            @artefacto
            def artefacto1(c):
                return c

            @artefacto
            def artefacto2(c):
                return c

            colecc = Coleccion(artefacto1, artefacto2)
            ret = Ejecutor(coleccion=colecc).ejecutar("artefacto1", "artefacto2")
            c1 = ret[artefacto1]
            c2 = ret[artefacto2]
            assert c1 is not c2
            # TODO: eventualmente, es posible que deseemos cambiar esto 
            # nuevamente, siempre que los valores efectivos dentro de la
            #  configuración sigan coincidiendo ...? Ehh
            assert c1.config is c2.config

        def nuevos_datos_de_config_se_conservan_entre_artefactos(self):
            @artefacto
            def artefacto1(c):
                c.foo = "bar"
                # NOTE: Devuelto para la inspección de prueba, no como 
                # mecanismo de compartir datos!
                return c

            @artefacto
            def artefacto2(c):
                return c

            colecc = Coleccion(artefacto1, artefacto2)
            ret = Ejecutor(coleccion=colecc).ejecutar("artefacto1", "artefacto2")
            c2 = ret[artefacto2]
            assert "foo" in c2.config
            assert c2.foo == "bar"

        def la_mutacion_de_config_se_conserva_entre_artefactos(self):
            @artefacto
            def artefacto1(c):
                c.config.correr.echo = True
                # NOTE: devuelto para inspección de prueba, ¡no como 
                # mecanismo para compartir datos!
                return c

            @artefacto
            def artefacto2(c):
                return c

            colecc = Coleccion(artefacto1, artefacto2)
            ret = Ejecutor(coleccion=colecc).ejecutar("artefacto1", "artefacto2")
            c2 = ret[artefacto2]
            assert c2.config.correr.echo is True

        def la_eliminacion_de_la_config_se_conserva_entre_artefactos(self):
            @artefacto
            def artefacto1(c):
                del c.config.correr.echo
                # NOTE: devuelto para inspección de prueba, ¡no como 
                # mecanismo para compartir datos!
                return c

            @artefacto
            def artefacto2(c):
                return c

            colecc = Coleccion(artefacto1, artefacto2)
            ret = Ejecutor(coleccion=colecc).ejecutar("artefacto1", "artefacto2")
            c2 = ret[artefacto2]
            assert "echo" not in c2.config.correr
