from dued import artefacto, Coleccion


@artefacto
def miartefacto(c):
    assert c.exterior.interior.hurra == "yaml"


hng = Coleccion(miartefacto)
