"""
JARVIS — brain/skill_executor.py
Maps AI-classified intents to actual skill handler calls.

Instead of 200 if/elif blocks, this cleanly dispatches:
    {"action": "open_app", "entities": {"app_name": "chrome"}}
    → jarvis.app_ctrl.open_app("chrome")
"""

from brain.skill_registry import SKILL_REGISTRY
from utils.logger import log


class SkillExecutor:
    """Maps SmartRouter intent results to actual skill executions."""

    def __init__(self, jarvis):
        """
        Args:
            jarvis: The main JARVIS instance (has .app_ctrl, .media, etc.)
        """
        self._j = jarvis

    def execute(self, intent_result: dict) -> str:
        """
        Execute a classified intent.

        Args:
            intent_result: {"action": "open_app", "entities": {"app_name": "chrome"}, ...}

        Returns:
            Response text to speak, or "" to let the old system handle it.
        """
        action = intent_result.get("action", "unknown")
        entities = intent_result.get("entities", {})
        source = intent_result.get("source", "")

        log.info(f"SkillExecutor: {action} | entities={entities} | source={source}")
        print(f"EXECUTOR: {intent_result}")

        try:
            # ── Clarification prompt (not an actual skill) ───────
            if action == "_clarify":
                return entities.get("prompt", "Could you clarify?")

            # ── Stop / Emergency ─────────────────────────────────
            if action == "stop":
                return "__STOP__"  # Signal to main loop

            # ── Send typed text (press Enter) ────────────────────
            if action == "send_typed":
                return "__SEND__"  # Signal to main loop

            # ── Open App ─────────────────────────────────────────
            if action == "open_app":
                app = entities.get("app_name", entities.get("app", ""))
                if app:
                    return self._j.app_ctrl.open_app(app)
                return ""

            # ── Close App ────────────────────────────────────────
            if action == "close_app":
                app = entities.get("app_name", entities.get("app", ""))
                if app:
                    return self._j.app_ctrl.close_app(app)
                return ""

            # 📱 WhatsApp Drafts & Monitor ───────────────────────────────────────────────────
            if action == "whatsapp_monitor_status":
                return self._j.whatsapp.get_monitor_status()
            if action == "whatsapp_call_monitor_status":
                if hasattr(self._j, "call_monitor") and self._j.call_monitor:
                    return self._j.call_monitor.get_call_monitor_status()
                return "Call monitor is not initialized, sir."
            
            if action == "telegram_status":
                if hasattr(self._j, "_telegram") and self._j._telegram:
                    return self._j._telegram.get_status()
                return "Telegram bridge is not initialized."

            # Telegram Call Controls
            if action == "whatsapp_call_status":
                if hasattr(self._j, "call_monitor") and self._j.call_monitor:
                    return self._j.call_monitor.get_current_call_status()
                return "Call monitor is not initialized."
            
            if action == "whatsapp_call_accept":
                if hasattr(self._j, "call_monitor") and self._j.call_monitor:
                    self._j.call_monitor._answer_call("WhatsApp")
                    return "Accept command sent."
                return "Call monitor is not initialized."

            if action == "whatsapp_call_decline":
                if hasattr(self._j, "call_monitor") and self._j.call_monitor:
                    self._j.call_monitor._decline_call("WhatsApp")
                    return "Decline command sent."
                return "Call monitor is not initialized."
            if action == "whatsapp_draft_list":
                return self._j.whatsapp.list_drafts()
            if action == "whatsapp_draft_clear":
                return self._j.whatsapp.clear_drafts()
            if action == "whatsapp_draft_read":
                did = entities.get("draft_id")
                if did is not None:
                    return self._j.whatsapp.read_draft(did)
                return ""
            if action == "whatsapp_draft_send":
                did = entities.get("draft_id")
                if did is not None:
                    return self._j.whatsapp.send_draft(did)
                return ""
            if action == "whatsapp_draft_reject":
                did = entities.get("draft_id")
                if did is not None:
                    return self._j.whatsapp.reject_draft(did)
                return ""

            # ── WhatsApp Send ────────────────────────────────────
            if action == "send_whatsapp":
                contact = entities.get("contact", "")
                message = entities.get("message", "")
                if contact and message:
                    return self._j.whatsapp.send_message(contact, message)
                return ""

            # ── WhatsApp Status Check ────────────────────────────
            if action == "whatsapp_status":
                contact = entities.get("contact", "")
                if contact:
                    return self._j.whatsapp.get_contact_status(contact)
                return ""

            # ── WhatsApp Schedule Message ────────────────────────
            if action == "whatsapp_schedule":
                contact = entities.get("contact", "")
                message = entities.get("message", "")
                time_str = entities.get("time", "")
                if contact and message and time_str:
                    return self._j.whatsapp.schedule_message(contact, message, time_str)
                return ""

            # ── WhatsApp Unread Count ────────────────────────────
            if action == "whatsapp_unread_count":
                return self._j.whatsapp.get_unread_count()

            # ── WhatsApp Emoji Send ──────────────────────────────
            if action == "whatsapp_emoji":
                contact = entities.get("contact", "")
                emoji = entities.get("emoji", "")
                if contact and emoji:
                    return self._j.whatsapp.send_emoji_only(contact, emoji)
                return ""

            # ── WhatsApp Send Screenshot ─────────────────────────
            if action == "whatsapp_screenshot":
                contact = entities.get("contact", "")
                if contact:
                    return self._j.whatsapp.send_screenshot(contact)
                return ""

            # ── WhatsApp Send Voice Note ─────────────────────────
            if action == "whatsapp_voice_note":
                contact = entities.get("contact", "")
                duration = int(entities.get("duration", 5))
                if contact:
                    return self._j.whatsapp.send_voice_note(contact, duration)
                return ""

            # ── WhatsApp Undo Last Message ───────────────────────
            if action == "whatsapp_undo":
                return self._j.whatsapp.undo_last_message()

            # ── WhatsApp Group Message ───────────────────────────
            if action == "whatsapp_group":
                group_name = entities.get("group_name", "")
                message = entities.get("message", "")
                if group_name and message:
                    return self._j.whatsapp.send_to_group(group_name, message)
                return ""

            # ── WhatsApp Bulk Message ────────────────────────────
            if action == "whatsapp_bulk":
                contacts = entities.get("contacts", [])
                if isinstance(contacts, str):
                    contacts = [c.strip() for c in contacts.replace(",", " ").split() if c.strip()]
                message = entities.get("message", "")
                if contacts and message:
                    return self._j.whatsapp.send_to_multiple(contacts, message)
                return ""

            # ── WhatsApp Translate and Send ──────────────────────
            if action == "whatsapp_translate":
                contact = entities.get("contact", "")
                message = entities.get("message", "")
                language = entities.get("language", "")
                if contact and message and language:
                    return self._j.whatsapp.translate_and_send(contact, message, language)
                return ""

            # ── WhatsApp Read ────────────────────────────────────
            if action == "read_whatsapp":
                contact = entities.get("contact", "")
                count = int(entities.get("count", 5))
                if contact:
                    return self._j.whatsapp.read_last_messages(contact, count)
                return ""

            # ── WhatsApp Open Chat ───────────────────────────────
            if action == "open_whatsapp_chat":
                contact = entities.get("contact", "")
                if contact:
                    return self._j.whatsapp.open_chat(contact)
                return ""

            # ── WhatsApp UI Controls ──────────────────────────────
            if action == "whatsapp_open_emoji_panel":
                return self._j.whatsapp.open_emoji_panel()
            if action == "whatsapp_open_sticker_panel":
                return self._j.whatsapp.open_sticker_panel()
            if action == "whatsapp_focus_chat_input":
                return self._j.whatsapp.focus_chat_input()
            if action == "whatsapp_send_sticker":
                contact = entities.get("contact", "")
                index = entities.get("index")
                if index is not None:
                    try:
                        # Normalize index value if it is a string/numeric word
                        idx_val = str(index).lower().strip()
                        import re
                        cleaned = re.sub(r"(st|nd|rd|th)$", "", idx_val).strip()
                        if cleaned.isdigit():
                            idx_val = int(cleaned)
                        else:
                            words = {
                                "first": 1, "one": 1, "1st": 1,
                                "second": 2, "two": 2, "2nd": 2,
                                "third": 3, "three": 3, "3rd": 3,
                                "fourth": 4, "four": 4, "4th": 4,
                                "fifth": 5, "five": 5, "5th": 5,
                                "sixth": 6, "six": 6, "6th": 6,
                                "seventh": 7, "seven": 7, "7th": 7,
                                "eighth": 8, "eight": 8, "8th": 8,
                                "ninth": 9, "nine": 9, "9th": 9,
                                "tenth": 10, "ten": 10, "10th": 10
                            }
                        return self._j.whatsapp.send_sticker_by_index(contact, int(idx_val))
                    except Exception as ex:
                        log.warning(f"Error parsing sticker index: {ex}")
                return ""

            # ── Type Text ────────────────────────────────────────
            if action == "type_text":
                text = entities.get("text", "")
                if text:
                    return self._j.whatsapp.type_and_wait(text)
                return ""

            # ── Media Control ────────────────────────────────────
            if action == "media_control":
                act = entities.get("action", "")
                if act == "pause":
                    return self._j.media.pause()
                elif act == "resume":
                    return self._j.media.resume()
                elif act in ("next", "skip"):
                    return self._j.media.next_track()
                elif act == "previous":
                    return self._j.media.previous_track()
                elif act == "stop":
                    return self._j.media.stop()
                return ""

            # ── Volume Control ───────────────────────────────────
            if action == "volume_control":
                direction = entities.get("direction", "")
                level = entities.get("level")
                if direction == "up":
                    return self._j.media.volume_up()
                elif direction == "down":
                    return self._j.media.volume_down()
                elif direction == "mute":
                    return self._j.media.mute()
                elif direction == "unmute":
                    return self._j.media.unmute()
                elif direction == "set" and level is not None:
                    return self._j.system.set_volume(int(level))
                return ""

            # ── Play Music ───────────────────────────────────────
            if action == "play_music":
                song = entities.get("song", entities.get("query", ""))
                artist = entities.get("artist", "")
                platform = entities.get("platform", "")
                if song:
                    return self._j.media.spotify_search_and_play(f"{song} {artist}".strip())
                return self._j.media.play_pause()

            # ── Screenshot ───────────────────────────────────────
            if action == "screenshot":
                return self._j.system.take_screenshot()

            # ── Brightness ───────────────────────────────────────
            if action == "brightness_control":
                direction = entities.get("direction", "")
                level = entities.get("level")
                if direction == "up":
                    return self._j.system.brightness_up()
                elif direction == "down":
                    return self._j.system.brightness_down()
                elif level is not None:
                    return self._j.system.set_brightness(int(level))
                return ""

            # ── System Info ──────────────────────────────────────
            if action == "system_info":
                info_type = entities.get("info_type", "health")
                if "battery" in info_type:
                    return self._j.system.battery_status()
                elif "cpu" in info_type or "temp" in info_type:
                    return self._j.system.hardware_temps()
                elif "ram" in info_type or "memory" in info_type:
                    return self._j.system.free_ram()
                elif "network" in info_type or "ip" in info_type:
                    return self._j.system.network_info()
                else:
                    return self._j.system.system_health()

            # ── Web Search ───────────────────────────────────────
            if action == "web_search":
                query = entities.get("query", "")
                if query:
                    return self._j.web_search.search(query)
                return ""

            # ── YouTube ──────────────────────────────────────────
            if action == "youtube_search":
                query = entities.get("query", "")
                if query:
                    return self._j.browser.youtube(query)
                return ""

            # ── Weather ──────────────────────────────────────────
            if action == "weather":
                city = entities.get("city")
                w_type = entities.get("type", "current")
                if "forecast" in (w_type or ""):
                    return self._j.weather.get_forecast(city)
                elif "aqi" in (w_type or "") or "air" in (w_type or ""):
                    return self._j.weather.get_aqi(city)
                elif "sunrise" in (w_type or "") or "sunset" in (w_type or ""):
                    return self._j.weather.get_sunrise_sunset(city)
                else:
                    return self._j.weather.get_current(city)

            # ── News ─────────────────────────────────────────────
            if action == "news":
                topic = entities.get("topic")
                mood = entities.get("mood")
                if topic:
                    return self._j.news.get_news(topic=topic)
                elif mood:
                    return self._j.news.get_news_by_mood(mood)
                else:
                    return self._j.news.get_headlines()

            # ── Email ────────────────────────────────────────────
            if action.startswith("email_") or action in ["send_email", "read_email"]:
                method_map = {
                    "send_email": "send_email",
                    "read_email": "read_recent_emails",
                    "email_compose_ai": "ai_compose_and_send",
                    "email_schedule": "schedule_email",
                    "email_undo": "undo_send",
                    "email_check_unread": "check_unread",
                    "email_search": "search_emails",
                    "email_reply": "reply_to_last",
                    "email_forward": "forward_last",
                    "email_delete": "delete_last_email",
                    "email_mark_read": "mark_all_read",
                    "email_brief": "morning_brief",
                    "email_stats": "get_stats"
                }
                print(f"\n[EMAIL TRACE]\nCommand: {entities.get('raw', 'N/A')}\nAction: {action}\nEntities: {entities}\nExecutor: {action}\nMethod: EmailHandler.{method_map.get(action, 'unknown')}()\n")

            if action == "send_email":
                return self._j.email.send_email(
                    entities.get("recipient", ""),
                    entities.get("subject", ""),
                    entities.get("body", ""),
                )

            if action == "read_email":
                return self._j.email.read_recent_emails()

            if action == "email_compose_ai":
                return self._j.email.ai_compose_and_send(
                    entities.get("recipient", ""),
                    entities.get("instruction", "")
                )

            if action == "email_schedule":
                return self._j.email.schedule_email(
                    entities.get("recipient", ""),
                    entities.get("subject", "Message from JARVIS"),
                    entities.get("body", ""),
                    entities.get("time", "")
                )

            if action == "email_undo":
                return self._j.email.undo_send()

            if action == "email_check_unread":
                return self._j.email.check_unread()

            if action == "email_search":
                return self._j.email.search_emails(entities.get("query", ""))

            if action == "email_reply":
                return self._j.email.reply_to_last(
                    entities.get("sender", ""),
                    entities.get("body", "")
                )

            if action == "email_forward":
                return self._j.email.forward_last(
                    entities.get("sender", ""),
                    entities.get("recipient", ""),
                    entities.get("body", "")
                )

            if action == "email_delete":
                return self._j.email.delete_last_email()

            if action == "email_mark_read":
                return self._j.email.mark_all_read()

            if action == "email_brief":
                return self._j.email.morning_brief()

            if action == "email_stats":
                return self._j.email.get_stats()

            # ── Time/Date ────────────────────────────────────────
            if action == "time_date":
                from datetime import datetime
                now = datetime.now()
                city = entities.get("city")
                if city:
                    return f"Let me check the time in {city}..."
                return f"It's {now.strftime('%I:%M %p')}, {now.strftime('%A, %B %d, %Y')}."

            # ── Math ─────────────────────────────────────────────
            if action == "math_calculate":
                expr = entities.get("expression", "")
                if expr:
                    try:
                        import re
                        safe = re.sub(r"[^0-9+\-*/().% ]", "", expr)
                        result = eval(safe)
                        if isinstance(result, float) and result == int(result):
                            return f"That's {int(result)}, sir."
                        return f"That's {result}, sir."
                    except Exception:
                        pass
                return ""

            # ── Reminder ─────────────────────────────────────────
            if action == "set_reminder":
                msg = entities.get("message", "")
                t = entities.get("time", "")
                if msg:
                    return self._j.reminder.set_reminder(msg, t)
                return ""

            if action == "list_reminders":
                return self._j.reminder.list_reminders()
                
            if action == "manage_reminders":
                act = entities.get("action", "")
                raw = entities.get("raw", "")
                if act == "list":
                    return self._j.reminder.list_reminders()
                elif act == "delete":
                    import re
                    match = re.search(r'(?:delete|remove|cancel)\s+reminder\s+(O-\d+|R-\d+|\d+|\w+)', raw, re.IGNORECASE)
                    if match:
                        return self._j.reminder.delete_reminder(match.group(1))
                    return self._j.reminder.delete_reminder(raw.replace("delete reminder", "").strip())
                elif act == "edit":
                    import re
                    match = re.search(r'edit\s+reminder\s+(O-\d+|R-\d+|\d+)\s+(.+)', raw, re.IGNORECASE)
                    if match:
                        rid = match.group(1)
                        rest = match.group(2)
                        new_time = None
                        new_freq = None
                        if "to " in rest:
                            val = rest.split("to ")[-1].strip()
                            if any(d in val for d in ["daily", "weekly", "monthly", "monday", "morning", "evening", "hourly"]):
                                new_freq = val
                            else:
                                new_time = val
                        return self._j.reminder.edit_reminder(rid, new_time, new_freq)
                    return "Please provide the reminder ID and new time/frequency."
                else: # set
                    mins, at_time, msg = self._j.reminder.parse_time_from_text(raw)
                    if not msg:
                        msg = "Reminder"
                    if "every" in raw or "daily" in raw or "weekly" in raw:
                        freq = "daily"
                        if "weekly" in raw: freq = "weekly"
                        if "hourly" in raw: freq = "hourly"
                        return self._j.reminder.set_recurring_reminder(msg, freq, at_time or "09:00")
                    return self._j.reminder.set_reminder(msg, minutes=mins, at_time=at_time)

            if action == "set_timer":
                dur = entities.get("duration", "")
                return self._j.reminder.set_timer(dur)

            # ── Agent Tasks ──────────────────────────────────────
            if action == "agent_tasks":
                raw = entities.get("raw", "")
                if "show" in raw or "list" in raw or "what" in raw or "my tasks" in raw:
                    tasks = self._j.agent_manager.list_active_tasks()
                    if not tasks:
                        return "You have no active tasks running."
                    t_list = "\n".join(f"Task {t['id']}: {t['goal']} (Step {t['current_step']}) - {t['status']}" for t in tasks)
                    return f"Here are your active tasks:\n{t_list}"
                elif "cancel" in raw or "stop" in raw:
                    import re
                    match = re.search(r'\b(?:task\s*)?(\d+)\b', raw)
                    if match:
                        tid = int(match.group(1))
                        self._j.agent_manager.cancel_task(tid)
                        return f"Task {tid} has been cancelled."
                    return "Which task ID would you like to cancel?"
                elif "resume" in raw or "continue" in raw:
                    import re
                    match = re.search(r'\b(?:task\s*)?(\d+)\b', raw)
                    if match:
                        tid = int(match.group(1))
                        self._j.agent_manager.resume_task(tid)
                        return f"Task {tid} has been resumed."
                    return "Which task ID would you like to resume?"
                elif "status" in raw:
                    tasks = self._j.agent_manager.list_active_tasks()
                    if not tasks:
                        return "You have no active tasks."
                    t_list = "\n".join(f"Task {t['id']}: {t['goal']} (Step {t['current_step']}) - {t['status']}" for t in tasks)
                    return f"Task status:\n{t_list}"
                return "I'm not sure what you want to do with agent tasks."

            # ── Calendar ─────────────────────────────────────────
            if action == "calendar_event":
                act = entities.get("action", "")
                raw_text = entities.get("raw", "").lower()
                
                if not act:
                    if "add" in raw_text or "create" in raw_text or "schedule" in raw_text:
                        act = "add"
                    elif "cancel" in raw_text or "delete" in raw_text or "remove" in raw_text:
                        act = "cancel"
                    else:
                        act = "view"
                        
                if "add" in act or "create" in act:
                    return self._j.calendar.add_event(raw_text)
                elif "cancel" in act or "delete" in act:
                    title = entities.get("title", "")
                    if not title:
                        import re
                        clean = raw_text
                        for word in ["cancel", "delete", "remove", "event", "meeting"]:
                            clean = clean.replace(word, "").strip()
                        title = clean
                    return self._j.calendar.cancel_event(title)
                else:
                    if "tomorrow" in raw_text:
                        return self._j.calendar.get_tomorrow()
                    elif "week" in raw_text:
                        return self._j.calendar.get_this_week()
                    elif "next" in raw_text:
                        return self._j.calendar.get_next_event()
                    elif "all" in raw_text:
                        return self._j.calendar.list_all_events()
                    return self._j.calendar.get_today()

            # ── Vision ───────────────────────────────────────────
            if action == "vision_camera":
                mode = entities.get("mode", "identify")
                if "read" in mode or "text" in mode:
                    return self._j.vision.read_text_from_camera()
                elif "person" in mode or "face" in mode:
                    return self._j.vision.identify_person()
                else:
                    return self._j.vision.identify_objects()

            if action == "vision_screen":
                return self._j.vision.what_is_on_screen()

            # ── App Mode ─────────────────────────────────────────
            if action == "app_mode":
                mode = entities.get("mode", "")
                if mode:
                    return self._j.app_ctrl.activate_mode(mode)
                return ""

            # ── Voice Control ────────────────────────────────────
            if action == "voice_control":
                act = entities.get("action", "")
                if "faster" in act:
                    spd = min(2.0, self._j.speaker._kokoro_speed + 0.2)
                    self._j.speaker._kokoro_speed = spd
                    self._j.speaker._save_config()
                    return f"Speed set to {spd:.1f}x."
                elif "slower" in act:
                    spd = max(0.5, self._j.speaker._kokoro_speed - 0.2)
                    self._j.speaker._kokoro_speed = spd
                    self._j.speaker._save_config()
                    return f"Speed set to {spd:.1f}x."
                elif "list" in act:
                    voices = self._j.speaker.list_voices()
                    return f"Available voices: {', '.join(voices[:10])}"
                return ""

            # ── Memory ───────────────────────────────────────────
            if action == "memory":
                act = entities.get("action", "")
                fact = entities.get("fact", "")
                fact_key = entities.get("fact_key", "")
                fact_value = entities.get("fact_value", "")
                
                # ── Clear Memory ──
                if "forget" in act or "clear" in act or "delete" in act:
                    self._j._waiting_for_memory_clear = True
                    return "Are you sure you want to delete all memory? Please reply with 'yes confirm delete'."
                    
                mem = getattr(self._j.gemini, '_local_llm', None)
                mem = getattr(mem, 'memory', None) if mem else None
                
                # ── Store structured key-value fact ──
                if fact_key and fact_value:
                    if hasattr(self._j, '_personal_mem') and self._j._personal_mem:
                        self._j._personal_mem.set(fact_key, fact_value.title())
                    if mem:
                        mem.add_user_message(f"my {fact_key} is {fact_value}")
                    return f"Got it, sir. I'll remember that your {fact_key} is {fact_value.title()}."
                    
                # ── Store raw text fact ──
                elif fact:
                    learned = ""
                    if hasattr(self._j, '_personal_mem') and self._j._personal_mem:
                        learned = self._j._personal_mem.try_learn(fact)
                    if mem:
                        mem.add_user_message(f"remember that {fact}" if not fact.startswith("remember") else fact)
                    return learned if learned else "Got it, I'll remember that, sir."
                    
                # ── Recall facts ──
                else:
                    if hasattr(self._j, '_personal_mem') and self._j._personal_mem:
                        recall_ans = self._j._personal_mem.try_recall(entities.get("raw", ""))
                        if recall_ans:
                            return recall_ans
                    if mem:
                        facts = mem.get_facts_prompt()
                        if facts:
                            response = facts.replace("Things I know about the user:\n- ", "").replace("\n- ", ", ")
                            return f"I remember: {response}"
                    return "I don't know much about you yet."

            # ── Voice Switching ───────────────────────────────────
            if action == "change_voice":
                voice_name = entities.get("voice_name", "")
                if voice_name and hasattr(self._j, "speaker") and self._j.speaker:
                    result = self._j.speaker.set_voice(voice_name)
                    # Play demo sentence in new voice
                    import threading as _th
                    def _demo():
                        import time as _t
                        _t.sleep(1.5)
                        self._j.speaker.speak("Hello! This is my new voice. Do you like it?")
                    _th.Thread(target=_demo, daemon=True).start()
                    return result
                return "Which voice? Say: change voice to George, Bella, Adam, etc."

            # ── Write Code ───────────────────────────────────────
            if action == "write_code":
                task = entities.get("task", "")
                language = entities.get("language", "")
                if task and hasattr(self._j, "code_writer") and self._j.code_writer:
                    self._j._speak("Opening VS Code and writing the code now, sir.")
                    lang = language or self._j.code_writer.detect_language(task)
                    filename = entities.get("filename", "") or self._j.code_writer.suggest_filename(task, lang)
                    result = self._j.code_writer.write_to_vscode(
                        task=task,
                        filename=filename,
                        language=lang,
                        speak_fn=self._j._speak,
                    )
                    return result or "Code written, sir."
                return ""

            # ── Solve Problem ────────────────────────────────────
            if action == "solve_problem":
                problem = entities.get("problem", "").strip()
                language = entities.get("language", "").strip()

                # Extract language from the problem string if it was accidentally swallowed
                if not language:
                    for lang in ["c++", "cpp", "java", "python", "javascript", "js", "go", "rust", "c#", "csharp", "c plus plus", "cplusplus"]:
                        if f"in {lang}" in problem.lower() or f"on {lang}" in problem.lower():
                            language = lang
                            break

                # Normalize language
                if language:
                    lang_lower = language.lower().strip()
                    if lang_lower in ["c++", "cpp", "c plus plus", "cplusplus"]:
                        language = "C++"
                    elif lang_lower in ["c#", "csharp", "c sharp"]:
                        language = "C#"
                    elif lang_lower in ["python", "py"]:
                        language = "Python"
                    elif lang_lower in ["java"]:
                        language = "Java"
                    elif lang_lower in ["javascript", "js"]:
                        language = "JavaScript"
                    elif lang_lower in ["typescript", "ts"]:
                        language = "TypeScript"
                    elif lang_lower in ["go", "golang"]:
                        language = "Go"
                    elif lang_lower in ["rust"]:
                        language = "Rust"
                    elif lang_lower in ["c"]:
                        language = "C"
                    else:
                        language = language.title()

                # Clean the problem name. If it indicates screen solve, set problem = ""
                screen_indicators = ["on the screen", "on my screen", "from screen", "from the screen", "on screen", "this", "this problem", "this code", "the code"]
                prob_lower = problem.lower()
                if any(ind in prob_lower for ind in screen_indicators) or prob_lower in ("", "problem", "code"):
                    problem = ""

                if hasattr(self._j, "problem_solver") and self._j.problem_solver:
                    lang_msg = f" in {language}" if language else ""
                    if problem:
                        self._j._speak(f"Working on {problem}{lang_msg}, sir.")
                        return self._j.problem_solver.solve_by_name(problem, language=language)
                    else:
                        self._j._speak(f"Looking at your screen to solve the problem{lang_msg}, sir.")
                        return self._j.problem_solver.solve_from_screen(language=language)
                return ""

            # ── Explain From Screen ──────────────────────────────
            if action == "explain_from_screen":
                if hasattr(self._j, "problem_solver") and self._j.problem_solver:
                    return self._j.problem_solver.explain_from_screen()
                return "Problem solver is not available."

            # ── Explain Solution ─────────────────────────────────
            if action == "explain_solution":
                if hasattr(self._j, "problem_solver") and self._j.problem_solver:
                    return self._j.problem_solver.explain_last()
                return "Problem solver is not available."

            # ── Paste Solution ───────────────────────────────────
            if action == "paste_solution":
                if hasattr(self._j, "problem_solver") and self._j.problem_solver:
                    return self._j.problem_solver.paste_solution()
                return "Problem solver is not available."

            # ── Optimize Code ────────────────────────────────────
            if action == "optimize_code":
                if hasattr(self._j, "problem_solver") and self._j.problem_solver:
                    return self._j.problem_solver.optimize_from_screen()
                return "Problem solver is not available."

            # ── Debug Code ───────────────────────────────────────
            if action == "debug_code":
                if hasattr(self._j, "problem_solver") and self._j.problem_solver:
                    return self._j.problem_solver.debug_from_screen()
                return "Problem solver is not available."
                
            # ── Get Complexity ─────────────────────────────────────
            if action == "get_complexity":
                if hasattr(self._j, "problem_solver") and self._j.problem_solver:
                    return self._j.problem_solver.get_complexity()
                return "Problem solver is not available."

            # ── Show Last Solution ─────────────────────────────────
            if action == "show_last_solution":
                if hasattr(self._j, "problem_solver") and self._j.problem_solver:
                    return self._j.problem_solver.show_last_solution()
                return "Problem solver is not available."

            # ── Explain Last Problem ───────────────────────────────
            if action == "explain_last_problem":
                if hasattr(self._j, "problem_solver") and self._j.problem_solver:
                    return self._j.problem_solver.explain_last_problem()
                return "Problem solver is not available."

            # ── Generate Image (AI art) ──────────────────────────────
            if action == "generate_image":
                prompt = entities.get("prompt", "")
                if prompt and hasattr(self._j, "image_gen") and self._j.image_gen:
                    self._j._speak(f"Generating the image now, sir. This may take a moment.")
                    return self._j.image_gen.generate_image(prompt)
                elif not prompt:
                    return "What should I draw, sir? Please describe the image."
                return "Image generation is not available right now, sir. Check your API keys."

            # ── Chat (general conversation) ──────────────────────
            if action == "chat":
                return ""  # Signal: let the existing Gemini handler respond

            # ── Shopping ─────────────────────────────────────────
            if action == "shopping":
                act = entities.get("action", "search")
                product = entities.get("product", "")
                if "wishlist" in act:
                    if "add" in act:
                        return self._j.shopping.add_to_wishlist(product)
                    elif "view" in act or "show" in act:
                        return self._j.shopping.view_wishlist()
                elif product:
                    return self._j.shopping.search_product(product)
                return ""

            # ── File Operations ──────────────────────────────────
            if action == "file_operation":
                act = entities.get("action", "")
                filename = entities.get("filename", "")
                if "search" in act or "find" in act:
                    return self._j.files.fuzzy_search(filename)
                elif "organize" in act:
                    return self._j.files.organize_downloads()
                elif "duplicate" in act:
                    return self._j.files.find_duplicates()
                elif "zip" in act:
                    return self._j.files.zip_file(filename)
                return ""

            # ── Clipboard ────────────────────────────────────────
            if action == "clipboard_operation":
                act = entities.get("action", "read")
                if "read" in act:
                    return self._j.clipboard.read_clipboard()
                elif "summarize" in act:
                    return self._j.clipboard.summarize_clipboard(self._j.gemini)
                elif "translate" in act:
                    lang = entities.get("language", "english")
                    return self._j.clipboard.translate_clipboard(lang)
                elif "history" in act:
                    return self._j.clipboard.get_history()
                return ""

            # ── Screen Control ───────────────────────────────────
            if action == "screen_control":
                return self._j.screen.execute(entities.get("action", ""))

            # ── Cursor Move To Element (OCR) ─────────────────────
            if action == "move_cursor_to":
                element = entities.get("element", entities.get("target", ""))
                if element:
                    from skills.screen_control import move_cursor_to_element
                    return move_cursor_to_element(element)
                return "Which element should I move the cursor to, sir?"

            # ── Click Element By Name (OCR) ──────────────────────
            if action == "click_element":
                element = entities.get("element", entities.get("target", ""))
                if element:
                    from skills.screen_control import click_element_by_name
                    return click_element_by_name(element)
                return "Which element should I click, sir?"

            # ── Cursor Direction Move ────────────────────────────
            if action == "move_cursor_direction":
                direction = entities.get("direction", "")
                pixels = int(entities.get("pixels", 100))
                if direction:
                    from skills.screen_control import move_cursor_direction
                    return move_cursor_direction(direction, pixels)
                return "Which direction, sir? Up, down, left, or right?"

            # ── Shutdown/Restart ─────────────────────────────────
            if action == "shutdown_system":
                act = entities.get("action", "")
                if "restart" in act:
                    return self._j.system.restart()
                elif "sleep" in act:
                    return self._j.system.sleep()
                elif "shutdown" in act:
                    return self._j.system.shutdown()
                return ""

            # ── Browser Control ──────────────────────────────────
            if action == "browser_control":
                act = entities.get("action", "")
                if "bookmark" in act:
                    return self._j.browser.bookmark_current_page()
                elif "zoom in" in act:
                    return self._j.browser.zoom_in()
                elif "zoom out" in act:
                    return self._j.browser.zoom_out()
                elif "back" in act:
                    return self._j.browser.go_back()
                elif "forward" in act:
                    return self._j.browser.go_forward()
                elif "reload" in act:
                    return self._j.browser.reload_page()
                elif "dark" in act:
                    return self._j.browser.toggle_dark_mode()
                return ""

            # ── Notification Control ─────────────────────────────
            if action == "notification_control":
                act = entities.get("action", "")
                if "dnd" in act or "disturb" in act:
                    return "Do not disturb mode activated."
                return ""

            # ── Knowledge Base / RAG ─────────────────────────────
            if action in ("knowledge_ingest", "knowledge_search",
                          "knowledge_ask", "knowledge_stats",
                          "knowledge_clear"):
                try:
                    from skills.knowledge_base import KnowledgeBaseSkill
                    kb = KnowledgeBaseSkill()
                    raw_text = entities.get("raw", entities.get("query", ""))
                    if action == "knowledge_ingest":
                        path = entities.get("file_path", entities.get("folder_path", raw_text))
                        return kb.handle(f"learn this file {path}")
                    elif action == "knowledge_search":
                        query = entities.get("query", raw_text)
                        return kb.handle(f"search my documents for {query}")
                    elif action == "knowledge_ask":
                        query = entities.get("query", raw_text)
                        return kb.handle(f"what do my notes say about {query}")
                    elif action == "knowledge_stats":
                        return kb.handle("how many documents do you know")
                    elif action == "knowledge_clear":
                        return kb.handle("forget all documents")
                except Exception as e:
                    log.error(f"Knowledge base error: {e}")
                    return "Knowledge base is not available right now, sir."

            # ── Unknown — let old system handle ──────────────────
            log.info(f"SkillExecutor: unhandled action '{action}'")
            return ""

        except Exception as e:
            log.error(f"SkillExecutor error for {action}: {e}")
            return ""
