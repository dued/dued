import imp
import os
import sys
import types

from pytest import raises

from dued import Config
from dued.cargador import Cargador, CargaDesdeElSitemaDeArchivos as FSLoader
from dued.excepciones import ColeccionNoEcontrada

from _util import soporte


class _CargadorBasico(Cargador):
    """
    Prueba el comportamiento del Cargador de alto nivel con un talón de
    buscador básico.

    Se usa cuando queremos asegurarnos de que estamos probando Cargador.load
    y no, por ejemplo, Implementación específica de 
    CargaDesdeElSitemaDeArchivos.
    """

    def buscar(self, nombre):
        self.fd, self.ruta, self.desc = t = imp.find_module(nombre, [soporte])
        return t


class Cargador_:
    def exhibe_el_objeto_de_configuracion_por_defecto(self):
        cargador = _CargadorBasico()
        assert isinstance(cargador.config, Config)
        assert cargador.config.artefactos.nombre_de_coleccion == "artefactos"

    def devuelve_modulo_y_ubicacion(self):
        mod, ruta = _CargadorBasico().cargar("hangar")
        assert isinstance(mod, types.ModuleType)
        assert ruta == soporte

    def puede_configurar_config_via_constructor(self):
        config = Config({"artefactos": {"nombre_de_coleccion": "misartefactos"}})
        cargador = _CargadorBasico(config=config)
        assert cargador.config.artefactos.nombre_de_coleccion == "misartefactos"

    def agrega_el_dir_padre_del_modulo_a_la_sistema_ruta(self):
        # no-explota prueba -- esta chicha.
        _CargadorBasico().cargar("hangar")

    def no_duplica_la_adicion_del_dir_principal(self):
        _CargadorBasico().cargar("hangar")
        _CargadorBasico().cargar("hangar")
        # Si el error está presente, será 2 al menos (y a menudo más, ya que
        # otras pruebas lo contaminarán(!).
        assert sys.path.count(soporte) == 1

    def cierra_objet_archivo_abierto(self):
        cargador = _CargadorBasico()
        cargador.cargar("foo")
        assert cargador.fd.closed

    def puede_cargar_el_paquete(self):
        cargador = _CargadorBasico()
        # Asegúrate de que no explote
        cargador.cargar("paquete")

    def nombre_de_carga_pordefault_es_config_artfactos_nombredecoleccion(self):
        "cargar() el nombre por default es config.artefactos.nombre_de_coleccion"

        class MockLoader(_CargadorBasico):
            def buscar(self, nombre):
                # Cordura
                assert nombre == "lista_simple_hng"
                return super(MockLoader, self).buscar(nombre)

        config = Config({"artefactos": {"nombre_de_coleccion": "lista_simple_hng"}})
        cargador = MockLoader(config=config)
        #  Más cordura: espere lista_simple_hng.py (no artefactos.py)
        mod, ruta = cargador.cargar()
        assert mod.__file__ == os.path.join(soporte, "lista_simple_hng.py")


class CargadorDelSistemaDeArchivos_:
    def setup(self):
        self.cargador = FSLoader(inicio=soporte)

    def punto_de_inicio_de_descubrimiento_tiene_como_valor_pordefecto_cwd(self):
        assert FSLoader().iniciar == os.getcwd()

    def expone_el_punto_de_inicio_como_atributo(self):
        assert FSLoader().iniciar == os.getcwd()

    def punto_de_inicio_configurable_via_kwarg(self):
        inicio = "/tmp/"
        assert FSLoader(inicio=inicio).iniciar == inicio

    def punto_de_inicio_configurable_via_config(self):
        config = Config({"artefactos": {"dir_raiz": "enningunaparte"}})
        assert FSLoader(config=config).iniciar == "enningunaparte"

    def genera_ColeccionNoEcontrada_si_no_se_encuentra(self):
        with raises(ColeccionNoEcontrada):
            self.cargador.cargar("nop")

    def genera_ImportError_si_la_coleccion_encontrada_no_se_puede_importar(self):
        # En lugar de enmascarar con una ColeccionNoEcontrada
        with raises(ImportError):
            self.cargador.cargar("ups")

    def busquedas_hacia_raiz_del_sistema_archivos(self):
        # Cargado mientras la raíz está en el mismo directorio que .py
        directly = self.cargador.cargar("foo")
        # Cargado mientras que la raíz tiene varios directorios más profundos
        # que el .py
        deep = os.path.join(soporte, "ignoreme", "ignoremetambien")
        indirectamente = FSLoader(inicio=deep).cargar("foo")
        assert directly == indirectamente
