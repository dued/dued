import os
import sys

from dued import Programa

import pytest

from _util import confirmar, trap, RAIZ


marcapytest = pytest.mark.usefixtures("integracion")


@trap
def _completar(invocacion, coleccion=None, **kwargs):
    cadenacol = ""
    if coleccion:
        cadenacol = "-c {}".format(coleccion)
    comando = "du --completar {0} -- du {0} {1}".format(cadenacol, invocacion)
    Programa(**kwargs).correr(comando, salir=False)
    return sys.stdout.getvalue()


# TODO: eliminar a favor de afirmaciones directas, necesita una forma sencilla
# de llegar a stderr en lugar de solo stdout.
def _assert_contiene(pajar, aguja):
    assert aguja in pajar


class ImpresionDeScriptsDeCompletado:
    """
    Imprimiendo el script de completado
    """

    def setup(self):
        self.cwd_previo = os.getcwd()
        # Chdir a la raíz del sistema para (con suerte) evitar cualquier
        # artefactos.py. Esto probará que --script-completado funciona sin
        # artefactos cercanos.
        os.chdir(RAIZ)

    def desmontaje(self):
        os.chdir(self.cwd_previo)

    def solo_acepta_ciertos_shells(self):
        confirmar(
            "--script-completado",
            err="necesitaba valor y no se le dio ninguno",
            prueba=_assert_contiene,
        )
        confirmar(
            "--script-completado bla",
            # NOTE: esto necesita ser actualizado cuando el mundo real cambie,
            # como por ejemplo nuestras --help salida de prueba. Eso está bien
            # y es mejor que sólo reimplementar el código bajo prueba aquí.
            err='No se apoya el completado de la shell "bla". (las opciones son: bash, fish, zsh).',  # noqa
            prueba=_assert_contiene,
        )

    def impresiones_para_nombres_personalizados_binarios(self):
        salida, err = confirmar(
            "miapp --script-completado zsh",
            programa=Programa(nombres_binarios=["mia", "miapp"]),
            dued=False,
        )
        # Combina algunos centinelas de la prueba de vainilla, con 
        # comprobaciones de que realmente está reemplazando 'dued'
        # con los nombres binarios deseados
        assert "_completar_mia() {" in salida
        assert "dued" not in salida
        assert " mia miapp" in salida

    def nombres_pordefault_binarios_estan_completando_argv_0(self):
        salida, err = confirmar(
            "algunnombredeapp --script-completado zsh",
            programa=Programa(nombres_binarios=None),
            dued=False,
        )
        assert "_completar_aulgunnombredeapp() {" in salida
        assert " algunnombredeapp" in salida

    def trabaja_con_bash(self):
        salida, err = confirmar(
            "algunnombredeapp --script-completado bash", dued=False
        )
        assert "_completar_aulgunnombredeapp() {" in salida
        assert "completar -F" in salida
        for line in salida.splitlines():
            if line.startswith("completar -F"):
                assert line.endswith(" algunnombredeapp")

    def trabaja_con_fish(self):
        salida, err = confirmar(
            "algunnombredeapp --script-completado fish", dued=False
        )
        assert "function __completar_aulgunnombredeapp" in salida
        assert "completar --comando algunnombredeapp" in salida


class ShellCompletado:
    """
    Comportamiento de Shell tab-completado
    """

    def sin_entrada_significa_solo_nombres_de_artefactos(self):
        confirmar("-c lista_simple_hng --completar", salida="z-altonivel\na.b.subartefacto\n")

    def completa_el_nombre_binario_personalizado(self):
        confirmar(
            "miapp -c integracion --completar -- ba",
            programa=Programa(binario="miapp"),
            dued=False,
            salida="bar",
            prueba=_assert_contiene,
        )

    def completa_el_nombre_binario_personalizado_con_alias(self):
        for used_binary in ("mi", "miapp"):
            confirmar(
                "{0} -c integracion --completar -- ba".format(used_binary),
                programa=Programa(binario="mi[app]"),
                dued=False,
                salida="bar",
                prueba=_assert_contiene,
            )

    def sin_entrada_sin_artefactos_produce_una_respuesta_vacía(self):
        confirmar("-c vacio --completar", salida="")

    def completado_del_nombre_de_artefactos_incluye_alias(self):
        for nombre in ("z\n", "altonivel"):
            assert nombre in _completar("", "alias_ordenado")

    def nivel_superior_con_guion_significa_opciones_principales(self):
        salida = _completar("-")
        # No tiene sentido reflejar todas las opciones nucleo (principales),
        # solo verifique algunas
        for bandera in ("--no-dedupe", "-d", "--depurar", "-V", "--version"):
            assert "{}\n".format(bandera) in salida

    def guiondoble_desnudo_muestra_solo_opciones_de_nucleo_largo(self):
        salida = _completar("--")
        assert "--no-dedupe" in salida
        assert "-V" not in salida

    def nombres_de_artefactos_solo_completan_otros_nombres_de_artefactos(self):
        # Porque solo los tokens que comienzan con un guión deberían aparecer
        # en las opciones.
        assert "imprimir-nombre" in _completar("imprimir-foo", "integracion")

    def completado_del_nombre_de_artefactos_incluye_artefactos_ya_vistos(self):
        # Porque es válido llamar al mismo artefacto >1 vez.
        assert "imprimir-foo" in _completar("imprimir-foo", "integracion")

    def per_task_banderas_complete_with_single_dashes(self):
        for bandera in ("--nombre", "-n"):
            assert bandera in _completar("imprimir-nombre -", "integracion")

    def por_banderas_de_artefacto_completado_con_guiones_dobles(self):
        salida = _completar("imprimir-nombre --", "integracion")
        assert "--nombre" in salida
        assert "-n\n" not in salida  # newline because -n is in --nombre

    def completado_de_bandera_incluye_booleanos_inversos(self):
        salida = _completar("bool-basico -", "foo")
        assert "--no-mibool" in salida

    def artefactos_con_args_posicionales_completado_con_banderas(self):
        # Porque, de lo contrario, completarlos no es válido de todos modos.
        # NOTE: esto actualmente duplica otra prueba porque esta prueba se
        # preocupa por un detalle específico.
        salida = _completar("imprimir-nombre --", "integracion")
        assert "--nombre" in salida

    def banderas_core_que_toman_valores_no_tienen_salida_de_completado(self):
        # Entonces, el completado predeterminado del shell está disponible.
        assert _completar("-f") == ""

    def banderas_por_artefacto_que_toman_valores_no_tienen_salida_de_completado(self):
        assert _completar("arg_basico --arg", "foo") == ""

    def banderas_core_bool_tienen_completado_de_nombre_de_artefactos(self):
        assert "miartefacto" in _completar("--echo", "foo")

    def por_artefacto_las_banderas_bool_tienen_completado_el_nombre_del_artefacto(self):
        assert "miartefacto" in _completar("bool-basico --mibool", "foo")

    def banderas_core_parciales_o_no_validas_imprimir_todas_las_banderas(self):
        for bandera in ("--echo", "--completar"):
            for given in ("--e", "--nop"):
                assert bandera in _completar(given)

    def por_artefacto_banderas_parciales_o_invalidas_imprimir_todas_las_banderas(self):
        for bandera in ("--arg1", "--otroarg"):
            for given in ("--ar", "--nop"):
                completado = _completar("args_multiples {}".format(given), "foo")
                assert bandera in completado
