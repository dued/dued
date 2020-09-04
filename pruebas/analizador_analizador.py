from pytest import raises

from dued.analizador import Analizador, Contexto, Argumento, ErrorDeAnalisis


class Parser_:
    def puede_tomar_contexto_inicial(self):
        c = Contexto()
        p = Analizador(inicial=c)
        assert p.inicial == c

    def puede_tomar_contexto_inicial_y_otros(self):
        c1 = Contexto("foo")
        c2 = Contexto("bar")
        p = Analizador(inicial=Contexto(), contextos=[c1, c2])
        assert p.contextos["foo"] == c1
        assert p.contextos["bar"] == c2

    def puede_tomar_solo_otros_contextos(self):
        c = Contexto("foo")
        p = Analizador(contextos=[c])
        assert p.contextos["foo"] == c

    def puede_tomar_solo_contextos_como_arg_sin_palabras_clave(self):
        c = Contexto("foo")
        p = Analizador([c])
        assert p.contextos["foo"] == c

    def genera_ValueError_para_Contextos_sin_nombre_en_contextos(self):
        with raises(ValueError):
            Analizador(inicial=Contexto(), contextos=[Contexto()])

    def genera_error_para_conflictos_de_nombres_de_contexto(self):
        with raises(ValueError):
            Analizador(contextos=(Contexto("foo"), Contexto("foo")))

    def genera_error_para_el_alias_de_contexto_y_los_conflictos_de_nombres(self):
        with raises(ValueError):
            Analizador((Contexto("foo", alias=("bar",)), Contexto("bar")))

    def genera_error_para_el_nombre_de_contexto_y_los_conflictos_de_alias(self):
        # Es decir inverso de lo anterior, que es una ruta de código diferente.
        with raises(ValueError):
            Analizador((Contexto("foo"), Contexto("bar", alias=("foo",))))

    def toma_ignorar_kwarg_desconocido(self):
        Analizador(ignorar_desconocido=True)

    def ignorar_defaults_desconocido_a_False(self):
        assert Analizador().ignorar_desconocido is False

    class analizar_args:
        def analiza_lista_de_cadenas_sys_argv_style(self):
            "analiza la lista de cadenas sys.argv-style"
            # Pruebas no hinchables FTL
            miartefacto = Contexto(nombre="miartefacto")
            miartefacto.agregar_arg("arg")
            p = Analizador(contextos=[miartefacto])
            p.analizar_args(["miartefacto", "--arg", "valor"])

        def devuelve_solo_contextos_mencionados(self):
            artefacto1 = Contexto("miartefacto")
            artefacto2 = Contexto("otroartefacto")
            resultado = Analizador((artefacto1, artefacto2)).analizar_args(["otroartefacto"])
            assert len(resultado) == 1
            assert resultado[0].nombre == "otroartefacto"

        def genera_error_si_encuentran_contextos_desconocidos(self):
            with raises(ErrorDeAnalisis):
                Analizador().analizar_args(["foo", "bar"])

        def sin_analizar_no_comparte_el_estado(self):
            r = Analizador(ignorar_desconocido=True).analizar_args(["self"])
            assert r.sin_analizar == ["self"]
            r2 = Analizador(ignorar_desconocido=True).analizar_args(["contenido"])
            assert r.sin_analizar == ["self"]  # NOT ['self', 'contenido']
            assert r2.sin_analizar == ["contenido"]  # NOT ['self', 'contenido']

        def ignorar_los_retornos_desconocidos_sin_analizar_argv_en_su_lugar(self):
            r = Analizador(ignorar_desconocido=True).analizar_args(["foo", "bar", "--baz"])
            assert r.sin_analizar == ["foo", "bar", "--baz"]

        def ignorar_desconocido_no_muta_resto_de_argv(self):
            p = Analizador([Contexto("ugh")], ignorar_desconocido=True)
            r = p.analizar_args(["ugh", "what", "-nowai"])
            # NOT: ['what', '-n', '-a', '-a', '-i']
            assert r.sin_analizar == ["what", "-nowai"]

        def siempre_incluye_contexto_inicial_si_se_le_dio_uno(self):
            # Incluso si no se vieron banderas nucleo/iniciales
            t1 = Contexto("t1")
            init = Contexto()
            resultado = Analizador((t1,), inicial=init).analizar_args(["t1"])
            assert resultado[0].nombre is None
            assert resultado[1].nombre == "t1"

        def contextos_devueltos_estan_en_orden_dado(self):
            t1, t2 = Contexto("t1"), Contexto("t2")
            r = Analizador((t1, t2)).analizar_args(["t2", "t1"])
            assert [x.nombre for x in r] == ["t2", "t1"]

        def argumentos_miembros_de_contexto_devueltos_contienen_valores_dados(self):
            c = Contexto("miartefacto", args=(Argumento("booleano", tipo=bool),))
            resultado = Analizador((c,)).analizar_args(["miartefacto", "--booleano"])
            assert resultado[0].args["booleano"].valor is True

        def bools_inversos_se_setean_correctamente(self):
            arg = Argumento("miarg", tipo=bool, default=True)
            c = Contexto("miartefacto", args=(arg,))
            r = Analizador((c,)).analizar_args(["miartefacto", "--no-miarg"])
            assert r[0].args["miarg"].valor is False

        def argumentos_que_toman_valores_obtienen_defaults_anulados_correctamente(
            self
        ):  # noqa
            args = (Argumento("arg", tipo=str), Argumento("arg2", tipo=int))
            c = Contexto("miartefacto", args=args)
            argv = ["miartefacto", "--arg", "mival", "--arg2", "25"]
            resultado = Analizador((c,)).analizar_args(argv)
            assert resultado[0].args["arg"].valor == "mival"
            assert resultado[0].args["arg2"].valor == 25

        def argumentos_devueltos_no_dados_contienen_valores_pordefecto(self):
            # Es decir un Contexto con argumentos A y B, dued sin mención 
            # de B, debería resultar en B existente en el resultado, con 
            # None, o el argumento no existe.
            a = Argumento("nombre", tipo=str)
            b = Argumento("edad", default=7)
            c = Contexto("miartefacto", args=(a, b))
            Analizador((c,)).analizar_args(["miartefacto", "--nombre", "blah"])
            assert c.args["edad"].valor == 7

        def devuelve_el_resto(self):
            "retorna -- style resto del trozo de cadena"
            r = Analizador((Contexto("foo"),)).analizar_args(
                ["foo", "--", "bar", "biz"]
            )
            assert r.remanente == "bar biz"

        def clona_contexto_inicial(self):
            a = Argumento("foo", tipo=bool)
            assert a.valor is None
            c = Contexto(args=(a,))
            p = Analizador(inicial=c)
            assert p.inicial is c
            r = p.analizar_args(["--foo"])
            assert p.inicial is c
            c2 = r[0]
            assert c2 is not c
            a2 = c2.args["foo"]
            assert a2 is not a
            assert a.valor is None
            assert a2.valor is True

        def clona_sin_contextos_iniciales(self):
            a = Argumento("foo")
            assert a.valor is None
            c = Contexto(nombre="miartefacto", args=(a,))
            p = Analizador(contextos=(c,))
            assert p.contextos["miartefacto"] is c
            r = p.analizar_args(["miartefacto", "--foo", "val"])
            assert p.contextos["miartefacto"] is c
            c2 = r[0]
            assert c2 is not c
            a2 = c2.args["foo"]
            assert a2 is not a
            assert a.valor is None
            assert a2.valor == "val"

        class errores_de_analisis:
            def setup(self):
                self.p = Analizador([Contexto(nombre="foo", args=[Argumento("bar")])])

            def valores_de_bandera_que_faltan_generan_ParseError(self):
                with raises(ErrorDeAnalisis):
                    self.p.analizar_args(["foo", "--bar"])

            def adjunta_contexto_a_ParseErrors(self):
                try:
                    self.p.analizar_args(["foo", "--bar"])
                except ErrorDeAnalisis as e:
                    assert e.contexto is not None

            def contexto_adjunto_es_None_fuera_de_contextos(self):
                try:
                    Analizador().analizar_args(["wat"])
                except ErrorDeAnalisis as e:
                    assert e.contexto is None

        class argumentos_posicionales:
            def _basic(self):
                arg = Argumento("pos", posicional=True)
                miartefacto = Contexto(nombre="miartefacto", args=[arg])
                return Analizador(contextos=[miartefacto])

            def arg_posicional_unico(self):
                r = self._basic().analizar_args(["miartefacto", "posval"])
                assert r[0].args["pos"].valor == "posval"

            def arg_posicional_omitido_genera_ParseError(self):
                try:
                    self._basic().analizar_args(["miartefacto"])
                except ErrorDeAnalisis as e:
                    esperado = "'miartefacto' no recibió los argumentos posicionales requeridos: 'pos'"  # noqa
                    assert str(e) == esperado
                else:
                    assert False, "No subió ErrorDeAnalisis!"

            def arg_posicionales_omitidos_genera_ParseError(self):
                try:
                    arg = Argumento("pos", posicional=True)
                    arg2 = Argumento("maspos", posicional=True)
                    miartefacto = Contexto(nombre="miartefacto", args=[arg, arg2])
                    Analizador(contextos=[miartefacto]).analizar_args(["miartefacto"])
                except ErrorDeAnalisis as e:
                    esperado = "'miartefacto' no recibió los argumentos posicionales requeridos: 'pos', 'maspos'"  # noqa
                    assert str(e) == esperado
                else:
                    assert False, "No subió ErrorDeAnalisis!"

            def args_posicionales_comen_nombres_de_contexto_validos_de_otra_manera(self):
                miartefacto = Contexto(
                    "miartefacto",
                    args=[
                        Argumento("pos", posicional=True),
                        Argumento("nonpos", default="default"),
                    ],
                )
                Contexto("lolwut")
                resultado = Analizador([miartefacto]).analizar_args(["miartefacto", "lolwut"])
                r = resultado[0]
                assert r.args["pos"].valor == "lolwut"
                assert r.args["nonpos"].valor == "default"
                assert len(resultado) == 1  # Not 2

            def args_posicionales_todavia_se_pueden_dar_como_banderas(self):
                # AKA "argumentos posicionales pueden venir en cualquier parte del contexto"
                pos1 = Argumento("pos1", posicional=True)
                pos2 = Argumento("pos2", posicional=True)
                nonpos = Argumento("nonpos", posicional=False, default="jeje")
                miartefacto = Contexto("miartefacto", args=[pos1, pos2, nonpos])
                assert miartefacto.args_posicionales == [pos1, pos2]
                r = Analizador([miartefacto]).analizar_args(
                    [
                        "miartefacto",
                        "--nonpos",
                        "hum",
                        "--pos2",
                        "pos2val",
                        "pos1val",
                    ]
                )[0]
                assert r.args["pos1"].valor == "pos1val"
                assert r.args["pos2"].valor == "pos2val"
                assert r.args["nonpos"].valor == "hum"

        class equals_signs:
            def _comparar(self, argname, dued, valor):
                c = Contexto("miartefacto", args=(Argumento(argname, tipo=str),))
                r = Analizador((c,)).analizar_args(["miartefacto", dued])
                assert r[0].args[argname].valor == valor

            def maneja_igual_estilo_banderas_largas(self):
                self._comparar("foo", "--foo=bar", "bar")

            def maneja_igual_estilo_banderas_cortas(self):
                self._comparar("f", "-f=bar", "bar")

            def no_requiere_escapar_signos_iguales_en_valor(self):
                self._comparar("f", "-f=biz=baz", "biz=baz")

        def maneja_multiples_banderas_booleanas_por_contexto(self):
            c = Contexto(
                "miartefacto",
                args=(Argumento("foo", tipo=bool), Argumento("bar", tipo=bool)),
            )
            r = Analizador([c]).analizar_args(["miartefacto", "--foo", "--bar"])
            a = r[0].args
            assert a.foo.valor is True
            assert a.bar.valor is True

    class valores_arg_opcionales:
        def setup(self):
            self.analizador = self._analizador()

        def _analizador(self, arguments=None):
            if arguments is None:
                arguments = (
                    Argumento(
                        nombres=("foo", "f"), opcional=True, default="midefault"
                    ),
                )
            self.contexto = Contexto("miartefacto", args=arguments)
            self.analizador = Analizador([self.contexto])
            return self.analizador

        def _analizar(self, argstr, analizador=None):
            analizador = analizador or self.analizador
            return analizador.analizar_args(["miartefacto"] + argstr.split())

        def _confirmar(self, argstr, esperado, analizador=None):
            resultado = self._analizar(argstr, analizador)
            assert resultado[0].args.foo.valor == esperado

        def ningun_valor_se_convierte_en_True_no_es_el_valor_por_defecto(self):
            self._confirmar("--foo", True)
            self._confirmar("-f", True)

        def valor_dado_se_conserva_normalmente(self):
            for argstr in (
                "--foo cualquier",
                "--foo=cualquier",
                "-f cualquier",
                "-f=cualquier",
            ):
                self._confirmar(argstr, "cualquier")

        def no_se_da_en_absoluto_utiliza_el_valor_por_defecto(self):
            self._confirmar("", "midefault")

        class controles_de_cordura_y_ambiguedad:
            def _prueba_para_ambiguedad(self, dued, analizador=None):
                msj = "Es ambiguo"
                try:
                    self._analizar(dued, analizador or self.analizador)
                # Resultado esperado
                except ErrorDeAnalisis as e:
                    assert msj in str(e)
                # No exception occurred at all? Bollocks.
                else:
                    assert False
                # Any other excepciones will naturally cause falla here.

            def posargs_sin_rellenar(self):
                p = self._analizador(
                    (
                        Argumento("foo", opcional=True),
                        Argumento("bar", posicional=True),
                    )
                )
                self._prueba_para_ambiguedad("--foo uhoh", p)

            def no_hay_ambiguedad_si_la_opcion_val_ya_se_ha_dado(self):
                p = self._analizador(
                    (
                        Argumento("foo", opcional=True),
                        Argumento("bar", tipo=bool),
                    )
                )
                # Esto NO debería suscitar un análisis de errores.
                resultado = self._analizar("--foo hola --bar", p)
                assert resultado[0].args["foo"].valor == "hola"
                assert resultado[0].args["bar"].valor is True

            def argumento_valido_NOT_es_ambiguo(self):
                # La única excepción que prueba la regla #
                self._analizador((Argumento("foo", opcional=True), Argumento("bar")))
                for form in ("--bar barval", "--bar=barval"):
                    resultado = self._analizar("--foo {}".format(form))
                    assert len(resultado) == 1
                    args = resultado[0].args
                    assert args["foo"].valor is True
                    assert args["bar"].valor == "barval"

            def argumento_valido_de_bandera_no_es_ambiguo(self):
                # The OTHER exception that proves the rule?
                self._analizador(
                    (
                        Argumento("foo", opcional=True),
                        Argumento("bar", tipo=bool),
                    )
                )
                resultado = self._analizar("--foo --bar")
                assert len(resultado) == 1
                args = resultado[0].args
                assert args["foo"].valor is True
                assert args["bar"].valor is True

            def argumento_valido_de_bandera_no_es_ambiguo(self):
                self._analizador((Argumento("foo", opcional=True),))
                resultado = self._analizar("--foo --bar")
                assert resultado[0].args["foo"].valor == "--bar"

            def nombre_de_artefacto(self):
                # miartefacto --foo myotroartefacto
                c1 = Contexto("miartefacto", args=(Argumento("foo", opcional=True),))
                c2 = Contexto("otroartefacto")
                p = Analizador([c1, c2])
                self._prueba_para_ambiguedad("--foo otroartefacto", p)

    class argumentos_tipo_lista:
        "argumentos (iterable) tipo-lista"

        def _analizar(self, *args):
            c = Contexto("miartefacto", args=(Argumento("milista", tipo=list),))
            argv = ["miartefacto"] + list(args)
            return Analizador([c]).analizar_args(argv)[0].args.milista.valor

        def no_se_puede_dar_ningun_tiempo_resultando_una_lista_vacia_por_default(self):
            assert self._analizar() == []

        def dado_una_vez_se_convierte_en_una_lista_de_elementos_unicos(self):
            assert self._analizar("--milista", "foo") == ["foo"]

        def dado_N_veces_se_convierte_en_lista_de_len_N(self):
            esperado = ["foo", "bar", "biz"]
            got = self._analizar(
                "--milista", "foo", "--milista", "bar", "--milista", "biz"
            )
            assert got == esperado

        def iterables_funcionan_correctamente_fuera_de_un_vacio(self):
            # Error no detectado donde estaba principalmente enfocado en el
            # caso de uso -vvv ... ¡los incrementables 'normales' nunca 
            # dejaron el estado 'esperando valor' en el analizador! así que
            # _subsequent_ artefacto nombres & such nunca se analizaron 
            # correctamente, siempre se agregaron a la lista.
            c = Contexto("miartefacto", args=[Argumento("milista", tipo=list)])
            c2 = Contexto("otroartefacto")
            argv = [
                "miartefacto",
                "--milista",
                "val",
                "--milista",
                "val2",
                "otroartefacto",
            ]
            resultado = Analizador([c, c2]).analizar_args(argv)
            # Cuando el error está presente, el resultado solo tiene un 
            # contexto (para 'mi artefacto') y su 'milista' consiste en 
            # ['val', 'val2', 'otro artefacto']. (el medio '--milista' se
            # manejó semi-correctamente).
            milista = resultado[0].args.milista.valor
            assert milista == ["val", "val2"]
            contextos = len(resultado)
            err = "¡Obtuve {} resultados de análisis de contexto en lugar de 2!".format(contextos)
            assert contextos == 2, err
            assert resultado[1].nombre == "otroartefacto"

    class repeticion_de_artefactos:
        def es_feliz_manejando_el_mismo_artefacto_varias_veces(self):
            artefacto1 = Contexto("miartefacto")
            resultado = Analizador((artefacto1,)).analizar_args(["miartefacto", "miartefacto"])
            assert len(resultado) == 2
            for x in resultado:
                assert x.nombre == "miartefacto"

        def args_de_artefacto_funcionan_correctamente(self):
            artefacto1 = Contexto("miartefacto", args=(Argumento("bah"),))
            resultado = Analizador((artefacto1,)).analizar_args(
                ["miartefacto", "--bah", "mehval1", "miartefacto", "--bah", "mehval2"]
            )
            assert resultado[0].args.bah.valor == "mehval1"
            assert resultado[1].args.bah.valor == "mehval2"

    class por_banderas_principales_de_artefacto:
        class general:
            def _echo(self):
                return Argumento("echo", tipo=bool, default=False)

            def banderas_core_funcionan_normalmente_cuando_no_hay_conflicto(self):
                # Contexto de análisis inicial con un --echo, más un artefacto sin argumentos
                inicial = Contexto(args=[self._echo()])
                artefacto1 = Contexto("miartefacto")
                analizador = Analizador(inicial=inicial, contextos=[artefacto1])
                # Llamar con --echo en el contexto por-artefacto, espere
                # que el contexto central se actualice (vs un error)
                resultado = analizador.analizar_args(["miartefacto", "--echo"])
                assert resultado[0].args.echo.valor is True

            def cuando_los_argumentos_de_conflicto_por_artefacto_ganan(self):
                # Contexto de análisis inicial con un --echo, más artefacto con el mismo
                inicial = Contexto(args=[self._echo()])
                artefacto1 = Contexto("miartefacto", args=[self._echo()])
                analizador = Analizador(inicial=inicial, contextos=[artefacto1])
                # Llamar con --echo en el contexto por-artefacto, espere que 
                # el contexto artefacto se actualice, y no nucleo.
                resultado = analizador.analizar_args(["miartefacto", "--echo"])
                assert resultado[0].args.echo.valor is False
                assert resultado[1].args.echo.valor is True

            def valor_que_requiere_que_banderas_cores_tambien_trabajen_correctamente(self):
                "banderas de núcleo que requieren-valor también funcionan correctamente"
                inicial = Contexto(args=[Argumento("ocultar")])
                artefacto1 = Contexto("miartefacto")
                analizador = Analizador(inicial=inicial, contextos=[artefacto1])
                resultado = analizador.analizar_args(["miartefacto", "--ocultar", "ambos"])
                assert resultado[0].args.ocultar.valor == "ambos"

        class casos_limite:
            def bool_core_pero_por_cadena_de_artefacto(self):
                # Contexto inicial de análisis con bool --ocultar, y un 
                # artefacto con un regular (cadena) --ocultar
                inicial = Contexto(
                    args=[Argumento("ocultar", tipo=bool, default=False)]
                )
                artefacto1 = Contexto("miartefacto", args=[Argumento("ocultar")])
                analizador = Analizador(inicial=inicial, contextos=[artefacto1])
                # Espera que, como la versión del artefacto gana, seamos 
                # capaces de llamarlo con un valor. (Si hubiera bichos raros
                # en los que la bandera del núcleo informara al análisis, esto fallaría.)
                resultado = analizador.analizar_args(["miartefacto", "--ocultar", "ambos"])
                assert resultado[0].args.ocultar.valor is False
                assert resultado[1].args.ocultar.valor == "ambos"

        class help_trata_el_nombre_del_contexto_como_su_valor:
            def por_si_mismo_caso_base(self):
                artefacto1 = Contexto("miartefacto")
                init = Contexto(args=[Argumento("help", opcional=True)])
                analizador = Analizador(inicial=init, contextos=[artefacto1])
                resultado = analizador.analizar_args(["miartefacto", "--help"])
                assert len(resultado) == 2
                assert resultado[0].args.help.valor == "miartefacto"
                assert "help" not in resultado[1].args

            def otros_tokens_luego_generan_errores_de_analisis(self):
                # NOTE: esto se debe a la carcasa especial donde suministramos
                # el nombre del artefacto como valor cuando la bandera se
                # llama literalmente "ayuda".
                artefacto1 = Contexto("miartefacto")
                init = Contexto(args=[Argumento("help", opcional=True)])
                analizador = Analizador(inicial=init, contextos=[artefacto1])
                with raises(ErrorDeAnalisis, match=r".*foobar.*"):
                    analizador.analizar_args(["miartefacto", "--help", "foobar"])

class AnalizarResultado:
    "Analiza Resultado"

    def setup(self):
        self.contexto = Contexto(
            "miartefacto", args=(Argumento("foo", tipo=str), Argumento("bar"))
        )
        argv = ["miartefacto", "--foo", "foo-val", "--", "my", "remanente"]
        self.resultado = Analizador((self.contexto,)).analizar_args(argv)

    def actua_como_una_lista_de_contextos_analizados(self):
        assert len(self.resultado) == 1
        assert self.resultado[0].nombre == "miartefacto"

    def exhibe_atributo_de_resto(self):
        assert self.resultado.remanente == "miremantente"
