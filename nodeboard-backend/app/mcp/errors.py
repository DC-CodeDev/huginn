"""Errores de dominio MCP — independientes de HTTP y del SDK MCP.

Jerarquía plana para facilitar captura en la capa de transporte.
Los mensajes externos son genéricos para no filtrar información interna.
"""


class MCPAuthenticationError(Exception):
    """Base de errores de autenticación MCP.

    No incluir token, hash, user_id ni detalles internos en el mensaje.
    Todas las credenciales inválidas deben producir el mismo mensaje
    externo genérico.
    """
    pass


class MissingBearerToken(MCPAuthenticationError):
    """El header Authorization está ausente o no es Bearer."""
    pass


class InvalidBearerToken(MCPAuthenticationError):
    """El token Bearer no cumple el formato esperado."""
    pass


class ExpiredMCPToken(MCPAuthenticationError):
    """El token MCP ha expirado."""
    pass


class RevokedMCPToken(MCPAuthenticationError):
    """El token MCP fue revocado."""
    pass


class InsufficientScope(Exception):
    """El contexto MCP no tiene el/los scope(s) requerido(s)."""
    pass


class ConstraintViolation(Exception):
    """El contexto MCP no cumple las constraints sobre el recurso solicitado."""
    pass
