class HRDError(Exception):
    """Base exception for hrd-py"""
    pass

class HRDCommunicationError(HRDError):
    """Exception raised for communication errors with HRD API"""
    pass

class HRDAuthError(HRDError):
    """Exception raised for authentication errors"""
    pass

class HRDAPIError(HRDError):
    """Exception raised when the API returns an error message"""
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code
