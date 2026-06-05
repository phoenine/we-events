from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from core.common.log import logger


class ThreadManager(threading.Thread):
    """轻量托管线程包装。

    Python 无法安全地强制终止正在运行的线程。本包装仅提供：
    - 一致的链式启动
    - 协作用途的停止请求标志
    - 异常捕获与诊断
    - 请求停止时可选的等待完成
    """

    def __init__(
        self,
        target: Callable[..., Any] | None = None,
        name: str | None = None,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        daemon: bool | None = None,
    ) -> None:
        super().__init__(name=name, daemon=daemon)
        self._target_func = target
        self._target_args = args
        self._target_kwargs = kwargs or {}
        self._stop_requested = threading.Event()
        self.exception: BaseException | None = None

    def start(self) -> None:
        """如果线程尚未启动则启动。"""
        if self.is_alive():
            return None
        super().start()
        return None

    def stop(self, timeout: float | None = None) -> bool:
        """请求协作者停止并可选等待完成。

        返回 True 表示线程已不再存活。目标函数必须显式检查 `stop_requested`
        才能中断长时间运行的任务。
        """
        self._stop_requested.set()
        if timeout is not None and self.is_alive():
            self.join(timeout=timeout)
        return not self.is_alive()

    def force_stop(self, timeout: float | None = None) -> bool:
        """stop() 的兼容别名。

        不会强制终止线程。保留此方法避免破坏旧的调用方，同时在代码中明确表明行为。
        """
        logger.warning("ThreadManager.force_stop() cannot kill Python threads; requesting stop")
        return self.stop(timeout=timeout)

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    @property
    def failed(self) -> bool:
        return self.exception is not None

    def run(self) -> None:
        try:
            if self._target_func is None:
                return
            self._target_func(*self._target_args, **self._target_kwargs)
        except BaseException as e:
            self.exception = e
            logger.exception(f"线程 {self.name} 发生异常")
        finally:
            logger.info(f"线程 {self.name} 已停止")
