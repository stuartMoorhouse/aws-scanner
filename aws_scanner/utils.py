"""Utility functions for AWS Scanner."""
import time
import functools
from typing import Callable, TypeVar, Any, Optional, Type, Tuple
from botocore.exceptions import ClientError, BotoCoreError, ConnectionError
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class AWSAccessDeniedError(Exception):
    """Raised when AWS access is denied."""
    pass


class AWSRateLimitError(Exception):
    """Raised when AWS rate limit is hit."""
    pass


def handle_aws_error(error: Exception, context: str) -> None:
    """
    Handle AWS errors with proper logging and categorization.
    
    Args:
        error: The exception that occurred
        context: Context string describing what was being done
        
    Raises:
        AWSAccessDeniedError: If access was denied
        AWSRateLimitError: If rate limited
    """
    if isinstance(error, ClientError):
        error_code = error.response['Error']['Code']
        error_message = error.response['Error']['Message']
        
        if error_code in ['AccessDeniedException', 'UnauthorizedOperation', 'AccessDenied']:
            logger.warning(f"Access denied for {context}: {error_message}")
            raise AWSAccessDeniedError(f"Access denied for {context}")
        elif error_code in ['RequestLimitExceeded', 'Throttling', 'TooManyRequestsException']:
            logger.warning(f"Rate limit hit for {context}: {error_message}")
            raise AWSRateLimitError(f"Rate limit hit for {context}")
        else:
            logger.error(f"AWS error in {context}: {error_code} - {error_message}")
            raise
    else:
        logger.exception(f"Unexpected error in {context}")
        raise


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (ClientError, ConnectionError, AWSRateLimitError)
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to retry function calls with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        backoff_factor: Factor to multiply delay by after each retry
        exceptions: Tuple of exception types to retry on
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {str(e)}. "
                            f"Retrying in {delay} seconds..."
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(f"All {max_attempts} attempts failed for {func.__name__}")
                        
            # If we get here, all retries failed
            if last_exception:
                raise last_exception
            else:
                raise RuntimeError(f"All retry attempts failed for {func.__name__}")
                
        return wrapper
    return decorator


class RateLimiter:
    """Simple rate limiter using token bucket algorithm."""
    
    def __init__(self, rate: float, burst: Optional[int] = None):
        """
        Initialize rate limiter.
        
        Args:
            rate: Number of requests per second allowed
            burst: Maximum burst size (defaults to rate)
        """
        self.rate = rate
        self.burst = burst or int(rate)
        self.tokens = float(self.burst)
        self.last_update = time.time()
        
    def acquire(self, tokens: int = 1) -> float:
        """
        Acquire tokens, blocking if necessary.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            Time waited in seconds
        """
        while True:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0
            else:
                # Calculate wait time
                deficit = tokens - self.tokens
                wait_time = deficit / self.rate
                logger.debug(f"Rate limit: waiting {wait_time:.2f}s")
                time.sleep(wait_time)
                return wait_time


def paginate_with_retry(paginator: Any, **kwargs: Any) -> Any:
    """
    Paginate through AWS results with retry logic.
    
    Args:
        paginator: Boto3 paginator object
        **kwargs: Arguments to pass to paginator
        
    Yields:
        Pages from the paginator
    """
    @retry_with_backoff()
    def get_page(page_iterator: Any) -> Any:
        return next(page_iterator)
        
    page_iterator = paginator.paginate(**kwargs)
    
    while True:
        try:
            page = get_page(page_iterator)
            yield page
        except StopIteration:
            break