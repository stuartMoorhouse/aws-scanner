"""Logging configuration for AWS Scanner."""
import logging
import logging.config
import json
from typing import Dict, Any
import sys


def setup_logging(log_level: str = 'INFO', log_format: str = 'text') -> None:
    """
    Set up logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Format for logs ('text' or 'json')
    """
    config: Dict[str, Any] = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'text': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'datefmt': '%Y-%m-%d %H:%M:%S'
            },
            'json': {
                'class': 'aws_scanner.logger.JSONFormatter'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': log_level,
                'formatter': log_format,
                'stream': 'ext://sys.stdout'
            }
        },
        'loggers': {
            'aws_scanner': {
                'level': log_level,
                'handlers': ['console'],
                'propagate': False
            },
            'boto3': {
                'level': 'WARNING',
                'handlers': ['console'],
                'propagate': False
            },
            'botocore': {
                'level': 'WARNING',
                'handlers': ['console'],
                'propagate': False
            },
            'urllib3': {
                'level': 'WARNING',
                'handlers': ['console'],
                'propagate': False
            }
        },
        'root': {
            'level': log_level,
            'handlers': ['console']
        }
    }
    
    logging.config.dictConfig(config)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_obj = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)
            
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'exc_info',
                          'exc_text', 'stack_info', 'pathname', 'processName',
                          'relativeCreated', 'thread', 'threadName', 'getMessage']:
                log_obj[key] = value
                
        return json.dumps(log_obj)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)