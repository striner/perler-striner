class BackendError(Exception):
    status_code = 500
    public_message = "internal server error"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.public_message)
        self.public_message = message or self.public_message


class InvalidRequestError(BackendError):
    status_code = 422
    public_message = "invalid processing request"


class UploadTooLargeError(BackendError):
    status_code = 413
    public_message = "uploaded image is too large"


class AlgorithmNotImplementedError(BackendError):
    status_code = 501
    public_message = "requested algorithm is not registered"


class AlgorithmVersionAmbiguousError(BackendError):
    status_code = 409
    public_message = "algorithm version is ambiguous"


class AlgorithmContractError(BackendError):
    status_code = 502
    public_message = "algorithm returned an invalid result"


class AlgorithmTimeoutError(BackendError):
    status_code = 504
    public_message = "algorithm execution timed out"


class AlgorithmProcessingError(BackendError):
    status_code = 422
    public_message = "image could not be processed reliably"


class BackendBusyError(BackendError):
    status_code = 503
    public_message = "backend request queue is full"


class AlgorithmUnavailableError(BackendError):
    status_code = 503
    public_message = "requested algorithm is unavailable"
