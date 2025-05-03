# AstrBot/data/plugins/astrbot_plugin_sleepmode/main.py

import asyncio
import datetime
import random
from typing import Optional, List

# --- Corrected Import Statements ---
from astrbot.api import (
    AstrBotConfig,
    logger # 使用 astrbot 提供的 logger
)
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent

# 从 filter 模块导入具体的 Enum 类型
from astrbot.api.event.filter import EventMessageType
# --- End of Corrected Import Statements ---


# 全局变量或类属性来存储解析后的时间
_sleep_time_obj: Optional[datetime.time] = None
_wake_time_obj: Optional[datetime.time] = None

@register(
    "astorbot_plugin_sleep",
    "Zhan_Kong", # 请替换成你的名字
    "一个让 AstrBot 在指定时间段内“睡觉”并限制特定群组响应的插件", # 更新描述
    "1.1.0", # 版本号递增
    "https://github.com/zhanwuzhijing/astrbot_plugin_sleep" # 请替换成你的仓库地址或留空
)
class SleepModePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.is_sleeping = False
        self._monitor_task: Optional[asyncio.Task] = None
        self.plugin_enabled = self.config.get("enable_plugin", True) # 读取全局开关

        if not self.plugin_enabled:
            logger.info("睡眠插件：插件已被禁用，将不会运行。")
            return # 如果插件禁用，则不执行后续初始化

        self._parse_times() # 解析配置中的时间
        logger.info(f"睡眠插件加载：睡眠时间 {_sleep_time_obj}, 起床时间 {_wake_time_obj}")

        # 创建后台任务来监控时间
        if _sleep_time_obj and _wake_time_obj:
            self._monitor_task = asyncio.create_task(self._monitor_sleep_schedule())
            logger.info("睡眠插件：已启动睡眠监控任务。")
        else:
            logger.warning("睡眠插件：时间配置无效或解析失败，无法启动睡眠监控任务。请检查插件配置。")

    def _parse_times(self):
        """解析配置文件中的时间字符串"""
        global _sleep_time_obj, _wake_time_obj
        try:
            sleep_str = self.config.get("sleep_time", "23:00")
            wake_str = self.config.get("wake_time", "07:00")
            _sleep_time_obj = datetime.datetime.strptime(sleep_str, "%H:%M").time()
            _wake_time_obj = datetime.datetime.strptime(wake_str, "%H:%M").time()
            logger.debug(f"睡眠插件：成功解析时间 - 睡眠: {_sleep_time_obj}, 起床: {_wake_time_obj}")
        except ValueError as e:
            logger.error(f"睡眠插件：无法解析时间配置 '{sleep_str}' 或 '{wake_str}'。请使用 HH:MM 格式。错误: {e}")
            _sleep_time_obj = None
            _wake_time_obj = None
        except Exception as e:
            logger.error(f"睡眠插件：解析时间时发生未知错误: {e}", exc_info=True)
            _sleep_time_obj = None
            _wake_time_obj = None


    def _is_currently_in_sleep_period(self) -> bool:
        """检查当前时间是否在睡眠时间段内"""
        # 如果插件禁用或时间无效，则不在睡眠期
        if not self.plugin_enabled or not _sleep_time_obj or not _wake_time_obj:
            return False

        now_time = datetime.datetime.now().time()

        if _sleep_time_obj > _wake_time_obj: # 跨天
            return now_time >= _sleep_time_obj or now_time < _wake_time_obj
        elif _sleep_time_obj < _wake_time_obj: # 当天
            return _sleep_time_obj <= now_time < _wake_time_obj
        else: # 时间相同，无效
            return False

    async def _send_or_log_message(self, message: str, message_type: str):
        """辅助函数：记录日志"""
        if message:
            log_msg = f"睡眠插件：{message_type} - {message}"
            logger.info(log_msg)
            print(f"[SleepMode Plugin] {message_type}: {message}")

    async def _monitor_sleep_schedule(self):
        """后台任务，每分钟检查一次时间，管理睡眠状态"""
        await asyncio.sleep(10) # 等待启动

        logger.info("睡眠插件：开始监控睡眠时间表...")
        while True:
            try:
                # 每次循环开始时检查插件是否仍然启用
                self.plugin_enabled = self.config.get("enable_plugin", True)
                if not self.plugin_enabled:
                    logger.info("睡眠插件：检测到插件已被禁用，停止监控任务。")
                    if self.is_sleeping: # 如果禁用时刚好在睡觉，强制唤醒状态
                        self.is_sleeping = False
                        logger.info("睡眠插件：插件禁用，强制设置为清醒状态。")
                    break # 退出监控循环

                if not _sleep_time_obj or not _wake_time_obj:
                    logger.warning("睡眠插件：监控任务检测到时间配置无效，暂停监控循环。请检查配置。")
                    await asyncio.sleep(300)
                    continue

                should_be_sleeping = self._is_currently_in_sleep_period()

                # 状态转换：从未睡 -> 睡
                if should_be_sleeping and not self.is_sleeping:
                    self.is_sleeping = True
                    sleep_msg = self.config.get("sleep_message", "")
                    await self._send_or_log_message(sleep_msg, "进入睡眠")

                # 状态转换：从睡 -> 未睡
                elif not should_be_sleeping and self.is_sleeping:
                    self.is_sleeping = False
                    wake_msg = self.config.get("wake_message", "")
                    max_delay_minutes = self.config.get("max_wake_delay_minutes", 5)
                    delay_seconds = 0
                    if isinstance(max_delay_minutes, int) and max_delay_minutes > 0:
                         delay_seconds = random.randint(0, max_delay_minutes * 60)

                    logger.info(f"睡眠插件：检测到起床时间，将在 {delay_seconds} 秒后发送起床消息。")
                    asyncio.create_task(self._delayed_wake_message(delay_seconds, wake_msg))

                await asyncio.sleep(60) # 每分钟检查一次

            except asyncio.CancelledError:
                logger.info("睡眠插件：监控任务被取消。")
                break
            except Exception as e:
                logger.error(f"睡眠插件：监控任务主循环出错: {e}", exc_info=True)
                await asyncio.sleep(300) # 出错后等待

    async def _delayed_wake_message(self, delay_seconds: int, wake_msg: str):
        """用于延迟发送起床消息的异步函数"""
        try:
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
            # 再次检查插件是否启用，避免在延迟期间被禁用还发送消息
            if self.config.get("enable_plugin", True):
                await self._send_or_log_message(wake_msg, "起床")
            else:
                 logger.info("睡眠插件：延迟起床消息准备发送时检测到插件已禁用，取消发送。")
        except asyncio.CancelledError:
            logger.info("睡眠插件：延迟起床消息任务被取消。")
        except Exception as e:
            logger.error(f"睡眠插件：发送延迟起床消息时出错: {e}", exc_info=True)


    # --- 事件处理器 ---
    @filter.event_message_type(EventMessageType.ALL, priority=100)
    async def handle_sleep_check(self, event: AstrMessageEvent):
        """
        高优先级事件处理器，检查是否启用、是否在睡眠时间、是否在受影响的群组或私聊中。
        如果是，则回复指定消息，并阻止后续处理。
        """
        # 1. 检查插件是否全局启用
        if not self.config.get("enable_plugin", True):
            # logger.debug("睡眠插件：插件已禁用，跳过事件处理。") # 过于频繁，注释掉
            return

        # 2. 检查当前是否在睡眠时间段
        if not self.is_sleeping:
            # logger.debug("睡眠插件：当前非睡眠时间，跳过处理。") # 过于频繁，注释掉
            return

        # 3. 检查当前事件是否应该受睡眠模式影响 (群组白名单 或 私聊设置)
        should_apply_sleep_mode = False
        group_id = event.get_group_id()
        enabled_groups: List[str] = self.config.get("enabled_group_ids", [])
        apply_private = self.config.get("apply_to_private_chat", True)

        if group_id: # 是群聊消息
            # 检查群组 ID 是否在启用列表中 (确保列表非空且 ID 在其中)
            if enabled_groups and group_id in enabled_groups:
                should_apply_sleep_mode = True
                logger.debug(f"睡眠插件：群聊 {group_id} 在白名单中，应用睡眠模式。")
            else:
                logger.debug(f"睡眠插件：群聊 {group_id} 不在白名单或白名单为空，不应用睡眠模式。")
        elif event.is_private_chat(): # 是私聊消息
            if apply_private:
                should_apply_sleep_mode = True
                logger.debug("睡眠插件：私聊消息，且配置为应用于私聊，应用睡眠模式。")
            else:
                logger.debug("睡眠插件：私聊消息，但未配置应用于私聊，不应用睡眠模式。")
        else: # 其他类型事件（理论上较少见，但以防万一）
             logger.debug(f"睡眠插件：收到非群聊/私聊消息类型，默认不应用睡眠模式。Event type: {event.get_message_type()}")


        # 4. 如果不应该应用睡眠模式，则直接返回，让事件继续
        if not should_apply_sleep_mode:
            return

        # --- 执行睡眠模式的阻止逻辑 ---
        logger.info(f"睡眠插件：检测到受影响的会话消息，当前处于睡眠状态。用户：{event.get_sender_name()} ({event.get_sender_id()})，将阻止处理。")

        # 阻止默认的 LLM 调用
        event.should_call_llm(False)
        logger.debug("睡眠插件：已设置禁止默认 LLM 调用。")

        # 发送睡眠期间的固定回复
        reply_msg = self.config.get("sleeping_reply", "")
        if reply_msg:
            logger.info(f"睡眠插件：向 {event.get_sender_name()} 发送睡眠回复。")
            try:
                yield event.plain_result(reply_msg)
            except Exception as e:
                logger.error(f"睡眠插件：发送睡眠回复时出错: {e}", exc_info=True)
        else:
            logger.info(f"睡眠插件：未配置睡眠回复，仅阻止事件。")

        # 停止事件传播，阻止其他插件或默认行为响应
        event.stop_event()
        logger.debug("睡眠插件：已停止事件传播。")


    # --- 插件生命周期 ---
    async def terminate(self):
        """插件卸载/停用时调用，用于清理资源"""
        logger.info("睡眠插件：正在终止...")
        if self._monitor_task and not self._monitor_task.done():
            logger.info("睡眠插件：正在取消监控任务...")
            self._monitor_task.cancel()
            try:
                await asyncio.wait_for(self._monitor_task, timeout=5.0)
            except asyncio.CancelledError:
                logger.info("睡眠插件：监控任务已成功取消。")
            except asyncio.TimeoutError:
                logger.warning("睡眠插件：取消监控任务超时。")
            except Exception as e:
                logger.error(f"睡眠插件：等待监控任务取消时发生异常: {e}", exc_info=True)
        else:
             logger.info("睡眠插件：监控任务未运行或已完成，无需取消。")

        self.is_sleeping = False # 确保状态重置
        self.plugin_enabled = False # 标记为禁用
        logger.info("睡眠插件：已终止。")