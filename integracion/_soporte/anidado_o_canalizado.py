from dued import artefacto


@artefacto
def calls_foo(c):
    c.correr("du -c anidado_o_canalizado foo")


@artefacto
def foo(c):
    c.correr("echo bah")
