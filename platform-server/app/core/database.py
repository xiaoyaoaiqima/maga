"""
Database connection and session management
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from app.core.config import settings
from app.models.base import Base


def _engine_options(url: str, *, analytics: bool = False) -> dict:
    if url.startswith("sqlite"):
        return {
            "echo": settings.MYSQL_ECHO,
            "pool_pre_ping": True,
        }
    if analytics:
        return {
            "echo": settings.MYSQL_ECHO,
            "pool_size": settings.MYSQL_ANALYTICS_POOL_SIZE,
            "max_overflow": settings.MYSQL_ANALYTICS_MAX_OVERFLOW,
            "pool_pre_ping": True,
            "pool_recycle": 1800,
            "pool_timeout": 30,
            "connect_args": {
                "autocommit": False,
                "connect_timeout": 5,
            },
        }
    return {
        "echo": settings.MYSQL_ECHO,
        "pool_size": settings.MYSQL_POOL_SIZE,
        "max_overflow": settings.MYSQL_MAX_OVERFLOW,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_timeout": 30,
        "connect_args": {
            "autocommit": False,
            "connect_timeout": 10,
        },
    }


# Create async engine
# 注意：aiomysql 连接不是线程安全的，每个线程/事件循环应该使用独立的连接
# pool_pre_ping=True 确保连接在使用前被检查，无效连接会被替换
engine: AsyncEngine = create_async_engine(
    settings.MYSQL_DATABASE_URL,
    **_engine_options(settings.MYSQL_DATABASE_URL),
)

# Create async session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Create async analytics engine (分析库)
# 注意：如果分析库不可访问，会在 get_analytics_db 中降级到主库
analytics_engine: AsyncEngine = create_async_engine(
    settings.MYSQL_ANALYTICS_DATABASE_URL,
    **_engine_options(settings.MYSQL_ANALYTICS_DATABASE_URL, analytics=True),
)

# Create async analytics session factory
analytics_async_session_factory = async_sessionmaker(
    analytics_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def init_db() -> None:
    """Initialize database with retry logic"""
    import asyncio
    from sqlalchemy.exc import OperationalError
    import app.models  # noqa: F401
    
    max_retries = 30
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                # Create all tables
                await conn.run_sync(Base.metadata.create_all)
            return  # Success, exit function
        except OperationalError as e:
            if attempt < max_retries - 1:
                print(f"Database connection failed (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                # Last attempt failed, raise the exception
                print(f"Database connection failed after {max_retries} attempts")
                raise
        except Exception as e:
            # For other exceptions, raise immediately
            print(f"Database initialization error: {e}")
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


AsyncSessionDep = Annotated[AsyncSession, Depends(get_db)]


@asynccontextmanager
async def get_db_context():
    """Context manager for database session"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_analytics_db_context():
    """
    分析库 context manager（带自动降级）

    用途：
    - Dashboard 分析查询
    - 报表统计
    - 其他只读查询场景

    降级策略：
    - 如果分析库被禁用（配置开关），自动使用主库
    - 如果分析库不可访问，自动降级到主库
    - 会记录降级日志便于排查

    使用方式：
        async with get_analytics_db_context() as session:
            result = await session.execute(query)
    """
    import logging
    from sqlalchemy.exc import OperationalError

    logger = logging.getLogger(__name__)

    # 检查分析库是否被配置开关禁用
    if not settings.analytics_enabled:
        logger.info(f"⚙️ 分析库已禁用（APP_ENV={settings.APP_ENV}），使用主库进行查询")
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
        return

    # 尝试使用分析库
    try:
        # 快速连接测试
        async with analytics_async_session_factory() as test_session:
            await test_session.execute(text("SELECT 1"))

        # 连接成功，使用分析库
        async with analytics_async_session_factory() as session:
            logger.debug("✅ 使用分析库进行查询")
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    except (OperationalError, Exception) as e:
        # 分析库连接失败，降级到主库
        logger.warning(f"⚠️ 分析库连接失败: {e}，降级到主库进行查询")
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


async def get_analytics_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async analytics database session (分析库)

    用途：
    - Dashboard 分析查询
    - 报表统计
    - 其他只读查询场景

    降级策略：
    - 如果分析库被禁用（配置开关），自动使用主库
    - 如果分析库不可访问，自动降级到主库
    - 会记录降级日志便于排查
    """
    import logging
    from sqlalchemy.exc import OperationalError

    logger = logging.getLogger(__name__)

    # 检查分析库是否被配置开关禁用
    if not settings.analytics_enabled:
        logger.info(f"⚙️ 分析库已禁用（APP_ENV={settings.APP_ENV}），使用主库进行查询")
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
        return

    # 尝试使用分析库
    try:
        # 快速连接测试（发送 ping）
        async with analytics_async_session_factory() as test_session:
            await test_session.execute(text("SELECT 1"))

        # 连接成功，使用分析库
        async with analytics_async_session_factory() as session:
            logger.debug("✅ 使用分析库进行查询")
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    except (OperationalError, Exception) as e:
        # 分析库连接失败，降级到主库
        logger.warning(f"⚠️ 分析库连接失败: {e}，降级到主库进行查询")
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
