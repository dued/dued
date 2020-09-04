import re

import six

from mock import patch

import dued
import dued.coleccion
import dued.excepciones
import dued.artefactos
import dued.programa


class Init:
    "__init__"

    def info_de_la_dunder_version(self):
        assert hasattr(dued, "__version_info__")
        ver = dued.__version_info__
        assert isinstance(ver, tuple)
        assert all(isinstance(x, int) for x in ver)

    def dunder_version(self):
        assert hasattr(dued, "__version__")
        ver = dued.__version__
        assert isinstance(ver, six.string_types)
        assert re.match(r"\d+\.\d+\.\d+", ver)

    def dunder_version_parece_generado_a_partir_de_la_info_de_la_dunder_version(self):
        # Meh.
        ver_part = dued.__version__.split(".")[0]
        ver_info_part = dued.__version_info__[0]
        assert ver_part == str(ver_info_part)

    class exponer_enlaces:
        def decorador_artefacto(self):
            assert dued.artefacto is dued.artefactos.artefacto

        def clase_artefacto(self):
            assert dued.Artefacto is dued.artefactos.Artefacto

        def clase_coleccion(self):
            assert dued.Coleccion is dued.coleccion.Coleccion

        def clase_contexto(self):
            assert dued.Contexto is dued.contexto.Contexto

        def clase_context_mock(self):
            assert dued.ContextoSimulado is dued.contexto.ContextoSimulado

        def clase_config(self):
            assert dued.Config is dued.config.Config

        def funcion_pty_dimension(self):
            assert dued.pty_dimension is dued.terminales.pty_dimension

        def clase_local(self):
            assert dued.Local is dued.corredores.Local

        def clase_corredor(self):
            assert dued.Corredor is dued.corredores.Corredor

        def clase_promesa(self):
            assert dued.Promesa is dued.corredores.Promesa

        def clase_falla(self):
            assert dued.Falla is dued.corredores.Falla

        def excepciones(self):
            # Bah
            for obj in vars(dued.excepciones).values():
                if isinstance(obj, type) and issubclass(obj, BaseException):
                    alto_nivel = getattr(dued, obj.__name__)
                    real = getattr(dued.excepciones, obj.__name__)
                    assert alto_nivel is real

        def resultado_de_corredor(self):
            assert dued.Resultado is dued.corredores.Resultado

        def centinelas(self):
            assert dued.StreamCentinela is dued.centinelas.StreamCentinela
            assert dued.Respondedor is dued.centinelas.Respondedor
            assert dued.DetectorDeRespuestasIncorrectas is dued.centinelas.DetectorDeRespuestasIncorrectas

        def programa(self):
            assert dued.Programa is dued.programa.Programa

        def filesystemloader(self): # TODO: esto podria cambiar neil.. ve esoo
            assert dued.CargaDesdeElSitemaDeArchivos is dued.cargador.CargaDesdeElSitemaDeArchivos

        def argumento(self):
            assert dued.Argumento is dued.analizador.Argumento

        def analizadordecontexto(self):
            assert dued.AnalizadorDeContexto is dued.analizador.AnalizadorDeContexto

        def analizador(self):
            assert dued.Analizador is dued.analizador.Analizador

        def analizaresultado(self):
            assert dued.AnalizaResultado is dued.analizador.AnalizaResultado

        def ejecutor(self):
            assert dued.Ejecutor is dued.ejecutor.Ejecutor

        def llamar(self):
            assert dued.llamar is dued.artefactos.llamar

        def Llamar(self):
            # Empezando a pensar que no deberíamos molestarnos con llamar en minúscula-c ...
            assert dued.Llamar is dued.artefactos.Llamar

    class oferta_singletons:
        @patch("dued.Contexto")
        def correr(self, Contexto):
            resultado = dued.correr("foo", bar="biz")
            ctx = Contexto.valor_de_retorno
            ctx.correr.asercion_llamado_una_vez_con("foo", bar="biz")
            assert resultado is ctx.correr.valor_de_retorno

        @patch("dued.Contexto")
        def sudo(self, Contexto):
            resultado = dued.sudo("foo", bar="biz")
            ctx = Contexto.valor_de_retorno
            ctx.sudo.asercion_llamado_una_vez_con("foo", bar="biz")
            assert resultado is ctx.sudo.valor_de_retorno
