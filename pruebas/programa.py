import json
import os
import sys

from dued.util import six, Lexicon
from mock import patch, Mock, ANY
import pytest
from pytest import skip
from pytest_relaxed import trap

from dued import (
    Argumento,
    Coleccion,
    Config,
    Ejecutor,
    CargaDesdeElSitemaDeArchivos,
    AnalizadorDeContexto,
    AnalizaResultado,
    Programa,
    Resultado,
    Artefacto,
    SalidaInesperada,
)
from dued import main
from dued.util import cd
from dued.config import fusionar_dics

from _util import (
    RAIZ,
    confirmar,
    cargar,
    correr,
    saltar_si_es_windows,
    archivo_de_soporte,
    ruta_de_soporte,
)


marcapytest = pytest.mark.usefixtures("integracion")


class Programa_:
    class init:
        "__init__"

        def puede_especificar_la_version(self):
            assert Programa(version="1.2.3").version == "1.2.3"

        def version_pordefecto_es_desconocida(self):
            assert Programa().version == "desconocida"

        def puede_especificar_el_hangar(self):
            foo = cargar("foo")
            assert Programa(hangar=foo).hangar is foo

        def puede_especificar_el_nombre(self):
            assert Programa(nombre="Miapp").nombre == "Miapp"

        def puede_especificar_el_binario(self):
            assert Programa(binario="miapp").binario == "miapp"

        def pordefecto_la_clase_cargador_es_FilesystemLoader(self):
            assert Programa().clase_cargador is CargaDesdeElSitemaDeArchivos

        def puede_especificar_clase_cargador(self):
            klase = object()
            assert Programa(clase_cargador=klase).clase_cargador == klase

        def pordefecto_clase_ejecutor_es_Ejecutor(self):
            assert Programa().clase_ejecutor is Ejecutor

        def puede_especificar_clase_ejecutor(self):
            klase = object()
            assert Programa(clase_ejecutor=klase).clase_ejecutor == klase

        def pordefecto_clase_config_es_Config(self):
            assert Programa().clase_config is Config

        def puede_especificar_clase_config(self):
            klase = object()
            assert Programa(clase_config=klase).clase_config == klase

    class miscelaneo:
        "comportamiento variado"

        def bandera_debug_activa_el_registro(self):
            # Tenemos que parchear nuestro registrador para entrar antes de
            # que inicie logcapture.
            with patch("dued.util.debug") as debug:
                Programa().correr("dued -d -c foo")
                debug.assert_called_with("mi-centinela")

        def debug_honrado_como_VarEnt_tambien(self, restablecer_entorno):
            os.environ["dued_DEBUG"] = "1"
            with patch("dued.util.debug") as debug:
                # NOTE: no se utiliza -d/--depurar
                Programa().correr("dued -c depuraciones foo")
                debug.assert_called_with("mi-centinela")

        def bytecode_omitido_pordefecto(self):
            confirmar("-c foo miartefacto")
            assert sys.dont_write_bytecode

        def generar_pyc_explicitamente_habilita_la_escritura_de_bytecode(self):
            confirmar("--generar-pyc -c foo miartefacto")
            assert not sys.dont_write_bytecode

    class normalizar_argv:
        @patch("dued.programa.sys")
        def pordefecto_a_sys_argv(self, mock_sys):
            argv = ["du", "--version"]
            mock_sys.argv = argv1
            p = Programa()
            p.imprimir_version = Mock()
            p.correr(salir=False)
            p.imprimir_version.asercion_llamada()

        def usa_una_lista_inalterada(self):
            p = Programa()
            p.imprimir_version = Mock()
            p.correr(["du", "--version"], salir=False)
            p.imprimir_version.asercion_llamada()

        def divide_una_cadena(self):
            p = Programa()
            p.imprimir_version = Mock()
            p.correr("du --version", salir=False)
            p.imprimir_version.asercion_llamada()

    class nombre:
        def pordefecto_a_mayusculas_cuando_no_es_binario(self):
            confirmar("miapp --version", salida="Miapp desconocida\n", dued=False)

        def se_beneficia_del_comportamiento_de_ruta_absoluta_binario(self):
            "se beneficia del comportamiento de ruta absoluta de binario()'s"
            confirmar(
                "/usr/local/bin/miapp --version",
                salida="Miapp desconocida\n",
                dued=False,
            )

        def utiliza_un_valor_reemplazado_cuando_se_proporciona(self):
            p = Programa(nombre="NoDued")
            confirmar("--version", salida="NoDued desconocido\n", programa=p)

    class binario:
        def pordefecto_es_argv_cuando_no_existe(self):
            stdout, _ = correr("miapp --help", dued=False)
            assert "miapp [--opcs-nucleo]" in stdout

        def utiliza_un_valor_reemplazado_cuando_se_proporciona(self):
            stdout, _ = correr(
                "miapp --help", dued=False, programa=Programa(binario="nop")
            )
            assert "nop [--opcs-nucleo]" in stdout

        @trap
        def usa_el_nombrebase_binario_cuando_se_invoca_absolutamente(self):
            Programa().correr("/usr/local/bin/miapp --help", salir=False)
            stdout = sys.stdout.getvalue()
            assert "miapp [--opcs-nucleo]" in stdout
            assert "/usr/local/bin" not in stdout

    class llamado_de:
        # NOTE: estas pruebas son bah debido al diseño del ciclo de vida 
        # del Programa (los atributos se modifican ejecutando correr(), como
        # cosas basadas en argv observado). No es genial, pero, cualquier.
        @trap
        def cuando_se_da_el_trato_completo_es_el_nombre(self):
            p = Programa()
            p.correr("cualquier --help", salir=False)
            assert p.llamado_de == "cualquier"

        @trap
        def cuando_se_da_una_ruta_es_el_nombrebase(self):
            p = Programa()
            p.correr("/usr/local/bin/cualquier --help", salir=False)
            assert p.llamado_de == "cualquier"

    class nombres_binarios:
        # NOTE: esto actualmente solo se usa para completar cosas, así que 
        # lo usamos para probar. TODO: tal vez haga esto más unit-y ...
        def cuando_no_existe_pordefecto_es_argv(self):
            stdout, _ = correr("foo --script-completado zsh", dued=False)
            assert " foo" in stdout

        def puede_ser_dado_directamente(self):
            programa = Programa(nombres_binarios=["foo", "bar"])
            stdout, _ = correr(
                "foo --script-completado zsh",
                dued=False,
                programa=programa,
            )
            assert " foo bar" in stdout

    class imprimir_version:
        def muestra_nombre_y_version(self):
            confirmar(
                "--version",
                programa=Programa(nombre="Miprograma", version="0.1.0"),
                salida="Miprograma 0.1.0\n",
            )

    class contexto_inicial:
        def contiene_argumentos_verdaderamente_principales_independientemente_del_valor_del_EN(self):
            # Spot chequeo. Consulte integration-style --help pruebas para
            # una verificación completa del argumento.
            for programa in (Programa(), Programa(hangar=Coleccion())):
                for arg in ("--completar", "--depurar", "--alarma-only", "--lista"):
                    stdout, _ = correr("--help", programa=programa)
                    assert arg in stdout

        def un_EN_nulo_desencadena_args_relacionados_con_el_artefacto(self):
            programa = Programa(hangar=None)
            for arg in programa.artefacto_args():
                stdout, _ = correr("--help", programa=programa)
                assert arg.nombre in stdout

        def un_EN_no_nulo_no_desencadena_args_relacionados_con_el_artefacto(self):
            for arg in Programa().artefacto_args():
                programa = Programa(hangar=Coleccion(miartefacto=Artefacto(Mock())))
                stdout, _ = correr("--help", programa=programa)
                assert arg.nombre not in stdout

    class cargar_coleccion:
        def se_queja_cuando_no_se_encuentra_la_colección_pordefecto(self):
            # NOTE: assumes system under prueba has no artefactos.py in root. Meh.
            with cd(RAIZ):
                confirmar("-l", err="No se puede encontrar ninguna coleccion llamada 'artefactos'!\n")

        def se_queja_cuando_no_encuentra_la_coleccion_explicita(self):
            confirmar(
                "-c naboo -l",
                err="No puedo encontrar ninguna coleccion llamada 'naboo'!\n",
            )

        @trap
        def utiliza_la_clase_cargador_entregada(self):
            klase = Mock(efecto_secundario=CargaDesdeElSitemaDeArchivos)
            Programa(clase_cargador=klase).correr("miapp --help foo", salir=False)
            klase.assert_called_with(inicio=ANY, config=ANY)

    class ejecutar:
        def utiliza_la_clase_ejecutor_entregada(self):
            klase = Mock()
            Programa(clase_ejecutor=klase).correr("miapp foo", salir=False)
            klase.assert_called_with(ANY, ANY, ANY)
            klase.valor_de_retorno.ejecutar.assert_called_with(ANY)

        def la_clase_ejecutor_se_puede_reemplazada_por_una_cadena_configurada(self):
            class ExecutorOverridingConfig(Config):
                @staticmethod
                def global_defaults():
                    defaults = Config.global_defaults()
                    ruta = "ejecutor_personalizado.EjecutorPersonalizado"
                    fusionar_dics(defaults, {"artefactos": {"clase_ejecutor": ruta}})
                    return defaults

            mock = cargar("ejecutor_personalizado").EjecutorPersonalizado
            p = Programa(clase_config=ExecutorOverridingConfig)
            p.correr("miapp noop", salir=False)
            assert mock.assert_called
            assert mock.valor_de_retorno.ejecutar.called

        def el_ejecutor_tiene_acceso_a_los_args_principales_y_al_resto(self):
            klase = Mock()
            cmd = "miapp -e foo -- miremanente"
            Programa(clase_ejecutor=klase).correr(cmd, salir=False)
            nucleo = klase.llamar_args[0][2]
            assert nucleo[0].args["echo"].valor
            assert nucleo.remanente == "miremanente"

    class args_nucleo:
        def devuelve_la_lista_de_args_principales(self):
            # Los argumentos principales son los args_nucleo o Argumentos 
            # nucleo.
            # Sobre todo, codificamos explícitamente el miembro doc'd de la
            # API publica en las pruebas.
            # Las comprobaciones al azar son suficientemente buenas, las 
            # pruebas de ayuda incluyen la oferta completa.
            args_nucleo = Programa().args_nucleo()
            nombres_de_args_nucleo = [x.nombres[0] for x in args_nucleo]
            for nombre in ("completar", "help", "pty", "version"):
                assert nombre in nombres_de_args_nucleo
            # Asegúrese también de que es una lista para facilitar su 
            # ajuste/anexado
            assert isinstance(args_nucleo, list)

    class args_propiedad:
        def abreviatura_de_self_args_nucleo(self):
            "es una abreviatura para self.nucleo[0].args"
            p = Programa()
            p.correr("miapp -e noop", salir=False)
            args = p.args
            assert isinstance(args, Lexicon)
            assert args.echo.valor is True

    class args_nucleo_desde_contextos_de_artefacto:
        # NOTE: muchos de estos usan Programa.args en lugar de 
        # Programa.nucleo[0], por conveniencia, aunque también porque 
        # inicialmente el comportamiento era _in_.args
        def el_contexto_nucleo_se_actualiza_con_banderas_nucleo_de_artefactos(self):
            # Parte de #466.
            p = Programa()
            p.correr("miapp -e noop --ocultar ambos", salir=False)
            # Fue dado en el núcleo
            assert p.args.echo.valor is True
            # Fue dado en por artefacto
            assert p.args.ocultar.valor == "ambos"

        def copiar_desde_el_contexto_del_artefacto_no_establece_valores_de_lista_vacios(self):
            # Un problema menor para los escalares, pero para los argumentos
            # de tipo lista, hacer .valor=<valor predeterminado> en realidad
            # termina creando una lista de listas.
            p = Programa()
            # Configura contexto de analisis de args-nucleo con un argumento
            # iterable que aún no ha visto ningún valor
            def args_nombredearchivo():
                return [Argumento("nombredearchivo", tipo=list)]

            p.nucleo = AnalizaResultado([AnalizadorDeContexto(args=args_nombredearchivo())])
            # Y un contexto de nucleo-vía-artefactos con una copia de ese 
            # mismo arg, que tampoco ha visto ningún valor todavía
            p.nucleo_via_artefactos = AnalizadorDeContexto(args=args_nombredearchivo())
            # Ahora el comportamiento de .args se puede probar como se desee
            assert p.args["nombredearchivo"].valor == []  # Not [[]]!

        def copiar_desde_el_contexto_del_artefacto_no_sobrescribe_los_valores_buenos(self):
            # Otro subcase, que también se aplica mayoritariamente a tipos de 
            # lista: el contexto del núcleo obtuvo un valor útil, no se 
            # encontró nada en el contexto por-artefacto; cuando se usa un
            # chequeo ingenuo 'no es Ninguno', esto sobrescribe el valor bueno
            # con una lista vacía.
            # (Otros tipos tienden a no tener este problema porque su ._value
            # es siempre None cuando no se establece. TODO: ¿tal vez esto 
            # debería considerarse un comportamiento incorrecto para los
            # argumentos de tipo de lista?)
            def crear_arg():
                return Argumento("nombredearchivo", tipo=list)

            p = Programa()
            # arg nucleo, que obtuvo un valor
            arg = crear_arg()
            arg.valor = "algun_archivo"  # se agrega a la lista
            p.nucleo = AnalizaResultado([AnalizadorDeContexto(args=[arg])])
            # Establecer la versión de nucleo-via-artefactos a la versión
            # vainilla/vacio/lista-vacía
            p.nucleo_via_artefactos = AnalizadorDeContexto(args=[crear_arg()])
            # Llamar .args, confirmar que no se sobrescribió el valor inicial

            assert p.args.nombredearchivo.valor == ["algun_archivo"]

    class correr:
        # NOTE: algunas de estas son pruebas de estilo integración, pero 
        # siguen siendo pruebas rápidas (por lo que no es necesario ingresar
        # a la suite de integración) y tocan las transformaciones en la línea
        # de comando que ocurren arriba o alrededor de las clases/métodos
        # analizadores reales (por lo que no es adecuado para las pruebas 
        # de unidad del analizador).

        def busca_y_carga_el_modulo_de_artefactos_pordefecto(self):
            confirmar("foo", salida="Hm\n")

        def no_busca_el_modulo_de_artefactos_si_se_dio_EN(self):
            confirmar(
                "foo",
                err="No tengo idea de lo que es 'foo'!\n",
                programa=Programa(hangar=Coleccion("vacio")),
            )

        def el_espacio_de_nombres_explícito_funciona_correctamente(self):
            # Regresión-ish prueba re # 288
            hng = Coleccion.del_modulo(cargar("integracion"))
            confirmar("imprimir-foo", salida="foo\n", programa=Programa(hangar=hng))

        def permite_la_especificacion_explicita_del_modulo_artefactos(self):
            confirmar("-c integracion imprimir-foo", salida="foo\n")

        def maneja_argumentos_de_artefactos(self):
            confirmar("-c integracion imprimir-nombre --nombre luke", salida="luke\n")

        def puede_cambiar_la_raiz_de_busqueda_de_la_coleccion(self):
            for bandera in ("-r", "--dir-raiz"):
                confirmar(
                    "{} rama/ raiz_alternativa".format(bandera),
                    salida="¡Bloqueado con la raiz_alternativa!\n",
                ) 

        def puede_cambiar_la_raiz_de_busqueda_de_la_colección_con_el_nombre_del_modulo_explicito(self):
            for bandera in ("-r", "--dir-raiz"):
                confirmar(
                    "{} rama/ -c explicito supremacy".format(bandera),
                    salida="¡No digas palabrotas!\n",
                )

        @trap
        @patch("dued.programa.sys.exit")
        def ParseErrors_muestra_mensaje_y_sale_1(self, mock_exit):
            p = Programa()
            # Correr con una entrada incorrecta definitivamente enfurece al
            # analizador; el hecho de que esta línea no genere una excepción
            # y por lo tanto falle la prueba, es lo que estamos probando ...
            nopi = "no-no-valida-lo-siento"
            p.correr("miapp {}".format(nopi))
            # Espere que imprimamos el cuerpo del núcleo del ErrorDeAnalisis
            # (por ejemplo, "¡No tengo idea de qué es foo!") Y salir 1.
            # (La intención  básicamente es, mostrar esa información sin un
            # rastreo completo).
            stderr = sys.stderr.getvalue()
            assert stderr == "¡No tengo idea de qué es '{}'!\n".format(nopi)
            mock_exit.assert_called_with(1)

        @trap
        @patch("dued.programa.sys.exit")
        def SalidaInesperada_sale_con_codigo_cuando_no_se_oculta(self, mock_exit):
            p = Programa()
            ups = SalidaInesperada(
                Resultado(comando="bah", salida=17, ocultar=tuple())
            )
            p.ejecutar = Mock(efecto_secundario=ups)
            p.correr("miapp foo")
            # NO espere que se imprima ningun repr, porque stdout/err no
            # estaban ocultos, por lo que no queremos agregar más verbosidad
            # molesta; queremos ser más similares a Make aquí.
            assert sys.stderr.getvalue() == ""
            # Pero seguimos saliendo con el código esperado (vs ej.1 o 0)
            mock_exit.assert_called_with(17)

        @trap
        @patch("dued.programa.sys.exit")
        def muestra_SalidaInesperada_cadena_cuando_hay_streams_ocultas(self, mock_exit):
            p = Programa()
            ups = SalidaInesperada(
                Resultado(
                    comando="bah",
                    salida=54,
                    stdout="cosas!",
                    stderr="horrorosas!",
                    codificacion="utf-8",
                    ocultar=("stdout", "stderr"),
                )
            )
            p.ejecutar = Mock(efecto_secundario=ups)
            p.correr("miapp foo")
            # Espere repr() de impresiones de excepción en stderr
            # NOTE: esto duplica parcialmente una prueba en corredores.py;
            # cualquier.
            stderr = sys.stderr.getvalue()
            esperado = """¡Encontré un código de salida de comando incorrecto!

Comando: 'bah'

Código de salida 54

Stdout:

cosas!

Stderr:

horrorosas!

"""
            assert stderr == esperado
            # Pero seguimos saliendo con el código esperado (vs ej.1 o 0)
            mock_exit.assert_called_with(54)

        @trap
        @patch("dued.programa.sys.exit")
        def SalidaInesperada_cadena_codifica_stdout_y_err(self, mock_exit):
            p = Programa()
            ups = SalidaInesperada(
                Resultado(
                    comando="bah",
                    salida=54,
                    stdout=u"esto no es ascii: \u1234",
                    stderr=u"esto tampoco es ascii: \u4321",
                    codificacion="utf-8",
                    ocultar=("stdout", "stderr"),
                )
            )
            p.ejecutar = Mock(efecto_secundario=ups)
            p.correr("miapp foo")
            # NOTE: usando ASCII binario explícito aquí, y accediendo a 
            # getvalue() sin procesar del sys.stderr falso (spec.trap lo 
            # decodifica automáticamente normalmente) para tener una prueba
            # no del todo tautológica. de lo contrario, estaríamos comparando
            # unicode con unicode. ¿encogimiento de hombros?
            esperado = b"""Encontre un codigo de salida de comando incorrecto!

Comando: 'bah'

Codigo de salida: 54

Stdout:

esto no es ascii: \xe1\x88\xb4

Stderr:

esto tampoco es ascii: \xe4\x8c\xa1

"""
            got = six.BytesIO.getvalue(sys.stderr)
            assert got == esperado

        def debe_mostrar_el_uso_principal_en_los_errores_de_analisis_del_nucleo(self):
            skip()

        def debe_mostrar_el_uso_de_contexto_en_los_errores_de_analisis_de_contexto(self):
            skip()

        @trap
        @patch("dued.programa.sys.exit")
        def convierte_KeyboardInterrupt_en_el_codigo_de_salida_1(self, mock_exit):
            p = Programa()
            p.ejecutar = Mock(efecto_secundario=KeyboardInterrupt)
            p.correr("miapp -c foo miartefacto")
            mock_exit.assert_called_with(1)

    class help_:
        "--help"

        class nucleo:
            def invocacion_vacia_sin_ningun_ertefacto_pordefecto_imprime_ayuda(self):
                stdout, _ = correr("-c foo")
                assert "Opciones principales:" in stdout

            # TODO: En Windows, no obtenemos un pty, por lo que no obtenemos
            # un tamaño de terminal garantizado de 80x24. Omita por ahora,
            # pero tal vez una solución adecuada sería simplemente eliminar
            # todos los espacios en blanco de los valores devueltos y 
            # esperados antes de probar. Entonces se ignora el tamaño del 
            # terminal.
            @saltar_si_es_windows
            def opcion_de_ayuda_basica_imprime_ayuda_basica(self):
                # TODO: ¿cambiar dinámicamente en función de los contenidos
                # del analizador? p.ej. no nucleo args == no [--opcs-nucleo],
                # no artefactos == no artefacto stuff? 
                # NOTE: prueba activará un tamaño de pty predeterminado de
                # 80x24, por lo que la siguiente cadena tiene el formato 
                # adecuado.
                # TODO: agregue más pruebas unit y para comportamientos
                # específicos:
                # * llenar terminal con columnas + espaciado
                # * ajustar el texto de ayuda en su propia columna
                esperado = """
Uso: du[ed] [--opcs-nucleo] artefacto1 [--artefacto1-opcs] ... artefactoN [--artefactoN-opcs]

Opciones principales:
      
  --completar                       Imprima candidatos de tab-completado para
                                    un análisis determinado.
  --ocultar=CADENA                  Establezca el valor predeterminado del 
                                    kwarg 'ocultar' de correr().    
  --no-dedupe                       Desactiva deduplication de artefacto.
  --script-completado=CADENA    Imprima el script de tab-completado para
                                    su shell preferido (bash-zsh-fish).
  --prompt-sudo            Solicita al ususario al inicio de sesion
                                    el valor para cofigurar sudo.password
  --generar-pyc                     Habilitar la creación de archivos .pyc.
  -c CADENA, --coleccion=CADENA     Especifique el nombre de la coleccion que
                                    se va a cargar.
  -d, --depurar                       Habilita la salida de depuración.
  -P INT, --prof-de-lista=INT       Al enumerar artefactos, solo muestre los 
                                    primeros niveles de INT.
  -e, --echo                        Echo ejecuta comandos antes de correr.
  -f CADENA, --config=CADENA        Archivo de configuración en tiempo de 
                                    ejecución que se va a utilizar..
  -F CADENA, --formlista=CADENA     Cambie el formato de visualización usado
                                    al enumerar artefactos. Debe ser uno de:
                                    plano (predeterminado), anidado, json.
  -h [CADENA], --help[=CADENA]      Muestre ayuda básica o por artefacto y 
                                    salga.
  -l [CADENA], --lista[=CADENA]     Liste los artefactos disponibles, 
                                    opcionalmente limitado a un espacio de 
                                    nombres.
  -p, --pty                         Utilice un pty al ejecutar comandos de 
                                    shell.
  -r CADENA, --dir-raiz=CADENA      Cambie el directorio raíz utilizado para
                                    encontrar módulos de artefacto.
  -S, --seco                        Comandos de echo en lugar de correr.
  -T INT, --tiempofuera=INT         Especifique un tiempo de espera de 
                                    ejecución de comandos globales, en seg.                                  
  -V, --version                     Mostrar versión y salir.
  -a, --solo-alerta                 Advertir, en lugar de fallar, cuando los
                                    comandos de shell fallan.

""".lstrip()
                for bandera in ["-h", "--help"]:
                    confirmar(bandera, salida=esperado, programa=main.programa)

            def la_ayuda_del_espacio_de_nombres_incluye_una_lista_de_subcomandos(self):
                t1, t2 = Artefacto(Mock()), Artefacto(Mock())
                colecc = Coleccion(artefacto1=t1, artefacto2=t2)
                p = Programa(hangar=colecc)
                # Comprueba los bits esperados, por lo que no tenemos que 
                # cambiar esto cada vez que cambian los argumentos de nucleo.
                for esperado in (
                    # La línea de uso cambia algo
                    "Uso: miapp [--opcs-nucleo] <subcomando> [--subcomando-opcs] ...\n",  # noqa
                    # Las opciones principales todavía están presentes
                    "Opciones principales:\n",
                    "--echo",
                    # Los subcomandos están listados
                    "Subcomandos:\n",
                    "  artefacto1",
                    "  artefacto2",
                ):
                    stdout, _ = correr("miapp --help", programa=p, dued=False)
                    assert esperado in stdout

            def la_ayuda_principal_no_se_enoja_si_falla_la_carga(self):
                # No espera artefactos.py en la raíz de FS
                with cd(RAIZ):
                    stdout, _ = correr("--help")
                    assert "Uso: " in stdout

        class por_artefacto:
            "por-artefacto"

            def imprime_ayuda_solo_para_los_artefactos(self):
                esperado = """
Uso: dued [--opcs-nucleo] holocron [--opciones] [aqui otro artefactos ...]

Textdocs:
  ninguno

Opciones:
  -h CADENA, --porque=CADENA   Motivo
  -a CADENA, --quien=CADENA   Quien al lado oscuro

""".lstrip()
                for bandera in ["-h", "--help"]:
                    confirmar("-c decoradores {} holocron".format(bandera), salida=esperado)

            def funciona_para_artefactos_sin_parametrizar(self):
                esperado = """
Uso: dued [--opcs-nucleo] biz [aqui otros artefactos ...]

Textdocs:
  ninguno

Opciones:
  ninguno

""".lstrip()
                confirmar("-c decoradores -h biz", salida=esperado)

            def honra_el_programa_binario(self):
                stdout, _ = correr(
                    "-c decoradores -h biz", programa=Programa(binario="nodued")
                )
                assert "Uso: nodued" in stdout

            def muestra_los_textdocs_si_se_han_dado(self):
                esperado = """
Uso: dued [--opcs-nucleo] foo [aqui otros artefactos ...]

Textdocs:
  Foo el bar.

Opciones:
  ninguno

""".lstrip()
                confirmar("-c decoradores -h foo", salida=esperado)

            def deduce_correctamente(self):
                esperado = """
Uso: dued [--opcs-nucleo] foo2 [aqui otros artefactos ...]

Textdocs:
  Foo el bar:

    codigo ejemplo

  Agregado en 1.0

Opciones:
  ninguno

""".lstrip()
                confirmar("-c decoradores -h foo2", salida=esperado)

            def deduce_correctamente_para_el_estilo_alt_textdocs(self):
                esperado = """
Uso: dued [--opcs-nucleo] foo3 [aqui otros artefactos ...]

Textdocs:
  Foo el otro bar:

    codigo ejemplo

  Agregado en 1.1

Opciones:
  ninguno

""".lstrip()
                confirmar("-c decoradores -h foo3", salida=esperado)

            def sale_despues_de_imprimir(self):
                # TODO: busque y pruebe las otras variantes de este caso de
                # error, como nucleo --help no salir, --lista no salir, etc.
                esperado = """
Uso: dued [--opcs-nucleo] holocron [--opciones] [aqui otros artefactos ...]

Textdocs:
  ninguno

Opciones:
  -h CADENA, --porque=CADENA   Motivo
  -a CADENA, --quien=CADENA   Quien al lado oscuro

""".lstrip()
                confirmar("-c decoradores -h holocron --lista", salida=esperado)

            def se_queja_si_se_da_un_nombre_de_artefacto_novalido(self):
                confirmar("-h sith", err="¡no tengo ni idea de lo que 'sith'!\n")

    class lista_de_artefactos:
        "--lista"

        def _listado(self, lines):
            return """
Artefactos disponibles:

{}

""".format(
                "\n".join("  " + x for x in lines)
            ).lstrip()

        def _lista_eq(self, coleccion, listado): # Lista ecualizada
            cmd = "-c {} --lista".format(coleccion)
            confirmar(cmd, salida=self._listado(listado))

        def salida_simple(self):
            esperado = self._listado(
                (
                    "bar",
                    "biz",
                    "boz",
                    "foo",
                    "post1",
                    "post2",
                    "imprimir-foo",
                    "imprimir-nombre",
                    "imprimir-arg-con-guionesbajos",
                )
            )
            for bandera in ("-l", "--lista"):
                confirmar("-c integracion {}".format(bandera), salida=esperado)

        def hangar(self):
            self._lista_eq("hangar", ("altonivel", "module.miartefacto"))

        def artefactos_de_nivel_superior_enumerados_primero(self):
            self._lista_eq("lista_simple_hng", ("z-altonivel", "a.b.subartefacto"))

        def alias_ordenados_alfabeticamente(self):
            self._lista_eq("alias_ordenado", ("altonivel (a, z)",))

        def artefactos_pordefecto(self):
            # sub-es artefacto predeterminado se muestra como "real.nombre (coleccion nombre)"
            self._lista_eq(
                "raiz_explicita",
                (
                    "alto-nivel (otro-alto)",
                    "sub-nivel.sub-artefacto (sub-nivel, sub-nivel.otro-sub)",
                ),
            )

        def textdocs_mostrados_junto(self):
            self._lista_eq(
                "textdocs:",
                (
                    "espacio-en-blanco-inicial  foo",
                    "no-textdocs",
                    "linea-uno                  foo",
                    "linea-dos                  foo",
                    "con-alias (a, b)           foo",
                ),
            )

        def los_textdocs_se_ajustan_al_ancho_de_terminal(self):
            self._lista_eq(
                "textdocs_sustancial",
                (
                    "no-textdocs",
                    "artefacto-uno       Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n                 Nullam id dictum",  # noqa
                    "artefacto-dos       Nulla eget ultrices ante. Curabitur sagittis commodo posuere.\n                 Duis dapibus",  # noqa
                ),
            )

        def colecciones_vacias_dicen_que_no_hay_artefactos(self):
            confirmar(
                "-c vacio -l", err="No se han encontrado artefactos en coleccion 'vacio'!\n"
            )

        def los_arboles_sustanciales_se_ordenan_por_hangar_y_profundidad(self):
            # Mediante el uso de una muestra más grande, podemos protegernos
            # contra comportamientos poco intuitivos que surgen de las 
            # pruebas de estilo de unidad simple anteriores. P.ej. 
            # implementaciones anteriores "rompieron" colecciones que tenían
            # más de 2 niveles de profundidad, porque mostraban todos los 
            # artefactos de segundo nivel antes que los de tercer nivel.
            # El código debe cuadrar esa preocupación con "mostrar los 
            # artefactos superficiales antes que los profundos" (frente a 
            # la clasificación alfa directa)
            esperado = """Artefactos disponibles:

  iterminal (termIA)                   Carga REPL con estado y config. de Py.
  prueba (correr-pruebas)              Corre suite prueba respaldada en args.
  faricar.all (fabric, faricar.all)    Fabrica los artefactos necesarios.
  fabric.c-ext (fabric.ext)            Construye nuestra extensión C interna.
  fabric.zap                           Una forma majadera de limpiar.
  fabric.docs.all (fabric.docs)        Fabrica todo formatos de docs.
  fabric.docs.html                     Genera solo salida HTML.
  fabric.docs.pdf                      Genere solo salida PDF.
  fabric.python.all (fabric.python)    Fabrica todos los paquetes de Python.
  fabric.python.sdist                  Construye tar.gz de estilo clásico.
  fabric.python.wheel                  Construye una distb. wheel (rueda).
  desplegar.db (desplegar.db-servers)  Implementar en nuestros DB servers.
  desplegar.omnipresente (desplegar)   Implementar en todos los objetivos.
  desplegar.web                        Actualiza y rebota los servidores web.
  provision.db                         Ponga en marcha uno o más DB servers.
  provision.web                        Ponga en marcha un Web server.

Default artefacto: prueba

"""
            stdout, _ = correr("-c arbol --lista")
            assert esperado == stdout

        class limitacion_de_hangares:
            def el_argumento_limita_la_visualizacion_a_un_hangar_dado(self):
                stdout, _ = correr("-c arbol --lista fabric")
                esperado = """Disponible 'fabric' artefactos:

  .all (.todo)            Fabrica los artefactos necesarios.
  .c-ext (.ext)           Construye nuestra extensión C interna.
  .zap                    Una forma majadera de limpiar.
  .docs.all (.docs)       Fabrica todo formatos de docs.
  .docs.html              Genera solo salida HTML.
  .docs.pdf               Genere solo salida PDF.
  .python.all (.python)   Fabrica todos los paquetes de Python.
  .python.sdist           Construye tar.gz de estilo clásico.
  .python.wheel           Construye una distb. wheel (rueda).

Default 'fabric' artefacto: .all

"""
                assert esperado == stdout

            def el_argumento_puede_ser_un_hangar_anidado(self):
                stdout, _ = correr("-c arbol --lista fabric.docs")
                esperado = """Disponible 'fabric.docs' artefactos:

  .all    Fabrica todo formatos de docs.
  .html   Genera solo salida HTML.
  .pdf    Genere solo salida PDF.

Default 'fabric.docs' artefacto: .all

"""
                assert esperado == stdout

            def un_hangar_vacio_dicen_que_no_hay_artefactos_en_el_namespace(self):
                # En otras palabras, es posible que el hangar exterior no esté
                # vacío, pero el interior sí. Esto debería actuar como cuando
                # no hay un hangar solicitado explícitamente y no hay 
                # artefactos.
                # TODO: ¿debería el nombre en el mensaje de error ser el 
                # completo en su lugar?
                confirmar(
                    "-c subcoleccion_vacia -l subcoleccion",
                    err="No artefactos found in coleccion 'subcoleccion'!\n",  # noqa
                )

            def los_hangares_invalidos_salen_emitiendo_mensaje(self):
                confirmar(
                    "-c vacio -l nop",
                    err="Sub-coleccion 'nop' not found!\n",
                )

        class limitacion_de_profundidad:
            def limita_la_visualización_a_la_profundidad_dada(self):
                # Caso base: profundidad=1 aka "muéstrame los espacios de nombres"
                esperado = """Artefactos disponibles (profundidad=1):

  iterminal (termIA)                    Carga REPL con estado y config. de Py.
  prueba (correr-pruebas)               Corre suite prueba respaldada en args.
  fabric [3 artefactos, 2 colecciones]  Artefactos p.compilar cód estático.
  desplegar [3 artefactos]              Cómo desplegar código y configs.
  provision [2 artefactos]              Código de config. del sistema.

Default artefacto: prueba

"""
                stdout, _ = correr("-c arbol --lista -F plano --prof-de-lista 1")
                assert esperado == stdout

            def no_caso_base(self):
                # caso Medio: profundidad=2
                esperado = """Artefactos disponibles (profundidad=2):

  iterminal (termIA)                    Carga REPL con estado y config. de Py.
  prueba (correr-pruebas)               Corre suite prueba respaldada en args.
  faricar.all (fabric, faricar.all)     Fabrica los artefactos necesarios.
  fabric.c-ext (fabric.ext)             Construye nuestra extensión C interna.
  fabric.zap                            Una forma majadera de limpiar.
  fabric.docs [3 artefactos]            Artefactos para gestion de doc Sphinx.
  fabric.python [3 artefactos]          Artefactos de distribución de PyPI /etc.
  desplegar.db (desplegar.db-servers)   Implementar en nuestros DB servers.
  desplegar.omnipresente (desplegar)    Implementar en todos los objetivos.
  desplegar.web                         Actualiza y rebota los servidores web.
  provision.db                          Ponga en marcha uno o más DB servers.
  provision.web                         Ponga en marcha un Web server.

Default artefacto: prueba

"""
                stdout, _ = correr("-c arbol --lista --prof-de-lista=2")
                assert esperado == stdout

            def profundidad_puede_ser_mas_profunda_que_la_profundidad_real(self):
                # caso Borde: profundidad > profundidad raal = lo mismo como
                # ningún arg profundidad
                esperado = """Artefactos disponibles (profundidad=5):

  iterminal (termIA)                    Carga REPL con estado y config. de Py.
  prueba (correr-pruebas)               Corre suite prueba respaldada en args.
  faricar.all (fabric, faricar.all)     Fabrica los artefactos necesarios.
  fabric.c-ext (fabric.ext)             Construye nuestra extensión C interna.
  fabric.zap                            Una forma majadera de limpiar.
  fabric.docs.all (fabric.docs)         Fabrica todo formatos de docs.
  fabric.docs.html                      Genera solo salida HTML.
  fabric.docs.pdf                       Genere solo salida PDF.
  fabric.python.all (fabric.python)     Fabrica todos los paquetes de Python.
  fabric.python.sdist                   Construye tar.gz de estilo clásico.
  fabric.python.wheel                   Construye una distb. wheel (rueda).
  desplegar.db (desplegar.db-servers)   Implementar en nuestros DB servers.
  desplegar.omnipresente (desplegar)    Implementar en todos los objetivos.
  desplegar.web                         Actualiza y rebota los servidores web.
  provision.db                          Ponga en marcha uno o más DB servers.
  provision.web                         Ponga en marcha un Web server.

Default artefacto: prueba

"""
                stdout, _ = correr("-c arbol --lista --prof-de-lista=5")
                assert esperado == stdout

            def trabaja_con_hangar_explícito(self):
                esperado = """Disponible 'fabric' artefactos (profundidad=1):

  .all (.todo)              Fabrica los artefactos necesarios.
  .c-ext (.ext)             Construye nuestra extensión C interna.
  .zap                      Una forma majadera de limpiar.
  .docs [3 artefactos]      Artefactos para gestion de doc Sphinx.
  .python [3 artefactos]    Artefactos de distribución de PyPI /etc.

Default 'fabric' artefacto: .all

"""
                stdout, _ = correr("-c arbol --lista fabric --prof-de-lista=1")
                assert esperado == stdout

            def bandera_corta_es_P(self):
                esperado = """Artefactos disponibles (profundidad=1):

  iterminal (termIA)                    Carga REPL con estado y config. de Py.
  prueba (correr-pruebas)               Corre suite prueba respaldada en args.
  fabric [3 artefactos, 2 colecciones]  Artefactos p.compilar cód estático.
  desplegar [3 artefactos]              Cómo desplegar código y configs.
  provision [2 artefactos]              Código de config. del sistema.

Default artefacto: prueba

"""
                stdout, _ = correr("-c arbol --lista --formlista=plano -P 1")
                assert esperado == stdout

            def profundidad_cero_es_lo_mismo_que_profundidad_maxima(self):
                esperado = """Artefactos disponibles:

  iterminal (termIA)                   Carga REPL con estado y config. de Py.
  prueba (correr-pruebas)              Corre suite prueba respaldada en args.
  faricar.all (fabric, faricar.all)    Fabrica los artefactos necesarios.
  fabric.c-ext (fabric.ext)            Construye nuestra extensión C interna.
  fabric.zap                           Una forma majadera de limpiar.
  fabric.docs.all (fabric.docs)        Fabrica todo formatos de docs.
  fabric.docs.html                     Genera solo salida HTML.
  fabric.docs.pdf                      Genere solo salida PDF.
  fabric.python.all (fabric.python)    Fabrica todos los paquetes de Python.
  fabric.python.sdist                  Construye tar.gz de estilo clásico.
  fabric.python.wheel                  Construye una distb. wheel (rueda).
  desplegar.db (desplegar.db-servers)  Implementar en nuestros DB servers.
  desplegar.omnipresente (desplegar)   Implementar en todos los objetivos.
  desplegar.web                        Actualiza y rebota los servidores web.
  provision.db                         Ponga en marcha uno o más DB servers.
  provision.web                        Ponga en marcha un Web server.

Default artefacto: prueba

"""
                stdout, _ = correr("-c arbol --lista --formlista=plano -P 0")
                assert esperado == stdout

        class format:
            def plano_es_formato_predeterminado_heredado(self):
                # Prueba de coherencia que --lista --formlista = plano es el
                # mismo que el antiguo "just --lista".
                esperado = """Artefactos disponibles:

  iterminal (termIA)                   Carga REPL con estado y config. de Py.
  prueba (correr-pruebas)              Corre suite prueba respaldada en args.
  faricar.all (fabric, faricar.all)    Fabrica los artefactos necesarios.
  fabric.c-ext (fabric.ext)            Construye nuestra extensión C interna.
  fabric.zap                           Una forma majadera de limpiar.
  fabric.docs.all (fabric.docs)        Fabrica todo formatos de docs.
  fabric.docs.html                     Genera solo salida HTML.
  fabric.docs.pdf                      Genere solo salida PDF.
  fabric.python.all (fabric.python)    Fabrica todos los paquetes de Python.
  fabric.python.sdist                  Construye tar.gz de estilo clásico.
  fabric.python.wheel                  Construye una distb. wheel (rueda).
  desplegar.db (desplegar.db-servers)  Implementar en nuestros DB servers.
  desplegar.omnipresente (desplegar)   Implementar en todos los objetivos.
  desplegar.web                        Actualiza y rebota los servidores web.
  provision.db                         Ponga en marcha uno o más DB servers.
  provision.web                        Ponga en marcha un Web server.

Default artefacto: prueba

"""
                stdout, _ = correr("-c arbol --lista --formlista=plano")
                assert esperado == stdout

            class anidado:
                def caso_base(self):
                    esperado = """Artefactos disponibles ('*' denota coleccion default):

  iterminal (termIA)        Carga REPL con estado y config. de Py.
  prueba* (correr-pruebas)  Corre suite prueba respaldada en args.
  fabric                    Artefactos p.compilar cód estático.
      .all* (.todo)         Fabrica los artefactos necesarios.
      .c-ext (.ext)         Construye nuestra extensión C interna.
      .zap                  Una forma majadera de limpiar.
      .docs                 Artefactos para gestion de doc Sphinx.
          .all*             Fabrica todo formatos de docs.
          .html             Genera solo salida HTML.
          .pdf              Genere solo salida PDF.
      .python               Artefactos de distribución de PyPI /etc.
          .all*             Fabrica todos los paquetes de Python.
          .sdist            Construye tar.gz de estilo clásico.
          .wheel            Construye una distb. wheel (rueda).
  desplegar                 Cómo desplegar código y configs.
      .db (.db-servers)     Implementar en nuestros DB servers.
      .omnipresente*        Implementar en todos los objetivos.
      .web                  Actualiza y rebota los servidores web.
  provision                 Código de config. del sistema.
      .db                   Ponga en marcha uno o más DB servers.
      .web                  Ponga en marcha un Web server.

Default artefacto: prueba

"""
                    stdout, _ = correr("-c arbol -l -F anidado")
                    assert esperado == stdout

                def honra_hangar_como_arg_de_lista(self):
                    stdout, _ = correr("-c arbol --lista fabric -F anidado")
                    esperado = """Disponible 'fabric' artefactos ('*' denota coleccion default):

  .all* (.todo)    Fabrica los artefactos necesarios.
  .c-ext (.ext)    Construye nuestra extensión C interna.
  .zap             Una forma majadera de limpiar.
  .docs            Artefactos para gestion de doc Sphinx.
      .all*        Fabrica todo formatos de docs.
      .html        Genera solo salida HTML.
      .pdf         Genere solo salida PDF.
  .python          Artefactos de distribución de PyPI /etc.
      .all*        Fabrica todos los paquetes de Python.
      .sdist       Construye tar.gz de estilo clásico.
      .wheel       Construye una distb. wheel (rueda).

Default 'fabric' artefacto: .all

"""
                    assert esperado == stdout

                def honra_arg_profundidad(self):
                    esperado = """Artefactos disponibles (profundidad=2; '*' denota coleccion default):

  iterminal (termIA)            Carga REPL con estado y config. de Py.
  prueba* (correr-pruebas)      Corre suite prueba respaldada en args.
  fabric                        Artefactos p.compilar cód estático.
      .all* (.todo)             Fabrica los artefactos necesarios.
      .c-ext (.ext)             Construye nuestra extensión C interna.
      .zap                      Una forma majadera de limpiar.
      .docs [3 artefactos]      Artefactos para gestion de doc Sphinx.
      .python [3 artefactos]    Artefactos de distribución de PyPI /etc.
  desplegar                     Cómo desplegar código y configs.
      .db (.db-servers)         Implementar en nuestros DB servers.
      .omnipresente*            Implementar en todos los objetivos.
      .web                      Actualiza y rebota los servidores web.
  provision                     Código de config. del sistema.
      .db                       Ponga en marcha uno o más DB servers.
      .web                      Ponga en marcha un Web server.

Default artefacto: prueba

"""
                    stdout, _ = correr("-c arbol -l -F anidado --prof-de-lista 2")
                    assert esperado == stdout

                def arg_profundidad_mas_profundo_que_la_profundidad_real(self):
                    esperado = """Artefactos disponibles (profundidad=5; '*' denota coleccion default):

  iterminal (termIA)        Carga REPL con estado y config. de Py.
  prueba* (correr-pruebas)  Corre suite prueba respaldada en args.
  fabric                    Artefactos p.compilar cód estático.
      .all* (.todo)         Fabrica los artefactos necesarios.
      .c-ext (.ext)         Construye nuestra extensión C interna.
      .zap                  Una forma majadera de limpiar.
      .docs                 Artefactos para gestion de doc Sphinx.
          .all*             Fabrica todo formatos de docs.
          .html             Genera solo salida HTML.
          .pdf              Genere solo salida PDF.
      .python               Artefactos de distribución de PyPI /etc.
          .all*             Fabrica todos los paquetes de Python.
          .sdist            Construye tar.gz de estilo clásico.
          .wheel            Construye una distb. wheel (rueda).
  desplegar                 Cómo desplegar código y configs.
      .db (.db-servers)     Implementar en nuestros DB servers.
      .omnipresente*        Implementar en todos los objetivos.
      .web                  Actualiza y rebota los servidores web.
  provision                 Código de config. del sistema.
      .db                   Ponga en marcha uno o más DB servers.
      .web                  Ponga en marcha un Web server.

Default artefacto: prueba

"""
                    stdout, _ = correr("-c arbol -l -F anidado --prof-de-lista 5")
                    assert esperado == stdout

                def todas_las_opciones_posibles(self):
                    esperado = """Disponible 'fabric' artefactos (profundidad=1; '*' denota coleccion default):

  .all* (.todo)             Fabrica los artefactos necesarios.
  .c-ext (.ext)             Construye nuestra extensión C interna.
  .zap                      Una forma majadera de limpiar.
  .docs [3 artefactos]      Artefactos para gestion de doc Sphinx.
  .python [3 artefactos]    Artefactos de distribución de PyPI /etc.

Default 'fabric' artefacto: .all

"""
                    stdout, _ = correr("-c arbol -l fabric -F anidado -D1")
                    assert esperado == stdout

                # TODO: tener estos en cada formato huele a POSIBLEMENTE un
                # buen uso para pruebas parametrizadas ...
                def un_hangar_vacio_dicen_que_no_hay_artefactos_en_el_namespace(self):
                    confirmar(
                        "-c subcoleccion_vacia -l subcoleccion -F anidado",
                        err="No encontre artefactos en coleccion 'subcoleccion'!\n",
                    )

                def los_hangares_invalidos_salen_emitiendo_mensaje(self):
                    confirmar(
                        "-c vacio -l jedi -F anidado",
                        err="Sub-coleccion 'jedi' no encontrada!\n",
                    )

            class json:
                def setup(self):
                    # Datos almacenados esperados como un archivo JSON real 
                    # porque es grande y parece una mierda si está insertado.
                    # Además, al hacer un recorrido de ida y vuelta, eliminamos
                    # la impresión bonita. Ganar-ganar?
                    self.arbol = json.loads(archivo_de_soporte("arbol.json"))
                    self.por_nombre = {
                        x["nombre"]: x for x in self.arbol["colecciones"]
                    }

                def caso_base(self):
                    stdout, _ = correr("-c arbol --lista --formlista=json")
                    assert self.arbol == json.loads(stdout)

                def honra_hangar_como_arg_de_lista(self):
                    stdout, _ = correr("-c arbol --lista desplegar --formlista=json")
                    esperado = self.por_nombre["desplegar"]
                    assert esperado == json.loads(stdout)

                def no_honra_el_arg_profundidad(self):
                    _, stderr = correr("-c arbol -l --formlista json -P 2")
                    esperado = "¡La opción --prof-de-lista no es compatible con el formato JSON!\n"  # noqa
                    assert esperado == stderr

                def no_honra_el_arg_profundidad_incluso_con_hangar(self):
                    _, stderr = correr("-c arbol -l fabric -F json -P 2")
                    esperado = "¡La opción --prof-de-lista no es compatible con el formato JSON!\n"  # noqa
                    assert esperado == stderr

                # TODO: ¿debería un hangar vacío pero válido en formato JSON
                # en realidad ser un dict vacío? Seamos coherentes con los 
                # otros formatos por ahora, pero ...
                def un_hangar_vacio_dicen_que_no_hay_artefactos_en_el_hangar(self):
                    confirmar(
                        "-c subcoleccion_vacia -l subcoleccion -F anidado",
                        err="¡No se han encontrado artefactos en coleccion 'subcoleccion'!\n",  # noqa
                    )

                # NOTE: esto probablemente debería salir con un mensaje incluso
                # si se determina que la prueba anterior re: valid-but-empty 
                # quiere un comportamiento sin error.
                def los_hangares_invalidos_salen_emitiendo_mensaje(self):
                    confirmar(
                        "-c vacio -l nop -F anidado",
                        err="Sub-coleccion 'nop' no encontrada!\n",
                    )

    class opciones_de_ejecucion:
        " correr() banderas CLI relacionadas afectan a los valores de config 'correr'"
       
        def _bandera_de_prueba(self, bandera, key, valor=True):
            p = Programa()
            p.ejecutar = Mock()  # neuter
            p.correr("du {} foo".format(bandera))
            assert p.config.correr[key] == valor

        def solo_alerta(self):
            self._bandera_de_prueba("-a", "alarma")

        def pty(self):
            self._bandera_de_prueba("-p", "pty")

        def ocultar(self):
            self._bandera_de_prueba("--ocultar ambos", "ocultar", valor="ambos")

        def echo(self):
            self._bandera_de_prueba("-e", "echo")

        def tiempofuera(self):
            for bandera in ("-T", "--tiempofuera"):
                p = Programa()
                p.ejecutar = Mock()  # neuter
                p.correr("du {} 5 foo".format(bandera))
                assert p.config.tiempo_de_descanso.comando == 5

    class configuracion:
        "Preocupaciones relacionadas con la configuración"

        def _klase(self):

            # Mock pobre que puede honrar .artefactos.nombre_de_coleccion 
            #(Cargador busca esto en la configuración por defecto).
            instancia_mock = Mock(
                artefactos=Mock(nombre_de_coleccion="cualquier", dir_raiz="bah")
            )
            return Mock(valor_de_retorno=instancia_mock)

        @trap
        def clase_config_honra_init_kwarg(self):
            klase = self._klase()
            Programa(clase_config=klase).correr("miapp foo", salir=False)
            # No te preocupes por los args reales...
            assert len(klase.llamada_a_lista_de_args) == 1

        @trap
        def el_atrib_config_esta_memorizado(self):
            klase = self._klase()
            # Can't .config without .correr (bah); .correr calls .config once.
            p = Programa(clase_config=klase)
            p.correr("miapp foo", salir=False)
            assert klase.call_count == 1
            # Second access should use cached value
            p.config
            assert klase.call_count == 1

        # NOTA: todas estas pruebas se basan en los artefactos duedd para 
        # realizar las afirmaciones (aserciones) necesarias.
        # TODO: ¿probablemente pueda ajustarlos para afirmar cosas sobre
        # Programa.config en su lugar?

        def los_archivos_de_config_por_py_se_cargan_antes_del_analisis_de_artefactos(self):
            # Se basa en que nombre_auto_guion se cargue a nivel de 
            # proyecto-conf; corrige # 467; cuando el error está presente,
            # el proyecto conf se carga _ después_ intento de analizar 
            # artefactos, provocando una explosión cuando yo_tengo_guionesbajos 
            # solo se envía al analizador con yo-tengo-guionesbajos.
            with cd(os.path.join("configs", "guionesbajos")):
                confirmar("yo_tengo_guionesbajos")

        def carga_hng_explicitos_en_el_archivos_de_config_del_proyecto (self):
            # Re: #234
            with cd(os.path.join("configs", "yaml")):
                confirmar("-c explicito miartefacto")

        class acte:     # Archivo de config en tiempoe jecucion
            def se_puede_configurar_a_traves_de_opciones_cli(self):
                with cd("configs"):
                    confirmar("-c acte -f yaml/dued.yaml miartefacto")

            def se_puede_configurar_via_vEnt(self, restablecer_entorno):
                os.environ["DUED_ACTE"] = "yaml/dued.yaml"
                with cd("configs"):
                    confirmar("-c acte miartefacto")

            def opcion_cli_gana_sobre_vEnt(self, restablecer_entorno):
                # Configure la variable de entorno para cargar la configuración
                # JSON en lugar de la YAML, que contiene una cadena "json" 
                # internamente.
                os.environ["DUED_ACTE"] = "json/dued.json"
                with cd("configs"):
                    # But correr the default prueba artefacto, which expects a "yaml"
                    # string. If the entorno var won, this would explode.
                    # Pero ejecute la prueba por defecto artefacto, que 
                    # espera una cadena "yaml". Si ganaba la ver  entorno,
                    # esto explotaría.
                    confirmar("-c acte -f yaml/dued.yaml miartefacto")

        def dedup_de_artefactos_honra_la_configuracion(self):
            # Un poco-corta duplica algunas pruebas en ejecutor.py, pero eh.
            with cd("configs"):
                # Tiempoej conf file : ACTE
                confirmar(
                    "-c integracion -f no-dedupe.yaml biz",
                    salida="""
foo
foo
bar
biz
post1
post2
post2
""".lstrip(),
                )
                # Marcas de bandera en acte
                confirmar(
                    "-c integracion -f dedupe.yaml --no-dedupe biz",
                    salida="""
foo
foo
bar
biz
post1
post2
post2
""".lstrip(),
                )

        # * depurar (top level?)
        # * ocultar (correr.ocultar...jeje)
        # * pty (correr.pty)
        # * alarma (correr.alarma)

        def las_vEnt_cargan_con_el_prefijo(self, monkeypatch):
            monkeypatch.setenv("DUED_CORRER_ECHO", "1")
            confirmar("-c contextualizado checar-echo")

        def prefijo_en_vEnt_puede_ser_invalidado(self, monkeypatch):
            monkeypatch.setenv("MIAPP_CORRE_OCULTO", "ambos")
            # Esto obliga a la ejecución, incluido Ejecutor, a correr
            # NOTE: no es realmente posible reelaborar el impl, por lo que 
            # esta prueba es más limpia: los artefactos requieren la config
            # por-artefacto/por-coleccion, que solo se puede realizar en el
            # momento en que se va a ejecutar un artefacto determinado. A 
            # menos que revisemos la relación Programa/Ejecutor para que 
            # Programa haga más del trabajo pesado re: artefacto 
            # buscar/cargar/etc ... 
            # NOTE: checar-ocultar hará kaboom si el correr.ocultar de su 
            # contexto no está establecido en True (por defecto False).
            class MiConf(Config):
                entorno_prefijo = "MIAPP"

            p = Programa(clase_config=MiConf)
            p.correr("du -c contextualizado checar-ocultar")

    class otro_comportamiento:
        @patch("dued.programa.getpass.getpass")
        def prompt_sudo_por_delante(self, pedirpass):
            pedirpass.valor_de_retorno = "mipassword"
            # Artefacto bajo prueba hace expectativas re: sudo config (en
            # realidad ni siquiera sudo, el uso de config de sudo se prueba
            # en Config pruebas)
            with ruta_de_soporte():
                try:
                    Programa().correr(
                        "du --prompt-sudo -c prompt_sudo confirmar-config"  # noqa
                    )
                except SystemExit as e:
                    # Si la llamada interna falló, ya habremos visto su 
                    # salida, y esto solo asegurará que nosotros mismos 
                    # estemos marcados como fallidos
                    assert e.code == 0
            # Chequeo de coherencia que pedirpass escupió promot de salida deseada
            prompt = "Valor de configuración deseado de 'sudo.password': "
            pedirpass.asercion_llamado_una_vez_con(prompt)
