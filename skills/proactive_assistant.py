"""
JARVIS — skills/proactive_assistant.py
Proactive Personal Assistant Engine.
Evaluates context every few minutes and generates proactive alerts using Gemini.
"""
import time
import threading
from datetime import datetime
from utils.logger import log
from memory.database import get_connection

EVALUATION_INTERVAL = 300  # Evaluate every 5 minutes

class ProactiveAssistant:
    def __init__(self, gemini_handler, speak_fn):
        self.gemini = gemini_handler
        self.speak = speak_fn
        self._running = False
        self._thread = None
        self._cooldowns = {}  # In-memory cooldown per alert type/message
        
        # Load undelivered alerts from DB on startup
        self._delivered_alerts = set()
        self._load_alert_history()

    def _load_alert_history(self):
        try:
            with get_connection() as conn:
                cursor = conn.execute("SELECT alert_type, message FROM assistant_alerts WHERE delivered_at IS NOT NULL ORDER BY delivered_at DESC LIMIT 50")
                for row in cursor.fetchall():
                    self._delivered_alerts.add((row[0], row[1]))
        except Exception as e:
            log.error(f"Failed to load alert history: {e}")

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._daemon_loop, daemon=True)
        self._thread.start()
        log.info("🌟 Proactive Assistant daemon started.")

    def stop(self):
        self._running = False
        log.info("🌟 Proactive Assistant daemon stopped.")

    def _daemon_loop(self):
        last_llm_eval = 0
        while self._running:
            now = time.time()
            
            # 1. Deterministic Hard Alerts (every 30 seconds)
            try:
                self._check_hard_alerts()
            except Exception as e:
                log.error(f"Proactive Assistant hard-alert check failed: {e}")
                
            # 2. LLM Unified Context Eval (every EVALUATION_INTERVAL)
            if now - last_llm_eval >= EVALUATION_INTERVAL:
                try:
                    self._evaluate_and_alert()
                except Exception as e:
                    log.error(f"Proactive Assistant LLM evaluation failed: {e}")
                last_llm_eval = time.time()
            
            # Wait for 30 seconds
            for _ in range(30):
                if not self._running:
                    break
                time.sleep(1)

    def _check_hard_alerts(self):
        now = datetime.now()
        
        # 1. Check Calendar Events
        try:
            import json
            import os
            calendar_file = os.path.join("data", "calendar.json")
            if os.path.exists(calendar_file):
                with open(calendar_file, "r", encoding="utf-8") as f:
                    events = json.load(f)
                    for e in events:
                        if e.get("date") == now.strftime("%Y-%m-%d") and e.get("time"):
                            event_time_str = f"{e['date']} {e['time']}"
                            event_time = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M")
                            delta = (event_time - now).total_seconds() / 60.0
                            
                            if delta < -1: continue # past
                            elif delta <= 0: self._trigger_scheduled_alert(e['id'], 'calendar', 'start', e['name'])
                            elif delta <= 5: self._trigger_scheduled_alert(e['id'], 'calendar', '5m', e['name'])
                            elif delta <= 15: self._trigger_scheduled_alert(e['id'], 'calendar', '15m', e['name'])
                            elif delta <= 60: self._trigger_scheduled_alert(e['id'], 'calendar', '60m', e['name'])
        except Exception as e:
            log.error(f"Error checking calendar hard alerts: {e}")
            
        # 2. Check Reminders
        try:
            with get_connection() as conn:
                cursor = conn.execute("SELECT id, message, remind_at FROM reminders WHERE is_done = 0")
                reminders = cursor.fetchall()
                
            for r in reminders:
                trigger_time = datetime.strptime(r[2], "%Y-%m-%d %H:%M:%S")
                delta = (trigger_time - now).total_seconds() / 60.0
                
                if delta < -1: continue # past
                elif delta <= 0: self._trigger_scheduled_alert(str(r[0]), 'reminder', 'start', r[1])
                elif delta <= 5: self._trigger_scheduled_alert(str(r[0]), 'reminder', '5m', r[1])
                elif delta <= 15: self._trigger_scheduled_alert(str(r[0]), 'reminder', '15m', r[1])
        except Exception as e:
            log.error(f"Error checking reminder hard alerts: {e}")

    def _trigger_scheduled_alert(self, entity_id, entity_type, window, text):
        try:
            with get_connection() as conn:
                cursor = conn.execute("SELECT delivered_at FROM scheduled_alerts WHERE entity_id = ? AND entity_type = ? AND alert_window = ?", (entity_id, entity_type, window))
                if cursor.fetchone():
                    return # Already delivered
                
                # Insert to prevent duplicate
                conn.execute(
                    "INSERT INTO scheduled_alerts (entity_id, entity_type, alert_window, target_time, delivered_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                    (entity_id, entity_type, window)
                )
                
                # Also insert into assistant_alerts for LLM context history
                if entity_type == 'calendar':
                    if window == 'start': msg = f"Sir, your event '{text}' is starting now."
                    else: msg = f"Sir, your event '{text}' is starting in {window.replace('m', ' minutes')}."
                    alert_type = 'CALENDAR'
                else:
                    if window == 'start': msg = f"Sir, reminder: {text}."
                    else: msg = f"Sir, you have a reminder for {text} in {window.replace('m', ' minutes')}."
                    alert_type = 'REMINDER'
                    
                conn.execute(
                    "INSERT INTO assistant_alerts (alert_type, message, delivered_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (alert_type, msg)
                )
                conn.commit()
                
            # Log and Speak
            log.info(f"dYOY Proactive Hard Alert [{alert_type}]: {msg}")
            if self.speak:
                self.speak(msg)
        except Exception as e:
            log.error(f"Failed to process hard alert: {e}")

    def _evaluate_and_alert(self):
        # Build unified context
        context_str = self.gemini._build_unified_context()
        
        prompt = (
            "You are the Proactive Personal Assistant Engine of JARVIS.\n"
            "Analyze the following context (including calendar, reminders, emails, whatsapp drafts, and memories).\n"
            "Your goal is to generate ONE single, highly relevant, proactive alert if needed right now.\n"
            "Examples of good alerts:\n"
            "- 'Sir, your interview is starting in 1 hour. Should I prepare your notes?'\n"
            "- 'Sir, you have a pending WhatsApp draft for Mom that has not been sent.'\n"
            "- 'Sir, remember to drink water as per your reminder.'\n\n"
            "If no urgent or relevant proactive alert is needed, output exactly: NO_ALERT\n"
            "If an alert is needed, output it in this exact format:\n"
            "ALERT_TYPE: [type, e.g., CALENDAR, REMINDER, WHATSAPP, EMAIL]\n"
            "MESSAGE: [The spoken alert text]\n\n"
            f"=== CONTEXT ===\n{context_str}\n=================\n"
        )
        
        try:
            # We don't want to use conversational history. ask_quick is perfect.
            response = self.gemini.ask_quick(prompt)
            if not response:
                return
            response = response.strip()
            
            if response == "NO_ALERT" or "NO_ALERT" in response:
                return
                
            alert_type = None
            message = None
            for line in response.splitlines():
                if line.startswith("ALERT_TYPE:"):
                    alert_type = line.split(":", 1)[1].strip()
                elif line.startswith("MESSAGE:"):
                    message = line.split(":", 1)[1].strip()
                    
            if alert_type and message:
                self._process_alert(alert_type, message)
        except Exception as e:
            log.warning(f"Proactive Assistant LLM error: {e}")

    def _process_alert(self, alert_type: str, message: str):
        # 1. Prevent Spam / Duplicate
        # If we already delivered this exact message recently, ignore it.
        if (alert_type, message) in self._delivered_alerts:
            return
            
        # 2. Check Cooldown for alert type (e.g. max 1 alert per 30 minutes for WHATSAPP)
        now = time.time()
        last_time = self._cooldowns.get(alert_type, 0)
        # 30 minute cooldown per category
        if now - last_time < 1800:
            return
            
        # 3. Store and Deliver
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO assistant_alerts (alert_type, message, delivered_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (alert_type, message)
                )
                conn.commit()
            
            # Mark delivered
            self._delivered_alerts.add((alert_type, message))
            self._cooldowns[alert_type] = now
            
            # Speak out the alert
            log.info(f"🌟 Proactive Alert [{alert_type}]: {message}")
            if self.speak:
                self.speak(message)
                
        except Exception as e:
            log.error(f"Failed to process proactive alert: {e}")
