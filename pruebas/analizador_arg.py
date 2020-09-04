from pytest import skip, raises

from dued.analizador import Argumento


class Argumento_:
    class init:
        "__init__"

        def puede_llevar_lista_de_nombres(self):
            nombres = ("--foo", "-f")
            a = Argumento(nombres=nombres)
            # herp a derp
            for nombre in nombres:
                assert nombre in a.nombres

        def puede_tomar_el_nombre_arg(self):
            assert "-b" in Argumento(nombre="-b").nombres

        def debe_tener_al_menos_un_nombre(self):
            with raises(TypeError):
                Argumento()

        def arg_default_es_nombre_no_nombres(self):
            assert "b" in Argumento("b").nombres

        def puede_declarar_posicional(self):
            assert Argumento(nombre="foo", posicional=True).posicional is True

        def posicional_es_False_por_defecto(self):
            assert Argumento(nombre="foo").posicional is False

        def puede_setear_el_nombre_del_atrib__para_controlar_el_atrib_nombre(self):
            a = Argumento("foo", nombre_de_atributo="bar")
            assert a.nombre == "bar"  # not 'foo'

    class repr:
        "__repr__"

        def muestra_informacion_util(self):
            arg = Argumento(nombres=("nombre", "nick1", "nick2"))
            esperado = "<Argumento: {} ({})>".format("nombre", "nick1, nick2")
            assert repr(arg) == esperado

        def no_muestra_parientes_de_apodo_si_no_hay_apodos(self):
            assert repr(Argumento("nombre")) == "<Argumento: nombre>"

        def muestra_posicionalidad(self):
            arg = Argumento("nombre", posicional=True)
            assert repr(arg) == "<Argumento: nombre *>"

        def muestra_opcionalidad(self):
            arg = Argumento("nombre", opcional=True)
            assert repr(arg) == "<Argumento: nombre ?>"

        def posicionalidad_y_opcionalidad_se_unen(self):
            # TODO: pero ¿tienen sentido en el mismo argumento? Por ahora, es
            # mejor tener una prueba sin sentido que una falta ...
            arg = Argumento("nombre", opcional=True, posicional=True)
            assert repr(arg) == "<Argumento: nombre *?>"

        def muestra_tipo_si_no_str(self):
            assert repr(Argumento("age", tipo=int)) == "<Argumento: age [int]>"

        def todas_las_cosas_juntas(self):
            arg = Argumento(
                nombres=("bah", "m"), tipo=int, opcional=True, posicional=True
            )
            assert repr(arg) == "<Argumento: bah (m) [int] *?>"

    class tipo_kwarg:
        "'tipo' kwarg"

        def es_opcional(self):
            Argumento(nombre="a")
            Argumento(nombre="b", tipo=int)

        def defaults_a_str(self):
            assert Argumento("a").tipo == str

        def no_bool_implica_valor(self):
            assert Argumento(nombre="a", tipo=int).toma_valor
            assert Argumento(nombre="b", tipo=str).toma_valor
            assert Argumento(nombre="c", tipo=list).toma_valor

        def bool_implica_que_no_se_necesita_ningún_valor(self):
            assert not Argumento(nombre="a", tipo=bool).toma_valor

        def bool_implica_predeterminado_False_no_None(self):
            # Ahora mismo, analizando una bandera bool no se ha dado resultado
            # en Ninguno. TODO: puede querer más matices aquí -- False cuando
            # se da una bandera --no-XXX, True si --XXX, None si no se ve?
            # Solo tiene sentido si agregamos cosas automáticas --no-XXX 
            # (piense ./configurar)
            skip()

        def puede_validar_en_el_set(self):
            with raises(ValueError):
                Argumento("a", tipo=int).valor = "five"

        def lista_implica_el_valor_inicial_de_lista_vacía(self):
            assert Argumento("milista", tipo=list).valor == []

    class nombres:
        def devuelve_la_tupla_de_todos_los_nombres(self):
            assert Argumento(nombres=("--foo", "-b")).nombres == ("--foo", "-b")
            assert Argumento(nombre="--foo").nombres == ("--foo",)

        def se_normaliza_a_una_tupla(self):
            assert isinstance(Argumento(nombres=("a", "b")).nombres, tuple)

    class nombre:
        def devuelve_el_primer_nombre(self):
            assert Argumento(nombres=("a", "b")).nombre == "a"

    class nicknombres:
        def devuelve_el_resto_de_nombres(self):
            assert Argumento(nombres=("a", "b")).nicknombres == ("b",)

    class toma_valor:
        def True_por_defecto(self):
            assert Argumento(nombre="a").toma_valor

        def False_si_el_tipo_es_bool(self):
            assert not Argumento(nombre="-b", tipo=bool).toma_valor

    class value_set:
        "valor="

        def disponible_como_punto_valor_bruto(self):
            "available as .valor_bruto"
            a = Argumento("a")
            a.valor = "foo"
            assert a.valor_bruto == "foo"

        def sin_transformar_aparece_como_punto_valor(self):
            "sin transformar, aparece como .valor"
            a = Argumento("a", tipo=str)
            a.valor = "foo"
            assert a.valor == "foo"

        def transformado_aparece_como_punto_valor_con_original_como_valor_bruto(self):
            "transformed, modified valor is .valor, original is .valor_bruto"
            a = Argumento("a", tipo=int)
            a.valor = "5"
            assert a.valor == 5
            assert a.valor_bruto == "5"

        def tipo_lista_de_desencadenadores_anexar_en_lugar_de_sobrescribir(self):
            # TODO: cuando se pone de esta manera hace que la API se vea 
            # bastante extraña; tal vez un signo, deberíamos cambiar a métodos
            # de establecimiento explícitos (seleccionados en tipo, tal vez)
            # en lugar de usar un establecedor implícito
            a = Argumento("milista", tipo=list)
            assert a.valor == []
            a.valor = "val1"
            assert a.valor == ["val1"]
            a.valor = "val2"
            assert a.valor == ["val1", "val2"]

        def incremento_True_desencadena_el_incremento_por_default(self):
            a = Argumento("verbose", tipo=int, default=0, incremento=True)
            assert a.valor == 0
            # NOTE: el analizador actualmente sólo dice "Argumento.toma_valor
            # es falso? Va a poner True/False ahí." Así que esto parece bastante
            # tonto fuera de contexto (como con los tipos-de-lista de arriba.)
            a.valor = True
            assert a.valor == 1
            for _ in range(4):
                a.valor = True
            assert a.valor == 5

    class valor:
        def devuelve_el_valor_por_defecto_si_no_esta_configurado(self):
            a = Argumento("a", default=25)
            assert a.valor == 25

    class valor_bruto:
        def es_None_cuando_no_hay_un_valor_realmente_visto(self):
            a = Argumento("a", tipo=int)
            assert a.valor_bruto is None

    class obtuvo_valor:
        def prueba_de_tipo_no_list_para_valor_None(self):
            arg = Argumento("a")
            assert not arg.obtuvo_valor
            arg.valor = "algo"
            assert arg.obtuvo_valor

        def prueba_de_tipo_list_para_valor_de_lista_vacia(self):
            arg = Argumento("a", tipo=list)
            assert not arg.obtuvo_valor
            arg.valor = "agrega-me"
            assert arg.obtuvo_valor

    class asigna_valor:
        def casting_por_defecto(self):
            a = Argumento("a", tipo=int)
            a.asigna_valor("5")
            assert a.valor == 5

        def permite_setear_valor_sin_casting(self):
            a = Argumento("a", tipo=int)
            a.asigna_valor("5", cast=False)
            assert a.valor == "5"
