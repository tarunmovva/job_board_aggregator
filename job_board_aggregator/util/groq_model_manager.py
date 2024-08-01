"""
Groq Model Manager with LFU (Least Frequently Used) algorithm for model rotation.
Implements 1-minute sliding window to track model usage and select least used models.
Async-safe version for concurrent processing.
"""

import os
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from job_board_aggregator.config import logger


class GroqModelManager:
    """
    Manages Groq model selection using LFU algorithm with sliding window.
    Includes rate limit tracking to temporarily mark models as unavailable.
    """
    
    def __init__(self, window_minutes: int = 1):
        """
        Initialize the Groq model manager.
        
        Args:
            window_minutes: Size of sliding window in minutes for LFU calculation
        """
        self.window_minutes = window_minutes
        self.window_seconds = window_minutes * 60
        
        # Async-safe locks for concurrent access
        self._lock = asyncio.Lock()
        
        # Load configuration
        self.rotation_enabled = os.getenv('GROQ_MODEL_ROTATION_ENABLED', 'true').lower() == 'true'
        self.models = self._load_models()
        self.fallback_model = os.getenv('GROQ_MODEL', 'llama3-70b-8192')
        
        # Usage tracking: {model_name: [(timestamp, success), ...]}
        self.usage_history: Dict[str, List[Tuple[float, bool]]] = defaultdict(list)
        
        # Rate limit tracking: {model_name: rate_limit_expiry_timestamp}
        self.rate_limited_models: Dict[str, float] = {}
        
        # Statistics
        self.stats = {
            'total_requests': 0,
            'window_cleanups': 0,
            'model_selections': defaultdict(int),
            'rate_limit_hits': defaultdict(int)
        }
        
        logger.info(f"GroqModelManager initialized:")
        logger.info(f"  Rotation enabled: {self.rotation_enabled}")
        logger.info(f"  Models available: {len(self.models)}")
        logger.info(f"  Models: {self.models}")
        logger.info(f"  Window size: {window_minutes} minutes")
        logger.info(f"  Fallback model: {self.fallback_model}")
    
    def _load_models(self) -> List[str]:
        """Load available models from environment configuration."""
        models_env = os.getenv('GROQ_MODELS', '')
        
        if not models_env:
            # Fall back to single model configuration
            fallback = os.getenv('GROQ_MODEL', 'llama3-70b-8192')
            logger.warning(f"GROQ_MODELS not set, using single model: {fallback}")
            return [fallback]
        
        # Parse comma-separated models
        models = [model.strip() for model in models_env.split(',') if model.strip()]
        
        if not models:
            fallback = os.getenv('GROQ_MODEL', 'llama3-70b-8192')
            logger.warning("No valid models found in GROQ_MODELS, using fallback")
            return [fallback]
        
        return models
    
    def _cleanup_old_entries(self) -> int:
        """
        Remove usage entries older than the sliding window and cleanup expired rate limits.
        
        Returns:
            Number of entries removed
        """
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        removed_count = 0
        
        for model_name in list(self.usage_history.keys()):
            original_count = len(self.usage_history[model_name])
            
            # Keep only entries within the window
            self.usage_history[model_name] = [
                (timestamp, success) for timestamp, success in self.usage_history[model_name]
                if timestamp > cutoff_time
            ]
            
            new_count = len(self.usage_history[model_name])
            removed_count += (original_count - new_count)
            
            # Remove empty entries
            if not self.usage_history[model_name]:
                del self.usage_history[model_name]
        
        # Cleanup expired rate limits
        expired_models = []
        for model_name, expiry_time in self.rate_limited_models.items():
            if current_time >= expiry_time:
                expired_models.append(model_name)
        
        for model_name in expired_models:
            del self.rate_limited_models[model_name]
            logger.info(f"[LFU] Rate limit expired for model {model_name}, marking as available")
        
        if removed_count > 0:
            self.stats['window_cleanups'] += 1
            logger.debug(f"[LFU] Window cleanup: removed {removed_count} entries older than {self.window_minutes}min")
        
        return removed_count
    
    def _is_model_available(self, model_name: str) -> bool:
        """
        Check if a model is currently available (not rate limited).
        
        Args:
            model_name: Name of the model to check
            
        Returns:
            True if model is available, False if rate limited
        """
        current_time = time.time()
        
        # Check if model is currently rate limited
        if model_name in self.rate_limited_models:
            expiry_time = self.rate_limited_models[model_name]
            if current_time < expiry_time:
                return False
            else:
                # Rate limit has expired, remove from tracking
                del self.rate_limited_models[model_name]
                logger.info(f"[LFU] Rate limit expired for model {model_name}, marking as available")
        
        return True
    
    def mark_model_rate_limited(self, model_name: str, retry_after_seconds: float = 60.0) -> None:
        """
        Mark a model as rate limited until the retry time expires.
        
        Args:
            model_name: Name of the model that hit rate limit
            retry_after_seconds: Number of seconds until the model is available again
        """
        expiry_time = time.time() + retry_after_seconds
        self.rate_limited_models[model_name] = expiry_time
        self.stats['rate_limit_hits'][model_name] += 1
        
        logger.warning(f"[LFU] Model {model_name} marked as rate limited for {retry_after_seconds:.1f}s (until {datetime.fromtimestamp(expiry_time).strftime('%H:%M:%S')})")
    
    def get_available_models(self) -> List[str]:
        """
        Get list of currently available (non-rate-limited) models.
        
        Returns:
            List of available model names
        """
        available_models = []
        for model in self.models:
            if self._is_model_available(model):
                available_models.append(model)
        
        return available_models
    
    def _get_model_usage_count(self, model_name: str) -> int:
        """
        Get the usage count for a model within the current window.
        
        Args:
            model_name: Name of the model
            
        Returns:
            Number of times the model was used in the current window
        """
        if model_name not in self.usage_history:
            return 0
        
        # Count entries, including pending ones (success=None)
        return len(self.usage_history[model_name])
        """
        Get the usage count for a model within the current window.
        
        Args:
            model_name: Name of the model
            
        Returns:
            Number of times the model was used in the current window
        """
        if model_name not in self.usage_history:
            return 0
        
        # Count entries, including pending ones (success=None)
        return len(self.usage_history[model_name])
    
    def _get_model_success_rate(self, model_name: str) -> float:
        """
        Get the success rate for a model within the current window.
        
        Args:
            model_name: Name of the model
            
        Returns:
            Success rate as a float between 0.0 and 1.0
        """
        if model_name not in self.usage_history:
            return 1.0  # Assume new models are good
        
        entries = self.usage_history[model_name]
        if not entries:
            return 1.0
        
        # Only count completed entries (ignore pending ones with success=None)
        completed_entries = [(t, s) for t, s in entries if s is not None]
        if not completed_entries:
            return 1.0  # No completed entries yet, assume good
        
        successful_calls = sum(1 for _, success in completed_entries if success)
        return successful_calls / len(completed_entries)
    
    async def get_next_model(self) -> str:
        """
        Get the next model to use based on LFU algorithm, skipping rate-limited models.
        
        Returns:
            Model name to use for the next request
        """
        async with self._lock:
            # Clean up old entries first
            self._cleanup_old_entries()
            
            # If rotation is disabled, always return fallback model (if available)
            if not self.rotation_enabled:
                if self._is_model_available(self.fallback_model):
                    logger.debug(f"[LFU] Rotation disabled, using fallback model: {self.fallback_model}")
                    return self.fallback_model
                else:
                    logger.warning(f"[LFU] Fallback model {self.fallback_model} is rate limited, but rotation is disabled")
                    return self.fallback_model
            
            # Get available (non-rate-limited) models
            available_models = self.get_available_models()
            
            if not available_models:
                logger.warning("[LFU] All models are rate limited! Returning fallback model anyway")
                return self.fallback_model
            
            # If only one model available, return it
            if len(available_models) == 1:
                model = available_models[0]
                logger.debug(f"[LFU] Single available model: {model}")
                return model
            
            # Calculate usage scores for available models only
            model_scores = []
            for i, model in enumerate(available_models):
                usage_count = self._get_model_usage_count(model)
                success_rate = self._get_model_success_rate(model)
                selection_count = self.stats['model_selections'].get(model, 0)
                
                # LFU score: lower is better
                # Factor in success rate: failed models get higher scores (less preferred)
                # Add selection count to prevent concurrent requests from all picking same model
                base_score = usage_count / max(success_rate, 0.1)  # Avoid division by zero
                selection_penalty = selection_count * 0.1  # Small penalty for recent selections
                tie_breaker = i * 0.01  # Ensure different models chosen when all else equal
                
                lfu_score = base_score + selection_penalty + tie_breaker
                
                model_scores.append((lfu_score, model))
                logger.debug(f"[LFU] Available model {model}: usage={usage_count}, success_rate={success_rate:.2f}, selections={selection_count}, score={lfu_score:.2f}")
            
            # Sort by score (ascending - least frequently used first)
            model_scores.sort(key=lambda x: x[0])
            selected_model = model_scores[0][1]
            
            # Update statistics IMMEDIATELY to affect next concurrent selection
            self.stats['total_requests'] += 1
            self.stats['model_selections'][selected_model] += 1
            
            # Pre-record a "selection" event to track model allocation
            current_time = time.time()
            if selected_model not in self.usage_history:
                self.usage_history[selected_model] = []
            # Add a temporary "selection" marker that will be updated by record_usage
            self.usage_history[selected_model].append((current_time, None))  # None indicates pending
            
            logger.info(f"[LFU] Selected model: {selected_model} (score: {model_scores[0][0]:.2f}) from {len(available_models)} available models")
            
            return selected_model
    
    async def record_usage(self, model_name: str, success: bool, timestamp: Optional[float] = None) -> None:
        """
        Record a model usage event (async-safe).
        
        Args:
            model_name: Name of the model used
            success: Whether the request was successful
            timestamp: Unix timestamp of the event (defaults to current time)
        """
        async with self._lock:
            if timestamp is None:
                timestamp = time.time()
            
            # Find and update the most recent pending selection (marked with None)
            if model_name in self.usage_history:
                for i in range(len(self.usage_history[model_name]) - 1, -1, -1):
                    entry_time, entry_success = self.usage_history[model_name][i]
                    # Find the most recent pending entry (success=None) within 5 seconds
                    if entry_success is None and abs(timestamp - entry_time) <= 5.0:
                        # Update the pending entry with actual result
                        self.usage_history[model_name][i] = (timestamp, success)
                        break
                else:
                    # No pending entry found, add new entry
                    self.usage_history[model_name].append((timestamp, success))
            else:
                # First usage for this model
                self.usage_history[model_name] = [(timestamp, success)]
            
            status = "success" if success else "failure"
            logger.debug(f"[LFU] Recorded {status} for model {model_name} at {datetime.fromtimestamp(timestamp)}")
    
    def get_usage_stats(self) -> Dict:
        """
        Get comprehensive usage statistics.
        
        Returns:
            Dictionary containing usage statistics
        """
        self._cleanup_old_entries()
        
        current_time = time.time()
        window_start = datetime.fromtimestamp(current_time - self.window_seconds)
        
        model_stats = {}
        for model in self.models:
            usage_count = self._get_model_usage_count(model)
            success_rate = self._get_model_success_rate(model)
            
            successful_calls = 0
            failed_calls = 0
            last_used = None
            
            if model in self.usage_history:
                for timestamp, success in self.usage_history[model]:
                    if success:
                        successful_calls += 1
                    else:
                        failed_calls += 1
                    
                    if last_used is None or timestamp > last_used:
                        last_used = timestamp
            
            model_stats[model] = {
                'usage_count': usage_count,
                'successful_calls': successful_calls,
                'failed_calls': failed_calls,
                'success_rate': success_rate,
                'last_used': datetime.fromtimestamp(last_used) if last_used else None,
                'is_rate_limited': not self._is_model_available(model),
                'rate_limit_expiry': datetime.fromtimestamp(self.rate_limited_models[model]) if model in self.rate_limited_models else None,
                'rate_limit_hits': self.stats['rate_limit_hits'].get(model, 0)
            }
        
        return {
            'window_start': window_start,
            'window_minutes': self.window_minutes,
            'rotation_enabled': self.rotation_enabled,
            'total_requests': self.stats['total_requests'],
            'window_cleanups': self.stats['window_cleanups'],
            'available_models': self.models,
            'currently_available_models': self.get_available_models(),
            'rate_limited_models': len(self.rate_limited_models),
            'model_selections': dict(self.stats['model_selections']),
            'rate_limit_hits': dict(self.stats['rate_limit_hits']),
            'model_stats': model_stats
        }
    
    def reset_stats(self) -> None:
        """Reset all usage statistics and history."""
        self.usage_history.clear()
        self.rate_limited_models.clear()
        self.stats = {
            'total_requests': 0,
            'window_cleanups': 0,
            'model_selections': defaultdict(int),
            'rate_limit_hits': defaultdict(int)
        }
        logger.info("[LFU] Usage statistics, history, and rate limits reset")


# Global singleton instance
_model_manager_instance: Optional[GroqModelManager] = None


def get_model_manager() -> GroqModelManager:
    """
    Get the global GroqModelManager instance (singleton pattern).
    
    Returns:
        GroqModelManager instance
    """
    global _model_manager_instance
    
    if _model_manager_instance is None:
        window_minutes = int(os.getenv('GROQ_LFU_WINDOW_MINUTES', '1'))
        _model_manager_instance = GroqModelManager(window_minutes=window_minutes)
    
    return _model_manager_instance


def reset_model_manager() -> None:
    """Reset the global model manager instance (useful for testing)."""
    global _model_manager_instance
    _model_manager_instance = None
