import queue
import threading
import time
import gc
from typing import Callable, Any
from core.common.log import logger


class TaskQueueManager:
    """任务队列管理器，用于管理和执行排队任务"""

    def __init__(self, maxsize=0, tag: str = ""):
        """初始化任务队列"""
        self._queue = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self._is_running = False
        self.tag = tag

    def add_task(self, task: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """添加任务到队列

        Args:
            task: 要执行的任务函数
            *args: 任务函数的参数
            **kwargs: 任务函数的关键字参数
        """
        if not self._is_running:
            self.run_task_background()
        self._queue.put((task, args, kwargs))
        logger.success(f"{self.tag}队列任务添加成功\n")

    def run_task_background(self) -> None:
        with self._lock:
            if self._is_running:
                logger.warning("队列任务已在后台运行，忽略重复启动")
                return
            self._is_running = True
        threading.Thread(target=self.run_tasks, daemon=True).start()
        logger.warning("队列任务后台运行")

    def run_tasks(self, timeout: float = 1.0) -> None:
        """执行队列中的所有任务，并持续运行以接收新任务"""
        try:
            while True:
                with self._lock:
                    if not self._is_running:
                        break
                try:
                    # 阻塞获取任务，避免CPU空转
                    task, args, kwargs = self._queue.get(timeout=timeout)
                    try:
                        start_time = time.time()
                        task(*args, **kwargs)
                        duration = time.time() - start_time
                        logger.info(f"\n任务执行完成, 耗时: {duration:.2f}秒")
                    except Exception as e:
                        logger.error(f"队列任务执行失败: {e}")
                    finally:
                        self._queue.task_done()
                except queue.Empty:
                    continue
        finally:
            with self._lock:
                self._is_running = False
            gc.collect()

    def get_queue_info(self) -> dict:
        """获取队列的当前状态信息"""
        with self._lock:
            return {
                "is_running": self._is_running,
                "pending_tasks": self._queue.qsize(),
            }

    def join(self) -> None:
        """阻塞等待队列中的所有任务完成"""
        self._queue.join()

    def stop(self) -> None:
        """停止任务执行"""
        with self._lock:
            self._is_running = False

    def clear_queue(self) -> None:
        """清空队列中的所有任务"""
        with self._lock:
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break
            logger.success("队列已清空")

    def delete_queue(self) -> None:
        """删除队列(停止并清空所有任务)"""
        with self._lock:
            self._is_running = False
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break
            logger.success("队列已删除")


TaskQueue = TaskQueueManager(tag="默认队列")

if __name__ == "__main__":

    def task1():
        time.sleep(3)
        logger.info("执行任务1")
        time.sleep(3)

    def task2(name):
        time.sleep(2)
        logger.info(f"执行任务2, 参数: {name}")
        time.sleep(6)

    manager = TaskQueueManager(tag="默认队列")
    manager.run_task_background()
    manager.add_task(task1)
    manager.add_task(task2, "测试任务")

    manager.join()
    manager.stop()
