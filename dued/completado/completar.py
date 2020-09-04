"""
Mecanismo CLI de completado, ejecutado por el nucleo con la bandera
``--completar``.
"""

import glob
import os
import re
import shlex

from ..excepciones import Salida, ErrorDeAnalisis
from ..analizador import Analizador
from ..util import debug, clave_orden_del_nombre_de_artefacto


def completar(nombres, nucleo, contexto_inicial, coleccion):
    # Eliminar el nombre del programa (los scripts nos dan la línea de comando completa)
    # TODO: ¿esto no puede manejar la ruta/al/script?
    invocacion = re.sub(r"^({}) ".format("|".join(nombres)), "", nucleo.remanente)
    debug("Completando para invocacion: {!r}".format(invocacion))
    # Tokeniza (shlex tendrá que hacer)
    tokens = shlex.split(invocacion)
    # Hacemos un analizador (analizador) -no podemos reusar el original
    # ya que está mutado ha sido sobrescrito-
    analizador = Analizador(inicial=contexto_inicial, contextos=coleccion.a_contextos())
    # Manejo de banderas (parcial o de lo contrario)
    if tokens and tokens[-1].startswith("-"):
        cola = tokens[-1]
        debug("La cola de la invocacion'es {!r} es bandera-similar".format(cola))
        # Parsear (analizar) suavemente invocación para obtener el contexto
        # 'actual'. Use el contexto visto por última vez en caso
        # de falla (se requiere para invocaciones parciales
        # que de lo contrario no serían válidas).
        try:
            debug("Buscando nombre de contexto en tokens: {!r}".format(tokens))
            contextos = analizador.analizar_args(tokens)
        except ErrorDeAnalisis as e:
            msj = (
                "Tengo error del analizador ({!r}), grabando su contexto ultima-vista {!r}"
            )  # noqa
            debug(msj.format(e, e.contexto))
            contextos = [e.contexto]
        # Vuelva al contexto nucleo si no se ve ningún contexto.
        debug("Analiza invocacion, en contextos: {!r}".format(contextos))
        if not contextos or not contextos[-1]:
            contexto = contexto_inicial
        else:
            contexto = contextos[-1]
        debug("Seleccionado contexto: {!r}".format(contexto))
        # Banderas desconocidas (podría ser, p.ej, solo tipado parcialmente;
        # podría ser completamente inválido; no importa) completo con banderas.
        debug("Buscando {!r} en {!r}".format(cola, contexto.banderas))
        if cola not in contexto.banderas:
            debug("No encontrado, completando con nombres de banderas")
            # Banderas Largas - parcial o solo guiones - completar c/ banderas largas
            if cola.startswith("--"):
                for nombre in filter(
                    lambda x: x.startswith("--"), contexto.nombres_de_banderas()
                ):
                    print(nombre)
            # Simplemente un guión, completes con todas las banderas
            elif cola == "-":
                for nombre in contexto.nombres_de_banderas():
                    print(nombre)
            # De lo contrario, es algo completamente inválido (una bandera corta
            # no reconocida o una bandera de estilo java como -foo), así no retorne
            # nada (el shell aún intentará completarse con archivos, pero eso no
            # perjudica realmente).
            else:
                pass
        # Las banderas conocidas se completan sin nada o artefactos, dependiendo
        else:
            # Banderas que esperan valores: no hacer nada, para permitir que se complete
            # el shell predeterminado (generalmente el archivo) (que queremos
            # activar en este caso).
            if contexto.banderas[cola].toma_valor:
                debug("Encontrado, y toma un valor, así que no hay completado")
                pass
            #No tomar valores (por ejemplo, bools): imprimir nombres de tareas
            else:
                debug("Encontrado, no tiene valor, imprime nombres de artefactos")
                imprimir_nombres_de_artefactos(coleccion)
    # Si no es una bandera, es el nombre de un artefacto o un valor de bandera, por
    # lo tanto, completar con los nombres de los artefactos.
    else:
        debug("El último token no tiene bandera-similar, solo imprime el nombre del artefacto")
        imprimir_nombres_de_artefactos(coleccion)
    raise Salida


def imprimir_nombres_de_artefactos(coleccion):
    for nombre in sorted(coleccion.nombres_de_artefactos, key=clave_orden_del_nombre_de_artefacto):
        print(nombre)
        # Solo pega el alias después de la cosa a la que están alias-relacionados.
        # Ordenar no es tan importante que valvalgae la pena ir hacia atrás aquí.
        for alias in coleccion.nombres_de_artefactos[nombre]:
            print(alias)


def imprimir_script_de_completado(shell, nombres):
    # Tome todos los archivos .completado en dued/finalización/. (Estos solían
    # no tener sufijo, pero sorpresa, eso es súper frágil.
    completions = {
        os.path.splitext(os.path.basename(x))[0]: x
        for x in glob.glob(
            os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "*.completion"
            )
        )
    }
    try:
        ruta = completions[shell]
    except KeyError:
        err = 'Completado parashell "{}" no admitido (las opciones son: {}).'
        raise ErrorDeAnalisis(err.format(shell, ", ".join(sorted(completions))))
    debug("Imprimir guión de finalización desde {}".format(ruta))
    # Elija un nombre de programa arbitrario para la propia invocación interna
    # del script (también se usa para construir nombres de funciones de 
    # completado cuando sea necesario)
    binario = nombres[0]
    with open(ruta, "r") as script:
        print(
            script.read().format(binario=binario, spaced_names=" ".join(nombres))
        )
