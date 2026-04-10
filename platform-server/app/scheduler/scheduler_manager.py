"""
APScheduler 调度器管理器
"""
import asyncio
import inspect
from typing import Optional, Dict, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from app.core.logger import get_logger

logger = get_logger()


class SchedulerManager:
    """调度器管理器 - 单例模式"""
    
    _instance: Optional["SchedulerManager"] = None
    _scheduler: Optional[AsyncIOScheduler] = None
    
    def __new__(cls) -> "SchedulerManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "SchedulerManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def init_scheduler(self) -> AsyncIOScheduler:
        """初始化调度器"""
        if self._scheduler is not None:
            return self._scheduler
        
        # 配置 JobStores 和 Executors
        jobstores = {
            'default': MemoryJobStore()
        }
        
        executors = {
            'default': ThreadPoolExecutor(20),  # 默认线程池，20个线程
            'generation': ThreadPoolExecutor(10),  # GENERATION 任务线程池
            'critic': ThreadPoolExecutor(10),  # CRITIC 任务线程池
        }
        
        job_defaults = {
            'coalesce': False,  # 不合并任务
            'max_instances': 3,  # 同一任务最多并发3个实例
        }
        
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone='Asia/Shanghai'
        )
        
        logger.info("Scheduler initialized with AsyncIOScheduler")
        return self._scheduler
    
    def start(self) -> None:
        """启动调度器"""
        if self._scheduler is None:
            self.init_scheduler()
        
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler started")
    
    def shutdown(self) -> None:
        """关闭调度器"""
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler shutdown")
    
    def add_cron_job(
        self,
        func,
        job_id: str,
        cron_expression: str,
        args: tuple = None,
        kwargs: dict = None,
        executor: str = 'default',
        misfire_grace_time: int = 3600,
        replace_existing: bool = True
    ) -> None:
        """
        添加 cron 定时任务
        
        Args:
            func: 要执行的函数
            job_id: 任务唯一标识
            cron_expression: cron 表达式 (5字段格式: 分 时 日 月 周)
            args: 函数位置参数
            kwargs: 函数关键字参数
            executor: 使用的执行器
            misfire_grace_time: 任务错过执行的容忍时间(秒)
            replace_existing: 如果任务已存在，是否替换
        """
        if self._scheduler is None:
            self.init_scheduler()
        
        # 解析 cron 表达式 (支持 5 字段和 6 字段格式)
        cron_parts = cron_expression.strip().split()
        
        if len(cron_parts) == 5:
            # 标准 5 字段格式: 分 时 日 月 周
            trigger = CronTrigger(
                minute=cron_parts[0],
                hour=cron_parts[1],
                day=cron_parts[2],
                month=cron_parts[3],
                day_of_week=cron_parts[4],
                timezone='Asia/Shanghai'
            )
        elif len(cron_parts) == 6:
            # 6 字段格式: 秒 分 时 日 月 周
            trigger = CronTrigger(
                second=cron_parts[0],
                minute=cron_parts[1],
                hour=cron_parts[2],
                day=cron_parts[3],
                month=cron_parts[4],
                day_of_week=cron_parts[5],
                timezone='Asia/Shanghai'
            )
        else:
            raise ValueError(f"Invalid cron expression: {cron_expression}")
        
        # 检查是否是 async 函数
        is_async = asyncio.iscoroutinefunction(func) or inspect.iscoroutinefunction(func)
        
        if is_async:
            # async 函数：不指定 executor，让 AsyncIOScheduler 在事件循环中执行
            self._scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                args=args or (),
                kwargs=kwargs or {},
                misfire_grace_time=misfire_grace_time,
                replace_existing=replace_existing
            )
            logger.info(f"Added async cron job: {job_id}, cron: {cron_expression} (running in event loop)")
        else:
            # 同步函数：使用指定的 executor（线程池）
            self._scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                args=args or (),
                kwargs=kwargs or {},
                executor=executor,
                misfire_grace_time=misfire_grace_time,
                replace_existing=replace_existing
            )
            logger.info(f"Added sync cron job: {job_id}, cron: {cron_expression}, executor: {executor}")
    
    def remove_job(self, job_id: str) -> bool:
        """移除任务"""
        if self._scheduler is None:
            return False
        
        try:
            self._scheduler.remove_job(job_id)
            logger.info(f"Removed job: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to remove job {job_id}: {e}")
            return False
    
    def pause_job(self, job_id: str) -> bool:
        """暂停任务"""
        if self._scheduler is None:
            return False
        
        try:
            self._scheduler.pause_job(job_id)
            logger.info(f"Paused job: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to pause job {job_id}: {e}")
            return False
    
    def resume_job(self, job_id: str) -> bool:
        """恢复任务"""
        if self._scheduler is None:
            return False
        
        try:
            self._scheduler.resume_job(job_id)
            logger.info(f"Resumed job: {job_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to resume job {job_id}: {e}")
            return False
    
    def get_job(self, job_id: str) -> Optional[Any]:
        """获取任务"""
        if self._scheduler is None:
            return None
        
        return self._scheduler.get_job(job_id)
    
    def get_jobs(self) -> list:
        """获取所有任务"""
        if self._scheduler is None:
            return []
        
        return self._scheduler.get_jobs()


# 全局调度器管理器实例
def get_scheduler_manager() -> SchedulerManager:
    """获取全局调度器管理器"""
    return SchedulerManager.get_instance()

