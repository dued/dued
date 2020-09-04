from dued.util import lineadeayuda


class util:
    class lineadeayuda:
        def es_None_si_no_hay_textdocs(self):
            def foo(c):
                pass

            assert lineadeayuda(foo) is None

        def es_todo_si_textdocs_es_una_linea(self):
            def foo(c):
                "foo!"
                pass

            assert lineadeayuda(foo) == "foo!"

        def franja_izquierdas_nueva_línea_que_lleva_una_linea(self):
            def foo(c):
                """
                foo!
                """
                pass

            assert lineadeayuda(foo) == "foo!"

        def es_la_primera_linea_en_un_textdocs_multilinea(self):
            def foo(c):
                """
                foo?

                foo!
                """
                pass

            assert lineadeayuda(foo) == "foo?"

        def es_None_si_textdocs_coincide_con_el_tipos_de_objecto(self):
            # Es decir, no queremos un textdocs que viene de la clase en lugar
            # de la instancia.
            class Foo(object):
                "Yo soy un Foo"
                pass

            foo = Foo()
            assert lineadeayuda(foo) is None

        def instancia_adjunta_textdocs_todavia_se_muestra(self):
            # Esto es en realidad una propiedad de la semántica de objetos
            # regulares, pero lo que sea, porque no tienen una prueba para 
            # ello.
            class Foo(object):
                "Yo soy un Foo"
                pass

            foo = Foo()
            foo.__doc__ = "Yo soy un foo"
            assert lineadeayuda(foo) == "Yo soy un foo"
