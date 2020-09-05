import copy

from pytest import raises

from dued.analizador import Argumento, Contexto
from dued.artefactos import artefacto
from dued.coleccion import Coleccion


class Contexto_:
    "AnalizadorDeContexto"  # bah

    def puede_tener_un_nombre(self):
        c = Contexto(nombre="nombredeartefacto")
        assert c.nombre == "nombredeartefacto"

    def puede_tener_un_alias(self):
        c = Contexto(nombre="realname", alias=("otronombre", "yup"))
        assert "otronombre" in c.alias

    def puede_dar_arg_lista_al_momento_de_inicio(self):
        a1 = Argumento("foo")
        a2 = Argumento("bar")
        c = Contexto(nombre="nombre", args=(a1, a2))
        assert c.args["foo"] is a1

    # TODO: conciliar este tipo de organización de prueba con las pruebas
    # orientadas a .banderas dentro de 'agregar_arg'. Parte de este 
    # comportamiento está técnicamente impulsado por agregar_arg.
    class args:
        def setup(self):
            self.c = Contexto(
                args=(
                    Argumento("foo"),
                    Argumento(nombres=("bar", "biz")),
                    Argumento("baz", nombre_de_atributo="wat"),
                )
            )

        def expuesto_como_dic(self):
            assert "foo" in self.c.args.keys()

        def expuesto_como_Lexicon(self):
            assert self.c.args.bar == self.c.args["bar"]

        def dic_args_incluye_todos_los_nombres_de_arg(self):
            for x in ("foo", "bar", "biz"):
                assert x in self.c.args

        def nombres_de_atrib_de_arg_aparecen_en_args_pero_no_en_banderas(self):
            # Ambos aparecen como argumentos "orientados a Python"
            for x in ("baz", "wat"):
                assert x in self.c.args
            # Pero nombre_de_atributo es solo para acceso a Python y no
            # se muestra al analizador.
            assert "wat" not in self.c.banderas

    class agregar_arg:
        def setup(self):
            self.c = Contexto()

        def puede_tomar_una_instancia_de_Argumento(self):
            a = Argumento(nombres=("foo",))
            self.c.agregar_arg(a)
            assert self.c.args["foo"] is a

        def puede_tomar_el_nombre_arg(self):
            self.c.agregar_arg("foo")
            assert "foo" in self.c.args

        def puede_tomar_kwargs_para_un_solo_Argumento(self):
            self.c.agregar_arg(nombres=("foo", "bar"))
            assert "foo" in self.c.args and "bar" in self.c.args

        def genera_ValueError_en_duplicado(self):
            self.c.agregar_arg(nombres=("foo", "bar"))
            with raises(ValueError):
                self.c.agregar_arg(nombre="bar")

        def agrega_un_nombre_similarabandera_a_las_banderas_de_puntos(self):
            "agrega un nombre banderalike a .banderas"
            self.c.agregar_arg("foo")
            assert "--foo" in self.c.banderas

        def agrega_todos_nombres_a_punto_banderas(self):
            "agrega todos los nombres a .banderas"
            self.c.agregar_arg(nombres=("foo", "bar"))
            assert "--foo" in self.c.banderas
            assert "--bar" in self.c.banderas

        def agrega_true_a_bools_a_banderas_inversas(self):
            self.c.agregar_arg(nombre="mibandera", default=True, tipo=bool)
            assert "--mibandera" in self.c.banderas
            assert "--no-mibandera" in self.c.banderas_inversas
            assert self.c.banderas_inversas["--no-mibandera"] == "--mibandera"

        def banderas_inv_trabajan_bien_con_nombres_guionbajo_en_artefactos(self):
            # Use un Artefacto aquí en lugar de crear un argumento en 
            # bruto(raw), estamos probando parcialmente la transformación de
            # Artefacto.obtener_argumentos() 'de nombres-subrayados aquí. Sí, eso
            # lo convierte en una prueba de integración, pero es bueno probarlo
            # aquí en este nivel y no solo en cli pruebas.
            @artefacto
            def miartefacto(c, opcion_guionbajo=True):
                pass

            self.c.agregar_arg(miartefacto.obtener_argumentos()[0])
            banderas = self.c.banderas_inversas["--no-opcion-guionbajo"]
            assert banderas == "--opcion-guionbajo"

        def convierte_los_nombres_de_un_solo_caracter_en_banderas_cortas(self):
            self.c.agregar_arg("f")
            assert "-f" in self.c.banderas
            assert "--f" not in self.c.banderas

        def agrega_args_posicionales_a_args_posicionales(self):
            self.c.agregar_arg(nombre="pos", posicional=True)
            assert self.c.args_posicionales[0].nombre == "pos"

        def args_posicionales_vacios_cuando_no_se_da_ninguno(self):
            assert len(self.c.args_posicionales) == 0

        def args_posicionales_llenos_en_orden(self):
            self.c.agregar_arg(nombre="pos1", posicional=True)
            assert self.c.args_posicionales[0].nombre == "pos1"
            self.c.agregar_arg(nombre="abc", posicional=True)
            assert self.c.args_posicionales[1].nombre == "abc"

        def modificaciones_posicionales_de_los_args_afectan_la_copia_de_los_args(self):
            self.c.agregar_arg(nombre="hrm", posicional=True)
            assert self.c.args["hrm"].valor == self.c.args_posicionales[0].valor
            self.c.args_posicionales[0].valor = 17
            assert self.c.args["hrm"].valor == self.c.args_posicionales[0].valor

    class deepcopy:
        "__deepcopy__ copia profunda"

        def setup(self):
            self.arg = Argumento("--booleano")
            self.orig = Contexto(
                nombre="miartefacto", args=(self.arg,), alias=("otronombre",)
            )
            self.nuevo = copy.deepcopy(self.orig)

        def devuelve_copia_correcta(self):
            assert self.nuevo is not self.orig
            assert self.nuevo.nombre == "miartefacto"
            assert "otronombre" in self.nuevo.alias

        def incluye_argumentos(self):
            assert len(self.nuevo.args) == 1
            assert self.nuevo.args["--booleano"] is not self.arg

        def modificaciones_a_los_argumentos_copiados_no_tocan_los_originales(self):
            nuevo_arg = self.nuevo.args["--booleano"]
            nuevo_arg.valor = True
            assert nuevo_arg.valor
            assert not self.arg.valor

    class ayuda_para:
        def setup(self):
            # Contexto normal, no relacionado con artefacto/colección
            self.ordinario = Contexto(
                args=(Argumento("foo"), Argumento("bar", help="bar el baz"))
            )
            # Artefacto/Colección Contexto generado 
            # (expondrá banderas n tales)
            @artefacto(help={"otroarg": "otra ayuda"}, opcional=["valopc"])
            def miartefacto(c, miarg, otroarg, valopc, intval=5):
                pass

            col = Coleccion(miartefacto)
            self.tasked = col.a_contextos()[0]

        def genera_ValueError_para_valores_no_bandera(self):
            with raises(ValueError):
                self.ordinario.ayuda_para("foo")

        def ordinario_sin_cadenadeayuda(self):
            assert self.ordinario.ayuda_para("--foo") == ("--foo=CADENA", "")

        def ordinario_con_cadenadeayuda(self):
            resultado = self.ordinario.ayuda_para("--bar")
            assert resultado == ("--bar=CADENA", "bar el baz")

        def artefacto_impulsado_con_cadenadeayuda(self):
            resultado = self.tasked.ayuda_para("--otroarg")
            assert resultado == ("-o CADENA, --otroarg=CADENA", "otra ayuda")

        # Sí, las siguientes 3 pruebas son idénticas en forma, pero
        # técnicamente prueban comportamientos diferentes. HERPIN Y
        # DERPIN
        def artefacto_impulsado_sin_cadenadeayuda(self):
            resultado = self.tasked.ayuda_para("--miarg")
            assert resultado == ("-m CADENA, --miarg=CADENA", "")

        def forma_corta_antes_que_forma_larga(self):
            resultado = self.tasked.ayuda_para("--miarg")
            assert resultado == ("-m CADENA, --miarg=CADENA", "")

        def signo_igual_solo_para_forma_larga(self):
            resultado = self.tasked.ayuda_para("--miarg")
            assert resultado == ("-m CADENA, --miarg=CADENA", "")

        def tipo_de_mapa_de_marcador_de_posición(self):
            # Strings
            helpfor = self.tasked.ayuda_para("--miarg")
            assert helpfor == ("-m CADENA, --miarg=CADENA", "")
            # Ints
            helpfor = self.tasked.ayuda_para("--intval")
            assert helpfor == ("-i INT, --intval=INT", "")
            # TODO: others

        def entradas_de_banderacorta_también_funcionan(self):
            m = self.tasked.ayuda_para("-m")
            miarg = self.tasked.ayuda_para("--miarg")
            assert m == miarg

        def valores_opcionales_usan_corchetes(self):
            resultado = self.tasked.ayuda_para("--valopc")
            assert resultado == ("-p [CADENA], --valopc[=CADENA]", "")

        def guiionbajo_args(self):
            c = Contexto(args=(Argumento("yo_tengo_guionesbajos", help="yup"),))
            resultado = c.ayuda_para("--yo-tengo-guionesbajos")
            assert resultado == ("--yo-tengo-guionesbajos=CADENA", "yup")

        def args_por_defecto_verdad(self):
            c = Contexto(args=(Argumento("esverdad", tipo=bool, default=True),))
            assert c.ayuda_para("--esverdad") == ("--[no-]esverdad", "")

    class help_tuplas:
        def devuelve_lista_de_tuplas_de_ayuda(self):
            # TODO: considere rehacer ayuda_para para ser más flexible en la
            # entrada --arg value o bandera; o incluso objetos Argumento. ?
            # @artefacto (ayuda = {"otroarg": "otra ayuda"})
            @artefacto(help={"otroarg": "otra ayuda"})
            def miartefacto(c, miarg, otroarg):
                pass

            c = Coleccion(miartefacto).a_contextos()[0]
            esperado = [c.ayuda_para("--miarg"), c.ayuda_para("--otroarg")]
            assert c.help_tuplas() == esperado

        def  _assert_de_orden(self, name_tuples, expected_bandera_order):
            c = Contexto(args=[Argumento(nombres=x) for x in name_tuples])
            esperado = [c.ayuda_para(x) for x in expected_bandera_order]
            assert c.help_tuplas() == esperado

        def ordena_alfabeticamente_por_banderacorta_primero(self):
            # Where shortbanderas exist, they take precedence
            self. _assert_de_orden(
                [("zarg", "a"), ("arg", "z")], ["--zarg", "--arg"]
            )

        def caso_ignorado_durante_la_clasificacion(self):
            self. _assert_de_orden(
                [("a",), ("B",)],
                # In raw cmp() uppercase would come before lowercase,
                # and we'd get ['-B', '-a']
                ["-a", "-B"],
            )

        def minusculas_gana_cuando_los_valores_son_identicos_de_lo_contrario(self):
            self. _assert_de_orden([("V",), ("v",)], ["-v", "-V"])

        def ordena_alfabéticamente_por_banderalarga_cuando_no_hay_bandacorta(self):
            # Where no shortbandera, sorts by longbandera
            self. _assert_de_orden(
                [("otroarg",), ("arglargo",)], ["--arglargo", "--otroarg"]
            )

        def clasifica_la_salida_de_ayuda_heterogenea_con_opciones_de_solo_banderalarga_primero(
            self
        ):  # noqa
            # Cuando las dos opciones anteriores se mezclan, las opciones
            # de solo bandera larga son lo primero.
            # P.ej.:
            #   --alfa
            #   --beta
            #   -a, --aaaagh
            #   -b, --bah
            #   -c
            self. _assert_de_orden(
                [("c",), ("a", "aaagh"), ("b", "bah"), ("beta",), ("alfa",)],
                ["--alfa", "--beta", "-a", "-b", "-c"],
            )

        def opciones_corelike_mixtas(self):
            self. _assert_de_orden(
                [
                    ("V", "version"),
                    ("c", "coleccion"),
                    ("h", "help"),
                    ("l", "lista"),
                    ("r", "raiz"),
                ],
                ["-c", "-h", "-l", "-r", "-V"],
            )

    class faltan_argumentos_posicionales:
        def representa_valores_perdidos_de_argumentos_posicionales(self):
            arg1 = Argumento("arg1", posicional=True)
            arg2 = Argumento("arg2", posicional=False)
            arg3 = Argumento("arg3", posicional=True)
            c = Contexto(nombre="foo", args=(arg1, arg2, arg3))
            assert c.faltan_argumentos_posicionales == [arg1, arg3]
            c.args_posicionales[0].valor = "wat"
            assert c.faltan_argumentos_posicionales == [arg3]
            c.args_posicionales[1].valor = "hrm"
            assert c.faltan_argumentos_posicionales == []

    class str:
        "__str__"

        def sin_args_la_salida_es_simple(self):
            assert str(Contexto("foo")) == "<analizador/Contexto 'foo'>"

        def args_se_muestran_como_repr(self):
            cadena = str(Contexto("bar", args=[Argumento("arg1")]))
            assert (
                cadena == "<analizador/Contexto 'bar': {'arg1': <Argumento: arg1>}>"
            )  # noqa
