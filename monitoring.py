"""
CRUXpider监控和错误处理模块
"""
import time
import functools
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class APIMonitor:
    """API调用监控器"""
    
    def __init__(self):
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'avg_response_time': 0,
            'last_error': None,
            'uptime_start': time.time()
        }
        self.response_times = []
    
    def record_request(self, success: bool, response_time: float, error: Optional[str] = None):
        """记录API请求统计"""
        self.stats['total_requests'] += 1
        
        if success:
            self.stats['successful_requests'] += 1
        else:
            self.stats['failed_requests'] += 1
            self.stats['last_error'] = error
        
        self.response_times.append(response_time)
        if len(self.response_times) > 100:  # 保持最近100个响应时间
            self.response_times.pop(0)
        
        self.stats['avg_response_time'] = sum(self.response_times) / len(self.response_times)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = time.time() - self.stats['uptime_start']
        return {
            **self.stats,
            'uptime_seconds': uptime,
            'success_rate': self.stats['successful_requests'] / max(1, self.stats['total_requests']) * 100
        }

def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"尝试 {attempt + 1} 失败: {str(e)}, {delay}秒后重试...")
                        time.sleep(delay * (2 ** attempt))  # 指数退避
                    else:
                        logger.error(f"所有重试尝试都失败了: {str(e)}")
            
            raise last_exception
        return wrapper
    return decorator

def monitor_api_call(monitor: APIMonitor):
    """API调用监控装饰器"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                response_time = time.time() - start_time
                monitor.record_request(True, response_time)
                return result
            except Exception as e:
                response_time = time.time() - start_time
                monitor.record_request(False, response_time, str(e))
                raise
        return wrapper
    return decorator

# 全局监控器实例
api_monitor = APIMonitor()
