from mock import Mock
from pytest import raises, skip

from dued import Contexto, Config, artefacto, Artefacto, Llamar, Coleccion
from dued import CargaDesdeElSitemaDeArchivos as Cargador

from _util import soporte


#
# NOTE: La mayoría de las pruebas de Artefacto usan @artefacto ya que es la
# interfaz principal y es una envoltura muy delgada alrededor de Artefacto.
# De esta forma no tenemos que escribir 2x pruebas para Artefacto y @artefacto.
# Meh :)
#


def _func(c):
    pass


class task_:
    "@artefacto"

    def _carga(self, nombre):
        mod, _ = self.cargador.cargar(nombre)
        return Coleccion.del_modulo(mod)

    def setup(self):
        self.cargador = Cargador(inicio=soporte)
        self.ordinario = self._carga("decoradores")

    def permite_acceso_al_objeto_contenedor(self):
        def lolcats(c):
            pass

        assert artefacto(lolcats).cuerpo == lolcats

    def permite_especificacion_de_alias(self):
        assert self.ordinario["foo"] == self.ordinario["bar"]

    def permite_multiples_alias(self):
        assert self.ordinario["foo"] == self.ordinario["otrobar"]

    def permite_especificacion_predeterminada(self):
        assert self.ordinario[""] == self.ordinario["biz"]

    def tiene_opcion_de_autoprint(self):
        ap = self._carga("autoimpresion")
        assert ap["nop"].autoimpresion is False
        assert ap["yup"].autoimpresion is True

    def genera_ValueError_en_multiples_defaults(self):
        with raises(ValueError):
            self._carga("decorador_multi_default")

    def setea_ayuda_arg(self):
        assert self.ordinario["holocron"].help["porque"] == "Motivo"

    def setea_tipo_arg(self):
        skip()

    def establece_que_args_son_opcionales(self):
        assert self.ordinario["valores_opcionales"].opcional == ("miopc",)

    def permite_anotar_args_como_posicionales(self):
        assert self.ordinario["un_posicional"].posicional == ["pos"]
        assert self.ordinario["dos_posicionales"].posicional == ["pos1", "pos2"]

    def permite_anotar_args_como_iterables(self):
        assert self.ordinario["valores_iterables"].iterable == ["milista"]

    def permite_anotar_args_como_incrementables(self):
        arg = self.ordinario["valores_incrementables"]
        assert arg.incremento == ["verbose"]

    def cuando_faltan_arg_posicionales_todos_los_args_no_default_son_posicionales(self):
        arg = self.ordinario["posicionales_implícitos"]
        assert arg.posicional == ["pos1", "pos2"]

    def args_de_contexto_no_deben_aparecer_en_la_lista_posicional_implícita(self):
        @artefacto
        def miartefacto(c):
            pass

        assert len(miartefacto.posicional) == 0

    def pre_artefactos_almacenados_directamente(self):
        @artefacto
        def cualquier(c):
            pass

        @artefacto(pre=[cualquier])
        def func(c):
            pass

        assert func.pre == [cualquier]

    def permite_args_estelares_como_atajo_para_pre(self):
        @artefacto
        def pre1(c):
            pass

        @artefacto
        def pre2(c):
            pass

        @artefacto(pre1, pre2)
        def func(c):
            pass

        assert func.pre == (pre1, pre2)

    def no_permite_la_ambiguedad_entre_args_estelares_y_pre_kwarg(self):
        @artefacto
        def pre1(c):
            pass

        @artefacto
        def pre2(c):
            pass

        with raises(TypeError):

            @artefacto(pre1, pre=[pre2])
            def func(c):
                pass

    def setea_el_nombre(self):
        @artefacto(nombre="foo")
        def bar(c):
            pass

        assert bar.nombre == "foo"

    def devuelve_instancias_de_Artefacto_por_defecto(self):
        @artefacto
        def miartefacto(c):
            pass

        assert isinstance(miartefacto, Artefacto)

    def klase_kwarg_permite_anular_la_clase_utilizada(self):
        class MiArtefacto(Artefacto):
            pass

        @artefacto(klase=MiArtefacto)
        def miartefacto(c):
            pass

        assert isinstance(miartefacto, MiArtefacto)

    def klase_kwarg_funciona_para_subclasificadores_sin_kwargs(self):
        # Es decir la prueba anterior no detecta este caso de uso particular
        class MiArtefacto(Artefacto):
            pass

        def usa_MiArtefacto(*args, **kwargs):
            kwargs.setdefault("klase", MiArtefacto)
            return artefacto(*args, **kwargs)

        @usa_MiArtefacto
        def miartefacto(c):
            pass

        assert isinstance(miartefacto, MiArtefacto)

    def Kwargs_desconocidos_se_loquean_a_nivel_de_artefacto(self):
        # NOTE: este era un comportamiento no probado anteriormente. De 
        # hecho, acabamos de modificar CÓMO se genera TypeError (constructor
        # Artefacto, implícitamente, frente a explícitamente en @artefacto),
        # pero el resultado final es el mismo para cualquiera que no intente
        # escribir en cadena en función del mensaje de excepción.
        with raises(TypeError):

            @artefacto(cualquier="pieza")
            def miartefacto(c):
                pass


class Artefacto_:
    def tiene_repr_util(self):
        i = repr(Artefacto(_func))
        assert "_func" in i, "'func' no encontrado en {!r}".format(i)
        e = repr(Artefacto(_func, nombre="miedoso"))
        assert "miedoso" in e, "'miedoso' no encontrado en {!r}".format(e)
        assert "_func" not in e, "'_func' visto inesperadamente en {!r}".format(e)

    def prueba_de_igualdad(self):
        t1 = Artefacto(_func, nombre="foo")
        t2 = Artefacto(_func, nombre="foo")
        assert t1 == t2
        t3 = Artefacto(_func, nombre="bar")
        assert t1 != t3

    class funcion_como_comportamiento:
        # Cosas que les ayudan, por ejemplo, a aparecer en autodoc más fácilmente
        def inherits_module_from_body(self):
            miartefacto = Artefacto(_func, nombre="miedoso")
            assert miartefacto.__module__ is _func.__module__

    class atributos:
        def tiene_bandera_predeterminada(self):
            assert Artefacto(_func).es_predeterminado is False

        def nombre_predeterminado_es_el_nombre_del_cuerpo(self):
            assert Artefacto(_func).nombre == "_func"

        def puede_anular_nombre(self):
            assert Artefacto(_func, nombre="foo").nombre == "foo"

    class invocabilidad:
        def setup(self):
            @artefacto
            def foo(c):
                "Mi textdocs"
                return 5

            self.artefacto = foo

        def llamada_dunder_entornouelve_la_llamada_del_cuerpo(self):
            contexto = Contexto()
            assert self.artefacto(contexto) == 5

        def errores_si_el_primer_arg_no_es_Contexto(self):
            @artefacto
            def miartefacto(c):
                pass

            with raises(TypeError):
                miartefacto(5)

        def errores_si_no_hay_primer_arg_en_absoluto(self):
            with raises(TypeError):

                @artefacto
                def miartefacto():
                    pass

        def rastrea_tiempos_llamados(self):
            contexto = Contexto()
            assert self.artefacto.llamados is False
            self.artefacto(contexto)
            assert self.artefacto.llamados is True
            assert self.artefacto.veces_de_llamado == 1
            self.artefacto(contexto)
            assert self.artefacto.veces_de_llamado == 2

        def envuelve_docstring_cuerpo(self):
            assert self.artefacto.__doc__ == "Mi textdocs"

        def envuelve_nombre_del_cuerpo(self):
            assert self.artefacto.__name__ == "foo"

    class obtener_argumentos:
        def setup(self):
            @artefacto(posicional=["arg_3", "arg1"], opcional=["arg1"])
            def miartefacto(c, arg1, arg2=False, arg_3=5):
                pass

            self.artefacto = miartefacto
            self.args = self.artefacto.obtener_argumentos()
            self.argdic = self._arglista_a_dic(self.args)

        def _arglista_a_dic(self, arglista):
            # Esto duplica Contexto.agregar_arg(x) para x en arglista :(
            ret = {}
            for arg in arglista:
                for nombre in arg.nombres:
                    ret[nombre] = arg
            return ret

        def _artefacto_a_dic(self, artefacto):
            return self._arglista_a_dic(artefacto.obtener_argumentos())

        def args_posicionales_son_primero(self):
            assert self.args[0].nombre == "arg_3"
            assert self.args[1].nombre == "arg1"
            assert self.args[2].nombre == "arg2"

        def tipos_se_conservan(self):
            # Recuerde que el 'tipo' predeterminado es una cadena.
            assert [x.tipo for x in self.args] == [int, str, bool]

        def se_conserva_la_bandera_de_posicion(self):
            assert [x.posicional for x in self.args] == [True, True, False]

        def se_conserva_la_bandera_opcional(self):
            assert [x.opcional for x in self.args] == [False, True, False]

        def opcional_evita_default_bool_afecten_al_tipo(self):
            # Re # 416. Consulte las notas en la función bajo prueba para
            # conocer la justificación.
            @artefacto(opcional=["miarg"])
            def miartefacto(c, miarg=False):
                pass

            arg = miartefacto.obtener_argumentos()[0]
            assert arg.tipo is str  # no booleano!

        def plus_opcional_noboleano_predeterminado_no_anula_tipo(self):
            @artefacto(opcional=["miarg"])
            def miartefacto(c, miarg=17):
                pass

            arg = miartefacto.obtener_argumentos()[0]
            assert arg.tipo is int  # not str!

        def convierte_la_firma_de_la_funcion_en_Argumentos(self):
            assert len(self.args), 3 == str(self.args)
            assert "arg2" in self.argdic

        def banderascortas_creadas_por_defecto(self):
            assert "a" in self.argdic
            assert self.argdic["a"] is self.argdic["arg1"]

        def banderascortas_no_les_importa_posicionales(self):
            "El posicionamiento no afecta si se hacen banderascortas"
            for corto, largo_ in (("a", "arg1"), ("r", "arg2"), ("g", "arg-3")):
                assert self.argdic[corto] is self.argdic[largo_]

        def autocreacion_de_banderascortas_se_puede_desactivar(self):
            @artefacto(auto_banderascortas=False)
            def miartefacto(c, arg):
                pass

            args = self._artefacto_a_dic(miartefacto)
            assert "a" not in args
            assert "arg" in args

        def autocreacion_de_banderascortas_no_colisionan(self):
            "Banderas-cortas creadas automáticamente no colisionan"
            @artefacto
            def miartefacto(c, arg1, arg2, barg):
                pass

            args = self._artefacto_a_dic(miartefacto)
            assert "a" in args
            assert args["a"] is args["arg1"]
            assert "r" in args
            assert args["r"] is args["arg2"]
            assert "b" in args
            assert args["b"] is args["barg"]

        def auto_banderascortas_tempranas__no_debe_bloquear_las_banderascortas_reales(self):
            # Es decir "artefacto --foo -f" => --foo NO debería elegir '-f' para su 
            # banderacorta o '-f' está totalmente jodido.
            @artefacto
            def miartefacto(c, arglargo, l):
                pass

            args = self._artefacto_a_dic(miartefacto)
            assert "arglargo" in args
            assert "o" in args
            assert args["o"] is args["arglargo"]
            assert "l" in args

        def argumentos_de_contexto_no_se_devuelven(self):
            @artefacto
            def miartefacto(c):
                pass

            assert len(miartefacto.obtener_argumentos()) == 0

        def guionesbajos_se_convierten_en_guiones(self):
            @artefacto
            def miartefacto(c, arg_extesnso):
                pass

            arg = miartefacto.obtener_argumentos()[0]
            assert arg.nombres == ("arg-extesnso", "l")
            assert arg.nombre_de_atributo == "arg_extesnso"
            assert arg.nombre == "arg_extesnso"


# Artefacto ficticio para la prueba de llamada
_ = object()


class Llamada_:
    def setup(self):
        self.artefacto = Artefacto(Mock(__name__="miartefacto"))

    class init:
        class artefacto:
            def es_requerido(self):
                with raises(TypeError):
                    Llamar()

            def es_el_primer_posarg(self):
                assert Llamar(_).artefacto is _

        class llamado_de:
            def pordefecto_a_None(self):
                assert Llamar(_).llamado_de is None

            def puede_ser_dado(self):
                assert Llamar(_, llamado_de="foo").llamado_de == "foo"

        class args:
            def por_defecto_es_tupla_vacía(self):
                assert Llamar(_).args == tuple()

            def puede_ser_dado(self):
                assert Llamar(_, args=(1, 2, 3)).args == (1, 2, 3)

        class kwargs:
            def por_defecto_es_dic_vacio(self):
                assert Llamar(_).kwargs == dict()

            def puede_ser_dado(self):
                assert Llamar(_, kwargs={"foo": "bar"}).kwargs == {"foo": "bar"}

    class stringrep:
        "__str__"

        def incluye_nombre_del_artefacto(self):
            llamar = Llamar(self.artefacto)
            assert str(llamar) == "<Llamar 'miartefacto', args: (), kwargs: {}>"

        def trabaja_para_subclases(self):
            class MiLlamada(Llamar):
                pass

            llamar = MiLlamada(self.artefacto)
            assert "<MiLlamada" in str(llamar)

        def incluye_args_y_kwargs(self):
            llamar = Llamar(
                self.artefacto,
                args=("posarg1", "posarg2"),
                # Dict de clave-única para evitar problemas ordenamiento de dict
                kwargs={"kwarg1": "val1"},
            )
            esperado = "<Llamar 'miartefacto', args: ('posarg1', 'posarg2'), kwargs: {'kwarg1': 'val1'}>"  # noqa
            assert str(llamar) == esperado

        def incluye_aka_si_se_da_un_nombre_explícito(self):
            llamar = Llamar(self.artefacto, llamado_de="noesmiartefacto")
            esperado = "<Llamar 'miartefacto' (called as: 'noesmiartefacto'), args: (), kwargs: {}>"  # noqa
            assert str(llamar) == esperado

        def omite_alias_si_el_nombre_explícito_es_el_mismo_que_el_nombre_del_artefacto(self):
            llamar = Llamar(self.artefacto, llamado_de="miartefacto")
            assert str(llamar) == "<Llamar 'miartefacto', args: (), kwargs: {}>"

    class crear_contexto:
        def requiere_argumento_de_configuracion(self):
            with raises(TypeError):
                Llamar(_).crear_contexto()

        def crea_un_nuevo_Contexto_a_partir_de_la_config_dada(self):
            conf = Config(defaults={"foo": "bar"})
            c = Llamar(_).crear_contexto(conf)
            assert isinstance(c, Contexto)
            assert c.foo == "bar"

    class clon:
        def devuelve_un_objeto_nuevo_pero_equivalente(self):
            orig = Llamar(self.artefacto)
            clon = orig.clonar()
            assert clon is not orig
            assert clon == orig

        def puede_clonar_en_una_subclase(self):
            orig = Llamar(self.artefacto)

            class MiLlamada(Llamar):
                pass

            clon = orig.clonar(dentro=MiLlamada)
            assert clon == orig
            assert isinstance(clon, MiLlamada)

        def se_le_pueden_dar_kwargs_adicionales_para_clonar_con(self):
            orig = Llamar(self.artefacto)

            class MiLlamada(Llamar):
                def __init__(self, *args, **kwargs):
                    self.hurra = kwargs.pop("hurra")
                    super(MiLlamada, self).__init__(*args, **kwargs)

            clon = orig.clonar(dentro=MiLlamada, with_={"hurra": "woo"})
            assert clon.hurra == "woo"
