import os

from dued import Coleccion, artefacto
from dued.util import LOG_FORMAT

from invocations import travis, checks
#from invocations.docs import docs, www, sites, watch_docs
from invocations.pytest import coverage as coverage_, test as prueba_
from invocations.packaging import vendorize, release


@artefacto
def prueba(
    c,
    verbose=False,
    color=True,
    capture="no",
    modulo=None,
    k=None,
    x=False,
    opcs="",
    pty=True,
):
    """
    Corredor pytest. Ver `invocations.pytest.prueba` para más detalles.

    Este es un simple envoltorio alrededor del artefacto antes mencionado,
    que hace un par de cambios menores por defecto apropiados para este 
    conjunto de pruebas en particular, como:

    - poniendo ``captura=no`` en lugar de ``captura=sys``, como hacemos una
      gran cantidad de pruebas IO de subprocesos que incluso la captura de
      ``sys`` se estropea
    - poniendo ``verbose=False`` porque tenemos un gran número de pruebas y
      saltarse la salida verbosa por defecto es un ~20% de ahorro de tiempo).
    """
    # TODO: actualizar el conjunto de pruebas para usar 
    # c.config.correr.ing_stream = False globalmente.
    # de alguna manera.
    return prueba_(
        c,
        verbose=verbose,
        color=color,
        capture=capture,
        modulo=modulo,
        k=k,
        x=x,
        opcs=opcs,
        pty=pty,
    )


# TODO: reemplazar con invocations' una vez que el problema de "llamar al 
# verdadero probador local" sea resuelto (ver otros TODOs). Por ahora esto es
# sólo un copiar/pegar/modificar.
@artefacto(help=prueba.help)
def integracion(c, opcs=None, pty=True):
    """
    Corre la suite de pruebas de integración. Puede ser lento!
    """
    opcs = opcs or ""
    opcs += " integracion/"
    prueba(c, opcs=opcs, pty=pty)


@artefacto
def cobertura(c, report="term", opcs=""):
    """
    Correr pytest en modo de cobertura. Ver "invocations.pytest.coverage"
    para más detalles.
    """
    # Usar nuestra propia prueba() en lugar de la de ellos.
    # TODO: permitir a covertura() buscar la prueba() del espacio cercano al
    # nombre en lugar de codificar su propia prueba o hacerlo de esta manera
    # con un arg.
    return coverage_(c, report=report, opcs=opcs, tester=prueba)


@artefacto
def regresion(c, jobs=8):
    """
    Ejecute un comprobador de regresión con correr() costoso y 
    difícil-de-probar-en-pytest.

    :param int jobs:
         Número de trabajos a correr, en total. Idealmente, número de CPUs.

    """
    os.chdir("integracion/_soporte")
    cmd = "seq {} | parallel -n0 --halt=now,fail=1 du -c regresion chequeo"
    c.correr(cmd.format(jobs))

# hng = Espacio de nombres
hng = Coleccion(
    prueba,
    cobertura,
    integracion,
    regresion,
    vendorize,
    release,
#    www,
#    docs,
#    sites,
#    watch_docs,
    travis,
    checks.blacken,
)
hng.configurar(
    {
        "blacken": {
            # Sáltate el directorio de vendor y la venv alternativa 
            # (sólo para Travis) cuando te blackeneas.
            # TODO: esto hace que parezca que realmente quiero un explícito 
            # arg/conf-opt en el blacken artefacto para "rutas excluidos"...ha
            "find_opts": "-and -not \( -ruta './dued/vendor*' -or -ruta './alt_env*' -or -ruta './fabricar*' \)"  # noqa
        },
        "pruebas": {"logformat": LOG_FORMAT, "paquete": "dued"},
        "travis": {
            "sudo": {"usuario": "sudouser", "password": "mipass"},
            "black": {"version": "18.6b4"},
        },
        "packaging": {
            "sign": True,
            "wheel": True,
            "checar_desc": True,
            # Because of PyYAML's dual source nonsense =/
            "dual_wheels": True,
            "changelog_file": os.path.join(
                www.configuracion()["sphinx"]["source"], "changelog.rst"
            ),
        },
    }
)
