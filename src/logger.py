import logging
import logging.config
import os
from pathlib import Path

import platformdirs
import structlog
from rich.traceback import install
from structlog.typing import Processor

logger = structlog.getLogger(__name__)


def get_log_level() -> int:
    return int(os.environ.get("PYTHON_LOG_LEVEL", logging.INFO))


def get_pre_chain() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.stdlib.ExtraAdder(),
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
    ]


def get_log_file() -> Path:
    log_dir = platformdirs.user_log_path("agent_joggler", ensure_exists=True)
    log_file = log_dir / "agent_joggler.log"
    return log_file


def setup_logging(name: str) -> None:
    install(show_locals=True)
    pre_chain = get_pre_chain()
    log_file = get_log_file()

    logger.info("Logging to file", log_file=log_file)

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        structlog.processors.JSONRenderer(),
                    ],
                    "foreign_pre_chain": pre_chain,
                },
                "colored": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        structlog.dev.ConsoleRenderer(colors=True),
                    ],
                    "foreign_pre_chain": pre_chain,
                },
            },
            "handlers": {
                "default": {
                    "level": "DEBUG",
                    "class": "logging.StreamHandler",
                    "formatter": "colored",
                },
                "file": {
                    "level": "DEBUG",
                    "class": "logging.handlers.RotatingFileHandler",
                    "maxBytes": 1024 * 1024 * 10,
                    "backupCount": 5,
                    "filename": log_file,
                    "formatter": "plain",
                },
            },
            "loggers": {
                "": {
                    "handlers": ["default", "file"],
                    "level": "DEBUG",
                    "propagate": True,
                },
            },
        }
    )

    structlog.contextvars.bind_contextvars(process_name=name)
    structlog.configure(
        processors=pre_chain
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(get_log_level()),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
