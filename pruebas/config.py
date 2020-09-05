import pickle
import os
from os.path import join, expanduser

from dued.util import six
from mock import patch, call, Mock
import pytest
from pytest_relaxed import raises

from dued.corredores import Local
from dued.config import Config
from dued.excepciones import (
    VarEntAmbigua,
    VarEntInestable,
    TipoDeArchivoDesconocido,
    MiembroDeConfigNoSeleccionable,
)

from _util import saltar_si_es_windows, soporte


marcapytest = pytest.mark.usefixtures("integracion")


CONFIGS_RUTA = "configs"
TIPOS = ("yaml", "yml", "json", "python")


def _carga(kwarg, tipo_, **kwargs):
    ruta = join(CONFIGS_RUTA, tipo_ + "/")
    kwargs[kwarg] = ruta
    return Config(**kwargs)


class Config_:
    class atributos_de_clase:
        # TODO: mover todos los demás kwargs que no contienen datos a este modo
        class prefijo:
            def pordefecto_a_dued(self):
                assert Config().prefijo == "dued"

            @patch.object(Config, "_cargar_yaml")
            def informa_nombres_de_archivos_de_config(self, cargar_yaml):
                class MiConf(Config):
                    prefijo = "otro"

                MiConf(sistema_prefijo="dir/")
                cargar_yaml.assert_cualquier_llamada("dir/otro.yaml")

            def informa_prefijo_var_ent(self):
                os.environ["OTRO_FOO"] = "bar"

                class MiConf(Config):
                    prefijo = "otro"

                c = MiConf(defaults={"foo": "nobar"})
                c.cargar_entorno_shell()
                assert c.foo == "bar"

        class prefijo_de_archivo:
            def pordefecto_a_None(self):
                assert Config().prefijo_de_archivo is None

            @patch.object(Config, "_cargar_yaml")
            def informa_nombres_de_archivos_de_config(self, cargar_yaml):
                class MiConf(Config):
                    prefijo_de_archivo = "otro"

                MiConf(sistema_prefijo="dir/")
                cargar_yaml.assert_cualquier_llamada("dir/otro.yaml")

        class entorno_prefijo:
            def pordefecto_a_None(self):
                assert Config().entorno_prefijo is None

            def informa_var_ent_cargados(self):
                os.environ["OTRO_FOO"] = "bar"

                class MiConf(Config):
                    entorno_prefijo = "otro"

                c = MiConf(defaults={"foo": "nobar"})
                c.cargar_entorno_shell()
                assert c.foo == "bar"

    class global_defaults:
        @saltar_si_es_windows
        def ajustes_basicos(self):
            # Solo un resumen de lo que debería ser la configuración de la 
            # línea de base ... por alguna razón, no estamos capturando todos
            # estos de manera confiable (incluso si sus valores por defecto a
            # menudo están implícitos en las pruebas que los anulan, por ej.,
            # corredor pruebas alrededor de alarma=True , etc.).
            esperado = {
                "correr": {
                    "asincrono": False,
                    "rechazado": False,
                    "seco": False,
                    "echo": False,
                    "echo_stdin": None,
                    "codificacion": None,
                    "entorno": {},
                    "err_stream": None,
                    "retroceder": True,
                    "ocultar": None,
                    "ing_stream": None,
                    "sal_stream": None,
                    "pty": False,
                    "reemplazar_ent": False,
                    "shell": "/bin/bash",
                    "alarma": False,
                    "centinelas": [],
                },
                "corredores": {"local": Local},
                "sudo": {
                    "password": None,
                    "prompt": "[sudo] password: ",
                    "usuario": None,
                },
                "artefactos": {
                    "nombre_auto_guion": True,
                    "nombre_de_coleccion": "artefactos",
                    "dedupe": True,
                    "clase_ejecutor": None,
                    "dir_raiz": None,
                },
                "tiempo_de_descanso": {"comando": None},
            }
            assert Config.global_defaults() == esperado

    class init:
        "__init__"

        def puede_estar_vacio(self):
            assert Config().__class__ == Config  # derp

        @patch.object(Config, "_cargar_yaml")
        def configurar_el_prefijo_de_ubicacion_global(self, cargar_yaml):
            # ¿Esto es un poco miedoso pero más útil que simplemente replicar
            # la misma prueba más abajo?
            Config(sistema_prefijo="bah/")
            cargar_yaml.assert_cualquier_llamada("bah/dued.yaml")

        @saltar_si_es_windows
        @patch.object(Config, "_cargar_yaml")
        def prefijo_pordefecto_del_sistema_es_etc(self, cargar_yaml):
            # TODO: ¿hacer que esto funcione en Windows de alguna manera
            # sin ser una tautología total? je.
            Config()
            cargar_yaml.assert_cualquier_llamada("/etc/dued.yaml")

        @patch.object(Config, "_cargar_yaml")
        def configura_prefijo_de_ubic_del_usuario(self, cargar_yaml):
            Config(ususario_prefijo="cualquier/")
            cargar_yaml.assert_cualquier_llamada("cualquier/dued.yaml")

        @patch.object(Config, "_cargar_yaml")
        def prefijo_de_usuario_pordefecto_es_homedir_mas_punto(self, cargar_yaml):
            Config()
            cargar_yaml.assert_cualquier_llamada(expanduser("~/.dued.yaml"))

        @patch.object(Config, "_cargar_yaml")
        def configura_la_ubicacion_del_proyecto(self, cargar_yaml):
            Config(dir_de_py="algunproyecto").cargar_proyecto()
            cargar_yaml.assert_cualquier_llamada(join("algunproyecto", "dued.yaml"))

        @patch.object(Config, "_cargar_yaml")
        def configure_ruta_al_acte(self, cargar_yaml):
            Config(acte_ruta="alguna/ruta.yaml").cargar_acte()
            cargar_yaml.assert_cualquier_llamada("alguna/ruta.yaml")

        def acepta_valores_pordefecto_dict_kwarg(self):
            c = Config(defaults={"super": "bajo nivel"})
            assert c.super == "bajo nivel"

        def anula_el_dict_es_el_primer_posarg(self):
            c = Config({"nuevo": "datos", "correr": {"ocultar": True}})
            assert c.correr.ocultar is True  # default es False
            assert c.correr.alarma is False  # en valores predet. globales, intactos
            assert c.nuevo == "datos"  # datos solo presentes al nivel anulaciones

        def anula_el_dict_es_ademas_un_kwarg(self):
            c = Config(anulaciones={"correr": {"ocultar": True}})
            assert c.correr.ocultar is True

        @patch.object(Config, "cargar_sistema")
        @patch.object(Config, "cargar_usuario")
        @patch.object(Config, "combinar")
        def archivos_de_sistema_y_del_usuario_se_cargan_automáticamente(
            self, combinar, cargar_u, cargar_s
        ):
            Config()
            cargar_s.asercion_llamado_una_vez_con(combinar=False)
            cargar_u.asercion_llamado_una_vez_con(combinar=False)
            combinar.asercion_llamado_una_vez_con()

        @patch.object(Config, "cargar_sistema")
        @patch.object(Config, "cargar_usuario")
        def puede_aplazar_la_carga_de_arch_de_sistema_y_de_usuario(self, cargar_u, cargar_s):
            config = Config(lento=True)
            assert not cargar_s.called
            assert not cargar_u.called
            # ¡Asegúrese de que los niveles predeterminados sigan en su lugar!
            # (Cuando hay un error, es decir, combinar() nunca se llama, la 
            # configuración aparece efectivamente vacía).
            assert config.correr.echo is False

    class API_basica:
        "Componentes API básicos"

        def se_puede_usar_directamente_despues_de_init(self):
            # No cargar() aqui...
            c = Config({"muchos de estos": "prueba parece similar"})
            assert c["muchos de estos"] == "prueba parece similar"

        def permite_acceso_a_dic_y_attr(self):
            # TODO: combinar con pruebas para Contexto probablemente
            c = Config({"foo": "bar"})
            assert c.foo == "bar"
            assert c["foo"] == "bar"

        def valores_de_dic_anidados_tambien_permiten_el_acceso_dual(self):
            # TODO: ídem
            c = Config({"foo": "bar", "biz": {"baz": "boz"}})
            # Comprobación de cordura: anidado no elimina de manera simple
            # el nivel superior
            assert c.foo == "bar"
            assert c["foo"] == "bar"
            # Verificación real
            assert c.biz.baz == "boz"
            assert c["biz"]["baz"] == "boz"
            assert c.biz["baz"] == "boz"
            assert c["biz"].baz == "boz"

        def acceso_a_atrib_tiene_un_mensaje_de_error_util(self):
            c = Config()
            try:
                c.nop
            except AttributeError as e:
                esperado = """
No se encontró ningún atributo o key de configuración para 'nop'

Claves válidas: ['correr', 'corredores', 'sudo', 'artefactos', 'tiempo_de_descanso']

Atributos vigentes válidos: ['limpiar', 'clonar', 'entorno_prefijo', 'prefijo_de_archivo', 'datos_desde', 'global_defaults', '_cargar_archivo_de_conf_base', 'cargar_coleccion', 'cargar_defaults', 'cargar_anulaciones', 'cargar_proyecto', 'cargar_acte', 'cargar_entorno_shell', 'cargar_sistema', 'cargar_usuario', 'combinar', 'pop', 'popitem', 'prefijo', 'setea_ubic_del_py', 'setea_ruta_del_acte', 'setdefault', 'actualizar']
""".strip()  # noqa
                assert str(e) == esperado
            else:
                assert False, "¡No obtuve un AttributeError en una key incorrecta!"

        def subclaves_se_combinan_no_se_sobrescriben(self):
            # Asegura que las keys anidadas se fusionen profundamente
            # en lugar de superficialmente.
            defaults = {"foo": {"bar": "baz"}}
            anulaciones = {"foo": {"nobar": "nobaz"}}
            c = Config(defaults=defaults, anulaciones=anulaciones)
            assert c.foo.nobar == "nobaz"
            assert c.foo.bar == "baz"

        def es_iterable_como_dic(self):
            c = Config(defaults={"a": 1, "b": 2})
            assert set(c.keys()) == {"a", "b"}
            assert set(list(c)) == {"a", "b"}

        def admite_protocolos_de_dic_de_solo_lectura(self):
            # Utilice un  de un solo par de keys para evitar problemas de
            # clasificación en las pruebas.
            c = Config(defaults={"foo": "bar"})
            c2 = Config(defaults={"foo": "bar"})
            assert "foo" in c
            assert "foo" in c2  # principalmente solo para activar la carga: x
            assert c == c2
            assert len(c) == 1
            assert c.get("foo") == "bar"
            if six.PY2:
                assert c.has_key("foo") is True  # noqa
                assert list(c.iterkeys()) == ["foo"]
                assert list(c.itervalues()) == ["bar"]
            assert list(c.items()) == [("foo", "bar")]
            assert list(six.iteritems(c)) == [("foo", "bar")]
            assert list(c.keys()) == ["foo"]
            assert list(c.values()) == ["bar"]

        class carga_en_acte_defaults_y_anulaciones:
            def defaults_se_pueden_dar_via_metodo(self):
                c = Config()
                assert "foo" not in c
                c.cargar_defaults({"foo": "bar"})
                assert c.foo == "bar"

            def defaults_pueden_omitir_la_combinacion(self):
                c = Config()
                c.cargar_defaults({"foo": "bar"}, combinar=False)
                assert "foo" not in c
                c.combinar()
                assert c.foo == "bar"

            def anulacion_se_puede_dar_via_metodo(self):
                c = Config(defaults={"foo": "bar"})
                assert c.foo == "bar"  # defaults level
                c.cargar_anulaciones({"foo": "nobar"})
                assert c.foo == "nobar"  # nivel anulaciones

            def anulaciones_pueden_omitir_la_fusion(self):
                c = Config()
                c.cargar_anulaciones({"foo": "bar"}, combinar=False)
                assert "foo" not in c
                c.combinar()
                assert c.foo == "bar"

        class metodos_de_aliminacion:
            def pop(self):
                # Raiz
                c = Config(defaults={"foo": "bar"})
                assert c.pop("foo") == "bar"
                assert c == {}
                # Con el arg predeterminado
                assert c.pop("hum", "bien entonces") == "bien entonces"
                # Hoja (key diferente para evitar ErrorDeFusionAmbiguo)
                c.anidado = {"hojaclave": "hojavalor"}
                assert c.anidado.pop("hojaclave") == "hojavalor"
                assert c == {"anidado": {}}

            def delitem(self):
                "__delitem__"
                c = Config(defaults={"foo": "bar"})
                del c["foo"]
                assert c == {}
                c.anidado = {"hojaclave": "hojavalor"}
                del c.anidado["hojaclave"]
                assert c == {"anidado": {}}

            def delattr(self):
                "__delattr__"
                c = Config(defaults={"foo": "bar"})
                del c.foo
                assert c == {}
                c.anidado = {"hojaclave": "hojavalor"}
                del c.anidado.hojaclave
                assert c == {"anidado": {}}

            def limpiar(self):
                c = Config(defaults={"foo": "bar"})
                c.limpiar()
                assert c == {}
                c.anidado = {"hojaclave": "hojavalor"}
                c.anidado.clear()
                assert c == {"anidado": {}}

            def popitem(self):
                c = Config(defaults={"foo": "bar"})
                assert c.popitem() == ("foo", "bar")
                assert c == {}
                c.anidado = {"hojaclave": "hojavalor"}
                assert c.anidado.popitem() == ("hojaclave", "hojavalor")
                assert c == {"anidado": {}}

        class metodos_de_modificacion:
            def setitem(self):
                c = Config(defaults={"foo": "bar"})
                c["foo"] = "nobar"
                assert c.foo == "nobar"
                del c["foo"]
                c["anidado"] = {"hojaclave": "hojavalor"}
                assert c == {"anidado": {"hojaclave": "hojavalor"}}

            def setdefault(self):
                c = Config({"foo": "bar", "anidado": {"hojaclave": "hojavalor"}})
                assert c.setdefault("foo") == "bar"
                assert c.anidado.setdefault("hojaclave") == "hojavalor"
                assert c.setdefault("notfoo", "nobar") == "nobar"
                assert c.notfoo == "nobar"
                anidado = c.anidado.setdefault("otrahoja", "otroval")
                assert anidado == "otroval"
                assert c.anidado.otrahoja == "otroval"

            def actualizar(self):
                c = Config(
                    defaults={"foo": "bar", "anidado": {"hojaclave": "hojavalor"}}
                )
                # Regular : actualizar(dic)
                c.actualizar({"foo": "nobar"})
                assert c.foo == "nobar"
                c.anidado.actualizar({"hojaclave": "otroval"})
                assert c.anidado.hojaclave == "otroval"
                # Aparentemente permitido pero completamente inútil.
                c.actualizar()
                esperado = {"foo": "nobar", "anidado": {"hojaclave": "otroval"}}
                assert c == esperado
                # Kwarg edition
                c.actualizar(foo="otrobar")
                assert c.foo == "otrobar"
                # Iterator of 2-tuples edition
                c.anidado.actualizar(
                    [("hojaclave", "otrovalormas"), ("newhoja", "giro")]
                )
                assert c.anidado.hojaclave == "otrovalormas"
                assert c.anidado.newhoja == "giro"

        def restablecimiento_de_los_valores_eliminados_funciona_ok(self):
            # Suena como una estupidez para probar, pero cuando tenemos que
            # rastrear eliminaciones y mutaciones manualmente ... es algo 
            # fácil de pasar por alto
            c = Config(defaults={"foo": "bar"})
            assert c.foo == "bar"
            del c["foo"]
            # Controles de cordura
            assert "foo" not in c
            assert len(c) == 0
            # Vuelvi a ponerlo ... como un valor diferente, por diversión
            c.foo = "antiguamente bar"
            # Y asegúrate de que se atasque
            assert c.foo == "antiguamente bar"

        def eliminar_las_claves_principales_de_las_claves_eliminadas_las_subsume(self):
            c = Config({"foo": {"bar": "biz"}})
            del c.foo["bar"]
            del c.foo
            # Asegúrate de no terminar de alguna manera con 
            # {'foo': {'bar': None}}
            assert c._eliminaciones == {"foo": None}

        def admite_mutacion_via_acceso_a_atributos(self):
            c = Config({"foo": "bar"})
            assert c.foo == "bar"
            c.foo = "nobar"
            assert c.foo == "nobar"
            assert c["foo"] == "nobar"

        def admite_mutaciones_anidadas_via_acceso_a_atributos(self):
            c = Config({"foo": {"bar": "biz"}})
            assert c.foo.bar == "biz"
            c.foo.bar = "nobiz"
            assert c.foo.bar == "nobiz"
            assert c["foo"]["bar"] == "nobiz"

        def atrib_y_metodos_reales_triunfan_sobre_el_proxy_de_atrib(self):
            # Preparar
            class MiConfig(Config):
                miatrib = None

                def mimetodo(self):
                    return 7

            c = MiConfig({"miatrib": "foo", "mimetodo": "bar"})
            # Por defecto, el atributo y el valor de configuración están separados
            assert c.miatrib is None
            assert c["miatrib"] == "foo"
            # Después de un setattr, lo mismo ocurre

            c.miatrib = "notfoo"
            assert c.miatrib == "notfoo"
            assert c["miatrib"] == "foo"
            # Método y valor de configuración separados
            assert callable(c.mimetodo)
            assert c.mimetodo() == 7
            assert c["mimetodo"] == "bar"
            # Y lo mismo después de setattr
            def monos():
                return 13

            c.mimetodo = monos
            assert c.mimetodo() == 13
            assert c["mimetodo"] == "bar"

        def config_en_si_mismo_almacenado_como_nombre_privado(self):
            # Es decir se puede hacer referencia a una key llamada 'config',
            # que es relativamente común (por ejemplo, 
            # <Config> .miservicio.config -> el contenido de un archivo de config
            # o ruta, etc.)
            c = Config()
            c["foo"] = {"bar": "baz"}
            c["cualquier"] = {"config": "miconfig"}
            assert c.foo.bar == "baz"
            assert c.cualquier.config == "miconfig"

        def atrib_reales_heredados_tambien_ganan_sobre_las_claves_de_config(self):
            class MiConfigPrincipal(Config):
                atrib_principal = 17

            class MiConfig(MiConfigPrincipal):
                pass

            c = MiConfig()
            assert c.atrib_principal == 17
            c.atrib_principal = 33
            ups = "¡Ups! ¡Parece que config. ganó sobre el atrib real!"
            assert "atrib_principal" not in c, ups
            assert c.atrib_principal == 33
            c["atrib_principal"] = "quince"
            assert c.atrib_principal == 33
            assert c["atrib_principal"] == "quince"

        def pueden_establecer_atrib_inexistentes_para_crear_nuevas_config_de_nivel_sup(self):
            # Es decir algun_configfoo = 'bar' es como algun_config['foo'] = 'bar'.
            # Cuando esta prueba se rompe, generalmente significa que 
            # algun_config.foo = 'bar' establece un atributo regular,
            # ¡y la configuración en sí nunca se toca!
            c = Config()
            c.algun_ajuste = "algun_valor"
            assert c["algun_ajuste"] == "algun_valor"

        def setear_atrib_inexistente_tambien_funciona_anidado(self):
            c = Config()
            c.un_nido = {}
            assert c["un_nido"] == {}
            c.un_nido.un_huevo = True
            assert c["un_nido"]["un_huevo"]

        def visualizar_cadena(self):
            "__str__ y amigos"
            config = Config(defaults={"foo": "bar"})
            assert repr(config) == "<Config: {'foo': 'bar'}>"

        def la_combinacion_no_borra_las_modificaciones_o_eliminaciones_del_usuario(self):
            c = Config({"foo": {"bar": "biz"}, "error": True})
            c.foo.bar = "nobiz"
            del c["error"]
            assert c["foo"]["bar"] == "nobiz"
            assert "error" not in c
            c.combinar()
            # Volverá a 'biz' si los cambios del usuario no se guardan por sí
            # mismos (anteriormente eran solo mutaciones en la configuración
            # central almacenada en caché)
            assert c["foo"]["bar"] == "nobiz"
            # Y esto todavía estaría aquí también
            assert "error" not in c

    class carga_del_archivo_de_configuracion:
        "Carga del archivo de configuración"

        def sistema_global(self):
            "Archivos conf de todo el sistema"
            # NOTE: usando lento = True para evitar la carga automática y
            # poder probar que cargar_sistema() funciona.
            for tipo_ in TIPOS:
                config = _carga("sistema_prefijo", tipo_, lento=True)
                assert "exterior" not in config
                config.cargar_sistema()
                assert config.exterior.interior.hurra == tipo_

        def sistema_puede_omitir_la_combinacion(self):
            config = _carga("sistema_prefijo", "yml", lento=True)
            assert "exterior" not in config._sistema
            assert "exterior" not in config
            config.cargar_sistema(combinar=False)
            # Prueba que cargamos en el dicc por nivel, pero no en la
            # configuración central/fusionada.
            assert "exterior" in config._sistema
            assert "exterior" not in config

        def especifico_del_ususario(self):
            "Archivos conf específicos del usuario"
            # NOTE: usando lento = True para evitar la carga automática para
            # que podamos probar que cargar_usuario() funciona.
            for tipo_ in TIPOS:
                config = _carga("ususario_prefijo", tipo_, lento=True)
                assert "exterior" not in config
                config.cargar_usuario()
                assert config.exterior.interior.hurra == tipo_

        def usuario_puede_omitir_la_combinacion(self):
            config = _carga("ususario_prefijo", "yml", lento=True)
            assert "exterior" not in config._ususario
            assert "exterior" not in config
            config.cargar_usuario(combinar=False)
            # Prueba que cargamos en el dicc por nivel, pero no en la
            # configuración central/fusionada.
            assert "exterior" in config._ususario
            assert "exterior" not in config

        def especifico_del_py(self):
            "Local-to-project conf files"
            for tipo_ in TIPOS:
                c = Config(dir_de_py=join(CONFIGS_RUTA, tipo_))
                assert "exterior" not in c
                c.cargar_proyecto()
                assert c.exterior.interior.hurra == tipo_

        def py_puede_omitir_la_combinacion(self):
            config = Config(
                dir_de_py=join(CONFIGS_RUTA, "yml"), lento=True
            )
            assert "exterior" not in config._py
            assert "exterior" not in config
            config.cargar_proyecto(combinar=False)
            # Prueba que cargamos en el dicc por nivel, pero no en la
            # configuración central/fusionada.
            assert "exterior" in config._py
            assert "exterior" not in config

        def no_carga_archivo_especifico_del_py_si_no_proporciona_la_ubic_del_py(self):
            c = Config()
            assert c._proyecto_ruta is None
            c.cargar_proyecto()
            assert list(c._py.keys()) == []
            defaults = ["artefactos", "correr", "corredores", "sudo", "tiempo_de_descanso"]
            assert set(c.keys()) == set(defaults)

        def ubic_del_py_se_puede_establecer_despues_de_init(self):
            c = Config()
            assert "exterior" not in c
            c.setea_ubic_del_py(join(CONFIGS_RUTA, "yml"))
            c.cargar_proyecto()
            assert c.exterior.interior.hurra == "yml"

        def config_de_acte_via_bandera_cli(self):
            c = Config(acte_ruta=join(CONFIGS_RUTA, "yaml", "dued.yaml"))
            c.cargar_acte()
            assert c.exterior.interior.hurra == "yaml"

        def tiempoej_puede_omitir_la_combinacion(self):
            ruta = join(CONFIGS_RUTA, "yaml", "dued.yaml")
            config = Config(acte_ruta=ruta, lento=True)
            assert "exterior" not in config._acte
            assert "exterior" not in config
            config.cargar_acte(combinar=False)
            # Prueba que cargamos en el dicc por nivel, pero no en la
            # configuración central/fusionada.
            assert "exterior" in config._acte
            assert "exterior" not in config

        @raises(TipoDeArchivoDesconocido)
        def sufijo_desconocido_en_ruta_al_acte_genera_un_error_util(self):
            c = Config(acte_ruta=join(CONFIGS_RUTA, "tuerca.ini"))
            c.cargar_acte()

        def modulos_Python_no_cargan_vars_especiales(self):
            "Los módulos de Python no cargan vars especiales"
            # Pida prestado el módulo Python de otra prueba.
            c = _carga("sistema_prefijo", "python")
            # Prueba de cordura que funciona en minúsculas
            assert c.exterior.interior.hurra == "python"
            # Prueba real de que se eliminan los elementos integrados, etc.
            for special in ("incorporados", "archivo", "paquete", "nombre", "doc"):
                assert "__{}__".format(special) not in c

        def modulos_Python_excepto_de_manera_util_en_módulos_no_seleccionables(self):
            # Re: # 556; cuando hay un error, aparece un TypeError en su lugar
            # (concedido, en el momento de la fusión, pero queremos que 
            # aumente lo antes posible, por lo que estamos probando el 
            # nuevo comportamiento previsto: aumentar en el momento de la 
            # carga de configuración.
            c = Config()
            c.setea_ruta_del_acte(join(soporte, "tiene_modulos.py"))
            esperado = r"'os' es un modulo.*dado un artefacto archivo.*error"
            with pytest.raises(MiembroDeConfigNoSeleccionable, match=esperado):
                c.cargar_acte(combinar=False)

        @patch("dued.config.debug")
        def archivos_inexistentes_se_omiten_y_registran(self, mock_debug):
            c = Config()
            c._cargar_yml = Mock(efecto_secundario=IOError(2, "oh nueces"))
            c.setea_ruta_del_acte("es-un.yml")  # Desencadena el uso de _cargar_yml
            c.cargar_acte()
            mock_debug.assert_cualquier_llamada("No vi ningún es-un.yml, saltando.")

        @raises(IOError)
        def se_generan_IOErrors_de_archivos_no_perdidos(self):
            c = Config()
            c._cargar_yml = Mock(efecto_secundario=IOError(17, "¿uh, qué?"))
            c.setea_ruta_del_acte("es-un.yml")  # Desencadena el uso de _cargar_yml
            c.cargar_acte()

    class carga_config_a_nivel_de_coleccion:
        def realizado_explicita_y_directamente(self):
            # TODO: ¿queremos actualizar los otros niveles para permitir
            # una carga 'directa' como esta, ahora que todos tienen métodos
            #  explícitos?
            c = Config()
            assert "foo" not in c
            c.cargar_coleccion({"foo": "bar"})
            assert c.foo == "bar"

        def la_combinacion_se_puede_diferir(self):
            c = Config()
            assert "foo" not in c._coleccion
            assert "foo" not in c
            c.cargar_coleccion({"foo": "bar"}, combinar=False)
            assert "foo" in c._coleccion
            assert "foo" not in c

    class comparacion_y_hashing:
        def comparacion_mira_la_config_combinada(self):
            c1 = Config(defaults={"foo": {"bar": "biz"}})
            # Valores predeterminados vacíos para suprimir 
            # global_defaults
            c2 = Config(defaults={}, anulaciones={"foo": {"bar": "biz"}})
            assert c1 is not c2
            assert c1._defaults != c2._defaults
            assert c1 == c2

        def permite_comparacion_con_diccs_realistas(self):
            c = Config({"foo": {"bar": "biz"}})
            assert c["foo"] == {"bar": "biz"}

        @raises(TypeError)
        def es_explícitamente_no_hashable(self):
            hash(Config())

    class vars_ent:
        "Entorno variables"

        def caso_base_predeterminado_es_el_prefijo_dued(self):
            os.environ["DUED_FOO"] = "bar"
            c = Config(defaults={"foo": "nobar"})
            c.cargar_entorno_shell()
            assert c.foo == "bar"

        def ajustes_no_predeclarados_no_se_consumen(self):
            os.environ["DUED_HOLA"] = "¿soy yo a quien estás buscando?"
            c = Config()
            c.cargar_entorno_shell()
            assert "HOLA" not in c
            assert "hola" not in c

        def guionbajo_nivel_superior(self):
            os.environ["DUED_FOO_BAR"] = "biz"
            c = Config(defaults={"foo_bar": "nobiz"})
            c.cargar_entorno_shell()
            assert c.foo_bar == "biz"

        def guionesbajos_anidados(self):
            os.environ["DUED_FOO_BAR"] = "biz"
            c = Config(defaults={"foo": {"bar": "nobiz"}})
            c.cargar_entorno_shell()
            assert c.foo.bar == "biz"

        def ambos_tipos_de_guiones_bajos_mezclados(self):
            os.environ["DUED_FOO_BAR_BIZ"] = "baz"
            c = Config(defaults={"foo_bar": {"biz": "nobaz"}})
            c.cargar_entorno_shell()
            assert c.foo_bar.biz == "baz"

        @raises(VarEntAmbigua)
        def guiones_bajos_ambiguos_no_adivina(self):
            os.environ["DUED_FOO_BAR"] = "biz"
            c = Config(defaults={"foo_bar": "wat", "foo": {"bar": "huh"}})
            c.cargar_entorno_shell()

        class conversion_de_tipos:
            def cadenas_reemplazadas_por_el_valor_entorno(self):
                os.environ["DUED_FOO"] = u"mivalor"
                c = Config(defaults={"foo": "miviejovalor"})
                c.cargar_entorno_shell()
                assert c.foo == u"mivalor"
                assert isinstance(c.foo, six.text_type)

            def unicode_reemplazado_por_el_valor_entorno(self):
                # Python 3 no le permite poner objetos 'bytes' en 
                # os.environ, por lo que la prueba no tiene sentido allí.
                if six.PY3:
                    return
                os.environ["DUED_FOO"] = "miunicode"
                c = Config(defaults={"foo": u"miviejovalor"})
                c.cargar_entorno_shell()
                assert c.foo == "miunicode"
                assert isinstance(c.foo, str)

            def None_reemplazado(self):
                os.environ["DUED_FOO"] = "algo"
                c = Config(defaults={"foo": None})
                c.cargar_entorno_shell()
                assert c.foo == "algo"

            def booleanos(self):
                for entrada_, resultado in (
                    ("0", False),
                    ("1", True),
                    ("", False),
                    ("bah", True),
                    ("false", True),
                ):
                    os.environ["DUED_FOO"] = entrada_
                    c = Config(defaults={"foo": bool()})
                    c.cargar_entorno_shell()
                    assert c.foo == resultado

            def entradas_tipo_booleano_con_valores_pordefecto_no_booleanos(self):
                for entrada_ in ("0", "1", "", "bah", "false"):
                    os.environ["DUED_FOO"] = entrada_
                    c = Config(defaults={"foo": "bar"})
                    c.cargar_entorno_shell()
                    assert c.foo == entrada_

            def tipos_numericos_se_convierten(self):
                pruebas = [
                    (int, "5", 5),
                    (float, "5.5", 5.5),
                    # TODO: more?
                ]
                # No se puede usar '5L' en Python 3, incluso tenerlo en una
                # rama lo molesta.
                if not six.PY3:
                    pruebas.append((long, "5", long(5)))  # noqa
                for old, new_, resultado in pruebas:
                    os.environ["DUED_FOO"] = new_
                    c = Config(defaults={"foo": old()})
                    c.cargar_entorno_shell()
                    assert c.foo == resultado

            def tipos_arbitrarios_tambien_trabajan(self):
                os.environ["DUED_FOO"] = "cualquier"

                class Meh(object):
                    def __init__(self, thing=None):
                        pass

                obj_viejo = Meh()
                c = Config(defaults={"foo": obj_viejo})
                c.cargar_entorno_shell()
                assert isinstance(c.foo, Meh)
                assert c.foo is not obj_viejo

            class tipos_inconvertibles:
                @raises(VarEntInestable)
                def _tipo_inconvertible(self, default):
                    os.environ["DUED_FOO"] = "cosas"
                    c = Config(defaults={"foo": default})
                    c.cargar_entorno_shell()

                def listas(self):
                    self._tipo_inconvertible(["a", "lista"])

                def tuplas(self):
                    self._tipo_inconvertible(("a", "tuple"))

    class jerarquia:
        "Config jerarquia en vigor"

        #
        # NOTE: la mayoría de estos solo aprovechan los dispositivos de prueba
        # existentes (que viven en sus propios directorios y tienen valores
        # diferentes para la tecla 'hurra'), ya que normalmente no necesitamos
        # más de 2-3 ubicaciones de archivos diferentes para una prueba.
        #

        def coleccion_anula_los_valores_pordefecto(self):
            c = Config(defaults={"anidado": {"ajuste": "default"}})
            c.cargar_coleccion({"anidado": {"ajuste": "coleccion"}})
            assert c.anidado.ajuste == "coleccion"

        def coleccion_de_anulaciones_en_todo_el_sistema(self):
            c = Config(sistema_prefijo=join(CONFIGS_RUTA, "yaml/"))
            c.cargar_coleccion({"exterior": {"interior": {"hurra": "defaults"}}})
            assert c.exterior.interior.hurra == "yaml"

        def usuario_anula_todo_el_sistema(self):
            c = Config(
                sistema_prefijo=join(CONFIGS_RUTA, "yaml/"),
                ususario_prefijo=join(CONFIGS_RUTA, "json/"),
            )
            assert c.exterior.interior.hurra == "json"

        def usuario_anula_la_colección(self):
            c = Config(ususario_prefijo=join(CONFIGS_RUTA, "json/"))
            c.cargar_coleccion({"exterior": {"interior": {"hurra": "defaults"}}})
            assert c.exterior.interior.hurra == "json"

        def proyecto_anula_al_usuario(self):
            c = Config(
                ususario_prefijo=join(CONFIGS_RUTA, "json/"),
                dir_de_py=join(CONFIGS_RUTA, "yaml"),
            )
            c.cargar_proyecto()
            assert c.exterior.interior.hurra == "yaml"

        def proyecto_anula_todo_el_sistema(self):
            c = Config(
                sistema_prefijo=join(CONFIGS_RUTA, "json/"),
                dir_de_py=join(CONFIGS_RUTA, "yaml"),
            )
            c.cargar_proyecto()
            assert c.exterior.interior.hurra == "yaml"

        def proyecto_anula_la_coleecion(self):
            c = Config(dir_de_py=join(CONFIGS_RUTA, "yaml"))
            c.cargar_proyecto()
            c.cargar_coleccion({"exterior": {"interior": {"hurra": "defaults"}}})
            assert c.exterior.interior.hurra == "yaml"

        def varent_anulan_el_proyecto(self):
            os.environ["dued_OUTER_INNER_HOORAY"] = "entorno"
            c = Config(dir_de_py=join(CONFIGS_RUTA, "yaml"))
            c.cargar_proyecto()
            c.cargar_entorno_shell()
            assert c.exterior.interior.hurra == "entorno"

        def varent_anulan_al_usuario(self):
            os.environ["dued_OUTER_INNER_HOORAY"] = "entorno"
            c = Config(ususario_prefijo=join(CONFIGS_RUTA, "yaml/"))
            c.cargar_entorno_shell()
            assert c.exterior.interior.hurra == "entorno"

        def varent_anulan_todo_el_sistema(self):
            os.environ["dued_OUTER_INNER_HOORAY"] = "entorno"
            c = Config(sistema_prefijo=join(CONFIGS_RUTA, "yaml/"))
            c.cargar_entorno_shell()
            assert c.exterior.interior.hurra == "entorno"

        def varent_anulan_la_coleccion(self):
            os.environ["dued_OUTER_INNER_HOORAY"] = "entorno"
            c = Config()
            c.cargar_coleccion({"exterior": {"interior": {"hurra": "defaults"}}})
            c.cargar_entorno_shell()
            assert c.exterior.interior.hurra == "entorno"

        def tiempoej_anulan_varent(self):
            os.environ["dued_OUTER_INNER_HOORAY"] = "entorno"
            c = Config(acte_ruta=join(CONFIGS_RUTA, "json", "dued.json"))
            c.cargar_acte()
            c.cargar_entorno_shell()
            assert c.exterior.interior.hurra == "json"

        def tiempoej_anulan_proyecto(self):
            c = Config(
                acte_ruta=join(CONFIGS_RUTA, "json", "dued.json"),
                dir_de_py=join(CONFIGS_RUTA, "yaml"),
            )
            c.cargar_acte()
            c.cargar_proyecto()
            assert c.exterior.interior.hurra == "json"

        def tiempoej_anulan_ususario(self):
            c = Config(
                acte_ruta=join(CONFIGS_RUTA, "json", "dued.json"),
                ususario_prefijo=join(CONFIGS_RUTA, "yaml/"),
            )
            c.cargar_acte()
            assert c.exterior.interior.hurra == "json"

        def tiempoej_anula_todo_el_sistema(self):
            c = Config(
                acte_ruta=join(CONFIGS_RUTA, "json", "dued.json"),
                sistema_prefijo=join(CONFIGS_RUTA, "yaml/"),
            )
            c.cargar_acte()
            assert c.exterior.interior.hurra == "json"

        def tiempoej_anula_coleccion(self):
            c = Config(acte_ruta=join(CONFIGS_RUTA, "json", "dued.json"))
            c.cargar_coleccion({"exterior": {"interior": {"hurra": "defaults"}}})
            c.cargar_acte()
            assert c.exterior.interior.hurra == "json"

        def cli_anula_anular_todo(self):
            "Las anulaciones basadas en CLI ganan frente a todas las demás capas"
            # TODO: expandirse a pruebas más explícitas como las anteriores? bah
            c = Config(
                anulaciones={"exterior": {"interior": {"hurra": "anulaciones"}}},
                acte_ruta=join(CONFIGS_RUTA, "json", "dued.json"),
            )
            c.cargar_acte()
            assert c.exterior.interior.hurra == "anulaciones"

        def yaml_evita_yml_json_o_python(self):
            c = Config(sistema_prefijo=join(CONFIGS_RUTA, "los-cuatro/"))
            assert "solo-json" not in c
            assert "solo_python" not in c
            assert "solo-yml" not in c
            assert "solo-yaml" in c
            assert c.shared == "yaml-valor"

        def yml_evita_json_o_python(self):
            c = Config(sistema_prefijo=join(CONFIGS_RUTA, "tres-de-ellos/"))
            assert "solo-json" not in c
            assert "solo_python" not in c
            assert "solo-yml" in c
            assert c.shared == "yml-valor"

        def json_evita_python(self):
            c = Config(sistema_prefijo=join(CONFIGS_RUTA, "json-y-python/"))
            assert "solo_python" not in c
            assert "solo-json" in c
            assert c.shared == "json-valor"

    class clon:
        def conserva_miembros_basicos(self):
            c1 = Config(
                defaults={"key": "default"},
                anulaciones={"key": "anular"},
                sistema_prefijo="global",
                ususario_prefijo="usuario",
                dir_de_py="proyecto",
                acte_ruta="acte.yaml",
            )
            c2 = c1.clonar()
            # NOTE: esperando valores por defecto idénticos también pruebas 
            # implícitamente que clonar() pasa en defaults= en lugar de hacer
            # un init + copy vacío. (Cuando ese no es el caso, terminamos con
            # global_defaults() que se vuelve a ejecutar y se vuelve
            # a agregar a _defaults ...)
            assert c2._defaults == c1._defaults
            assert c2._defaults is not c1._defaults
            assert c2._anula == c1._anula
            assert c2._anula is not c1._anula
            assert c2._sistema_prefijo == c1._sistema_prefijo
            assert c2._ususario_prefijo == c1._ususario_prefijo
            assert c2._proyecto_prefijo == c1._proyecto_prefijo
            assert c2.prefijo == c1.prefijo
            assert c2.prefijo_de_archivo == c1.prefijo_de_archivo
            assert c2.entorno_prefijo == c1.entorno_prefijo
            assert c2._ruta_al_acte == c1._ruta_al_acte

        def conserva_config_combinada(self):
            c = Config(
                defaults={"key": "default"}, anulaciones={"key": "anular"}
            )
            assert c.key == "anular"
            assert c._defaults["key"] == "default"
            c2 = c.clonar()
            assert c2.key == "anular"
            assert c2._defaults["key"] == "default"
            assert c2._anula["key"] == "anular"

        def conserva_datos_del_archivo(self):
            c = Config(sistema_prefijo=join(CONFIGS_RUTA, "yaml/"))
            assert c.exterior.interior.hurra == "yaml"
            c2 = c.clonar()
            assert c2.exterior.interior.hurra == "yaml"
            assert c2._sistema == {"exterior": {"interior": {"hurra": "yaml"}}}

        @patch.object(
            Config,
            "_cargar_yaml",
            valor_de_retorno={"exterior": {"interior": {"hurra": "yaml"}}},
        )
        def no_recarga_los_datos_del_archivo(self, cargar_yaml):
            ruta = join(CONFIGS_RUTA, "yaml/")
            c = Config(sistema_prefijo=ruta)
            c2 = c.clonar()
            assert c2.exterior.interior.hurra == "yaml"
            # Manera mala de decir "solo me llamaron con esta invocación 
            # específica una vez" (ya que assert_called_with se enoja con
            # otras invocaciones con diferentes argumentos)
            llamadas = cargar_yaml.llamada_a_lista_de_args
            mi_llamada = llamar("{}dued.yaml".format(ruta))
            try:
                llamadas.remover(mi_llamada)
                assert mi_llamada not in llamadas
            except ValueError:
                err = "{} no encontrado en {} veces!"
                assert False, err.format(mi_llamada, llamadas)

        def conserva_data_de_entorno(self):
            os.environ["DUED_FOO"] = "bar"
            c = Config(defaults={"foo": "nobar"})
            c.cargar_entorno_shell()
            c2 = c.clonar()
            assert c2.foo == "bar"

        def funciona_correctamente_cuando_se_subclasifica(self):
            # ¡Porque a veces, la implementación # 1 es realmente ingenua!
            class MiConfig(Config):
                pass

            c = MiConfig()
            assert isinstance(c, MiConfig)  # sanity
            c2 = c.clonar()
            assert isinstance(c2, MiConfig)  # actual prueba

        class dentro_de_kwarg:
            "'dentro' kwarg"

            def no_se_requiere(self):
                c = Config(defaults={"bah": "bien"})
                c2 = c.clonar()
                assert c2.bah == "bien"

            def genera_TypeError_si_value_no_es_la_subclase_Config(self):
                try:
                    Config().clonar(dentro=17)
                except TypeError:
                    pass
                else:
                    assert False, "¡El obj que no-es-clase no generó TypeError!"

                class Foo(object):
                    pass

                try:
                    Config().clonar(dentro=Foo)
                except TypeError:
                    pass
                else:
                    assert False, "Non-subclass no genera TypeError!"

            def clones_resultantes_se_escriben_como_nueva_clase(self):
                class MiConfig(Config):
                    pass

                c = Config()
                c2 = c.clonar(dentro=MiConfig)
                assert type(c2) is MiConfig

            def valores_no_conflictivos_se_fusionan(self):
                # NOTE: Esto es realmente sólo comportamiento básico del clonar.
                class MiConfig(Config):
                    @staticmethod
                    def global_defaults():
                        orig = Config.global_defaults()
                        orig["nuevo"] = {"datos": "oh"}
                        return orig

                c = Config(defaults={"otro": {"datos": "hola"}})
                c["acte"] = {"modificacion": "que onda"}
                c2 = c.clonar(dentro=MiConfig)
                # Nuevos datos predeterminados de MiConfig presente
                assert c2.nuevo.datos == "oh"
                # Así como los datos predeterminados antiguos de la instancia
                # clonada
                assert c2.otro.datos == "hola"
                # Y mods de usuario de acte de la instancia clonada
                assert c2.acte.modificacion == "que onda"

        def no_hace_depcopy(self):
            c = Config(
                defaults={
                    # se fusionará con los dics felizmente
                    "oh": {"querido": {"dios": object()}},
                    # Y valores compuestos de copia superficial
                    "superficial": {"objetos": ["copia", "bien"]},
                    # conservará referencias a dic íntimo, tristemente. No
                    # mucho podemos hacer sin incurrir en problemas deepcopy
                    # (o ponerlo en práctica de nuevo completamente)
                    "bien": {"nopuedo": ["tener", {"todo": "queremos"}]},
                }
            )
            c2 = c.clonar()
            # Identidad básica
            assert c is not c2, "Clon tenía la misma identidad que original!"
            # Los dicts se recrean
            assert c.oh is not c2.oh, "La key de nivel superior tenía la misma identidad."
            assert (
                c.oh.querido is not c2.oh.querido
            ), "¡La key de nivel medio tenía la misma identidad!"  # noqa
            # Los valores básicos se copian
            err = "¡Objeto() hoja tenía la misma identidad!"
            assert c.oh.querido.dios is not c2.oh.querido.dios, err
            assert c.superficial.objetos == c2.superficial.objetos
            err = "¡La lista superficial tenía la misma identidad!"
            assert c.superficial.objetos is not c2.superficial.objetos, err
            # Los objetos no-dict profundamente anidados siguen siendo 
            # problemáticos, oh bueno
            err = "¿Eh, un dict-in-a-lista profundamente anidado tenía una identidad diferente?" # noqa
            assert c.bien.nopuedo[1] is c2.bien.nopuedo[1], err
            err = "¿Eh, un valor de dict-in-a-lista profundamente anidado tenía una identidad diferente?"  # noqa
            assert (
                c.bien.nopuedo[1]["todo"]
                is c2.bien.nopuedo[1]["todo"]
            ), err  # noqa

    def puede_ser_encurtido(self):
        c = Config(anulaciones={"foo": {"bar": {"biz": ["baz", "buzz"]}}})
        c2 = pickle.loads(pickle.dumps(c))
        assert c == c2
        assert c is not c2
        assert c.foo.bar.biz is not c2.foo.bar.biz


# NOTE: fusionar_dics tiene su propia unidad pruebas de muy bajo nivel en su propio archivo
