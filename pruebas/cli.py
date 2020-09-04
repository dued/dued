from dued.coleccion import Coleccion
from dued.analizador import Analizador
from dued.artefactos import artefacto


class AnalisisCLI:
    """
    Pruebas de análisis de alto nivel
    """

    def setup(self):
        @artefacto(posicional=[], iterable=["mi_lista"], incremento=["verbose"])
        def mi_artefacto(
            c,
            micadena,
            s,
            booleano=False,
            b=False,
            v=False,
            nombre_largo=False,
            bool_true=True,
            _guionbajo_principal=False,
            guionbajo_posterior=False,
            mi_lista=None,
            verbose=0,
        ):
            pass

        @artefacto(alias=["mi_artefacto27"])
        def mi_artefacto2(c):
            pass

        @artefacto(default=True)
        def mi_artefacto3(c, micadena):
            pass

        @artefacto
        def mi_artefacto4(c, limpiar=False, browse=False):
            pass

        @artefacto(alias=["otro"], default=True)
        def sub_artefacto(c):
            pass

        sub_colecc = Coleccion("sub_colecc", sub_artefacto)
        self.c = Coleccion(mi_artefacto, mi_artefacto2, mi_artefacto3, mi_artefacto4, sub_colecc)

    def _analizador(self):
        return Analizador(self.c.a_contextos())

    def _analizar(self, argstr):
        return self._analizador().analizar_args(argstr.split())

    def _comparar(self, dued, banderaname, valor):
        dued = "mi-artefacto " + dued
        resultado = self._analizar(dued)
        assert resultado[0].args[banderaname].valor == valor

    def _comparar_nombres(self, dado, real):
        assert self._analizar(dado)[0].nombre == real

    def banderas_guinesbajos_se_pueden_dar_como_discontinuas(self):
        self._comparar("--nombre-largo", "nombre_largo", True)

    def guionesbajos_iniciales_son_ignorados(self):
        self._comparar("--guionbajo-principal", "_guionbajo_principal", True)

    def guinesbajos_posteriores_se_ignoran(self):
        self._comparar("--guionbajo-posterior", "guionbajo_posterior", True)

    def banderas_booleanas_inversas(self):
        self._comparar("--bool-no-es-true", "bool_true", False)

    def espaciodenombre_de_artefacto(self):
        self._comparar_nombres("sub-colecc.sub-artefacto", "sub-colecc.sub-artefacto")

    def alias(self):
        self._comparar_nombres("mi-artefacto27", "mi-artefacto2")

    def alias_de_subcoleccion(self):
        self._comparar_nombres("sub-colecc.otro", "sub-colecc.sub-artefacto")

    def subcoleccion_de_artefactos_pordefecto(self):
        self._comparar_nombres("sub-colecc", "sub-colecc.sub-artefacto")

    def args_booleano(self):
        "mi-artefacto --booleano"
        self._comparar("--booleano", "booleano", True)

    def bandera_luego_espacio_luego_valor(self):
        "mi-artefacto --micadena foo"
        self._comparar("--micadena foo", "micadena", "foo")

    def bandera_luego_signo_igual_luego_valor(self):
        "mi-artefacto --micadena=foo"
        self._comparar("--micadena=foo", "micadena", "foo")

    def bandera_booleana_corta(self):
        "mi-artefacto -b"
        self._comparar("-b", "b", True)

    def bandera_corta_luego_espacio_luego_valor(self):
        "mi-artefacto -s valor"
        self._comparar("-s valor", "s", "valor")

    def bandera_corta_luego_signo_igual_luego_valor(self):
        "mi-artefacto -s=valor"
        self._comparar("-s=valor", "s", "valor")

    def bandera_corta_con_valor_adyacente(self):
        "mi-artefacto -svalue"
        r = self._analizar("mi-artefacto -svalue")
        assert r[0].args.s.valor == "valor"

    def _bandera_valor_artefacto(self, valor):
        r = self._analizar("mi-artefacto -s {} mi-artefacto2".format(valor))
        assert len(r) == 2
        assert r[0].nombre == "mi-artefacto"
        assert r[0].args.s.valor == valor
        assert r[1].nombre == "mi-artefacto2"

    def bandera_valor_luego_artefacto(self):
        "mi-artefacto -s valor mi-artefacto2"
        self._bandera_valor_artefacto("valor")

    def bandera_valor_igual_que_el_nombre_del_artefacto(self):
        "mi-artefacto -s mi-artefacto2 mi-artefacto2"
        self._bandera_valor_artefacto("mi-artefacto2")

    def tres_artefactos_con_args(self):
        "mi-artefacto --booleano mi-artefacto3 --micadena foo mi-artefacto2"
        r = self._analizar("mi-artefacto --booleano mi-artefacto3 --micadena foo mi-artefacto2")
        assert len(r) == 3
        assert [x.nombre for x in r] == ["mi-artefacto", "mi-artefacto3", "mi-artefacto2"]
        assert r[0].args.booleano.valor
        assert r[1].args.micadena.valor == "foo"

    def artefactos_con_kwargs_con_nombre_duplicado(self):
        "mi-artefacto --micadena foo mi-artefacto3 --micadena bar"
        r = self._analizar("mi-artefacto --micadena foo mi-artefacto3 --micadena bar")
        assert r[0].nombre == "mi-artefacto"
        assert r[0].args.micadena.valor == "foo"
        assert r[1].nombre == "mi-artefacto3"
        assert r[1].args.micadena.valor == "bar"

    def múltiples_banderas_cortas_adyacentes(self):
        "mi-artefacto -bv (e inversas)"
        for args in ("-bv", "-vb"):
            r = self._analizar("mi-artefacto {}".format(args))
            a = r[0].args
            assert a.b.valor
            assert a.v.valor

    def bandera_tipo_lista_se_puede_dar_N_veces_construyendo_una_lista(self):
        "mi-artefacto --mi-lista foo --mi-lista bar"
        # Probe tanto el singular como el plural, solo para estar seguro.
        self._comparar("--mi-lista foo", "mi-lista", ["foo"])
        self._comparar("--mi-lista foo --mi-lista bar", "mi-lista", ["foo", "bar"])

    def bandera_tipo_incrementable_se_puede_usar_como_interruptor_o_contador(self):
        "mi-artefacto -v, -vv, -vvvvv etc, excepto con explicito --verbose"
        self._comparar("", "verbose", 0)
        self._comparar("--verbose", "verbose", 1)
        self._comparar("--verbose --verbose --verbose", "verbose", 3)
