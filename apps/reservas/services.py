"""
==============================================================================
BusDrex - MODULO: RESERVAS (apps/reservas/services.py)
Capa de Servicios y Logica Transaccional en Tercera Forma Normal (3FN)
Evaluacion 2: Programacion Back End | Anio: 2026
Estudiante: Benjamin Gomez | Seccion: AP-N4-C1
Proyecto 4: Reservas de Pasajes de Buses Interurbanos (Inspirado en Turbus.cl)
==============================================================================
Centraliza toda la logica de negocio y control de concurrencia:
1. realizar_checkout: Crea la Venta PENDIENTE con precios congelados en DetalleVenta
   vinculando Pasajero y Asiento. NO descuenta stock. Vacia el carro.
2. procesar_pago_venta: Transaccion atomica con bloqueo doble (venta + asientos) en
   MySQL/InnoDB. Ordena los asientos por id para evitar deadlocks entre transacciones
   concurrentes. Reintenta hasta 3 veces ante deadlock (error 1213) o lock timeout.
   Si algun asiento no esta DISPONIBLE: aborta TODA la compra (todo o nada) y
   responde 409 con la lista de asientos en conflicto.
   Doble seguro: UPDATE condicional que verifica la cantidad actualizada.
3. procesar_cancelacion_venta: Reposicion automatica e idempotente de asientos si la
   venta estaba PAGADA y el bus no ha zarpado. Anula boletos (ESTADO_ANULADO).
4. procesar_entrega_venta: Transicion valida PAGADO -> ENTREGADO.
5. cambiar_estado_venta: Validador estricto de transiciones de estados.
==============================================================================
CORRECCION DE CONCURRENCIA (causa del cruce detectado por el profesor):
- La version anterior bloqueaba los asientos PERO NO bloqueaba la fila de venta
  primero; si dos pagos llegaban simultaneamente, ambos leian el estado PENDIENTE
  de la venta antes de que el otro adquiriera el lock, y ambos procedian con los
  mismos asientos. Adicionalmente, los asientos se leian FUERA de la transaccion
  atomica antes del bloqueo, usando un estado desactualizado.
- Solucion: select_for_update() sobre la Venta primero (bloquea la fila de orden),
  luego select_for_update() sobre los Asientos ordenados por id ASC (evita deadlock
  por inversion de orden), y un UPDATE condicional como segundo seguro.
==============================================================================
"""

import time
import logging
from decimal import Decimal
from django.db import transaction, OperationalError
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import CarroPasajes, ItemCarro, Venta, DetalleVenta, Boleto
from transporte.models import Asiento

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Constantes de reintentos ante deadlock / lock wait timeout de MySQL/InnoDB
# MySQL error 1213: Deadlock found when trying to get lock; try restarting transaction
# MySQL error 1205: Lock wait timeout exceeded; try restarting transaction
# ------------------------------------------------------------------------------
MYSQL_DEADLOCK_ERRNO = 1213
MYSQL_LOCK_TIMEOUT_ERRNO = 1205
MAX_REINTENTOS_PAGO = 3       # Numero maximo de reintentos ante deadlock
ESPERA_REINTENTO_SEG = 0.15   # Pausa entre reintentos (segundos)


# ==============================================================================
# AUXILIAR: Detectar si una OperationalError de MySQL es deadlock o lock timeout
# ==============================================================================
def _es_deadlock_o_timeout(exc):
    """
    Retorna True si la excepcion OperationalError corresponde a un deadlock
    (errno 1213) o a un lock wait timeout (errno 1205) de MySQL/InnoDB.
    Se extrae el errno desde los args de la excepcion de MySQLdb/PyMySQL.
    """
    args = exc.args
    if args and isinstance(args[0], int):
        return args[0] in (MYSQL_DEADLOCK_ERRNO, MYSQL_LOCK_TIMEOUT_ERRNO)
    # Fallback: buscar en la representacion textual
    msg = str(exc).lower()
    return 'deadlock' in msg or 'lock wait timeout' in msg


# ==============================================================================
# 1. CHECKOUT (CREACION DE ORDEN PENDIENTE CON PRECIOS CONGELADOS)
# ==============================================================================
def realizar_checkout(usuario):
    """
    ==========================================================================
    TRANSACCION DE CHECKOUT (PASAJERO)
    ==========================================================================
    - Toma el contenido del CarroPasajes del usuario.
    - Valida que el carro no este vacio y que los viajes programados sean futuros.
    - VALIDACION TEMPRANA: Rechaza asientos ya OCUPADOS o servicios zarpados.
      Dos carros con el mismo asiento DISPONIBLE siguen siendo validos hasta el
      pago; el conflicto se resuelve de forma atomica al pagar.
    - Crea la Venta en estado PENDIENTE.
    - Crea los registros inmutables de DetalleVenta congelando el precio pactado
      y vinculando el Pasajero titular (3FN).
    - Vacia el carro de compras.
    - REGLA CRITICA: En este paso NO se descuenta stock de asientos.
    ==========================================================================
    """
    carro, _ = CarroPasajes.objects.get_or_create(usuario=usuario)
    items = list(carro.items.select_related(
        'asiento__servicio__ruta__origen__ciudad',
        'asiento__servicio__ruta__destino__ciudad',
        'asiento__servicio__bus',
        'pasajero'
    ).all())

    if not items:
        raise ValidationError({"error": "El carro de pasajes esta vacio. Debe seleccionar al menos un asiento."})

    ahora = timezone.now()

    # --------------------------------------------------------------------------
    # VALIDACION TEMPRANA (sin descontar stock):
    # Rechaza asientos ya OCUPADOS o servicios zarpados al momento del checkout.
    # Permite que dos carros tengan el mismo asiento DISPONIBLE (el conflicto
    # real se resuelve atomicamente al pagar con select_for_update).
    # --------------------------------------------------------------------------
    asientos_ocupados = []
    for item in items:
        servicio = item.asiento.servicio
        if servicio.fecha_hora_salida <= ahora:
            raise ValidationError({
                "error": (
                    f"El servicio para el asiento #{item.asiento.numero_asiento} "
                    f"({servicio.ruta}) ya ha iniciado su viaje."
                )
            })
        if item.asiento.estado != Asiento.ESTADO_DISPONIBLE:
            asientos_ocupados.append(str(item.asiento.numero_asiento))

    if asientos_ocupados:
        raise ValidationError({
            "error": (
                "No se puede hacer checkout: los siguientes asientos ya estan ocupados: "
                + ", ".join(asientos_ocupados)
                + ". Eliminelos del carro y elija otros."
            ),
            "asientos_ocupados": asientos_ocupados,
        })

    total_venta = carro.calcular_total()
    if total_venta <= Decimal('0.00'):
        raise ValidationError({"error": "El total de la compra debe ser superior a cero."})

    with transaction.atomic():
        # Crear la Venta en estado inicial PENDIENTE con total historico congelado
        venta = Venta.objects.create(
            usuario=usuario,
            total=total_venta,
            estado=Venta.ESTADO_PENDIENTE
        )

        # Congelar los pasajes en DetalleVenta (3FN: FK a Asiento y FK a Pasajero)
        detalles_a_crear = [
            DetalleVenta(
                venta=venta,
                asiento=item.asiento,
                pasajero=item.pasajero,
                precio_unitario=item.precio
            )
            for item in items
        ]
        DetalleVenta.objects.bulk_create(detalles_a_crear)

        # Vaciar el carro del usuario una vez transferido a la orden PENDIENTE
        carro.items.all().delete()

        logger.info(
            f"[CHECKOUT EXITOSO] Venta #{venta.id} creada en estado PENDIENTE "
            f"con {len(detalles_a_crear)} pasajes para {usuario.username}."
        )

        return venta


# ==============================================================================
# 2. NUCLEO DEL PAGO ATOMICO (bloqueo doble, orden por id, doble seguro)
# ==============================================================================
def _ejecutar_pago_atomico(venta):
    """
    ==========================================================================
    NUCLEO ATOMICO DEL PAGO
    ==========================================================================
    DEBE llamarse SIEMPRE dentro de un bloque transaction.atomic() exterior.
    Implementa el protocolo completo anti-cruce entre cuentas:

    Paso A: Bloquea la fila de la Venta con select_for_update() para que dos
            pagos simultaneos de la misma orden no puedan proceder en paralelo.
    Paso B: Re-lee el estado de la venta con el bloqueo activo; si ya no esta
            PENDIENTE (otro hilo la pago primero), aborta sin error de conflicto.
    Paso C: Obtiene los ids de asientos de la orden.
    Paso D: Bloquea los asientos con select_for_update() ordenados por id ASC.
            El orden fijo garantiza que dos transacciones concurrentes que
            comparten asientos siempre intenten adquirir los locks en el mismo
            orden, evitando deadlocks por inversion de orden.
    Paso E: Valida servicio no zarpado con datos ya bloqueados.
    Paso F: Con los asientos ya bloqueados, valida de nuevo su estado.
            Si ALGUNO no esta DISPONIBLE, aborta toda la compra (todo o nada).
    Paso G: DOBLE SEGURO: UPDATE condicional filter(estado=DISPONIBLE).update(
            estado=OCUPADO) y verifica que la cantidad actualizada sea exacta.
            Si no coincide, fuerza rollback.
    Paso H: Solo despues de ambos controles: emite Boletos.
    Paso I: Venta -> PAGADO.

    Raises:
        ValidationError con status_code=409 si hay asientos en conflicto.
    ==========================================================================
    """
    # -- Paso A: Bloqueo de la fila de Venta (evita doble pago concurrente) --
    venta_bloqueada = (
        Venta.objects.select_for_update()
        .filter(pk=venta.pk)
        .first()
    )
    if venta_bloqueada is None:
        raise ValidationError({"error": "La orden de venta no fue encontrada."})

    # -- Paso B: Re-leer el estado con bloqueo activo --
    if venta_bloqueada.estado == Venta.ESTADO_PAGADO:
        raise ValidationError({"error": "Esta orden ya se encuentra en estado PAGADO."})

    if venta_bloqueada.estado != Venta.ESTADO_PENDIENTE:
        raise ValidationError({
            "error": (
                f"No se puede pagar una orden en estado "
                f"{venta_bloqueada.get_estado_display()}. Debe estar PENDIENTE."
            )
        })

    # -- Paso C: Obtener ids de asientos de la orden --
    detalles = list(
        venta_bloqueada.detalles
        .select_related('asiento__servicio', 'pasajero')
        .all()
    )
    if not detalles:
        raise ValidationError({"error": "La orden no contiene detalles de pasajes a pagar."})

    # Ordenar los ids de asientos SIEMPRE de forma ascendente.
    # Esto garantiza que dos transacciones con asientos comunes adquieran
    # los locks en el mismo orden -> previene deadlock por inversion de orden.
    asientos_ids = sorted({d.asiento_id for d in detalles})
    ahora = timezone.now()

    # -- Paso D: Bloqueo pesimista de asientos ordenados por id ASC --
    asientos_bloqueados = list(
        Asiento.objects
        .select_for_update()
        .filter(id__in=asientos_ids)
        .select_related('servicio')
        .order_by('id')   # Orden deterministico para evitar deadlocks
    )

    # -- Paso E: Validar servicio no zarpado con datos ya bloqueados --
    for asiento in asientos_bloqueados:
        if asiento.servicio.fecha_hora_salida <= ahora:
            raise ValidationError({
                "error": (
                    f"El servicio #{asiento.servicio_id} ya ha zarpado. "
                    f"No es posible completar el pago."
                ),
                "asiento": asiento.numero_asiento
            })

    # -- Paso F: Verificar disponibilidad de todos los asientos bloqueados --
    asientos_en_conflicto = [
        asiento for asiento in asientos_bloqueados
        if asiento.estado != Asiento.ESTADO_DISPONIBLE
    ]

    if asientos_en_conflicto:
        # Construir lista detallada para la respuesta 409
        detalle_conflicto = [
            {
                "numero_asiento": a.numero_asiento,
                "servicio_id": a.servicio_id,
            }
            for a in asientos_en_conflicto
        ]
        numeros = [str(a.numero_asiento) for a in asientos_en_conflicto]
        logger.warning(
            f"[CONFLICTO DE PAGO] Venta #{venta.id}: Asientos ocupados {numeros}. "
            f"Rollback ejecutado. Venta se mantiene PENDIENTE."
        )
        # ValidationError dentro de atomic() provoca rollback automatico
        error = ValidationError({
            "error": "Transaccion rechazada: Uno o mas asientos ya no estan disponibles.",
            "asientos_en_conflicto": numeros,
            "detalle_conflicto": detalle_conflicto,
            "detalle": (
                "Los asientos fueron adquiridos por otra transaccion mientras "
                "la orden estaba pendiente. La venta sigue en estado PENDIENTE."
            ),
            "estado_venta": Venta.ESTADO_PENDIENTE,
        })
        # Asignar codigo HTTP 409 para diferenciarlo de un 400 generico
        error.status_code = 409
        raise error

    # -- Paso G: DOBLE SEGURO - UPDATE condicional (solo asientos DISPONIBLES) --
    # Marca todos los asientos como OCUPADOS en un unico UPDATE atomico.
    # Si entre el select_for_update y este UPDATE otro hilo cambio algun estado,
    # la cantidad actualizada sera menor que la esperada y se fuerza rollback.
    cantidad_actualizada = (
        Asiento.objects
        .filter(id__in=asientos_ids, estado=Asiento.ESTADO_DISPONIBLE)
        .update(estado=Asiento.ESTADO_OCUPADO)
    )

    if cantidad_actualizada != len(asientos_ids):
        # Situacion extremadamente improbable pero posible; forzar rollback
        logger.error(
            f"[DOBLE SEGURO FALLIDO] Venta #{venta.id}: Se esperaban "
            f"{len(asientos_ids)} actualizaciones pero ocurrieron {cantidad_actualizada}. "
            f"Rollback forzado."
        )
        raise ValidationError({
            "error": (
                "Transaccion rechazada: inconsistencia detectada al marcar asientos. "
                "Intente nuevamente."
            ),
            "estado_venta": Venta.ESTADO_PENDIENTE,
        })

    # -- Paso H: Emitir Boletos nominativos OneToOne con DetalleVenta (3FN) --
    for d in detalles:
        # Si no existe boleto para este detalle, se genera (idempotencia)
        if not hasattr(d, 'boleto'):
            boleto = Boleto(
                detalle_venta=d,
                estado=Boleto.ESTADO_VALIDO
            )
            boleto.save()

    # -- Paso I: Transicionar la venta a PAGADO --
    venta_bloqueada.estado = Venta.ESTADO_PAGADO
    venta_bloqueada._cancelacion_procesada_por_servicio = True
    venta_bloqueada.save(update_fields=['estado'])

    # Refrescar el objeto original que el llamador tiene en su scope
    venta.estado = Venta.ESTADO_PAGADO

    logger.info(
        f"[PAGO EXITOSO] Venta #{venta.id} PAGADA. "
        f"Boletos emitidos para {len(detalles)} detalles."
    )

    return venta_bloqueada


# ==============================================================================
# 2. PAGO DE VENTA (TRANSACCION ATOMICA CON BLOQUEO PESIMISTA)
# ==============================================================================
def procesar_pago_venta(venta, usuario=None):
    """
    ==========================================================================
    PAGO TRANSACCIONAL CON BLOQUEO PESIMISTA (select_for_update)
    ==========================================================================
    Funcion publica usada por el endpoint de pago del pasajero Y por el PATCH
    del admin (a traves de cambiar_estado_venta). Garantiza que ambas rutas
    de pago usen exactamente la misma logica atomica anti-cruce.

    - Verifica que la venta pertenezca al usuario (si se provee usuario).
    - Reintenta hasta MAX_REINTENTOS_PAGO veces ante deadlock de MySQL.
    - Responde 409 si hay asientos en conflicto (todo o nada, sin pagos parciales).
    ==========================================================================
    """
    # -- Aislamiento entre cuentas: solo el duenio puede pagar su venta --
    if usuario and venta.usuario_id != usuario.id:
        raise ValidationError({
            "error": "No posee permisos para pagar esta orden de venta."
        })

    # Validaciones previas al bloqueo (sin transaccion aun)
    if venta.estado == Venta.ESTADO_PAGADO:
        raise ValidationError({"error": "Esta orden ya se encuentra en estado PAGADO."})

    if venta.estado != Venta.ESTADO_PENDIENTE:
        raise ValidationError({
            "error": (
                f"No se puede pagar una orden en estado "
                f"{venta.get_estado_display()}. Debe estar PENDIENTE."
            )
        })

    # -- Reintentos ante deadlock o lock wait timeout de MySQL/InnoDB --
    ultimo_error = None
    for intento in range(1, MAX_REINTENTOS_PAGO + 1):
        try:
            with transaction.atomic():
                return _ejecutar_pago_atomico(venta)
        except ValidationError:
            # ValidationError de negocio (conflicto de asientos, etc.): no reintentar
            raise
        except OperationalError as exc:
            if _es_deadlock_o_timeout(exc):
                ultimo_error = exc
                logger.warning(
                    f"[DEADLOCK/TIMEOUT] Venta #{venta.id}, intento {intento}/"
                    f"{MAX_REINTENTOS_PAGO}. Reintentando en {ESPERA_REINTENTO_SEG}s."
                )
                if intento < MAX_REINTENTOS_PAGO:
                    time.sleep(ESPERA_REINTENTO_SEG)
                continue
            # Otro error de BD: relanzar sin reintentar
            raise

    # Agotados los reintentos: informar al cliente
    logger.error(
        f"[PAGO FALLIDO] Venta #{venta.id}: agotados {MAX_REINTENTOS_PAGO} reintentos "
        f"ante deadlock/timeout. Ultimo error: {ultimo_error}"
    )
    raise ValidationError({
        "error": (
            "No fue posible completar el pago debido a alta concurrencia en el servidor. "
            "Por favor intente nuevamente en unos segundos."
        )
    })


# ==============================================================================
# 3. CANCELACION DE VENTA (REPOSICION AUTOMATICA E IDEMPOTENTE)
# ==============================================================================
def procesar_cancelacion_venta(venta, usuario=None, es_admin=False):
    """
    ==========================================================================
    CANCELACION Y REPOSICION AUTOMATICA DE ASIENTOS
    ==========================================================================
    - Pasajero: Solo puede cancelar sus propias ventas en estado PENDIENTE.
    - Admin de Flota: Puede cancelar ventas en estado PENDIENTE o PAGADO.
    - Si la venta pasa de PAGADO a CANCELADO antes de la salida:
      Los asientos vuelven a DISPONIBLE y los boletos se marcan ANULADO.
    - Si la venta era PENDIENTE: no se toca stock (nunca fue descontado).
    - Idempotencia garantizada: cancelar una orden ya cancelada no repone dos veces.
    - Aislamiento: la reposicion usa UPDATE condicional sobre el pk exacto,
      por lo que no afecta asientos ni boletos de otras cuentas.
    ==========================================================================
    """
    # -- Aislamiento entre cuentas: solo el duenio puede cancelar su venta --
    if usuario and not es_admin:
        if venta.usuario_id != usuario.id:
            raise ValidationError({"error": "No posee permisos sobre esta venta."})
        if venta.estado != Venta.ESTADO_PENDIENTE:
            raise ValidationError({
                "error": (
                    "Los pasajeros solo pueden cancelar ordenes que se encuentren "
                    "en estado PENDIENTE."
                )
            })

    # Idempotencia: Si ya esta cancelada, no se hace nada
    if venta.estado == Venta.ESTADO_CANCELADO:
        return venta

    # Validar transiciones permitidas hacia CANCELADO
    if venta.estado not in [Venta.ESTADO_PENDIENTE, Venta.ESTADO_PAGADO]:
        raise ValidationError({
            "error": f"No se puede cancelar una venta en estado {venta.get_estado_display()}."
        })

    estado_anterior = venta.estado
    ahora = timezone.now()

    with transaction.atomic():
        if estado_anterior == Venta.ESTADO_PAGADO:
            # ------------------------------------------------------------------
            # REPOSICION DE STOCK: Solo si el servicio aun no ha zarpado.
            # Se usa UPDATE condicional filter(estado=OCUPADO).update() para
            # reposicion atomica e idempotente: solo repone los asientos que
            # efectivamente estan OCUPADO, sin afectar asientos de otras cuentas.
            # ------------------------------------------------------------------
            detalles = list(
                venta.detalles
                .select_related('asiento__servicio')
                .prefetch_related('boleto')
                .all()
            )
            for detalle in detalles:
                asiento = detalle.asiento
                servicio = asiento.servicio

                if servicio.fecha_hora_salida > ahora:
                    # Reposicion idempotente: solo actualiza si el asiento esta OCUPADO
                    repuestos = (
                        Asiento.objects
                        .filter(pk=asiento.pk, estado=Asiento.ESTADO_OCUPADO)
                        .update(estado=Asiento.ESTADO_DISPONIBLE)
                    )
                    if repuestos:
                        logger.info(
                            f"[STOCK REPUESTO] Asiento #{asiento.numero_asiento} "
                            f"(Servicio #{servicio.id}) devuelto a DISPONIBLE "
                            f"por cancelacion de Venta #{venta.id}."
                        )
                else:
                    logger.warning(
                        f"[STOCK RETENIDO] Asiento #{asiento.numero_asiento} "
                        f"retenido porque el bus ya zarpo."
                    )

                # Anular el boleto correspondiente (idempotente)
                if hasattr(detalle, 'boleto'):
                    if detalle.boleto.estado != Boleto.ESTADO_ANULADO:
                        detalle.boleto.estado = Boleto.ESTADO_ANULADO
                        detalle.boleto.save(update_fields=['estado'])

        elif estado_anterior == Venta.ESTADO_PENDIENTE:
            # En estado PENDIENTE nunca se descontó stock; no hay reposicion que hacer
            logger.info(
                f"[CANCELACION PENDIENTE] Venta #{venta.id} cancelada. "
                f"No se modifico stock de asientos."
            )

        # Actualizar estado de la venta
        venta.estado = Venta.ESTADO_CANCELADO
        venta._cancelacion_procesada_por_servicio = True
        venta.save(update_fields=['estado'])

        return venta


# ==============================================================================
# 4. ENTREGA DE VENTA (TRANSICION PAGADO -> ENTREGADO)
# ==============================================================================
def procesar_entrega_venta(venta):
    """
    Transiciona una venta de PAGADO a ENTREGADO (viaje completado / servicio prestado).
    """
    if venta.estado == Venta.ESTADO_ENTREGADO:
        return venta

    if venta.estado != Venta.ESTADO_PAGADO:
        raise ValidationError({
            "error": (
                f"Para entregar una orden debe estar en estado PAGADO. "
                f"Estado actual: '{venta.estado}'."
            )
        })

    venta.estado = Venta.ESTADO_ENTREGADO
    venta._cancelacion_procesada_por_servicio = True
    venta.save(update_fields=['estado'])
    return venta


# ==============================================================================
# 5. ENRUTADOR MAESTRO DE TRANSICIONES DE ESTADO (MAQUINA DE ESTADOS)
# ==============================================================================
def cambiar_estado_venta(venta, nuevo_estado, es_admin=False):
    """
    ==========================================================================
    MAQUINA DE ESTADOS DE LA VENTA
    ==========================================================================
    Transiciones validas:
    - PENDIENTE -> PAGADO
    - PENDIENTE -> CANCELADO
    - PAGADO -> ENTREGADO
    - PAGADO -> CANCELADO
    Cualquier otra se rechaza con error 400 claro.

    NOTA: Las transiciones que implican pago (PENDIENTE->PAGADO) llaman a
    procesar_pago_venta, que es la UNICA funcion autorizada para descontar
    stock. El admin PATCH y el endpoint de pasajero usan la misma logica.
    ==========================================================================
    """
    if venta.estado == nuevo_estado:
        return venta

    estado_actual = venta.estado

    if estado_actual == Venta.ESTADO_PENDIENTE:
        if nuevo_estado == Venta.ESTADO_PAGADO:
            # Sin usuario: el admin ejecuta el pago (no valida propiedad)
            return procesar_pago_venta(venta)
        elif nuevo_estado == Venta.ESTADO_CANCELADO:
            return procesar_cancelacion_venta(venta, es_admin=es_admin)

    elif estado_actual == Venta.ESTADO_PAGADO:
        if nuevo_estado == Venta.ESTADO_ENTREGADO:
            return procesar_entrega_venta(venta)
        elif nuevo_estado == Venta.ESTADO_CANCELADO:
            return procesar_cancelacion_venta(venta, es_admin=es_admin)

    # Si llega aqui, la transicion no esta permitida
    raise ValidationError({
        "error": (
            f"Transicion de estado no valida: de '{estado_actual}' a '{nuevo_estado}'. "
            f"Las transiciones permitidas son: PENDIENTE->PAGADO, PENDIENTE->CANCELADO, "
            f"PAGADO->ENTREGADO, PAGADO->CANCELADO."
        ),
        "estado_actual": estado_actual,
        "estado_solicitado": nuevo_estado
    })
