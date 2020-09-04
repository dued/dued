from pytest import raises

from dued.config import fusionar_dics, copiar_dic, ErrorDeFusionAmbiguo


class fusionar_dics_:
    # NOTE: por lo general, no me gusta hacer pruebas unitarias verdaderas de
    # plomería de bajo nivel; prefiero inferir que todo funciona examinando el
    # comportamiento de nivel superior, pero a veces es necesario sellar la 
    # salida de ciertos errores más fácilmente.

    def fusion_de_datos_en_dic_vacio(self):
        d1 = {}
        d2 = {"foo": "bar"}
        fusionar_dics(d1, d2)
        assert d1 == d2

    def actualizar_con_None_actua_como_la_fusion_de_dic_vacio(self):
        # Cuando hay un error, AttributeError se genera en None.items()
        d1 = {"mis": "datos"}
        d2 = None
        fusionar_dics(d1, d2)
        assert d1 == {"mis": "datos"}

    def fusiones_de_datos_ortogonal(self):
        d1 = {"foo": "bar"}
        d2 = {"biz": "baz"}
        fusionar_dics(d1, d2)
        assert d1 == {"foo": "bar", "biz": "baz"}

    def actualizaciones_arg_ganan_valores(self):
        d1 = {"foo": "bar"}
        d2 = {"foo": "nobar"}
        fusionar_dics(d1, d2)
        assert d1 == {"foo": "nobar"}

    def la_falta_de_coincidencia_del_tipo_nodic_se_sobreescribe_ok(self):
        d1 = {"foo": "bar"}
        d2 = {"foo": [1, 2, 3]}
        fusionar_dics(d1, d2)
        assert d1 == {"foo": [1, 2, 3]}

    def fusion_de_dic_en_nodic_genera_error(self):
        # TODO: o ... ¡¿debería ?! Si un usuario realmente quiere tomar una
        # ruta de configuración preexistente y hacerla 'más profunda'
        # sobrescribiendo, por ejemplo, una cadena con un dic de cadenas
        # (o cualquier) ... ¿se les debería permitir?
        d1 = {"foo": "bar"}
        d2 = {"foo": {"uh": "oh"}}
        with raises(ErrorDeFusionAmbiguo):
            fusionar_dics(d1, d2)

    def fusion_nodic_en_dic_genera_error(self):
        d1 = {"foo": {"uh": "oh"}}
        d2 = {"foo": "bar"}
        with raises(ErrorDeFusionAmbiguo):
            fusionar_dics(d1, d2)

    def los_valores_de_hoja_anidada_se_fusionan_ok(self):
        d1 = {"foo": {"bar": {"biz": "baz"}}}
        d2 = {"foo": {"bar": {"biz": "nobaz"}}}
        fusionar_dics(d1, d2)
        assert d1 == {"foo": {"bar": {"biz": "nobaz"}}}

    def los_niveles_de_rama_mixtos_se_fusionan_ok(self):
        d1 = {"foo": {"bar": {"biz": "baz"}}, "bah": 17, "miprop": "ok"}
        d2 = {"foo": {"bar": {"biz": "nobaz"}}, "bah": 25}
        fusionar_dics(d1, d2)
        esperado = {
            "foo": {"bar": {"biz": "nobaz"}},
            "bah": 25,
            "miprop": "ok",
        }
        assert d1 == esperado

    def fusiones_de_valores_de_dic_no_son_referencias(self):
        nucleo = {}
        colecc = {"foo": {"bar": {"biz": "colecc valor"}}}
        proy = {"foo": {"bar": {"biz": "proy valor"}}}
        # Fusión inicial: cuando hay un error, esto establece el núcleo['foo']
        # en todo el dic 'foo' en 'proy' como referencia, lo que significa que
        # se 'enlaza' con el dic 'proy' siempre que se fusionen otras cosas
        # en él
        fusionar_dics(nucleo, proy)
        assert nucleo == {"foo": {"bar": {"biz": "proy valor"}}}
        assert proy["foo"]["bar"]["biz"] == "proy valor"
        # Las pruebas de identidad también pueden probar el error temprano
        assert (
            nucleo["foo"] is not proy["foo"]
        ), "Core foo es literalmente proy foo!"  # noqa
        # Fusión posterior: esta vez solo sobrescribe los valores de hoja 
        # (por lo tanto, no hay un cambio real, pero esto es lo que hace el
        # código de fusión de configuración real, así que porque no)
        fusionar_dics(nucleo, proy)
        assert nucleo == {"foo": {"bar": {"biz": "proy valor"}}}
        assert proy["foo"]["bar"]["biz"] == "proy valor"
        # El problema se fusiona: cuando hay un error, nucleo['foo'] hace 
        # referencia a 'foo' dentro de 'proy', por lo que esto termina
        # modificando "nucleo", ¡pero en realidad también afecta a "proy"!
        fusionar_dics(nucleo, colecc)
        # Expect that the nucleo dict got the update from 'colecc'...
        assert nucleo == {"foo": {"bar": {"biz": "colecc valor"}}}
        # BUT that 'proy' remains UNTOUCHED
        assert proy["foo"]["bar"]["biz"] == "proy valor"

    def combina_tipos_de_archivo_por_referencia(self):
        with open(__file__) as fd:
            d1 = {}
            d2 = {"foo": fd}
            fusionar_dics(d1, d2)
            assert d1["foo"].closed is False


class copy_dict_:
    def devuelve_una_copia_profunda_de_un_dic(self):
        # NOTE: no es una deepcopy real...
        source = {"foo": {"bar": {"biz": "baz"}}}
        copy = copiar_dic(source)
        assert copy["foo"]["bar"] == source["foo"]["bar"]
        assert copy["foo"]["bar"] is not source["foo"]["bar"]
        copy["foo"]["bar"]["biz"] = "nobaz"
        assert source["foo"]["bar"]["biz"] == "baz"
