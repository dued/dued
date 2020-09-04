from __future__ import print_function

import operator

from dued.util import reduce

from pytest import raises

from dued.coleccion import Coleccion
from dued.artefactos import artefacto, Artefacto

from _util import load, ruta_de_soporte


@artefacto
def _miartefacto(c):
    print("woo!")


def _func(c):
    pass


class Collection_:
    class init:
        "__init__"

        def puede_aceptar_varargs_de_artefactos(self):
            "puede aceptar artefactos como *args"

            @artefacto
            def artefacto1(c):
                pass

            @artefacto
            def artefacto2(c):
                pass

            c = Coleccion(artefacto1, artefacto2)
            assert "artefacto1" in c
            assert "artefacto2" in c

        def tambien_puede_aceptar_colecciones_como_varargs(self):
            sub = Coleccion("sub")
            hng = Coleccion(sub)
            assert hng.colecciones["sub"] == sub

        def kwargs_actuan_como_args_de_nombre_para_objetos_dados(self):
            sub = Coleccion()

            @artefacto
            def artefacto1(c):
                pass

            hng = Coleccion(loltask=artefacto1, notsub=sub)
            assert hng["loltask"] == artefacto1
            assert hng.colecciones["notsub"] == sub

        def arg_de_cadena_inicial_actua_como_nombre(self):
            sub = Coleccion("sub")
            hng = Coleccion(sub)
            assert hng.colecciones["sub"] == sub

        def arg_cadena_inicial_engrana_con_varargs_y_kwargs(self):
            @artefacto
            def artefacto1(c):
                pass

            @artefacto
            def artefacto2(c):
                pass

            sub = Coleccion("sub")
            hng = Coleccion("raiz", artefacto1, sub, sometask=artefacto2)
            for x, y in (
                (hng.nombre, "raiz"),
                (hng["artefacto1"], artefacto1),
                (hng.colecciones["sub"], sub),
                (hng["algunartefacto"], artefacto2),
            ):
                assert x == y

        def acepta_la_ruta_decarga_como_kwarg(self):
            assert Coleccion().cargado_de is None
            assert Coleccion(cargado_de="a/ruta").cargado_de == "a/ruta"

        def acepta_nombres_de_guiones_autometicos_como_kwarg(self):
            assert Coleccion().nombre_auto_guion is True
            assert Coleccion(nombre_auto_guion=False).nombre_auto_guion is False

    class metodos_especiales_utiles:
        def _meh(self):
            @artefacto
            def artefacto1(c):
                pass

            @artefacto
            def artefacto2(c):
                pass

            @artefacto
            def artefacto3(c):
                pass

            submeh = Coleccion("submeh", artefacto3)
            return Coleccion("bah", artefacto1, artefacto2, submeh)

        def setup(self):
            self.c = self._meh()

        def repr_(self):
            "__repr__"
            esperado = "<Coleccion 'bah': artefacto1, artefacto2, submeh...>"
            assert esperado == repr(self.c)

        def igualdad_consiste_en_nombres_de_artefactos_y_colecciones(self):
            # Verdaderamente igual
            assert self.c == self._meh()
            # Mismo contenido, diferente nombre == no igual
            difnombre = self._meh()
            difnombre.nombre = "nomeh"
            assert difnombre != self.c
            # Y una revisión de cordura que no olvidamos __ne __... porque
            # eso definitivamente sucedió en un momento
            assert not difnombre == self.c
            # Mismo nombre, mismos artefactos, diferentes colecciones == no iguales
            difcols = self._meh()
            del difcols.colecciones["submeh"]
            assert difcols != self.c
            # Mismo nombre, diferentes artefactos, mismas colecciones == no iguales
            difartefactos = self._meh()
            del difartefactos.artefactos["artefacto1"]
            assert difartefactos != self.c

        def booleano_es_equivalente_a_tareas_y_o_colecciones(self):
            # ¿Sin artefactos o coleccs? Vacío/false
            assert not Coleccion()
            # ¿Artefactos pero no coleccs? True
            @artefacto
            def foo(c):
                pass

            assert Coleccion(foo)
            # Coleccs pero no artefactos: True
            assert Coleccion(foo=Coleccion(foo))
            # TODO: si un árbol que no es "vacio" pero no tiene nada PERO 
            # otras colecciones vacías en él, debe ser verdadero o falso, es
            # algo cuestionable - pero dado que no daría como resultado 
            # nombres de artefacto utilizables, digamos que es Falso. (Además,
            # esto nos permite usar .nombres_de_artefactos como la abreviatura
            # impl ...)
            assert not Coleccion(foo=Coleccion())

    class del_modulo:
        def setup(self):
            self.c = Coleccion.del_modulo(load("integracion"))

        class parametros:
            def setup(self):
                self.mod = load("integracion")
                self.del_modulo = Coleccion.del_modulo

            def anular_nombre(self):
                assert self.del_modulo(self.mod).nombre == "integracion"
                anular = self.del_modulo(self.mod, nombre="no-integracion")
                assert anular.nombre == "no-integracion"

            def configuracion_en_linea(self):
                # No se ha proporcionado ninguna configuración, no se ha obtenido ninguna
                assert self.del_modulo(self.mod).configuracion() == {}
                # La configuración kwarg dada se refleja cuando se obtiene la configuración
                colecc = self.del_modulo(self.mod, config={"foo": "bar"})
                assert colecc.configuracion() == {"foo": "bar"}

            def nombre_y_configuracion_simultaneamente(self):
                # Pruebe con posargs para hacer cumplir los pedidos, solo por seguridad.
                c = self.del_modulo(self.mod, "el nombre", {"la": "config"})
                assert c.nombre == "el nombre"
                assert c.configuracion() == {"la": "config"}

            def nombres_de_guiones_automaticos_pasados_al_constructor(self):
                # Sanity
                assert self.del_modulo(self.mod).nombre_auto_guion is True
                # Test
                colecc = self.del_modulo(self.mod, nombre_auto_guion=False)
                assert colecc.nombre_auto_guion is False

        def agrega_artefactos(self):
            assert "imprimir-foo" in self.c

        def deriva_el_nombre_de_la_coleccion_del_nombre_del_modulo(self):
            assert self.c.nombre == "integracion"

        def copia_docstring_del_modulo(self):
            esperado = "Un accesorio estilo semi-integración-prueba que abarca múltiples ejemplos de funciones."  # noqa
            # Es suficiente comprobar la primera línea.
            assert self.c.__doc__.strip().split("\n")[0] == esperado

        def funciona_muy_bien_con_subclases(self):
            class MiColeccion(Coleccion):
                pass

            c = MiColeccion.del_modulo(load("integracion"))
            assert isinstance(c, MiColeccion)

        def los_nombres_de_los_submodulos_eliminan_al_ultimo_fragmento(self):
            with ruta_de_soporte():
                from paquete import modulo
            c = Coleccion.del_modulo(modulo)
            assert modulo.__name__ == "paquete.modulo"
            assert c.nombre == "modulo"
            assert "miartefacto" in c  # Sanity

        def honra_colecciones_explicitas(self):
            colecc = Coleccion.del_modulo(load("raiz_explicita"))
            assert "alto-nivel" in colecc.artefactos
            assert "sub-nivel" in colecc.colecciones
            # La verdadera prueba clave
            assert "sub-artefacto" not in colecc.artefactos

        def permite_que_las_tareas_con_nombres_explícitos_anulen_el_nombre_enlazado(self):
            colecc = Coleccion.del_modulo(load("nombre_de_subcol_afact"))
            assert "nombre-explicito" in colecc.artefactos  # no 'nombre_implicito'

        def devuelve_objs_Coleccion_unicos_para_el_mismo_modulo_de_entrada(self):
            # Ignorando self.c por ahora, en caso de que cambie más tarde.
            # Primero, un módulo sin raíz Hangar
            mod = load("integracion")
            c1 = Coleccion.del_modulo(mod)
            c2 = Coleccion.del_modulo(mod)
            assert c1 is not c2
            # Ahora uno *con* una raíz Hangar (que anteriormente tenía errores)
            mod2 = load("raiz_explicita")
            c3 = Coleccion.del_modulo(mod2)
            c4 = Coleccion.del_modulo(mod2)
            assert c3 is not c4

        class rais_explicita_en:
            def setup(self):
                mod = load("raiz_explicita")
                mod.hng.configurar(
                    {
                        "clave": "incorporado",
                        "otraclave": "yup",
                        "subconfig": {"miclave": "mivalor"},
                    }
                )
                mod.hng.nombre = "builtin_name"
                self.nocambiado = Coleccion.del_modulo(mod)
                self.cambiado = Coleccion.del_modulo(
                    mod,
                    nombre="anular_nombre",
                    config={
                        "clave": "anular",
                        "subconfig": {"miotraclave": "miotrovalor"},
                    },
                )

            def config_hng_linea_con_EN_de_la_raiz_anula_lo_incorporado(self):
                assert self.nocambiado.configuracion()["clave"] == "incorporado"
                assert self.cambiado.configuracion()["clave"] == "anular"

            def config_en_linea_se_anula_via_fusion_no_reemplazo(self):
                assert "otraclave" in self.cambiado.configuracion()

            def config_anula_recursivamente_fusiones(self):
                subconfig = self.cambiado.configuracion()["subconfig"]
                assert subconfig["miclave"] == "mivalor"

            def nombre_en_linea_anula_nombre_del_objeto_del_hng_raiz(self):
                assert self.nocambiado.nombre == "nombre-incorporado"
                assert self.cambiado.nombre == "anular-nombre"

            def nombre_del_objeto_del_hng_raiz_anula_el_nombre_del_modulo(self):
                # Duplica parte de la prueba anterior para ser explícitos.
                # Es decir prueba que el nombre no acaba siendo 'raiz_explicita'.
                assert self.nocambiado.nombre == "nombre-incorporado"

            def docstring_aun_copiado_del_modulo(self):
                esperado = "LETRAS EXPLICITAS"
                assert self.nocambiado.__doc__.strip() == esperado
                assert self.cambiado.__doc__.strip() == esperado

    class ad_artefacto:
        def setup(self):
            self.c = Coleccion()

        def asociados_dados_invocables_con_nombre_dado(self):
            self.c.ad_artefacto(_miartefacto, "foo")
            assert self.c["foo"] == _miartefacto

        def usa_nombre_de_la_funcion_como_nombre_implicito(self):
            self.c.ad_artefacto(_miartefacto)
            assert "_miartefacto" in self.c

        def prefiere_el_nombre_kwarg_sobre_el_atributo_nombre_del_artefacto(self):
            self.c.ad_artefacto(Artefacto(_func, nombre="nofunc"), nombre="sifunc")
            assert "sifunc" in self.c
            assert "nofunc" not in self.c

        def prefiere_el_atributo_de_nombre_de_artefacto_sobre_el_nombre_de_funcion(self):
            self.c.ad_artefacto(Artefacto(_func, nombre="nofunc"))
            assert "nofunc" in self.c
            assert "_func" not in self.c

        def genera_ValueError_si_no_se_encuentra_ningun_nombre(self):
            # No se puede usar una lambda aquí porque son funciones técnicamente reales.
            class Invocable(object):
                def __call__(self):
                    pass

            with raises(ValueError):
                self.c.ad_artefacto(Artefacto(Invocable()))

        def genera_ValueError_en_multiples_defaults(self):
            t1 = Artefacto(_func, default=True)
            t2 = Artefacto(_func, default=True)
            self.c.ad_artefacto(t1, "foo")
            with raises(ValueError):
                self.c.ad_artefacto(t2, "bar")

        def genera_ValueError_si_elartefacto_agregado_refleja_el_nombre_de_la_subcoleccion(self):
            self.c.ad_coleccion(Coleccion("sub"))
            with raises(ValueError):
                self.c.ad_artefacto(_miartefacto, "sub")

        def permite_especificar_el_artefacto_por_defecto(self):
            self.c.ad_artefacto(_miartefacto, default=True)
            assert self.c.default == "_miartefacto"

        def especificando_el_seteo_del_artefacto_pordefecto_False_anulacion(self):
            @artefacto(default=True)
            def soy_yo(c):
                pass

            self.c.ad_artefacto(soy_yo, default=False)
            assert self.c.default is None

        def permite_especificar_alias(self):
            self.c.ad_artefacto(_miartefacto, alias=("artefacto1", "artefacto2"))
            assert self.c["_miartefacto"] is self.c["artefacto1"] is self.c["artefacto2"]

        def alias_son_fundidos(self):
            @artefacto(alias=("foo", "bar"))
            def biz(c):
                pass

            # NOTE: use la tupla anterior y la lista a continuación para 
            # asegurarse de que no haya problemas de tipo
            self.c.ad_artefacto(biz, alias=["baz", "boz"])
            for x in ("foo", "bar", "biz", "baz", "boz"):
                assert self.c[x] is self.c["biz"]

    class ad_coleccion:
        def setup(self):
            self.c = Coleccion()

        def agrega_coleccion_como_subcoleccion_de_self(self):
            c2 = Coleccion("foo")
            self.c.ad_coleccion(c2)
            assert "foo" in self.c.colecciones

        def puede_tomar_objetos_modulo(self):
            self.c.ad_coleccion(load("integracion"))
            assert "integracion" in self.c.colecciones

        def genera_ValueError_si_coleccion_sin_nombre(self):
            # Las colecciones no-root deben tener un nombre explícito dado a
            # través de kwarg, tener un atributo de nombre establecido o ser
            # un módulo con __name__ definido.
            raiz = Coleccion()
            sub = Coleccion()
            with raises(ValueError):
                raiz.ad_coleccion(sub)

        def genera_ValueError_si_la_coleccion_tiene_el_mismo_nombre_que_el_artefacto(self):
            self.c.ad_artefacto(_miartefacto, "sub")
            with raises(ValueError):
                self.c.ad_coleccion(Coleccion("sub"))

    class getitem:
        "__getitem__"

        def setup(self):
            self.c = Coleccion()

        def encuentra_sus_propios_artefactos_por_nombre(self):
            # TODO: duplica una prueba ad_artefacto anterior, ¿arreglar?
            self.c.ad_artefacto(_miartefacto, "foo")
            assert self.c["foo"] == _miartefacto

        def busca_artefactos_de_subcoleccion_por_nombre_con_puntos(self):
            sub = Coleccion("sub")
            sub.ad_artefacto(_miartefacto)
            self.c.ad_coleccion(sub)
            assert self.c["sub._miartefacto"] == _miartefacto

        def honra_alias_en_sus_propios_artefactos(self):
            t = Artefacto(_func, alias=["bar"])
            self.c.ad_artefacto(t, "foo")
            assert self.c["bar"] == t

        def honra_los_alias_de_artefactos_de_subcoleccion(self):
            self.c.ad_coleccion(load("decoradores"))
            assert "decoradores.bar" in self.c

        def respeta_el_propio_artefacto_pordefault_sin_argumentos(self):
            t = Artefacto(_func, default=True)
            self.c.ad_artefacto(t)
            assert self.c[""] == t

        def respeta_los_artefactos_pordefecto_de_la_subcoleccion_en_el_nombre_de_la_subcoleccion(self):
            sub = Coleccion.del_modulo(load("decoradores"))
            self.c.ad_coleccion(sub)
            # Sanity
            assert self.c["decoradores.biz"] is sub["biz"]
            # Real prueba
            assert self.c["decoradores"] is self.c["decoradores.biz"]

        def genera_ValueError_sin_nombre_y_sin_valor_pordefecto(self):
            with raises(ValueError):
                self.c[""]

        def ValueError_para_el_nombre_de_artefacto_subcol_sin_valor_predeterminado(self):
            self.c.ad_coleccion(Coleccion("cualquier"))
            with raises(ValueError):
                self.c["cualquier"]

    class a_contextos:
        def setup(self):
            @artefacto
            def miartefacto(c, texto, booleano=False, number=5):
                print(texto)

            @artefacto(alias=["miartefacto27"])
            def miartefacto2(c):
                pass

            @artefacto(alias=["otroartefacto"], default=True)
            def subartefacto(c):
                pass

            sub = Coleccion("sub", subartefacto)
            self.c = Coleccion(miartefacto, miartefacto2, sub)
            self.contextos = self.c.a_contextos()
            alias_tups = [list(x.alias) for x in self.contextos]
            self.alias = reduce(operator.add, alias_tups, [])
            # Focus on 'miartefacto' as it has the more interesting sig
            self.contexto = [x for x in self.contextos if x.nombre == "miartefacto"][0]

        def devuelve_iterable_de_Contextos_correspondientes_a_artefactos(self):
            assert self.contexto.nombre == "miartefacto"
            assert len(self.contextos) == 3

        class nombre_auto_guion:
            def nombres_de_contexto_se_vuelven_discontinuos_automaticamente(self):
                @artefacto
                def mi_artefacto(c):
                    pass

                contextos = Coleccion(mi_artefacto).a_contextos()
                assert contextos[0].nombre == "mi-artefacto"

            def se_filtra_a_artefactos_de_subcoleccion(self):
                @artefacto
                def artefacto_externo(c):
                    pass

                @artefacto
                def artefacto_interno(c):
                    pass

                colecc = Coleccion(artefacto_externo, interior=Coleccion(artefacto_interno))
                contextos = colecc.a_contextos()
                esperado = {"artefacto-exterior", "interior.interior-artefacto"}
                assert {x.nombre for x in contextos} == esperado

            def se_filtra_a_los_nombres_de_las_subcolecciones(self):
                @artefacto
                def mi_artefacto(c):
                    pass

                colecc = Coleccion(interior_colecc=Coleccion(mi_artefacto))
                contextos = colecc.a_contextos()
                assert contextos[0].nombre == "interior-colecc.mi-artefacto"

            def los_alias_tambien_estan_discontinuos(self):
                @artefacto(alias=["hola_estoy_subguionado"])
                def cualquier(c):
                    pass

                contextos = Coleccion(cualquier).a_contextos()
                assert "hola-estoy-subguionado" in contextos[0].alias

            def los_guiones_bajos_iniciales_y_finales_no_se_ven_afectados(self):
                @artefacto
                def _lo_que_siempre_(c):
                    pass

                @artefacto
                def _enfriador_interior_(c):
                    pass

                interior = Coleccion("interior", _enfriador_interior_)
                contextos = Coleccion(_lo_que_siempre_, interior).a_contextos()
                esperado = {"_lo_que-siempre_", "interior._enfriador-interior_"}
                assert {x.nombre for x in contextos} == esperado

            def _guiones_bajos_anidados(self, nombre_auto_guion=None):
                @artefacto(alias=["otro_nombre"])
                def mi_artefacto(c):
                    pass

                @artefacto(alias=["otro_interior"])
                def artefacto_interno(c):
                    pass

                # NOTE: explícitamente no dar kwarg a la subcolección; esto
                # prueba que el espacio de nombres de nivel superior realiza
                # la transformación inversa cuando es necesario.
                sub = Coleccion("interior_colecc", artefacto_interno)
                return Coleccion(
                    mi_artefacto, sub, nombre_auto_guion=nombre_auto_guion
                )

            def honra_el_seteo_de_inicio_en_el_hng_superior(self):
                colecc = self._guiones_bajos_anidados(nombre_auto_guion=False)
                contextos = colecc.a_contextos()
                nombres = ["mi_artefacto", "interior_colecc.artefacto_interno"]
                alias = [["otro_nombre"], ["interior_colecc.otro_interior"]]
                assert sorted(x.nombre for x in contextos) == sorted(nombres)
                assert sorted(x.alias for x in contextos) == sorted(alias)

            def las_transformaciones_se_aplican_a_en_de_modulos_explícitos(self):
                # Síntoma cuando hay un error: Coleccion.a_contextos() muere 
                # porque itera sobre .nombres_de_artefactos (transformado) y
                # luego intenta usar resultado para acceder a __getitem__ 
                # (sin transformación automática ... porque en todas las demás
                # situaciones, las claves de estructura de artefacto ya están
                # transformadas; ¡pero este no fue el caso de del_modulo() con
                # objetos explícitos 'hng'!)
                hangar = self._guiones_bajos_anidados()

                class FakeModule(object):
                    __name__ = "mi_modulo"
                    hng = hangar

                colecc = Coleccion.del_modulo(
                    FakeModule(), nombre_auto_guion=False
                )
                # NOTE: underscores, not dashes
                esperado = {"mi_artefacto", "interior_colecc.artefacto_interno"}
                assert {x.nombre for x in colecc.a_contextos()} == esperado

        def permite_el_acceso_tipobandera_via_banderas(self):
            assert "--texto" in self.contexto.banderas

        def arglista_posicional_preserva_el_orden_dado(self):
            @artefacto(posicional=("segundo", "primero"))
            def miartefacto(c, primero, segundo, third):
                pass

            colecc = Coleccion()
            colecc.ad_artefacto(miartefacto)
            c = colecc.a_contextos()[0]
            esperado = [c.args["segundo"], c.args["primero"]]
            assert c.args_posicionales == esperado

        def expone_nombres_de_artefactos_con_EN(self):
            assert "sub.subartefacto" in [x.nombre for x in self.contextos]

        def expone_alias_de_artefactos_con_EN(self):
            assert "sub.otroartefacto" in self.alias

        def expone_los_artefactos_pordefecto_de_la_subcoleccion(self):
            assert "sub" in self.alias

        def expone_alias(self):
            assert "miartefacto27" in self.alias

    class nombres_de_artefactos:
        def setup(self):
            self.c = Coleccion.del_modulo(load("raiz_explicita"))

        def devuelve_todos_los_nombres_de_artefactos_incluidas_sus_acciones(self):
            nombres = set(self.c.nombres_de_artefactos.keys())
            assert nombres == {"alto-nivel", "sub-nivel.sub-artefacto"}

        def includes_aliases_and_defaults_as_values(self):
            nombres = self.c.nombres_de_artefactos
            assert nombres["alto-nivel"] == ["otro-alto"]
            nombres_de_subartefactos = nombres["sub-nivel.sub-artefacto"]
            assert nombres_de_subartefactos == ["sub-nivel.otro-sub", "sub-nivel"]

    class configuracion:
        "metodos de configuración"

        def setup(self):
            self.raiz = Coleccion()
            self.artefacto = Artefacto(_func, nombre="artefacto")

        def seteo_y_obtencion_basico(self):
            self.raiz.configurar({"foo": "bar"})
            assert self.raiz.configuracion() == {"foo": "bar"}

        def configurar_realiza_la_fusion(self):
            self.raiz.configurar({"foo": "bar"})
            assert self.raiz.configuracion()["foo"] == "bar"
            self.raiz.configurar({"biz": "baz"})
            assert set(self.raiz.configuracion().keys()), {"foo" == "biz"}

        def configurar_la_combinacion_es_recursivo_para_dic_anidados(self):
            self.raiz.configurar({"foo": "bar", "biz": {"baz": "boz"}})
            self.raiz.configurar({"biz": {"otrobaz": "otroboz"}})
            c = self.raiz.configuracion()
            assert c["biz"]["baz"] == "boz"
            assert c["biz"]["otrobaz"] == "otroboz"

        def configurar_permite_sobrescribir(self):
            self.raiz.configurar({"foo": "one"})
            assert self.raiz.configuracion()["foo"] == "one"
            self.raiz.configurar({"foo": "two"})
            assert self.raiz.configuracion()["foo"] == "two"

        def devuelve_llamada_dic(self):
            assert self.raiz.configuracion() == {}
            self.raiz.configurar({"foo": "bar"})
            assert self.raiz.configuracion() == {"foo": "bar"}

        def acceso_fusiona_desde_subcolecciones(self):
            interior = Coleccion("interior", self.artefacto)
            interior.configurar({"foo": "bar"})
            self.raiz.configurar({"biz": "baz"})
            # With no interior coleccion
            assert set(self.raiz.configuracion().keys()) == {"biz"}
            # With interior coleccion
            self.raiz.ad_coleccion(interior)
            claves = set(self.raiz.configuracion("interior.artefacto").keys())
            assert claves == {"foo", "biz"}

        def padres_sobrescriben_a_hijos_en_el_camino(self):
            interior = Coleccion("interior", self.artefacto)
            interior.configurar({"foo": "interior"})
            self.raiz.ad_coleccion(interior)
            # Antes de actualizar la configuración coleccion raiz, refleja el int
            assert self.raiz.configuracion("interior.artefacto")["foo"] == "interior"
            self.raiz.configurar({"foo": "exterior"})
            # Después, refleja el exterior (ya que ahora anula)
            assert self.raiz.configuracion("interior.artefacto")["foo"] == "exterior"

        def subcolecciones_hermanos_ignoradas(self):
            interior = Coleccion("interior", self.artefacto)
            interior.configurar({"foo": "hola"})
            interios2 = Coleccion("interios2", Artefacto(_func, nombre="artefacto2"))
            interios2.configurar({"foo": "nop"})
            raiz = Coleccion(interior, interios2)
            assert raiz.configuracion("interior.artefacto")["foo"] == "hola"
            assert raiz.configuracion("interios2.artefacto2")["foo"] == "nop"

        def rutas_de_subcolecciones_pueden_tener_puntos(self):
            hoja = Coleccion("hoja", self.artefacto)
            hoja.configurar({"clave": "hoja-valor"})
            medio = Coleccion("medio", hoja)
            raiz = Coleccion("raiz", medio)
            config = raiz.configuracion("medio.hoja.artefacto")
            assert config == {"clave": "hoja-valor"}

        def Lrutas_de_subcoleccion_no_válidas_resultan_en_KeyError(self):
            # Directamente no válido
            with raises(KeyError):
                Coleccion("bah").configuracion("nop.artefacto")
            # Existe pero el nivel es incorrecto (debería ser 
            # 'root.artefacto', no solo 'artefacto')
            interior = Coleccion("interior", self.artefacto)
            with raises(KeyError):
                Coleccion("raiz", interior).configuracion("artefacto")

        def claves_no_tienen_que_existir_en_la_ruta_completa(self):
            # Un poco duplica cosas anteriores; bah Clave solo almacenada 
            # en hoja
            hoja = Coleccion("hoja", self.artefacto)
            hoja.configurar({"clave": "hoja-valor"})
            medio = Coleccion("medio", hoja)
            raiz = Coleccion("raiz", medio)
            config = raiz.configuracion("medio.hoja.artefacto")
            assert config == {"clave": "hoja-valor"}
            # Clave almacenada en medio + hoja pero no raíz
            medio.configurar({"clave": "soo"})
            assert raiz.configuracion("medio.hoja.artefacto") == {"clave": "soo"}

    class subcoleccion_desde_ruta:
        def ruta_de_nivel_superior(self):
            coleccion = Coleccion.del_modulo(load("arbol"))
            fabric = coleccion.colecciones["fabric"]
            assert coleccion.subcoleccion_desde_ruta("fabric") is fabric

        def ruta_anidada(self):
            coleccion = Coleccion.del_modulo(load("arbol"))
            docs = coleccion.colecciones["fabric"].colecciones["docs"]
            assert coleccion.subcoleccion_desde_ruta("fabric.docs") is docs

        def Ruta_no_valida(self):
            # Esto realmente es solo probar el comportamiento de Lexicon/dict,
            # pero bueno, bueno ser explícito, especialmente si alguna vez 
            # queremos que esto se convierta en Salida u otra excepción
            # personalizada. (Por ahora, la mayoría / todas las personas que
            # llaman capturan manualmente KeyError y generan Salida solo para
            # mantener la mayoría del uso de Salida en lo alto del stack ...)
            with raises(KeyError):
                coleccion = Coleccion.del_modulo(load("arbol"))
                coleccion.subcoleccion_desde_ruta("jeje.cualquier.pieza")

    class serializado:
        def colección_vacia(self):
            esperado = dict(
                nombre=None, help=None, artefactos=[], default=None, colecciones=[]
            )
            assert esperado == Coleccion().serializado()

        def coleccion_con_nombre_vacia(self):
            esperado = dict(
                nombre="foo", help=None, artefactos=[], default=None, colecciones=[]
            )
            assert esperado == Coleccion("foo").serializado()

        def coleccion_vacía_con_nombre_docstringed(self):
            esperado = dict(
                nombre="foo",
                help="Hola doc",
                artefactos=[],
                default=None,
                colecciones=[],
            )
            colecc = Coleccion("foo")
            colecc.__doc__ = "Hola doc"
            assert esperado == colecc.serializado()

        def nombre_docstring_default_y_artefactos(self):
            esperado = dict(
                nombre="desplegar",
                help="Cómo desplegar código y configs.",
                artefactos=[
                    dict(
                        nombre="db",
                        help="Implementar en nuestros DB servers.",
                        alias=["db-servers"],
                    ),
                    dict(
                        nombre="omnipresente",
                        help="Implementar en todos los objetivos.",
                        alias=[],
                    ),
                    dict(
                        nombre="web",
                        help="Actualiza y rebota los servidores web.",
                        alias=[],
                    ),
                ],
                default="omnipresente",
                colecciones=[],
            )
            with ruta_de_soporte():
                from arbol import desplegar

                colecc = Coleccion.del_modulo(desplegar)
            assert esperado == colecc.serializado()

        def nombrar_artefactos_y_colecciones_pordefecto_del_docstring(self):
            docs = dict(
                nombre="docs",
                help="Artefactos para gestion de doc Sphinx.",
                artefactos=[
                    dict(
                        nombre="all", help="Fabrica todo formatos de docs.", alias=[]
                    ),
                    dict(
                        nombre="html", help="Genera solo salida HTML.", alias=[]
                    ),
                    dict(
                        nombre="pdf", help="Genere solo salida PDF.", alias=[]
                    ),
                ],
                default="all",
                colecciones=[],
            )
            python = dict(
                nombre="python",
                help="Artefactos de distribución de PyPI /etc.",
                artefactos=[
                    dict(
                        nombre="all",
                        help="Fabrica todos los paquetes de Python.",
                        alias=[],
                    ),
                    dict(
                        nombre="sdist",
                        help="Construye tar.gz de estilo clásico.",
                        alias=[],
                    ),
                    dict(nombre="wheel", help="Construye una distb. wheel (rueda).", alias=[]),
                ],
                default="all",
                colecciones=[],
            )
            esperado = dict(
                nombre="fabric",
                help="Artefactos p.compilar cód estático.",
                artefactos=[
                    dict(
                        nombre="all",
                        help="Fabrica los artefactos necesarios.",
                        alias=["todo"],
                    ),
                    dict(
                        nombre="c-ext",
                        help="Construye nuestra extensión C interna.",
                        alias=["ext"],
                    ),
                    dict(nombre="zap", help="Una forma majadera de limpiar.", alias=[]),
                ],
                default="all",
                colecciones=[docs, python],
            )
            with ruta_de_soporte():
                from arbol import fabric

                colecc = Coleccion.del_modulo(fabric)
            assert esperado == colecc.serializado()

        def subcolecciones_sin_nombre(self):
            subcolecc = Coleccion()
            subcol_nombre = Coleccion("hola")
            # Estamos vinculando al nombre 'subcolecc', pero subcolecc en sí
            # no tiene atributo/valor .nombre, que es lo que se está probando.
            # Cuando hay un error, ese hecho hará que serializado() muera en
            # sorted() al compararlo con subcol_nombre (que tiene un nombre de
            # cadena).
            raiz = Coleccion(subcol_nombre, subcolecc=subcolecc)
            esperado = dict(
                nombre=None,
                default=None,
                help=None,
                artefactos=[],
                colecciones=[
                    # Espere anónimo primero ya que los ordenamos como si su
                    # nombre fuera la cadena vacía.
                    dict(
                        artefactos=[],
                        colecciones=[],
                        nombre=None,
                        default=None,
                        help=None,
                    ),
                    dict(
                        artefactos=[],
                        colecciones=[],
                        nombre="hola",
                        default=None,
                        help=None,
                    ),
                ],
            )
            assert esperado == raiz.serializado()
