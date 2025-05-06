# app/middleware/logging.py
import time
import uuid
from typing import Callable, Awaitable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from loguru import logger

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid.uuid4()) # ID unik per request
        start_time = time.time()

        # Menambahkan request_id ke state agar bisa diakses di endpoint (opsional)
        request.state.request_id = request_id

        # Log Request Masuk
        # Hindari logging body untuk request sensitif atau besar
        logger.info(
            f"RID:{request_id} START Request: {request.method} {request.url.path} "
            f"Client:{request.client.host}:{request.client.port}"
        )
        # Contoh log header (hati-hati dengan data sensitif seperti Authorization)
        # logger.debug(f"RID:{request_id} Headers: {dict(request.headers)}")

        try:
            response = await call_next(request)
            process_time = (time.time() - start_time) * 1000 # ms
            status_code = response.status_code

            # Log Response Keluar
            logger.info(
                f"RID:{request_id} END Request: {request.method} {request.url.path} "
                f"Status:{status_code} Duration:{process_time:.2f}ms"
            )

        except Exception as e:
            process_time = (time.time() - start_time) * 1000 # ms
            logger.error(
                f"RID:{request_id} FAILED Request: {request.method} {request.url.path} "
                f"Error:{e} Duration:{process_time:.2f}ms",
                exc_info=True # Sertakan traceback
            )
            # Penting: Raise ulang exception agar handler lain (misal generic_exception_handler) menangkapnya
            raise e

        return response