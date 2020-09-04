import os
import platform
import time

from mock import Mock
from pytest import skip, raises

from dued import (
    correr,
    Local,
    Contexto,
    ExcepcionDeHilo,
    Respondedor,
    DetectorDeRespuestasIncorrectas,
    ErrorDeCentinela,
    Falla,
    CaducoComando,
)

from _util import asegurar_el_uso_de_la_cpu


PYPY = platform.python_implementation() == "PyPy"


class Corredor_:
    def setup(self):
        os.chdir(os.path.join(os.path.dirname(__file__), "_soporte"))

    class respondiendo:
        def caso_base(self):
            # prueba básica "no explota": respond.py saldrá distinto de cero
            # a menos que esto funcione, provocando una Falla.
            centinela = Respondedor(r"Cual es la contraseña\?", "Subamarillo\n")
            # Tengo que dar -u o Python almacenará en búfer de línea su 
            # stdout, por lo que nunca veremos el prompt.
            correr(
                "python -u responder_base.py",
                centinelas=[centinela],
                ocultar=True,
                tiempofuera=5,
            )

        def ambos_streams(self):
            centinelas = [
                Respondedor("salida estandar", "con eso\n"),
                Respondedor("error estandar", "entre silla y teclado\n"),
            ]
            correr(
                "python -u responder_ambos.py",
                centinelas=centinelas,
                ocultar=True,
                tiempofuera=5,
            )

        def Errores_del_centinela_se_convierten_en_Fallas(self):
            centinela = DetectorDeRespuestasIncorrectas(
                patron=r"Cual es la contraseña\?",
                respuesta="Subamarillo\n",
                centinela="¡No eres ciudadano Cleb!",
            )
            try:
                correr(
                    "python -u responder_falla.py",
                    centinelas=[centinela],
                    ocultar=True,
                    tiempofuera=5,
                )
            except Falla as e:
                assert isinstance(e.motivo, ErrorDeCentinela)
                assert e.resultado.salida is None
            else:
                assert False, "No dio Falla!"

    class duplicando_stdin:
        def stdin_canalizado_no_se_combina_con_stdin_simulado(self):
            # Re: número 308 de GH
            # Morirá en OSError de tubería rota si el error está presente.
            correr("echo 'lollerskates' | du -c anidado_o_canalizado foo", ocultar=True)

        def sesiones_dued_anidadas_no_combinadas_con_stdin_simulado(self):
            # También sobre: GH número 308. Este simplemente se quedará 
            # colgado para siempre. ¡Cortejar!
            correr("du -c anidado_o_canalizado calls-foo", ocultar=True)

        def no_es_pesado_en_la_cpu(self):
            "la duplicación de stdin no requiere mucha CPU"
            # La medición de CPU bajo PyPy es ... bastante diferente. NBD.
            if PYPY:
                skip()
            # Se ha visto que Python 3.5 usa hasta ~ 6.0 s de tiempo de CPU bajo Travis
            with asegurar_el_uso_de_la_cpu(lt=7.0):
                correr("python -u ocupadoafull.py 10", pty=True, ocultar=True)

        def no_se_rompe_cuando_existe_stdin_sino_nulo(self):
            # Re: #425 - IOError ocurre cuando hay un error presente
            correr("du -c anidado_o_canalizado foo < /dev/null", ocultar=True)

    class colgadas_IO  :
        "IO hangs"

        def _colgada_en_tuberia_full(self, pty):
            class Ups(Exception):
                pass

            corredor = Local(Contexto())
            # Forzar el método de cuerpo-de-hilo de corredor IO para generar
            # una excepción para imitar explosiones de codificación del mundo
            # real/etc. Cuando hay un error, esto hará que la prueba se 
            # cuelgue hasta que finalice a la fuerza.
            corredor.manejar_stdout = Mock(efecto_secundario=Ups, __name__="sigh")
            # NOTE: tanto Darwin (10.10) como Linux (imagen docker de Travis)
            # tienen este archivo. Es lo suficientemente grande como para 
            # llenar la mayoría de los búferes de tubería, que es el
            # comportamiento de activación.
            try:
                corredor.correr("cat /usr/share/dict/words", pty=pty)
            except ExcepcionDeHilo as e:
                assert len(e.excepciones) == 1
                assert e.excepciones[0].type is Ups
            else:
                assert False, "no recibió esperado ExcepcionDeHilo!"

        def subproc_pty_no_deberia_colgarse_si_el_hilo_IO_tiene_una_excepcion(self):
            self._colgada_en_tuberia_full(pty=True)

        def subproc_nopty_no_deberia_colgarse_si_el_hilo_IO_tiene_una_excepcion(self):
            self._colgada_en_tuberia_full(pty=False)

    class tiempo_de_descanso:
        def no_se_dispara_cuando_el_comando_es_rapido(self):
            assert correr("sleep 1", tiempofuera=5)

        def desencadena_una_excepcion_cuando_el_comando_es_lento(self):
            antes = time.time()
            with raises(CaducoComando) as info:
                correr("sleep 5", tiempofuera=0.5)
            despues = time.time()
            # Modifique un poco la comprobación en tiempo real, <= 0,5 
            # normalmente falla debido a overhead, etc. ¿Es posible que
            # necesite aumentar más para evitar carreras? Meh.
            assert (despues - antes) <= 0.75
            # Comprobaciones de cordura del obj de excepción
            assert info.valor.tiempofuera == 0.5
            assert info.valor.resultado.comando == "sleep 5"
