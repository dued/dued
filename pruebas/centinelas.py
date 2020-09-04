from threading import Thread, Event

from dued.vendor.six.moves.queue import Queue, Empty

from dued import Respondedor, DetectorDeRespuestasIncorrectas, RespuestaNoAceptada

# NOTE: StreamCentinela es básicamente una interfaz/protocolo; ningún 
# comportamiento a prueba propio. Así que este archivo prueba principalmente
# a Respondedor, y algunas subclases.


class Respondedor_:
    def realiza_un_seguimiento_del_indice_visto_por_hilo(self):
        # Crea una instancia de un solo objeto que se usará en >1 hilo
        r = Respondedor(patron="foo", respuesta="pelea bar")  # bah
        # Thread cuerpo func que nos permite imitar el comportamiento real 
        # del hilo IO, con colas utilizadas en lugar de tuberías/archivos reales
        def cuerpo(respondedor, in_q, out_q, finished):
            while not finished.is_set():
                try:
                    # NOTE: use nowait() para que nuestro bucle esté activo y 
                    # pueda apagarse lo antes posible si se configura el final.
                    stream = in_q.get_nowait()
                    for respuesta in r.envio(stream):
                        out_q.put_nowait(respuesta)
                except Empty:
                    pass

        # Crea dos hilos de esa función de cuerpo, y colas / etc para cada uno
        t1_in, t1_out, t1_finished = Queue(), Queue(), Event()
        t2_in, t2_out, t2_finished = Queue(), Queue(), Event()
        t1 = Thread(objetivo=cuerpo, args=(r, t1_in, t1_out, t1_finished))
        t2 = Thread(objetivo=cuerpo, args=(r, t2_in, t2_out, t2_finished))
        # Iniciar los hilos
        t1.iniciar()
        t2.iniciar()
        try:
            stream = "peleadores foo"
            # El primer hilo básicamente siempre funcionará

            t1_in.put(stream)
            assert t1_out.get() == "pelea bar"
            # El segundo hilo get() bloqueará/tiempofuera si los threadlocals
            # no están en uso, porque la copia del segundo hilo del 
            # respondedor no tendrá su propio índice y por lo tanto ya estará
            # 'pasado' el 'foo' en el stream.
            t2_in.put(stream)
            assert t2_out.get(tiempofuera=1) == "pelea bar"
        except Empty:
            assert (
                False
            ), "Incapaz de leer desde el hilo 2 - implica que los índices threadlocal están rotos!"  # noqa
        # Close up.
        finally:
            t1_finished.set()
            t2_finished.set()
            t1.join()
            t2.join()

    def produce_respuesta_cuando_se_ve_un_patrón_de_cadena_regular(self):
        r = Respondedor(patron="vacio", respuesta="entregado")
        assert list(r.envio("la casa estaba vacía")) == ["entregado"]

    def produce_respuesta_cuando_se_ve_la_expresion_regular(self):
        r = Respondedor(patron=r"téc.*deuda", respuesta="pagarlo")
        respuesta = r.envio("técnicamente, sigue siendo deuda")
        assert list(respuesta) == ["pagarlo"]

    def multiples_visitas_dentro_del_stream_producen_multiples_respuestas(self):
        r = Respondedor(patron="saltar", respuesta="Que tan alto?")
        assert list(r.envio("saltar, esperar, saltar, esperar")) == ["Que tan alto?"] * 2

    def patrones_abarcan_varias_lineas(self):
        r = Respondedor(patron=r"llamas.*problema", respuesta="Lo siento mucho")
        salida = """
Solo me llamas
cuando tienes un problema
Nunca me llamas
Solo para saludar
"""
        assert list(r.envio(salida)) == ["Lo siento mucho"]


class RespondedorFallando_:
    def se_comporta_como_respondedor_regular_por_defecto(self):
        r = DetectorDeRespuestasIncorrectas(
            patron="sal[^ ]{2}", respuesta="qué tan alto?", centinela="jajaja no"
        )
        assert list(r.envio("saltar, esperar, saltar, esperar")) == ["qué tan alto?"] * 2

    def genera_excepcion_de_falla_cuando_se_detecta_centinela(self):
        r = DetectorDeRespuestasIncorrectas(
            patron="sal[^ ]{2}", respuesta="qué tan alto?", centinela="jajaja no"
        )
        # Se comporta normalmente al principio
        assert list(r.envio("saltar")) == ["qué tan alto?"]
        # ¡Pero entonces!
        try:
            r.envio("jajaja no")
        except RespuestaNoAceptada as e:
            mensaje = str(e)
            # Espere bits útiles en el texto de excepción
            err = "No vi patrón en {!r}".format(mensaje)
            assert "sal[^ ]{2}" in mensaje, err
            err = "No vi la falla centinela en {!r}".format(mensaje)
            assert "jajaja no" in mensaje, err
        else:
            assert False, "No subió RespuestaNoAceptada!"
