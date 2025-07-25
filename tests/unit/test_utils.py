"""Unit tests for utilities."""
import pytest
import time
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError, ConnectionError

from aws_scanner.utils import (
    handle_aws_error,
    retry_with_backoff,
    RateLimiter,
    paginate_with_retry,
    AWSAccessDeniedError,
    AWSRateLimitError
)


class TestHandleAWSError:
    """Test cases for handle_aws_error function."""
    
    def test_access_denied_error(self):
        """Test handling of access denied errors."""
        error = ClientError(
            {'Error': {'Code': 'AccessDeniedException', 'Message': 'Access denied'}},
            'DescribeInstances'
        )
        
        with pytest.raises(AWSAccessDeniedError):
            handle_aws_error(error, 'test context')
    
    def test_unauthorized_operation_error(self):
        """Test handling of unauthorized operation errors."""
        error = ClientError(
            {'Error': {'Code': 'UnauthorizedOperation', 'Message': 'Not authorized'}},
            'DescribeInstances'
        )
        
        with pytest.raises(AWSAccessDeniedError):
            handle_aws_error(error, 'test context')
    
    def test_rate_limit_error(self):
        """Test handling of rate limit errors."""
        error = ClientError(
            {'Error': {'Code': 'RequestLimitExceeded', 'Message': 'Too many requests'}},
            'DescribeInstances'
        )
        
        with pytest.raises(AWSRateLimitError):
            handle_aws_error(error, 'test context')
    
    def test_throttling_error(self):
        """Test handling of throttling errors."""
        error = ClientError(
            {'Error': {'Code': 'Throttling', 'Message': 'Rate exceeded'}},
            'DescribeInstances'
        )
        
        with pytest.raises(AWSRateLimitError):
            handle_aws_error(error, 'test context')
    
    def test_other_client_error(self):
        """Test handling of other client errors."""
        error = ClientError(
            {'Error': {'Code': 'InvalidParameterValue', 'Message': 'Invalid value'}},
            'DescribeInstances'
        )
        
        with pytest.raises(ClientError):
            handle_aws_error(error, 'test context')
    
    def test_non_client_error(self):
        """Test handling of non-ClientError exceptions."""
        error = ValueError('Some error')
        
        with pytest.raises(ValueError):
            handle_aws_error(error, 'test context')


class TestRetryWithBackoff:
    """Test cases for retry_with_backoff decorator."""
    
    def test_successful_call_no_retry(self):
        """Test successful function call without retry."""
        mock_func = Mock(return_value='success')
        decorated = retry_with_backoff(max_attempts=3)(mock_func)
        
        result = decorated()
        
        assert result == 'success'
        assert mock_func.call_count == 1
    
    def test_retry_on_client_error(self):
        """Test retry on ClientError."""
        mock_func = Mock()
        mock_func.side_effect = [
            ClientError({'Error': {'Code': 'Throttling'}}, 'Test'),
            ClientError({'Error': {'Code': 'Throttling'}}, 'Test'),
            'success'
        ]
        
        decorated = retry_with_backoff(
            max_attempts=3,
            initial_delay=0.01,
            backoff_factor=2.0
        )(mock_func)
        
        result = decorated()
        
        assert result == 'success'
        assert mock_func.call_count == 3
    
    def test_max_attempts_exceeded(self):
        """Test that exception is raised after max attempts."""
        error = ConnectionError('Connection failed')
        mock_func = Mock(side_effect=error)
        
        decorated = retry_with_backoff(
            max_attempts=3,
            initial_delay=0.01
        )(mock_func)
        
        with pytest.raises(ConnectionError):
            decorated()
        
        assert mock_func.call_count == 3
    
    def test_non_retryable_exception(self):
        """Test that non-retryable exceptions are raised immediately."""
        mock_func = Mock(side_effect=ValueError('Invalid value'))
        
        decorated = retry_with_backoff(
            max_attempts=3,
            exceptions=(ClientError,)
        )(mock_func)
        
        with pytest.raises(ValueError):
            decorated()
        
        assert mock_func.call_count == 1
    
    def test_backoff_timing(self):
        """Test exponential backoff timing."""
        mock_func = Mock()
        mock_func.side_effect = [
            ConnectionError('Failed'),
            ConnectionError('Failed'),
            'success'
        ]
        
        decorated = retry_with_backoff(
            max_attempts=3,
            initial_delay=0.1,
            backoff_factor=2.0
        )(mock_func)
        
        start_time = time.time()
        result = decorated()
        duration = time.time() - start_time
        
        assert result == 'success'
        # Should take at least 0.1 + 0.2 = 0.3 seconds
        assert duration >= 0.3
        assert duration < 0.5  # But not too long


class TestRateLimiter:
    """Test cases for RateLimiter class."""
    
    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(rate=10.0, burst=20)
        
        assert limiter.rate == 10.0
        assert limiter.burst == 20
        assert limiter.tokens == 20.0
    
    def test_default_burst(self):
        """Test default burst size."""
        limiter = RateLimiter(rate=5.0)
        
        assert limiter.burst == 5
        assert limiter.tokens == 5.0
    
    def test_acquire_no_wait(self):
        """Test acquiring tokens without waiting."""
        limiter = RateLimiter(rate=10.0, burst=10)
        
        wait_time = limiter.acquire(5)
        
        assert wait_time == 0.0
        assert limiter.tokens == 5.0
    
    def test_acquire_with_wait(self):
        """Test acquiring tokens with waiting."""
        limiter = RateLimiter(rate=10.0, burst=5)
        
        # Use all tokens
        limiter.acquire(5)
        
        # Try to acquire more
        start_time = time.time()
        wait_time = limiter.acquire(1)
        duration = time.time() - start_time
        
        assert wait_time > 0
        assert duration >= 0.1  # Should wait ~0.1 seconds for 1 token at rate 10/sec
    
    def test_token_replenishment(self):
        """Test that tokens are replenished over time."""
        limiter = RateLimiter(rate=10.0, burst=10)
        
        # Use some tokens
        limiter.acquire(8)
        assert limiter.tokens == 2.0
        
        # Wait for replenishment
        time.sleep(0.5)
        
        # Should have more tokens now
        limiter.acquire(0)  # Update tokens without acquiring
        assert limiter.tokens > 2.0
        assert limiter.tokens <= 10.0  # But not more than burst
    
    def test_burst_limit(self):
        """Test that tokens don't exceed burst limit."""
        limiter = RateLimiter(rate=10.0, burst=5)
        
        # Wait for potential token accumulation
        time.sleep(1.0)
        
        # Tokens should be capped at burst
        limiter.acquire(0)  # Update tokens
        assert limiter.tokens <= 5.0


class TestPaginateWithRetry:
    """Test cases for paginate_with_retry function."""
    
    def test_successful_pagination(self):
        """Test successful pagination without errors."""
        mock_paginator = Mock()
        pages = [
            {'Items': [1, 2, 3]},
            {'Items': [4, 5, 6]},
            {'Items': [7, 8, 9]}
        ]
        mock_paginator.paginate.return_value = iter(pages)
        
        results = list(paginate_with_retry(mock_paginator))
        
        assert results == pages
    
    def test_pagination_with_retry(self):
        """Test pagination with retry on error."""
        mock_paginator = Mock()
        
        # Create an iterator that fails once then succeeds
        def page_generator():
            yield {'Items': [1, 2, 3]}
            raise ClientError({'Error': {'Code': 'Throttling'}}, 'ListItems')
        
        pages = [
            {'Items': [1, 2, 3]},
            {'Items': [4, 5, 6]}
        ]
        
        # First call returns generator that fails
        # Second call returns successful pages
        mock_paginator.paginate.side_effect = [
            page_generator(),
            iter(pages[1:])  # Continue from second page
        ]
        
        with patch('aws_scanner.utils.time.sleep'):  # Speed up test
            results = []
            for page in paginate_with_retry(mock_paginator):
                results.append(page)
                if len(results) >= 2:  # Stop after getting expected pages
                    break
            
            assert len(results) >= 1
            assert results[0] == {'Items': [1, 2, 3]}