from dued import artefacto


@artefacto
def miartefacto(c):
    assert c.exterior.interior.hurra == "yaml"
