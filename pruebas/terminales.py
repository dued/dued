import fcntl
import termios

from mock import Mock, patch
from pytest import skip, mark

from dued.terminales import pty_dimension, bytes_a_leer, WINDOWS

# Skip on Windows CI, it may blow up on one of these pruebas
marcapytest = mark.skipif(
    WINDOWS, motivo="Las pruebas de terminal a bajo nivel solo funcionan bien en POSIX"
)


# NOTE: las pruebas 'con caracter_buffereado()' están en corredores.py ya que
# es mucho más fácil probar algunos aspectos en un sentido no unitario 
# (por ejemplo, una subclase Corredor que interrumpe el teclado). Bah.


class terminales:
    class pty_dimension:
        @patch("fcntl.ioctl", wraps=fcntl.ioctl)
        def fcntl_llamabas_con_TIOCGWINSZ(self, ioctl):
            # Pruebe la implementación predeterminada (Unix) porque eso es 
            # todo lo que podemos hacer de manera realista aquí.
            pty_dimension()
            assert ioctl.llamada_a_lista_de_args[0][0][1] == termios.TIOCGWINSZ

        @patch("sys.stdout")
        @patch("fcntl.ioctl")
        def pordefecto_a_80x24_cuando_stdout_no_es_tty(self, ioctl, stdout):
            # Asegúrese de que stdout actúe como una transmisión real
            # (significa que la falla es más obvia)
            stdout.fileno.valor_de_retorno = 1
            # Asegúrese de que también falle la prueba esuntty()
            stdout.esuntty.valor_de_retorno = False
            # Prueba
            assert pty_dimension() == (80, 24)

        @patch("sys.stdout")
        @patch("fcntl.ioctl")
        def utiliza_default_cuando_stdout_carece_de_fileno(self, ioctl, stdout):
            # es decir, cuando se accede a ella se produce AttributeError
            stdout.fileno.efecto_secundario = AttributeError
            assert pty_dimension() == (80, 24)

        @patch("sys.stdout")
        @patch("fcntl.ioctl")
        def utiliza_default_cuando_stdout_desencadena_error_en_ioctl(self, ioctl, stdout):
            ioctl.efecto_secundario = TypeError
            assert pty_dimension() == (80, 24)

    class bytes_para_leer:
        @patch("dued.terminales.fcntl")
        def devuelve_1_cuando_la_secuencia_carece_de_fileno(self, fcntl):
            # Un fileno() que existe pero devuelve un non-int es una forma
            # rápida de fallar util.tiene_fileno ().
            assert bytes_a_leer(Mock(fileno=lambda: None)) == 1
            assert not fcntl.ioctl.called

        @patch("dued.terminales.fcntl")
        def devuelve_1_cuando_la_secuencia_tiene_fileno_pero_no_es_un_tty(self, fcntl):
            # De todos modos explota de otra manera (struct.unpack se enoja
            # porque el resultado no es una cadena de la longitud correcta)
            # pero hagamos que ioctl muera de manera similar al caso del
            #  mundo real que estamos probando aquí (# 425)
            fcntl.ioctl.efecto_secundario = IOError(
                "Operación no compatible con el dispositivo"
            )
            stream = Mock(esuntty=lambda: False, fileno=lambda: 17)  # arbitrary
            assert bytes_a_leer(stream) == 1
            assert not fcntl.ioctl.called

        def devuelve_el_resultado_de_FIONREAD_cuando_la_secuencia_es_un_tty(self):
            skip()

        def devuelve_1_en_windows(self):
            skip()
