"""
==============================================================================
BusDrex - MÓDULO: RESERVAS (apps/reservas/signals.py)
Receptores de Señales para Respaldo de Control de Stock en 3FN
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
"""

import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Venta, Boleto
from transporte.models import Asiento

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Venta)
def capturar_estado_previo_venta(sender, instance, **kwargs):
    """
    Señal pre_save para capturar el estado anterior de la venta antes de su guardado,
    permitiendo detectar si existió un cambio efectivo hacia 'CANCELADO'.
    """
    if instance.id:
        try:
            instance._estado_previo = Venta.objects.get(id=instance.id).estado
        except Venta.DoesNotExist:
            instance._estado_previo = None
    else:
        instance._estado_previo = None


@receiver(post_save, sender=Venta)
def gestionar_cancelacion_y_liberacion_asientos(sender, instance, created, **kwargs):
    """
    Señal post_save como salvaguarda secundaria.
    Si la venta pasa a CANCELADO y NO fue procesada por la capa de servicios,
    libera los asientos antes del zarpe y anula los boletos en 3FN.
    """
    if getattr(instance, '_cancelacion_procesada_por_servicio', False):
        return

    if instance.estado == Venta.ESTADO_CANCELADO:
        estado_previo = getattr(instance, '_estado_previo', None)

        # Solo reponer si venía de PAGADO (en PENDIENTE nunca se descontó stock)
        if estado_previo == Venta.ESTADO_PAGADO:
            ahora = timezone.now()
            detalles = instance.detalles.select_related('asiento__servicio', 'boleto').all()

            for detalle in detalles:
                asiento = detalle.asiento
                servicio = asiento.servicio

                # Solo liberar si es ANTES de la salida programada del bus
                if servicio.fecha_hora_salida > ahora:
                    if asiento.estado != Asiento.ESTADO_DISPONIBLE:
                        asiento.estado = Asiento.ESTADO_DISPONIBLE
                        asiento.save(update_fields=['estado'])
                        logger.info(
                            f"[SEÑAL STOCK LIBERADO] Asiento #{asiento.numero_asiento} devuelto a DISPONIBLE."
                        )

                # Anular boleto si existe
                if hasattr(detalle, 'boleto'):
                    boleto = detalle.boleto
                    if boleto.estado != Boleto.ESTADO_ANULADO:
                        boleto.estado = Boleto.ESTADO_ANULADO
                        boleto.save(update_fields=['estado'])
