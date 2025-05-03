# AstrBot/data/plugins/astrbot_plugin_sleepmode/main.py

import asyncio
import datetime
import random # Keep random for delay calculation
from typing import Optional, List

# --- Corrected Import Statements ---
from astrbot.api import (
    AstrBotConfig,
    logger
)
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent, MessageChain # Import MessageChain

# From filter module import specific Enum types
from astrbot.api.event.filter import EventMessageType
# --- End of Corrected Import Statements ---


_sleep_time_obj: Optional[datetime.time] = None
_wake_time_obj: Optional[datetime.time] = None

@register(
    "astorbot_plugin_sleep", # Plugin name
    "Zhan_Kong", # Author
    "一个让 AstrBot 在指定时间段内“睡觉”并限制/通知特定群组的插件 (起床有延迟)", # Updated description
    "1.4.0", # Version incremented for delay feature
    "https://github.com/zhanwuzhijing/astrbot_plugin_sleep" # Repo URL
)
class SleepModePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.is_sleeping = False
        self._monitor_task: Optional[asyncio.Task] = None
        self.plugin_enabled = self.config.get("enable_plugin", True)

        if not self.plugin_enabled:
            logger.info("睡眠插件：插件已被禁用，将不会运行。")
            return

        self._parse_times()
        logger.info(f"睡眠插件加载：睡眠时间 {_sleep_time_obj}, 起床时间 {_wake_time_obj}")

        if _sleep_time_obj and _wake_time_obj:
            self._monitor_task = asyncio.create_task(self._monitor_sleep_schedule())
            logger.info("睡眠插件：已启动睡眠监控任务。")
        else:
            logger.warning("睡眠插件：时间配置无效或解析失败，无法启动睡眠监控任务。")

    def _parse_times(self):
        global _sleep_time_obj, _wake_time_obj
        try:
            sleep_str = self.config.get("sleep_time", "23:00")
            wake_str = self.config.get("wake_time", "07:00")
            _sleep_time_obj = datetime.datetime.strptime(sleep_str, "%H:%M").time()
            _wake_time_obj = datetime.datetime.strptime(wake_str, "%H:%M").time()
            logger.debug(f"成功解析时间 - 睡眠: {_sleep_time_obj}, 起床: {_wake_time_obj}")
        except ValueError as e:
            logger.error(f"无法解析时间配置 '{sleep_str}' 或 '{wake_str}'。请使用 HH:MM 格式。错误: {e}")
            _sleep_time_obj = None
            _wake_time_obj = None
        except Exception as e:
            logger.error(f"解析时间时发生未知错误: {e}", exc_info=True)
            _sleep_time_obj = None
            _wake_time_obj = None

    def _is_currently_in_sleep_period(self) -> bool:
        if not self.plugin_enabled or not _sleep_time_obj or not _wake_time_obj:
            return False
        now_time = datetime.datetime.now().time()
        if _sleep_time_obj > _wake_time_obj:
            return now_time >= _sleep_time_obj or now_time < _wake_time_obj
        elif _sleep_time_obj < _wake_time_obj:
            return _sleep_time_obj <= now_time < _wake_time_obj
        else:
            return False

    # --- Message Sending Function (Using 'GroupMessage' in UMO) ---
    async def _send_status_message_to_enabled_groups(self, message: str, message_type: str):
        """记录日志，并将状态消息发送到 `enabled_group_ids` 中配置的群组"""
        if not message: return

        log_msg = f"睡眠插件：{message_type} - {message}"
        logger.info(log_msg) # Always log locally
        print(f"[SleepMode Plugin] {message_type}: {message}") # Print to console

        target_group_ids: List[str] = self.config.get("enabled_group_ids", [])
        if not target_group_ids:
            logger.info("未在 'enabled_group_ids' 中配置任何群组，状态消息仅记录日志。")
            return

        try:
            message_chain = MessageChain().message(message)
        except Exception as e:
             logger.error(f"创建 MessageChain 时出错: {e}", exc_info=True)
             return

        logger.info(f"准备向 {len(target_group_ids)} 个已启用的群组发送状态消息 '{message_type}'...")
        platform_name = "aiocqhttp"

        sent_count = 0
        failed_count = 0
        for group_id in target_group_ids:
            if not group_id or not group_id.strip(): continue

            target_umo = f"{platform_name}:GroupMessage:{group_id.strip()}"
            logger.debug(f"尝试发送状态消息 '{message_type}' 到 UMO: {target_umo}")

            try:
                # logger.debug(f"调用 self.context.send_message with UMO='{target_umo}', chain='{message_chain}'") # Can be noisy
                success = await self.context.send_message(target_umo, message_chain)
                # logger.debug(f"self.context.send_message 返回: {success}") # Can be noisy

                if success:
                    logger.info(f"成功发送状态消息 '{message_type}' 到群组 {group_id}")
                    sent_count += 1
                else:
                    logger.warning(f"发送状态消息 '{message_type}' 到群组 {group_id} (UMO: {target_umo}) 失败，send_message 返回 False。")
                    failed_count += 1
                await asyncio.sleep(0.5)
            except ValueError as ve:
                 logger.error(f"发送状态消息 UMO 格式错误 (UMO: {target_umo}): {ve}", exc_info=True)
                 failed_count += 1
            except Exception as e:
                logger.error(f"发送状态消息时异常 (UMO: {target_umo}): {e}", exc_info=True)
                failed_count += 1
        logger.info(f"状态消息 '{message_type}' 发送完成。成功: {sent_count}，失败: {failed_count}")


    async def _monitor_sleep_schedule(self):
        await asyncio.sleep(10)
        logger.info("睡眠插件：开始监控睡眠时间表...")
        while True:
            try:
                self.plugin_enabled = self.config.get("enable_plugin", True)
                if not self.plugin_enabled:
                    logger.info("检测到插件已被禁用，停止监控任务。")
                    if self.is_sleeping: self.is_sleeping = False
                    break

                if not _sleep_time_obj or not _wake_time_obj:
                    logger.warning("监控任务检测到时间配置无效，暂停监控循环。")
                    await asyncio.sleep(300)
                    continue

                should_be_sleeping = self._is_currently_in_sleep_period()

                # Transition: Awake -> Sleep
                if should_be_sleeping and not self.is_sleeping:
                    self.is_sleeping = True
                    sleep_msg = self.config.get("sleep_message", "")
                    # Send sleep message immediately
                    await self._send_status_message_to_enabled_groups(sleep_msg, "进入睡眠")

                # Transition: Sleep -> Awake
                elif not should_be_sleeping and self.is_sleeping:
                    self.is_sleeping = False
                    wake_msg = self.config.get("wake_message", "")
                    # Calculate delay based on config
                    max_delay_minutes = self.config.get("max_wake_delay_minutes", 5)
                    delay_seconds = 0
                    if isinstance(max_delay_minutes, int) and max_delay_minutes > 0:
                         delay_seconds = random.randint(0, max_delay_minutes * 60)

                    # Log the delay locally, DO NOT send this message
                    logger.info(f"检测到起床时间，将在 {delay_seconds} 秒后尝试发送起床消息。")
                    # Create a task to send the actual wake message after the delay
                    asyncio.create_task(self._delayed_wake_message(delay_seconds, wake_msg))

                await asyncio.sleep(60) # Check every minute

            except asyncio.CancelledError:
                logger.info("监控任务被取消。")
                break
            except Exception as e:
                logger.error(f"监控任务主循环出错: {e}", exc_info=True)
                await asyncio.sleep(300)

    # --- Re-added _delayed_wake_message function ---
    async def _delayed_wake_message(self, delay_seconds: int, wake_msg: str):
        """Waits for the delay, then sends the wake-up message."""
        try:
            if delay_seconds > 0:
                logger.debug(f"延迟任务：开始等待 {delay_seconds} 秒发送起床消息。")
                await asyncio.sleep(delay_seconds)
                logger.debug(f"延迟任务：等待结束。")

            # Check if plugin is still enabled before sending
            if self.config.get("enable_plugin", True):
                 # Send the actual wake message now
                await self._send_status_message_to_enabled_groups(wake_msg, "起床")
            else:
                 logger.info("延迟起床消息准备发送时检测到插件已禁用，取消发送。")
        except asyncio.CancelledError:
            logger.info("延迟起床消息任务被取消。")
        except Exception as e:
            logger.error(f"发送延迟起床消息时出错: {e}", exc_info=True)


    @filter.event_message_type(EventMessageType.ALL, priority=100)
    async def handle_sleep_check(self, event: AstrMessageEvent):
        # (This function remains the same)
        if not self.config.get("enable_plugin", True): return
        if not self.is_sleeping: return

        should_apply_sleep_mode = False
        group_id = event.get_group_id()
        enabled_groups: List[str] = self.config.get("enabled_group_ids", [])
        apply_private = self.config.get("apply_to_private_chat", True)

        if group_id:
            if enabled_groups and group_id in enabled_groups:
                should_apply_sleep_mode = True
        elif event.is_private_chat():
            if apply_private:
                should_apply_sleep_mode = True

        if not should_apply_sleep_mode: return

        logger.info(f"检测到受影响的会话消息，睡眠中，将阻止处理。用户：{event.get_sender_name()}")
        event.should_call_llm(False)
        reply_msg = self.config.get("sleeping_reply", "")
        if reply_msg:
            try:
                yield event.plain_result(reply_msg)
            except Exception as e:
                logger.error(f"发送睡眠回复时出错: {e}", exc_info=True)
        event.stop_event()

    # --- Diagnostic Test Command (Kept for verification if needed) ---
    @filter.command("testsleepsend")
    async def test_send(self, event: AstrMessageEvent):
        # (This function remains the same)
        target_umo = event.unified_msg_origin
        group_id = event.get_group_id()
        if not group_id: yield event.plain_result("请在群聊中测试此命令。"); return
        enabled_groups: List[str] = self.config.get("enabled_group_ids", [])
        if group_id not in enabled_groups: yield event.plain_result(f"群组 {group_id} 未在本插件启用列表，但仍尝试发送。")
        yield event.plain_result(f"收到测试命令，尝试使用 context.send_message 发送消息回本群 (UMO: {target_umo})...")
        logger.info(f"测试发送: 目标 UMO = {target_umo}")
        message_chain = MessageChain().message(f"测试消息 (目标: {group_id})。")
        try:
            logger.debug(f"测试: 调用 self.context.send_message UMO='{target_umo}'")
            success = await self.context.send_message(target_umo, message_chain)
            logger.debug(f"测试: self.context.send_message 返回: {success}")
            if success: yield event.plain_result("测试消息发送成功！")
            else: yield event.plain_result("测试消息发送失败 (send_message 返回 False)。")
        except Exception as e:
            logger.error(f"测试发送时异常 for UMO {target_umo}: {e}", exc_info=True)
            yield event.plain_result(f"测试发送时发生异常: {e}")


    async def terminate(self):
        # (This function remains the same)
        logger.info("睡眠插件：正在终止...")
        if self._monitor_task and not self._monitor_task.done():
            logger.info("正在取消监控任务...")
            self._monitor_task.cancel()
            try: await asyncio.wait_for(self._monitor_task, timeout=5.0)
            except asyncio.CancelledError: logger.info("监控任务已成功取消。")
            except asyncio.TimeoutError: logger.warning("取消监控任务超时。")
            except Exception as e: logger.error(f"等待监控任务取消时发生异常: {e}", exc_info=True)
        else: logger.info("监控任务未运行或已完成。")
        self.is_sleeping = False
        self.plugin_enabled = False
        logger.info("睡眠插件：已终止。")