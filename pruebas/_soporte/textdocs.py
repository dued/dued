from dued import artefacto


@artefacto
def no_textdocs(c):
    pass


@artefacto
def linea_uno(c):
    """foo
    """


@artefacto
def linea_dos(c):
    """foo
    bar
    """


@artefacto
def espacio_en_blanco_inicial(c):
    """
    foo
    """


@artefacto(alias=("a", "b"))
def con_alias(c):
    """foo
    """
