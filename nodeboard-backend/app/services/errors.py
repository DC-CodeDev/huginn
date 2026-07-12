"""Excepciones de dominio independientes de FastAPI.

Estas excepciones transportan información estructurada que la capa HTTP
puede traducir a respuestas apropiadas sin que el dominio conozca HTTP.
"""


class DomainError(Exception):
    """Base de todas las excepciones de dominio."""
    pass


class ResourceNotFound(DomainError):
    """El recurso no existe o no pertenece al usuario actual.

    Ambos casos (no existe / no es propietario) se tratan igual para
    evitar enumeración de recursos de otros usuarios.
    """

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        message: str | None = None,
    ):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.message = message
        super().__init__(message or f"{resource_type} no encontrado")


class ForbiddenResource(DomainError):
    """El recurso existe pero el usuario no tiene permisos para accederlo.

    Útil cuando en el futuro se necesite distinguir "no existe" de
    "no autorizado" (ej. recursos compartidos entre usuarios).
    """

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        message: str | None = None,
    ):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.message = message
        super().__init__(message or f"Acceso denegado a {resource_type}")


class ValidationFailure(DomainError):
    """Error de validación de dominio — invariantes que no se cumplen.

    Indica que los datos proporcionados son semánticamente inválidos
    (ej. folder que no pertenece al studio indicado), no errores de
    sintaxis o de esquema.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class VersionConflict(DomainError):
    """El board fue modificado por otro cliente — versión obsoleta.

    Se lanza cuando una operación de escritura recibe un
    ``expected_version`` que no coincide con la versión actual
    del board en la base de datos.
    """

    def __init__(
        self,
        board_id: str,
        expected_version: int,
        current_version: int,
    ):
        self.board_id = board_id
        self.expected_version = expected_version
        self.current_version = current_version
        self.message = "El board fue modificado por otro cliente."
        super().__init__(self.message)


class InvalidScope(ValidationFailure):
    """Uno o más scopes no están permitidos."""

    def __init__(self, scopes: list[str]):
        self.scopes = scopes
        sorted_scopes = ", ".join(sorted(scopes))
        message = f"Scopes no válidos: {sorted_scopes}"
        super().__init__(message)


class OperationLimitExceeded(ValidationFailure):
    """Se excedió el límite de operación permitido.

    Indica que la cantidad de elementos en una operación batch
    supera el máximo configurado.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class RateLimitExceeded(DomainError):
    """La herramienta excedió su cuota temporal para el token actual."""

    def __init__(
        self,
        *,
        tool_name: str,
        limit: int,
        window_seconds: int,
        retry_after_seconds: int,
        message: str | None = None,
    ):
        self.tool_name = tool_name
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after_seconds = max(int(retry_after_seconds), 0)
        self.message = (
            message
            or "Se alcanzó el límite de solicitudes para esta herramienta."
        )
        super().__init__(self.message)


class IdempotencyConflict(DomainError):
    """La clave ya fue usada para un payload distinto."""

    def __init__(
        self,
        *,
        tool_name: str,
        idempotency_key: str,
        message: str | None = None,
    ):
        self.tool_name = tool_name
        self.idempotency_key = idempotency_key
        self.message = (
            message
            or "La clave de idempotencia ya fue usada con un payload diferente."
        )
        super().__init__(self.message)


class IdempotencyInProgress(DomainError):
    """La operación idempotente sigue activa o quedó reservada."""

    def __init__(
        self,
        *,
        tool_name: str,
        idempotency_key: str,
        message: str | None = None,
    ):
        self.tool_name = tool_name
        self.idempotency_key = idempotency_key
        self.message = (
            message
            or "La operación asociada a esta clave de idempotencia sigue en progreso."
        )
        super().__init__(self.message)


class IdempotencyStateUncertain(DomainError):
    """La operación pudo haberse aplicado, pero su resultado no quedó confirmado."""

    def __init__(
        self,
        *,
        tool_name: str,
        idempotency_key: str,
        message: str | None = None,
    ):
        self.tool_name = tool_name
        self.idempotency_key = idempotency_key
        self.message = (
            message
            or "El estado de la operación idempotente es incierto; pudo haberse aplicado."
        )
        super().__init__(self.message)
