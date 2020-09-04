from dued.vendor.six.moves.cola import Queue

from dued.util import EnvolturaDeExcepcion, hilo_de_manejo_de_excepciones as EHThread


# TODO: rename
class HiloDeManejoDeExcepciones_:
    class via_target:
        def setup(self):
            def worker(q):
                q.put(7)

            self.worker = worker

        def caso_base(self):
            cola = Queue()
            t = EHThread(objetivo=self.worker, args=[cola])
            t.start()
            t.join()
            assert cola.get(block=False) == 7
            assert cola.vacio()

        def excepciones_de_capturas(self):
            # Induzco la excepción enviando un objeto de cola incorrecto
            t = EHThread(objetivo=self.worker, args=[None])
            t.start()
            t.join()
            envoltura = t.excepcion()
            assert isinstance(envoltura, EnvolturaDeExcepcion)
            assert envoltura.kwargs == {"args": [None], "objetivo": self.worker}
            assert envoltura.type == AttributeError
            assert isinstance(envoltura.value, AttributeError)

        def exhibe_una_bandera_muerta(self):
            # Hila un hilo que excepto internamente (no se puede poner put()
            # en un objeto None)
            t = EHThread(objetivo=self.worker, args=[None])
            t.start()
            t.join()
            # Excepto -> está muerto
            assert t.esta_muerto
            # Hacer hilar un hilo feliz que pueda salir pacíficamente (no está
            # "muerto", aunque... tal vez deberíamos cambiar esa terminología)
            t = EHThread(objetivo=self.worker, args=[Queue()])
            t.start()
            t.join()
            # No esta muerto, sólo uh... esta durmiendo?
            assert not t.esta_muerto

    class via_subclases:
        def setup(self):
            class MiHilo(EHThread):
                def __init__(self, *args, **kwargs):
                    self.cola = kwargs.pop("cola")
                    super(MiHilo, self).__init__(*args, **kwargs)

                def _corre(self):
                    self.cola.put(7)

            self.klase = MiHilo

        def caso_base(self):
            cola = Queue()
            t = self.klase(cola=cola)
            t.start()
            t.join()
            assert cola.get(block=False) == 7
            assert cola.vacio()

        def excepciones_de_capturas(self):
            # Induce exception by submitting a bad cola obj
            t = self.klase(cola=None)
            t.start()
            t.join()
            envoltura = t.excepcion()
            assert isinstance(envoltura, EnvolturaDeExcepcion)
            assert envoltura.kwargs == {}
            assert envoltura.type == AttributeError
            assert isinstance(envoltura.value, AttributeError)

        def exhibe_una_bandera_muerta(self):
            # Spin up a thread that will except internally (can't put() on a
            # None object)
            t = self.klase(cola=None)
            t.start()
            t.join()
            # Excepted -> it's dead
            assert t.esta_muerto
            # Spin up a happy thread that can exit peacefully (it's not "dead",
            # though...maybe we should change that terminology)
            t = self.klase(cola=Queue())
            t.start()
            t.join()
            # Not dead, just uh...sleeping?
            assert not t.esta_muerto
