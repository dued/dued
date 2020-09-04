from dued import artefacto


@artefacto
def go(c):
    return c


@artefacto
def checar_alerta(c):
    # por defecto: False
    assert c.config.correr.alarma is True


@artefacto
def checar_pty(c):
    # por defecto: False
    assert c.config.correr.pty is True


@artefacto
def checar_oculto(c):
    # por defecto: None
    assert c.config.correr.ocultar == "ambos"


@artefacto
def checar_echo(c):
    # por defecto: False
    assert c.config.correr.echo is True
