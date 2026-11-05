"""
==============================================================================
BusDrex - MÓDULO: TRANSPORTE (apps/transporte/models.py)
Modelos de Datos Geográficos y Operativos en Tercera Forma Normal (3FN)
Evaluación 2: Programación Back End | Año: 2026
Estudiante: Benjamin Gómez | Sección: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Normalización 3FN implementada:
- Tablas: `region`, `ciudad`, `terminal`, `ruta`, `bus`, `servicio`, `asiento`, `oferta`
- Se elimina la dependencia transitiva Terminal -> Ciudad -> Región separando
  `region` (1:N) `ciudad` (1:N) `terminal`.
- `ruta` almacena `duracion_minutos` (entero) y restringe origen != destino.
- `servicio` incorpora `tarifa_semicama` y `tarifa_cama`.
- `asiento` cuenta con tipo (SEMICAMA / CAMA) y estado (DISPONIBLE / OCUPADO).
- Se protegen los registros históricos con `on_delete=models.PROTECT`.
==============================================================================
"""

from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError


class Region(models.Model):
    """
    ==========================================================================
    ENTIDAD REGION (Tabla: region) - 3FN Geográfica
    ==========================================================================
    Representa una región político-administrativa (ej. Región Metropolitana).
    ==========================================================================
    """
    nombre = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Nombre de la Región",
        help_text="Ejemplo: Región Metropolitana, Región del Biobío, Región de Valparaíso."
    )

    class Meta:
        db_table = 'region'
        verbose_name = "Región"
        verbose_name_plural = "Regiones"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Ciudad(models.Model):
    """
    ==========================================================================
    ENTIDAD CIUDAD (Tabla: ciudad) - 3FN Geográfica
    ==========================================================================
    Representa una ciudad perteneciente a una única Región.
    Evita dependencias transitivas en terminales.
    ==========================================================================
    """
    nombre = models.CharField(
        max_length=100,
        verbose_name="Nombre de la Ciudad",
        help_text="Ejemplo: Santiago, Concepción, Viña del Mar, Temuco."
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name='ciudades',
        verbose_name="Región Perteneciente"
    )

    class Meta:
        db_table = 'ciudad'
        verbose_name = "Ciudad"
        verbose_name_plural = "Ciudades"
        unique_together = ('nombre', 'region')
        ordering = ['region__nombre', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.region.nombre})"


class Terminal(models.Model):
    """
    ==========================================================================
    ENTIDAD TERMINAL (Tabla: terminal) - 3FN Geográfica
    ==========================================================================
    Representa un terminal físico de buses interurbanos.
    Se asocia directamente a una Ciudad (la región se infiere vía FK en 3FN).
    ==========================================================================
    """
    nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre del Terminal",
        help_text="Ejemplo: Terminal San Borja, Terminal Collao, Terminal Rodoviario."
    )
    ciudad = models.ForeignKey(
        Ciudad,
        on_delete=models.PROTECT,
        related_name='terminales',
        verbose_name="Ciudad de Ubicación"
    )

    class Meta:
        db_table = 'terminal'
        verbose_name = "Terminal"
        verbose_name_plural = "Terminales"
        unique_together = ('nombre', 'ciudad')
        ordering = ['ciudad__nombre', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.ciudad.nombre})"

    @property
    def ciudad_nombre(self) -> str:
        """Nombre de la ciudad para compatibilidad con vistas y serializadores."""
        return self.ciudad.nombre

    @property
    def region_nombre(self) -> str:
        """Nombre de la región inferida para compatibilidad."""
        return self.ciudad.region.nombre


class Bus(models.Model):
    """
    ==========================================================================
    ENTIDAD BUS (Tabla: bus)
    ==========================================================================
    Unidad rodante de la flota de buses de BusDrex con patente única.
    ==========================================================================
    """
    TIPO_SEMICAMA = 'SEMICAMA'
    TIPO_SALON_CAMA = 'SALON_CAMA'
    TIPO_PREMIUM = 'PREMIUM'

    TIPOS_BUS_CHOICES = (
        (TIPO_SEMICAMA, 'Semicama'),
        (TIPO_SALON_CAMA, 'Salón Cama'),
        (TIPO_PREMIUM, 'Premium / Cama Suite'),
    )

    patente = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="Patente / Placa Única",
        help_text="Formato oficial chileno (ej. ABCD-12 o AB-1234)."
    )
    modelo = models.CharField(
        max_length=100,
        verbose_name="Modelo del Vehículo",
        help_text="Ejemplo: Marcopolo Paradiso G8 1800 DD, Volvo B430R, Scania K400."
    )
    capacidad_total = models.PositiveIntegerField(
        default=40,
        verbose_name="Capacidad Total de Pasajeros",
        help_text="Número total de asientos físicos en el bus."
    )
    tipo_bus = models.CharField(
        max_length=50,
        choices=TIPOS_BUS_CHOICES,
        default=TIPO_SEMICAMA,
        verbose_name="Tipo / Categoría de Bus"
    )

    class Meta:
        db_table = 'bus'
        verbose_name = "Bus"
        verbose_name_plural = "Buses"
        ordering = ['patente']

    def __str__(self):
        return f"Bus {self.patente} - {self.modelo} ({self.get_tipo_bus_display()})"


class Ruta(models.Model):
    """
    ==========================================================================
    ENTIDAD RUTA (Tabla: ruta)
    ==========================================================================
    Enlace de origen y destino entre terminales con duración en minutos.
    Restringe origen != destino mediante clean() y CheckConstraint de BD.
    ==========================================================================
    """
    origen = models.ForeignKey(
        Terminal,
        on_delete=models.PROTECT,
        related_name='rutas_origen',
        verbose_name="Terminal de Origen"
    )
    destino = models.ForeignKey(
        Terminal,
        on_delete=models.PROTECT,
        related_name='rutas_destino',
        verbose_name="Terminal de Destino"
    )
    duracion_minutos = models.PositiveIntegerField(
        default=120,
        verbose_name="Duración del Viaje (Minutos)",
        help_text="Duración estimada en minutos (ej. 330 para 5 horas 30 min)."
    )

    def clean(self):
        """Validación a nivel de modelo para impedir origen idéntico al destino."""
        if self.origen_id and self.destino_id and self.origen_id == self.destino_id:
            raise ValidationError("El terminal de origen no puede ser idéntico al terminal de destino.")

    class Meta:
        db_table = 'ruta'
        verbose_name = "Ruta"
        verbose_name_plural = "Rutas"
        unique_together = ('origen', 'destino')
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(origen=models.F('destino')),
                name='check_ruta_origen_distinto_destino'
            )
        ]
        ordering = ['origen__ciudad__nombre', 'destino__ciudad__nombre']

    def __str__(self):
        return f"{self.origen.nombre} ({self.origen.ciudad.nombre}) -> {self.destino.nombre} ({self.destino.ciudad.nombre})"

    @property
    def duracion_formateada(self) -> str:
        """Formatea la duración en minutos a formato 'X hrs Y min'."""
        horas = self.duracion_minutos // 60
        mins = self.duracion_minutos % 60
        if horas > 0 and mins > 0:
            return f"{horas} hrs {mins} min"
        elif horas > 0:
            return f"{horas} hrs"
        return f"{mins} min"


class Servicio(models.Model):
    """
    ==========================================================================
    ENTIDAD SERVICIO (Tabla: servicio)
    ==========================================================================
    Itinerario programado asociando Ruta, Bus, fecha/hora de salida y
    tarifas diferenciadas por tipo de asiento (Semicama y Salón Cama).
    ==========================================================================
    """
    ruta = models.ForeignKey(
        Ruta,
        on_delete=models.PROTECT,
        related_name='servicios',
        verbose_name="Ruta del Itinerario"
    )
    bus = models.ForeignKey(
        Bus,
        on_delete=models.PROTECT,
        related_name='servicios',
        verbose_name="Bus Asignado"
    )
    fecha_hora_salida = models.DateTimeField(
        verbose_name="Fecha y Hora de Salida",
        help_text="Horario programado para el inicio del recorrido."
    )
    tarifa_semicama = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('15000.00'),
        verbose_name="Tarifa Semicama (CLP)",
        help_text="Precio por asiento estándar Semicama para este viaje."
    )
    tarifa_cama = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('22000.00'),
        verbose_name="Tarifa Salón Cama (CLP)",
        help_text="Precio por asiento Salón Cama para este viaje."
    )

    class Meta:
        db_table = 'servicio'
        verbose_name = "Servicio / Itinerario"
        verbose_name_plural = "Servicios e Itinerarios"
        ordering = ['fecha_hora_salida']

    def __str__(self):
        fecha_str = self.fecha_hora_salida.strftime("%d/%m/%Y %H:%M")
        return (
            f"Servicio #{self.id}: {self.ruta} [{fecha_str}] - "
            f"Semicama: ${self.tarifa_semicama:,.0f} | Cama: ${self.tarifa_cama:,.0f}"
        )

    @property
    def precio_desde(self) -> Decimal:
        """Retorna la tarifa base más económica disponible para el servicio."""
        return min(self.tarifa_semicama, self.tarifa_cama)

    def asientos_disponibles_count(self) -> int:
        """Retorna la cantidad actual de asientos en estado DISPONIBLE."""
        return self.asientos.filter(estado=Asiento.ESTADO_DISPONIBLE).count()

    def generar_asientos_automaticamente(self):
        """
        ======================================================================
        DISTRIBUCIÓN AUTOMÁTICA DE ASIENTOS (ESTÁNDAR TURBUS)
        ======================================================================
        Crea los asientos 1..capacidad_total con distribución realista:
        - Asientos 1 a 12 (Primer piso / Sector Salón Cama): tipo 'CAMA'.
        - Asientos 13 en adelante (Segundo piso / Sector Semicama): tipo 'SEMICAMA'.
        ======================================================================
        """
        capacidad = self.bus.capacidad_total
        asientos_existentes = set(self.asientos.values_list('numero_asiento', flat=True))

        limite_cama = min(12, max(4, int(capacidad * 0.3)))

        nuevos_asientos = []
        for num in range(1, capacidad + 1):
            if num not in asientos_existentes:
                tipo = Asiento.TIPO_CAMA if num <= limite_cama else Asiento.TIPO_SEMICAMA
                nuevos_asientos.append(
                    Asiento(
                        servicio=self,
                        numero_asiento=num,
                        tipo_asiento=tipo,
                        estado=Asiento.ESTADO_DISPONIBLE
                    )
                )

        if nuevos_asientos:
            Asiento.objects.bulk_create(nuevos_asientos)


class Asiento(models.Model):
    """
    ==========================================================================
    ENTIDAD ASIENTO (Tabla: asiento)
    ==========================================================================
    Unidad de inventario individual asociada a un Servicio.
    Posee tipo de confort (SEMICAMA / CAMA) y estado (DISPONIBLE / OCUPADO).
    ==========================================================================
    """
    TIPO_SEMICAMA = 'SEMICAMA'
    TIPO_CAMA = 'CAMA'

    TIPOS_ASIENTO_CHOICES = (
        (TIPO_SEMICAMA, 'Semicama'),
        (TIPO_CAMA, 'Salón Cama'),
    )

    ESTADO_DISPONIBLE = 'DISPONIBLE'
    ESTADO_OCUPADO = 'OCUPADO'

    ESTADOS_ASIENTO_CHOICES = (
        (ESTADO_DISPONIBLE, 'Disponible'),
        (ESTADO_OCUPADO, 'Ocupado'),
    )

    servicio = models.ForeignKey(
        Servicio,
        on_delete=models.CASCADE,
        related_name='asientos',
        verbose_name="Servicio Asociado"
    )
    numero_asiento = models.PositiveIntegerField(
        verbose_name="Número de Asiento",
        help_text="Número secuencial del asiento en el bus (ej. 1, 2, ..., 40)."
    )
    tipo_asiento = models.CharField(
        max_length=20,
        choices=TIPOS_ASIENTO_CHOICES,
        default=TIPO_SEMICAMA,
        verbose_name="Tipo de Asiento",
        help_text="Categoría de confort del asiento (Semicama o Salón Cama)."
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS_ASIENTO_CHOICES,
        default=ESTADO_DISPONIBLE,
        verbose_name="Estado de Disponibilidad"
    )

    class Meta:
        db_table = 'asiento'
        verbose_name = "Asiento"
        verbose_name_plural = "Asientos"
        unique_together = ('servicio', 'numero_asiento')
        ordering = ['servicio', 'numero_asiento']

    def __str__(self):
        return (
            f"Asiento #{self.numero_asiento} [{self.get_tipo_asiento_display()}] "
            f"(Servicio #{self.servicio_id}) - {self.get_estado_display()} - ${self.precio:,.0f}"
        )

    @property
    def precio(self) -> Decimal:
        """Retorna el precio dinámico del asiento según su categoría y las tarifas del servicio."""
        if self.tipo_asiento == self.TIPO_CAMA:
            return self.servicio.tarifa_cama
        return self.servicio.tarifa_semicama


class Oferta(models.Model):
    """
    ==========================================================================
    ENTIDAD OFERTA (Tabla: oferta)
    ==========================================================================
    Banners y promociones comerciales gestionadas por el Administrador de Flota.
    ==========================================================================
    """
    ruta = models.ForeignKey(
        Ruta,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ofertas',
        verbose_name="Ruta Asociada (Opcional)"
    )
    titulo = models.CharField(
        max_length=150,
        verbose_name="Título de la Oferta",
        help_text="Ejemplo: 'Escápate a Viña del Mar con 25% de Descuento'"
    )
    descripcion = models.TextField(
        blank=True,
        null=True,
        verbose_name="Descripción de la Promoción",
        help_text="Detalles comerciales de la oferta y condiciones del viaje."
    )
    descuento_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Descuento (%)",
        help_text="Porcentaje de descuento sobre la tarifa regular."
    )
    fecha_inicio = models.DateField(
        verbose_name="Fecha de Inicio de Vigencia"
    )
    fecha_fin = models.DateField(
        verbose_name="Fecha de Fin de Vigencia"
    )
    activa = models.BooleanField(
        default=True,
        verbose_name="¿Oferta Activa?"
    )

    class Meta:
        db_table = 'oferta'
        verbose_name = "Oferta / Promoción"
        verbose_name_plural = "Ofertas y Promociones"
        ordering = ['-activa', 'fecha_fin']

    def __str__(self):
        return f"Oferta: {self.titulo} ({'Activa' if self.activa else 'Inactiva'})"
