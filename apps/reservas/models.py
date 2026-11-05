"""
==============================================================================
BusDrex - MÓDULO: RESERVAS (apps/reservas/models.py)
Modelos de Datos para Pasajeros, Carro, Ventas, Detalles y Boletos en 3FN
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Cumplimiento 3FN según busdrex.dbml:
- Tablas: `pasajero`, `carro_pasajes`, `item_carro`, `venta`, `detalle_venta`, `boleto`.
- `pasajero`: Datos maestros de ocupantes (RUT único y normalizado, nombre_completo).
- `item_carro`: Vincula carro, asiento y pasajero vía FK. No guarda precio; se calcula
  dinámicamente desde el servicio según el tipo de asiento.
- `venta`: Registro de transacción (UUID único, total congelado, ciclo de vida estricto).
- `detalle_venta`: Historial inmutable con precio_unitario capturado al checkout.
- `boleto`: Relación 1 a 1 con DetalleVenta, UUID único, Hash SHA-256 y estado.
- `on_delete=models.PROTECT` aplicado rigurosamente en datos históricos.
==============================================================================
"""

import uuid
import hashlib
import re
from decimal import Decimal
from django.db import models
from django.conf import settings
from transporte.models import Asiento


class Pasajero(models.Model):
    """
    ==========================================================================
    ENTIDAD PASAJERO (Tabla: pasajero) - 3FN Maestro de Viajeros
    ==========================================================================
    Almacena los datos maestros de la persona que viaja en el bus.
    El nombre completo depende funcionalmente del RUT (RUT -> nombre_completo).
    Se normaliza el formato del RUT chileno (sin puntos, con guion y K mayúscula).
    ==========================================================================
    """
    rut = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="RUT / DNI del Pasajero",
        help_text="Identificación única del pasajero (normalizado: 12345678-K o pasaporte)."
    )
    nombre_completo = models.CharField(
        max_length=150,
        verbose_name="Nombre Completo del Pasajero",
        help_text="Nombre y apellidos del titular del viaje."
    )

    class Meta:
        db_table = 'pasajero'
        verbose_name = "Pasajero"
        verbose_name_plural = "Pasajeros"
        ordering = ['nombre_completo']

    def __str__(self):
        return f"{self.nombre_completo} ({self.rut})"

    @staticmethod
    def normalizar_rut(rut_str: str) -> str:
        """
        Normaliza una cadena de RUT eliminando puntos y espacios,
        asegurando guion previo al dígito verificador y K en mayúscula.
        Ejemplo: ' 12.345.678-k ' -> '12345678-K'
        """
        if not rut_str:
            return ""
        limpio = re.sub(r'[^0-9kK]', '', str(rut_str)).upper()
        if len(limpio) >= 2:
            return f"{limpio[:-1]}-{limpio[-1]}"
        return limpio


class CarroPasajes(models.Model):
    """
    ==========================================================================
    ENTIDAD CARRO DE PASAJES (Tabla: carro_pasajes) - Persistente 1 a 1
    ==========================================================================
    Carro de compras de pasajes asociado unívocamente a cada usuario (1 a 1).
    Reside en la base de datos MySQL y persiste intacto tras logout.
    ==========================================================================
    """
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='carro',
        verbose_name="Usuario Titular"
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Creación"
    )
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name="Última Actualización"
    )

    class Meta:
        db_table = 'carro_pasajes'
        verbose_name = "Carro de Pasajes"
        verbose_name_plural = "Carros de Pasajes"

    def __str__(self):
        return f"Carro de Pasajes #{self.id} (Usuario: {self.usuario.username})"

    def calcular_total(self) -> Decimal:
        """
        Calcula la sumatoria de precios de los ítems en el carro.
        Cada precio se obtiene dinámicamente según la tarifa del servicio y tipo de asiento.
        """
        total = Decimal('0.00')
        for item in self.items.select_related('asiento__servicio').all():
            total += item.precio
        return total

    def total_items(self) -> int:
        """Retorna la cantidad de pasajes incorporados en el carro."""
        return self.items.count()


class ItemCarro(models.Model):
    """
    ==========================================================================
    ENTIDAD ITEM CARRO (Tabla: item_carro) - 3FN
    ==========================================================================
    Ítem individual en el carro. Vincula Carro, Asiento y Pasajero.
    NO guarda precio en columna: el precio se calcula dinámicamente desde
    servicio.tarifa_* según asiento.tipo_asiento.
    NO descuenta stock de asientos hasta que la venta se paga.
    ==========================================================================
    """
    carro = models.ForeignKey(
        CarroPasajes,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Carro Asociado"
    )
    asiento = models.ForeignKey(
        Asiento,
        on_delete=models.CASCADE,
        related_name='items_carro',
        verbose_name="Asiento Seleccionado"
    )
    pasajero = models.ForeignKey(
        Pasajero,
        on_delete=models.PROTECT,
        related_name='items_carro',
        verbose_name="Pasajero Titular"
    )
    fecha_agregado = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Incorporación"
    )

    class Meta:
        db_table = 'item_carro'
        verbose_name = "Ítem de Carro"
        verbose_name_plural = "Ítems de Carro"
        unique_together = ('carro', 'asiento')
        ordering = ['id']

    def __str__(self):
        return (
            f"Ítem #{self.id}: Asiento #{self.asiento.numero_asiento} para "
            f"{self.pasajero.nombre_completo} (${self.precio:,.0f})"
        )

    @property
    def precio(self) -> Decimal:
        """Calcula el precio dinámico desde el asiento asociado."""
        return self.asiento.precio

    @property
    def nombre_pasajero(self) -> str:
        """Nombre completo del pasajero para compatibilidad con vistas y serializadores."""
        return self.pasajero.nombre_completo

    @property
    def rut_pasajero(self) -> str:
        """RUT del pasajero para compatibilidad con vistas y serializadores."""
        return self.pasajero.rut


class Venta(models.Model):
    """
    ==========================================================================
    ENTIDAD VENTA (Tabla: venta) - Orden Histórica Maestra
    ==========================================================================
    Cabecera de transacción comercial generada en el checkout.
    Estados:
    - PENDIENTE: Orden creada, no descuenta stock de asientos.
    - PAGADO: Transacción pagada exitosamente, descuenta stock y emite boletos.
    - ENTREGADO: Servicio realizado satisfactoriamente.
    - CANCELADO: Orden anulada; si estaba pagada, restaura stock y anula boletos.
    ==========================================================================
    """
    ESTADO_PENDIENTE = 'PENDIENTE'
    ESTADO_PAGADO = 'PAGADO'
    ESTADO_CANCELADO = 'CANCELADO'
    ESTADO_ENTREGADO = 'ENTREGADO'

    ESTADOS_VENTA_CHOICES = (
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_PAGADO, 'Pagado'),
        (ESTADO_CANCELADO, 'Cancelado'),
        (ESTADO_ENTREGADO, 'Entregado'),
    )

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='ventas',
        verbose_name="Comprador"
    )
    codigo_transaccion = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Código Único de Transacción (UUID)"
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS_VENTA_CHOICES,
        default=ESTADO_PENDIENTE,
        verbose_name="Estado de la Orden"
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Monto Total Congelado (CLP)",
        help_text="Snapshot del total liquidado al momento de realizar el checkout."
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Transacción"
    )

    class Meta:
        db_table = 'venta'
        verbose_name = "Venta / Orden"
        verbose_name_plural = "Ventas y Órdenes"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Venta #{self.id} [{self.codigo_transaccion}] - {self.get_estado_display()} - ${self.total:,.0f}"


class DetalleVenta(models.Model):
    """
    ==========================================================================
    ENTIDAD DETALLE VENTA (Tabla: detalle_venta) - Historial Inmutable 3FN
    ==========================================================================
    Registro histórico individual por cada asiento comprado.
    Almacena el precio pactado inmutable (precio_unitario) capturado al checkout,
    vinculado al Asiento y al Pasajero correspondiente.
    ==========================================================================
    """
    venta = models.ForeignKey(
        Venta,
        on_delete=models.CASCADE,
        related_name='detalles',
        verbose_name="Venta Matriz"
    )
    asiento = models.ForeignKey(
        Asiento,
        on_delete=models.PROTECT,
        related_name='detalles_venta',
        verbose_name="Asiento Asignado"
    )
    pasajero = models.ForeignKey(
        Pasajero,
        on_delete=models.PROTECT,
        related_name='detalles_venta',
        verbose_name="Pasajero Titular"
    )
    precio_unitario = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Precio Unitario Congelado (CLP)",
        help_text="Precio pactado inmutable capturado al momento del checkout."
    )

    class Meta:
        db_table = 'detalle_venta'
        verbose_name = "Detalle de Venta"
        verbose_name_plural = "Detalles de Ventas"
        ordering = ['id']

    def __str__(self):
        return (
            f"Detalle #{self.id} (Venta #{self.venta_id}): Asiento #{self.asiento.numero_asiento} "
            f"para {self.pasajero.nombre_completo} - ${self.precio_unitario:,.0f}"
        )

    @property
    def nombre_pasajero(self) -> str:
        """Nombre del pasajero obtenido desde la relación con Pasajero."""
        return self.pasajero.nombre_completo

    @property
    def rut_pasajero(self) -> str:
        """RUT del pasajero obtenido desde la relación con Pasajero."""
        return self.pasajero.rut


class Boleto(models.Model):
    """
    ==========================================================================
    ENTIDAD BOLETO (Tabla: boleto) - Ticket Electrónico 1 a 1 con DetalleVenta
    ==========================================================================
    Emisión electrónica de pasaje con relación OneToOne a DetalleVenta (3FN).
    Evita redundancia de venta, asiento y pasajero, accediendo a través del detalle.
    Incorpora UUID único irrepetible, Hash SHA-256 criptográfico y estado.
    ==========================================================================
    """
    ESTADO_VALIDO = 'VALIDO'
    ESTADO_ANULADO = 'ANULADO'

    ESTADOS_BOLETO_CHOICES = (
        (ESTADO_VALIDO, 'Válido'),
        (ESTADO_ANULADO, 'Anulado'),
    )

    detalle_venta = models.OneToOneField(
        DetalleVenta,
        on_delete=models.PROTECT,
        related_name='boleto',
        verbose_name="Detalle de Venta Asociado"
    )
    codigo_boleto = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Código de Boleto (UUID)"
    )
    codigo_hash = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        verbose_name="Hash de Seguridad (SHA-256)",
        help_text="Hash criptográfico generado a partir de la transacción, asiento y pasajero."
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS_BOLETO_CHOICES,
        default=ESTADO_VALIDO,
        verbose_name="Estado del Boleto"
    )
    fecha_emision = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha y Hora de Emisión"
    )

    class Meta:
        db_table = 'boleto'
        verbose_name = "Boleto / Ticket"
        verbose_name_plural = "Boletos y Tickets"
        ordering = ['-fecha_emision']

    # --------------------------------------------------------------------------
    # PROPIEDADES DELEGADAS A DETALLE_VENTA (COMPATIBILIDAD Y SIMPLICIDAD)
    # --------------------------------------------------------------------------
    @property
    def venta(self):
        """Retorna la venta matriz a través del detalle."""
        return self.detalle_venta.venta

    @property
    def asiento(self):
        """Retorna el asiento asignado a través del detalle."""
        return self.detalle_venta.asiento

    @property
    def pasajero(self):
        """Retorna la entidad Pasajero a través del detalle."""
        return self.detalle_venta.pasajero

    @property
    def nombre_pasajero(self) -> str:
        """Nombre del pasajero a través de la relación."""
        return self.detalle_venta.pasajero.nombre_completo

    @property
    def rut_pasajero(self) -> str:
        """RUT del pasajero a través de la relación."""
        return self.detalle_venta.pasajero.rut

    @property
    def precio_pagado(self) -> Decimal:
        """Precio unitario pactado a través del detalle."""
        return self.detalle_venta.precio_unitario

    def save(self, *args, **kwargs):
        """Genera el hash SHA-256 criptográfico si no ha sido generado previamente."""
        if not self.codigo_hash:
            contenido_semilla = (
                f"{self.codigo_boleto}-"
                f"{self.detalle_venta.asiento_id}-"
                f"{self.detalle_venta.pasajero.rut}"
            )
            self.codigo_hash = hashlib.sha256(contenido_semilla.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Boleto {self.codigo_boleto} | Asiento #{self.asiento.numero_asiento} | "
            f"{self.nombre_pasajero} ({self.get_estado_display()})"
        )
