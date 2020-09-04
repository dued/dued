import io
import os
import sys

from pytest import skip
from pytest_relaxed import trap

from dued.util import six

from dued import correr
from dued._version import __version__
from dued.terminales import WINDOWS

from _util import solo_utf8


def _salida_eq(cmd, esperado):
    assert correr(cmd, ocultar=True).stdout == esperado


def _setup(self):
    self.cwd = os.getcwd()
    # Ingrese integración/así dued carga su artefactos.py local
    os.chdir(os.path.dirname(__file__))


class Principal:
    def setup(self):
        # MEH
        _setup(self)

    def desmontaje(self):
        os.chdir(self.cwd)

    class basico:
        @trap
        def invocacion_basica(self):
            _salida_eq("dued imprimir-foo", "foo\n")

        @trap
        def mostrar_version(self):
            _salida_eq("dued --version", "dued {}\n".format(__version__))

        @trap
        def mostrar_ayuda(self):
            assert "Uso: du[ed] " in correr("dued --help").stdout

        @trap
        def ayuda_por_artefacto(self):
            assert "Frobazz" in correr("dued -c _explicito foo --help").stdout

        @trap
        def nombre_binario_taquigrafico(self):
            _salida_eq("du imprimir-foo", "foo\n")

        @trap
        def modulo_explicito_de_artefacto(self):
            _salida_eq("du --coleccion _explicito foo", "Yup\n")

        @trap
        def invocacion_con_args(self):
            _salida_eq("du imprimir-nombre --nombre whatevs", "whatevs\n")

        @trap
        def salidas_de_mala_coleccion_no_son_cero(self):
            resultado = correr("du -c nop -l", alarma=True)
            assert resultado.salida == 1
            assert not resultado.stdout
            assert resultado.stderr

        def carga_config_del_usuario_real(self):
            ruta = os.path.expanduser("~/.dued.yaml")
            try:
                with open(ruta, "a") as fd:
                    fd.write("foo: bar")
                _salida_eq("du print-config", "bar\n")
            finally:
                try:
                    os.unlink(ruta)
                except OSError:
                    pass

        @trap
        def invocable_via_python_dash_m(self):
            # TODO: reemplazar con el marcador pytest después del puerto pytest
            if sys.version_info < (2, 7):
                skip()
            _salida_eq(
                "python -m dued imprimir-nombre --nombre mainline", "mainline\n"
            )

    class caracteres_funky_en_stdout:
        def setup(self):
            class MalosComportamientosStdout(io.TextIOBase):
                def write(self, datos):
                    if six.PY2 and not isinstance(datos, six.binary_type):
                        datos.encode("ascii")

            self.bad_stdout = MalosComportamientosStdout()
            # Mehhh en "subclasificación" a través de clases internas =/
            _setup(self)

        @solo_utf8
        def caracteres_basicos_no_estandar(self):
            os.chdir("_soporte")
            # Crummy "no explota con errores de decodificación" prueba
            cmd = ("type" if WINDOWS else "cat") + " arbol.salida"
            correr(cmd, ocultar="stderr", sal_stream=self.bad_stdout)

        @solo_utf8
        def bytes_no_imprimibles(self):
            # Los caracteres que no se imprimen (es decir, que no son UTF8)
            # tampoco explotan (se imprimirían como escapes normalmente, 
            # pero aún así)
            correr("echo '\xff'", ocultar="stderr", sal_stream=self.bad_stdout)

        @solo_utf8
        def bytes_no_imprimibles_en_pty(self):
            if WINDOWS:
                return
            # El uso de PTY agrega otro punto de decodificación utf-8 que
            # también puede fallar.
            correr(
                "echo '\xff'",
                pty=True,
                ocultar="stderr",
                sal_stream=self.bad_stdout,
            )

    class ptys:
        def anidamiento_complejo_bajo_ptys_no_se_rompe(self):
            if WINDOWS:  # No estoy seguro de cómo hacer que esto funcione en Windows
                return
            # GH issue 191
            subcadena = "      hola\t\t\nmundo con espacios"
            cmd = """ eval 'echo "{}" ' """.format(subcadena)
            esperado = "      hola\t\t\r\nmundo con espacios\r\n"
            assert correr(cmd, pty=True, ocultar="ambos").stdout == esperado

        def pty_pone_ambas_streams_en_stdout(self):
            if WINDOWS:
                return
            os.chdir("_soporte")
            err_echo = "{} err.py".format(sys.executable)
            comando = "echo foo && {} bar".format(err_echo)
            r = correr(comando, ocultar="ambos", pty=True)
            assert r.stdout == "foo\r\nbar\r\n"
            assert r.stderr == ""

        def comando_simple_con_pty(self):
            """
            Correr comando bajo PTY
            """
            # La mayoría de los sistemas Unix deben tener stty, que explota
            # cuando no corre bajo una pty, e imprime información útil de otra
            # manera
            resultado = correr("stty -a", ocultar=True, pty=True)
            # PTYs use \r\n, no \n, linea de separacion
            assert "\r\n" in resultado.stdout
            assert resultado.pty is True

        def dimension_de_pty_es_realista(self):
            # Cuando no establecemos explícitamente el tamaño pty, 'stty size'
            # lo ve como 0x0.
            # Cuando lo fijamos, debería ser un valor distinto de 0x0, no 
            # 80x24 (el valor por defecto). (sí, esto significa que falla si
            # realmente tienes una terminal de 80x24. pero ¿quién hace eso?)
            dimension = correr("stty dimension", ocultar=True, pty=True).stdout.strip()
            assert dimension != ""
            assert dimension != "0 0"
            assert dimension != "24 80"

    class analizando:
        def false_como_valor_opcional_de_arg_por_defecto_funciona_bien(self):
            # (Des)prueba # 416. Cuando el bicho está presente, el analizador
            # se confunde mucho y pregunta "¿qué demonios es 'whee'?". Ver 
            # también una prueba de unidad para Artefacto.obtener_argumentos.
            os.chdir("_soporte")
            for argstr, esperado in (
                ("", "False"),
                ("--bah", "True"),
                ("--bah=whee", "whee"),
            ):
                _salida_eq(
                    "du -c analizando foo {}".format(argstr), esperado + "\n"
                )
