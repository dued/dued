"""
Clase de carga de la variable de configuración de entorno.

El uso de una clase aquí realmente no modela nada, pero hace que el paso de
estado (en una situación que lo requiera) sea más conveniente.

Este módulo actualmente se considera privado/un detalle de implementación y
no debe incluirse en la documentación de la API de Sphinx.
"""

import os

from .util import six

from .excepciones import VarEntInestable, VarEntAmbigua
from .util import debug


class Entorno(object):
    def __init__(self, config, prefijo):
        self._config = config
        self._prefijo = prefijo
        self.datos = {}  # Accumulator

    def cargar(self):
        """
        Devuelve un diccionario anidado que contiene valores de "os.environ".

        Específicamente, valores cuyas claves se asignan a ajustes de 
        configuración ya conocidos, lo que nos permite realizar un encasillado
        básico.

        Ver: ref: `entorno-vars` para más detalles.
        """
        # Obtener entorno var permitido -> mapa de valor existente
        vars_ent = self._gatear(ruta_clave=[], vars_ent={})
        m = "Escaneo para entorno vars según prefijo: {!r}, mapeando: {!r}"
        debug(m.format(self._prefijo, vars_ent))
        # Verifique el entorno var actual (honrando el prefijo) e intente configurar
        for env_var, ruta_clave in six.iteritems(vars_ent):
            real_var = (self._prefijo or "") + env_var
            if real_var in os.environ:
                self._setear_ruta(ruta_clave, os.environ[real_var])
        debug("Se obtuvo la configuración de entorno var: {!r}".format(self.datos))
        return self.datos

    def _gatear(self, ruta_clave, vars_ent):
        """
        Examina la configuración en la ubicación ``ruta_clave`` y devuelva las
        posibles variables de entorno.

        Utiliza el dicc ``vars_ent`` para determinar si existe un conflicto y,
        de ser así, genera una excepción. Este dicc tiene la siguiente forma::

            {
                'VAR_ENT_ESPERADA_AQUI': ['actual', 'anidado', 'ruta_clave'],
                ...
            }

        Devuelve otro diccionario de nuevos pares-de-claves como se indicó 
        anteriormente.
        """
        vars_nuevas = {}
        obj = self._obtener_ruta(ruta_clave)
        # Subdict -> recurse
        if (
            hasattr(obj, "claves")
            and callable(obj.claves)
            and hasattr(obj, "__getitem__")
        ):
            for clave in obj.claves():
                merged_vars = dict(vars_ent, **vars_nuevas)
                merged_path = ruta_clave + [clave]
                gateo = self._gatear(merged_path, merged_vars)
                # Manejador de conflictos
                for clave in gateo:
                    if clave in vars_nuevas:
                        err = "Encontrado> 1 fuente para {}"
                        raise VarEntAmbigua(err.format(clave))
                # Fusionar y continuar
                vars_nuevas.update(gateo)
        # Otro -> es hoja, no recursiva
        else:
            vars_nuevas[self._a_var_ent(ruta_clave)] = ruta_clave
        return vars_nuevas

    def _a_var_ent(self, ruta_clave):
        return "_".join(ruta_clave).upper()

    def _obtener_ruta(self, ruta_clave):
        # Los _obtener son dedesde self._config porque eso es lo que determina las 
        # variables de entorno válidas y/o valores para encasillamiento.
        obj = self._config
        for clave in ruta_clave:
            obj = obj[clave]
        return obj

    def _setear_ruta(self, ruta_clave, valor):
        # Los sets son para self.datos ya que eso es lo que estamos presentando
        # al objeto de configuración externo y depurando.
        obj = self.datos
        for clave in ruta_clave[:-1]:
            if clave not in obj:
                obj[clave] = {}
            obj = obj[clave]
        viejo = self._obtener_ruta(ruta_clave)
        nuevo_ = self._emitir(viejo, valor)
        obj[ruta_clave[-1]] = nuevo_

    def _emitir(self, viejo, nuevo_):
        if isinstance(viejo, bool):
            return nuevo_ not in ("0", "")
        elif isinstance(viejo, six.string_types):
            return nuevo_
        elif viejo is None:
            return nuevo_
        elif isinstance(viejo, (list, tuple)):
            err = "No se puede adaptar una cadena de entorno a una {}!"
            err = err.format(type(viejo))
            raise VarEntInestable(err)
        else:
            return viejo.__class__(nuevo_)
