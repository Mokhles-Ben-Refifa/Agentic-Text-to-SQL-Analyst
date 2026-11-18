"""Langfuse Observability and Tracing integration."""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def get_langfuse_callback(**kwargs: Any) -> Any:
    """Returns a Langfuse CallbackHandler if credentials are configured in the environment."""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    # Only initialize if valid non-template keys are provided
    if (
        public_key
        and secret_key
        and not public_key.startswith("your_")
        and not secret_key.startswith("your_")
    ):
        try:
            from langfuse.langchain import CallbackHandler

            return CallbackHandler(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
                **kwargs,
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Langfuse callback handler: {e}")
            return None
    return None
