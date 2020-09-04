from dued import artefacto


@artefacto
def confirmar_config(c):
    password = c.config.sudo.password
    assert password == "mipassword", "Tiene {!r}".format(password)
