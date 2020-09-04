import os
from os import name
import sys
import imp
from sys import path

from . import Config
from .excepciones import ColeccionNoEcontrada
from .util import debug


class Cargador(object):
    """
    Clase abstracta que define cómo buscar/importar una `.Coleccion` basada
    en sesión(es).

    .. versionadded:: 1.0
    """

    def __init__(self, config=None):
        """
        Configure un nuevo cargador con alguna configuración `.Config`.

        :param config:
            Una `.Config` explícita para usar; se hace referencia a esta para
            las opciones de configuración relacionadas con la carga.
            Por defecto es una ``Config()`` anónima si no se proporciona 
            ninguna.
        """
        if config is None:
            config = Config()
        self.config = config

    def buscar(self, nombre):
        """
        Método de busqueda específico de la implementación que busca la 
        colección ``nombre``

        Debe devolver una tupla de 4 válidos para el uso de `imp.load_module`,
        que suele ser una cadena de nombre seguida del contenido de la tupla
        de 3 devuelta por `imp.find_module` (``archivo``, ``nombre_de_ruta``,
        ``descripcion``.)

        Para ver una implementación de muestra, consulte 
        `.CargaDesdeElSitemaDeArchivos`.

        .. versionadded:: 1.0
        """
        raise NotImplementedError

    def cargar(self, nombre=None):
        """
        Carga y devuelve el módulo de colección identificado por ``nombre``.

        Este método requiere una implementación funcional de `.buscar` para
        funcionar.

        Además de importar el módulo nombrado, agregará el directorio 
        principal del módulo al frente de `sys.path` para proporcionar un
        comportamiento de importación normal de Python (es decir, para que
        el módulo cargado pueda cargar módulos o paquetes locales)

        :returns:
            Dos tuplas de ``(módulo, directorio)``' donde ``módulo`` es el 
            objeto de módulo de Python que contiene la coleccion, y 
            ``directorio`` es una cadena de la ruta al directorio en el que 
            se encontró el módulo.

        .. versionadded:: 1.0
        """
        if nombre is None:
            nombre = self.config.artefactos.nombre_de_coleccion
        # Busca el módulo de artefactos nombrado, según la implementación.
        # Generará una excepción si no se encuentra.
        fd, ruta, desc = self.buscar(nombre)
        try:
            # Asegúrese de que el directorio contenedor esté en sys.path en
            # caso de que el módulo que se está importando esté intentando 
            # cargar-nombres-locales.
            padre = os.path.dirname(ruta)
            if padre not in sys.path:
                sys.path.insert(0, padre)
            # Importación actual
            module = imp.load_module(nombre, fd, ruta, desc)
            # Retorna module + path.
            # TODO: ¿hay alguna razón por la que los clientes no se refieren 
            # simplemente a os.path.dirname(module .__ file__)?
            return module, padre
        finally:
            # Asegúrese de limpiar el objeto de archivo abierto devuelto por 
            # buscar(), si había uno (por ejemplo, paquetes encontrados, 
            # vs módulos, no abra ningún archivo).
            if fd:
                fd.close()


class CargaDesdeElSitemaDeArchivos(Cargador):
    """
    Carga archivos Python desde el sistema de archivos 
    (por ejemplo, ``artefactos.py``.)
    
    Busca de forma recursiva hacia la raíz del sistema de archivos desde
    un punto de inicio determinado.

    .. versionadded:: 1.0
    """

    # TODO: podría introducir config obj aquí para su transmisión a Coleccion
    # TODO: de lo contrario, Cargador tiene que saber sobre bits específicos para
    # transmitir, como guiones-automáticos, y tiene que hacer crecer uno de esos
    # por cada bit que Coleccion necesita saber
    def __init__(self, inicio=None, **kwargs):
        super(CargaDesdeElSitemaDeArchivos, self).__init__(**kwargs)
        if inicio is None:
            inicio = self.config.artefactos.dir_raiz
        self._start = inicio

    @property
    def iniciar(self):
        # Determine perezosamente la CWD predeterminada si el valor configurado es falso
        return self._start or os.getcwd()

    def buscar(self, nombre):
        # Acumule todos los directorios principales
        iniciar = self.iniciar
        debug("CargaDesdeElSitemaDeArchivos busca iniciando en {!r}".format(iniciar))
        padres = [os.path.abspath(iniciar)]
        padres.append(os.path.dirname(padres[-1]))
        while padres[-1] != padres[-2]:
            padres.append(os.path.dirname(padres[-1]))
        # Asegúrese de que no tengamos duplicados al final       
        if padres[-1] == padres[-2]:
            padres = padres[:-1]
        # Use find_module con nuestra lista de padres. ImportError de find_module 
        # significa "no se pudo encontrar" no "se encontró y no se pudo importar",
        # por lo que lo convertimos en una clase de excepción más obvia.
        try:
            tup = imp.find_module(nombre, padres)
            debug("Modulo encontrado: {!r}".format(tup[1]))
            return tup
        except ImportError:
            msj = "ImportError cargando {!r}, levantando ColeccionNoEcontrada"
            debug(msj.format(nombre))
            raise ColeccionNoEcontrada(nombre=nombre, inicio=iniciar)
