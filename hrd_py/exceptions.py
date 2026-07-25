class HRDError(Exception):
    """Base exception for hrd-py"""


class HRDCommunicationError(HRDError):
    """Exception raised for communication errors with HRD API"""


class HRDAuthError(HRDError):
    """Exception raised for authentication errors"""


class HRDAPIError(HRDError):
    """Exception raised when the API returns an error message"""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code
