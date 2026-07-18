import logging
import re
from datetime import datetime

log = logging.getLogger("jarvis")

def clean_message(m: str) -> str:
    import re
    m = re.sub(r'^\s*(⏳ Processing:|📱 Telegram:)\s*', '', m)
    m = m.strip()
    if m.endswith('...'):
        m = m[:-3]
    return m

class WhatsAppHandler:
    """
    Handles parsing and routing of all WhatsApp-related voice/text commands.
    Isolates notification callbacks and call filtering.
    """
    def __init__(self, whatsapp_skill, jarvis_instance):
        self.whatsapp = whatsapp_skill
        self.jarvis = jarvis_instance

    def setup_notification_listener(self):
        """
        Sets up the master notification listener.
        Replaces both inline definition blocks from main.py.
        """
        def _wa_notify_cb(app_name, contact, msg):
            # Fallback for old signature where app_name wasn't passed
            if not msg and not contact and app_name:
                # Signature mismatch handling if called differently
                pass

            # Handle the case where the callback only sends (contact, msg)
            if app_name and contact and msg is None:
                msg = contact
                contact = app_name
                app_name = "WhatsApp"

            if not app_name:
                app_name = "WhatsApp"
                
            # Keep stats
            if not hasattr(self.whatsapp, "monitor_stats"):
                self.whatsapp.monitor_stats = {"callbacks": 0, "drafts": 0, "speakers": 0, "filtered": 0, "last_time": "", "last_sender": "", "last_msg": ""}
            self.whatsapp.monitor_stats["callbacks"] += 1
            
            self.whatsapp.monitor_stats["last_time"] = datetime.now().strftime("%I:%M %p")
            self.whatsapp.monitor_stats["last_sender"] = contact
            self.whatsapp.monitor_stats["last_msg"] = msg

            msg = clean_message(msg)
            
            # --- CALL MONITOR SEPARATION ---
            # Route to feed_native_call, removing the OCR/call check from main.py
            if "voice call" in msg.lower() or "incoming voice call" in msg.lower():
                if hasattr(self.jarvis, "call_monitor") and self.jarvis.call_monitor:
                    self.jarvis.call_monitor.feed_native_call(contact, "WhatsApp", "voice", "Incoming voice call", contact)
                return
            elif "video call" in msg.lower() or "incoming video call" in msg.lower():
                if hasattr(self.jarvis, "call_monitor") and self.jarvis.call_monitor:
                    self.jarvis.call_monitor.feed_native_call(contact, "WhatsApp", "video", "Incoming video call", contact)
                return

            self.whatsapp.monitor_stats["speakers"] += 1
            self.jarvis._speak(f"New {app_name} from {contact}: {msg}")
            
            try:
                # Try to use the active gemini handler to build context
                context_str = self.jarvis.gemini._build_unified_context() if hasattr(self.jarvis.gemini, '_build_unified_context') else ""
                prompt = (
                    f"{context_str}\n\n"
                    f"A new WhatsApp message just arrived from {contact}: \"{msg}\"\n\n"
                    "Based on the context above, draft a short, natural, and helpful reply. "
                    "Only output the text of the reply. Do not include quotes or explanations."
                )
                
                # Check which generate method is available
                if hasattr(self.jarvis.gemini, 'ask_quick'):
                    generated_reply = self.jarvis.gemini.ask_quick(prompt).strip()
                elif hasattr(self.jarvis.gemini, 'model') and hasattr(self.jarvis.gemini.model, 'generate_content'):
                    generated_reply = self.jarvis.gemini.model.generate_content(prompt).text.strip()
                else:
                    generated_reply = "I couldn't generate a draft at this time."

                if generated_reply:
                    draft_id = self.whatsapp.save_draft(contact, msg, generated_reply)
                    if draft_id != -1:
                        self.whatsapp.monitor_stats["drafts"] += 1
                        self.jarvis._speak(f"I prepared draft {draft_id} for {contact}. Say 'read whatsapp draft {draft_id}' or 'send whatsapp draft {draft_id}'.")
                    else:
                        self.jarvis._speak("I generated a draft but could not save it to the database.")
            except Exception as e:
                log.error(f"Draft generation failed: {e}")
                self.jarvis._speak("I failed to generate a reply draft.")

        # If a listener was already running, stop it
        self.whatsapp.stop_notification_listener()
        return self.whatsapp.start_notification_listener(_wa_notify_cb)


    def handle(self, text: str, text_lower: str, intent: str, active_window: str = "") -> str | None:
        """
        Processes a command string for WhatsApp.
        Returns the response string if it's a WhatsApp command, else None.
        """
        # ==========================================================
        # TYPING / ON-SCREEN CONTROL
        # ==========================================================
        
        # WhatsApp: SEND what was typed
        _send_words = {"send", "enter", "send it", "send message", "press enter", "send now", "ok send", "go ahead send"}
        if text_lower.strip() in _send_words or text_lower in _send_words:
            if "whatsapp" in active_window.lower():
                try:
                    return self.whatsapp.send_typed_message()
                except Exception as e:
                    log.exception(e)
                    return "Error sending typed message."

        # WhatsApp: DELETE LAST WORD
        if "delete last word" in text_lower or "backspace word" in text_lower:
            if "whatsapp" in active_window.lower():
                try:
                    return self.whatsapp.delete_last_word()
                except Exception as e:
                    log.exception(e)
                    return "Error deleting word."

        # WhatsApp: BACKSPACE
        _bs_text = text_lower.strip()
        _bs_text = re.sub(r"\bback\s+space\b", "backspace", _bs_text)
        _bs_text = re.sub(r"\b(backspace|delete)\s+(backspace|delete)\b", r"\1 2", _bs_text)
        _bw_m = re.match(r"^(?:backspace|delete)\s*(\d+)?(?:\s*(?:letters?|chars?|characters?))?$", _bs_text)
        if _bw_m:
            _n = int(_bw_m.group(1)) if _bw_m.group(1) else 1
            if "whatsapp" in active_window.lower():
                try:
                    return self.whatsapp.backspace_in_chat(_n)
                except Exception as e:
                    log.exception(e)
                    return "Error hitting backspace."

        # WhatsApp: CLEAR TYPED MESSAGE
        if any(p in text_lower for p in ["clear message", "clear typed message", "clear text", "clear all", "clear whatsapp"]):
            if "whatsapp" in active_window.lower():
                try:
                    return self.whatsapp.clear_typed_message()
                except Exception as e:
                    log.exception(e)
                    return "Error clearing message."

        # "type X in whatsapp" (handled somewhat generally, but if explicit)
        _type_msg = self.whatsapp.parse_type_command(text)
        if _type_msg and "whatsapp" in active_window.lower():
            try:
                self.jarvis._speak(f"Typing in WhatsApp: {_type_msg}")
                return self.whatsapp.type_in_active_chat(_type_msg)
            except Exception as e:
                log.exception(e)
                return "Error typing in WhatsApp."

        # ==========================================================
        # NOTIFICATION LISTENER COMMANDS
        # ==========================================================
        if any(p in text_lower for p in ["start whatsapp notification", "watch for whatsapp", "watch whatsapp messages", "listen for whatsapp"]):
            result = self.setup_notification_listener()
            return result

        if any(p in text_lower for p in ["stop whatsapp notification", "stop watching whatsapp"]):
            return self.whatsapp.stop_notification_listener()

        # ==========================================================
        # DRAFTS
        # ==========================================================
        if text_lower == "show whatsapp drafts":
            return self.whatsapp.list_drafts()

        _cmd_read_draft = re.match(r"read whatsapp draft (\d+)", text_lower)
        if _cmd_read_draft:
            did = int(_cmd_read_draft.group(1))
            return self.whatsapp.read_draft(did)

        _cmd_send_draft = re.match(r"send whatsapp draft (\d+)", text_lower)
        if _cmd_send_draft:
            did = int(_cmd_send_draft.group(1))
            return self.whatsapp.send_draft(did)

        _cmd_reject_draft = re.match(r"reject whatsapp draft (\d+)", text_lower)
        if _cmd_reject_draft:
            did = int(_cmd_reject_draft.group(1))
            return self.whatsapp.reject_draft(did)

        if text_lower in ["clear whatsapp drafts", "clear drafts"]:
            return self.whatsapp.clear_drafts()

        # ==========================================================
        # UNREAD / MARK ALL
        # ==========================================================
        if any(p in text_lower for p in ["check unread whatsapp", "how many whatsapp messages", "check whatsapp unread"]):
            return self.whatsapp.get_unread_count()
            
        if any(p in text_lower for p in ["read unread whatsapp", "read whatsapp unread", "check unread messages"]):
            self.jarvis._speak("Scanning all unread WhatsApp chats, sir. Give me a moment.")
            return self.whatsapp.scan_all_unread_chats()

        if any(p in text_lower for p in ["mark all whatsapp", "mark whatsapp as read", "mark all read"]):
            return self.whatsapp.mark_all_as_read()

        # ==========================================================
        # OPEN CHAT
        # ==========================================================
        if any(w in text_lower for w in ["whatsapp", "chat", "message"]):
            _oc_m = re.search(
                r"(?:open|go\s+to|show|switch\s+to|take\s+me\s+to)\s+"
                r"(?:chat\s+with\s+|whatsapp\s+(?:chat\s+)?(?:of\s+|with\s+)?)?([a-zA-Z ]+?)"
                r"(?:'s)?\s*(?:chat|whatsapp|message|conversation)?\s*(?:on whatsapp|in whatsapp|on wa|in wa)?$",
                text_lower,
            )
            if not _oc_m:
                _oc_m = re.search(
                    r"([a-zA-Z ]+?)'?s?\s+(?:chat|whatsapp)\s*(?:open|show|go)?\s*(?:on whatsapp|in whatsapp|on wa|in wa)?$",
                    text_lower,
                )
            if _oc_m:
                _oc_name = _oc_m.group(1).strip()
                _valid_open = False
                for _pref in ["open ", "go to ", "show ", "switch to ", "take me to ", "chat with ", "whatsapp with ", "whatsapp of "]:
                    if _pref in text_lower:
                        _valid_open = True
                        break
                if _oc_name and _valid_open and _oc_name not in ["whatsapp", "chat", "message", "the", "my"]:
                    try:
                        return self.whatsapp._open_chat(_oc_name)
                    except Exception as e:
                        log.exception(e)
                        return "I encountered an error trying to do that."

        # ==========================================================
        # VOICE NOTES
        # ==========================================================
        _vn_m = re.search(r"send(?: a)? voice note to (.+?) for (\d+) seconds?", text_lower)
        if _vn_m:
            _vn_who = _vn_m.group(1).strip()
            _vn_dur = int(_vn_m.group(2))
            return self.whatsapp.send_voice_note(_vn_who, _vn_dur)

        # ==========================================================
        # SCREENSHOT + SEND
        # ==========================================================
        if any(p in text_lower for p in ["send screenshot to", "share screenshot with"]):
            m = re.search(r"(?:send|share) screenshot (?:to|with) (.+)", text_lower)
            if m:
                sc_contact = m.group(1).strip()
                self.jarvis._speak(f"Taking and sending screenshot to {sc_contact}, sir.")
                try:
                    return self.whatsapp.send_screenshot(sc_contact)
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."

        # ==========================================================
        # PHASE 4 AND OTHER EXPLICIT COMMANDS
        # ==========================================================
        # Add Contact
        if any(p in text_lower for p in ["add contact", "add to contacts", "save contact", "new contact"]):
            _ac_m = re.search(r"(?:add|save|new)\s+contact\s+(\w+)(?:\s+as\s+(\w+))?", text_lower)
            if not _ac_m:
                _ac_m = re.search(r"add\s+(\w+)\s+to\s+contacts", text_lower)
            if _ac_m:
                _ac_name = _ac_m.group(1).strip()
                _ac_display = (_ac_m.group(2) or "").strip() if len(_ac_m.groups()) > 1 else ""
                try:
                    return self.whatsapp.add_contact(_ac_name, _ac_display)
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."

        # List Contacts
        if any(p in text_lower for p in ["list contacts", "my contacts", "show contacts", "who are my contacts"]):
            try:
                return self.whatsapp.list_contacts()
            except Exception as e:
                log.exception(e)
                return "I encountered an error trying to do that."

        # Daily summary
        if any(p in text_lower for p in ["what did i send today", "what did i send", "whatsapp daily", "daily summary whatsapp", "whatsapp summary"]):
            try:
                return self.whatsapp.daily_summary()
            except Exception as e:
                log.exception(e)
                return "I encountered an error trying to do that."

        # Summarize chat
        if any(p in text_lower for p in ["summarize my chat", "summarise my chat", "summarize chat", "summarise chat"]):
            _sum_m = re.search(r"(?:summarize|summarise)\s+(?:my\s+)?chat\s+with\s+(\w+)", text_lower)
            _sum_contact = _sum_m.group(1) if _sum_m else ""
            if _sum_contact:
                self.jarvis._speak(f"Summarizing chat with {_sum_contact}, sir.")
                try:
                    return self.whatsapp.summarize_chat(_sum_contact)
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."
            return "Who should I summarize the chat with, sir?"

        # Contact Status
        if re.search(r"(?:is\s+\w+\s+online|last\s+seen\s+(?:of\s+)?\w+|when\s+(?:was|did)\s+\w+|check\s+\w+\s+status|\w+\s+online\??|\w+\s+last\s+seen)", text_lower):
            _stat_m = re.search(
                r"(?:is\s+(\w+)\s+online|last\s+seen\s+(?:of\s+)?(\w+)|when\s+(?:was|did)\s+(\w+)|check\s+(\w+)\s+status|(\w+)\s+(?:online|last\s+seen))",
                text_lower,
            )
            if _stat_m:
                _stat_contact = next((g for g in _stat_m.groups() if g), "").strip()
                if _stat_contact in {"when", "is", "check", "the", "of", "a"}:
                    _stat_contact = ""
                if _stat_contact:
                    self.jarvis._speak(f"Checking {_stat_contact}'s status on WhatsApp, sir.")
                    try:
                        return self.whatsapp.get_contact_status(_stat_contact)
                    except Exception as e:
                        log.exception(e)
                        return "I encountered an error trying to do that."
            return "Who should I check status for, sir?"

        # Emoji-only send
        if re.search(r"(?:send\s+)?(?:\w+\s+)?emoji\s+to\s+\w+", text_lower):
            _em_m = re.search(r"(?:send\s+)?(\w+)\s+emoji\s+to\s+(\w+)", text_lower)
            _em_bare = re.search(r"emoji\s+to\s+(\w+)", text_lower)
            if _em_m:
                _em_emoji = _em_m.group(1).strip()
                _em_contact = _em_m.group(2).strip()
                self.jarvis._speak(f"Sending {_em_emoji} emoji to {_em_contact}, sir.")
                try:
                    return self.whatsapp.send_emoji_only(_em_contact, _em_emoji)
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."
            elif _em_bare:
                _em_contact = _em_bare.group(1).strip()
                self.jarvis._speak(f"Sending heart emoji to {_em_contact}, sir.")
                try:
                    return self.whatsapp.send_emoji_only(_em_contact, "heart")
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."

        # Stats
        if any(p in text_lower for p in ["whatsapp stats", "message stats", "who do i message most", "most messaged contact", "most messaged", "who do i text most", "whatsapp analytics"]):
            if any(w in text_lower for w in ["most messaged", "message most", "text most"]):
                try:
                    return self.whatsapp.most_messaged_contact()
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."
            else:
                try:
                    return self.whatsapp.get_stats()
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."

        # Undo last message
        if any(p in text_lower for p in ["undo last message", "delete that message", "delete last message", "unsend message", "delete for everyone"]):
            self.jarvis._speak("Trying to delete the last message, sir.")
            try:
                return self.whatsapp.undo_last_message()
            except Exception as e:
                log.exception(e)
                return "I encountered an error trying to do that."

        # Reply to last
        if text_lower.startswith("reply ") or "reply to last" in text_lower:
            reply_text = re.sub(r"^reply\s+", "", text, flags=re.IGNORECASE).strip()
            if reply_text:
                self.jarvis._speak(f"Replying: {reply_text}")
                try:
                    return self.whatsapp.reply_to_last(reply_text, self.jarvis._stop_event)
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."
            return "What should I reply, sir?"

        # Forward last message
        if any(p in text_lower for p in ["forward last message to", "forward message to", "forward that to"]):
            m = re.search(r"forward (?:last )?message to (.+)", text_lower)
            if m:
                fwd_contact = m.group(1).strip()
                self.jarvis._speak(f"Forwarding to {fwd_contact}, sir.")
                try:
                    return self.whatsapp.forward_last_message(fwd_contact, self.jarvis._stop_event)
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."
            return "Who should I forward to, sir?"

        # Schedule message
        if any(p in text_lower for p in ["schedule message", "schedule a message", "schedule whatsapp", "send message at ", "remind me to message", "send good morning at", "send good night at", "message rahul at", "message mom at"]):
            con, msg, t = self.whatsapp.parse_schedule_command(text)
            if con and msg and t:
                self.jarvis._speak(f"Scheduling message to {con} at {t}, sir.")
                try:
                    return self.whatsapp.schedule_message(con, msg, t)
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."
            return "To schedule, say: 'schedule message to mom good night at 22:00'"

        # List scheduled
        if any(p in text_lower for p in ["list scheduled", "show scheduled", "what's scheduled"]):
            try:
                return self.whatsapp.list_scheduled()
            except Exception as e:
                log.exception(e)
                return "I encountered an error trying to do that."

        # AI Compose and send
        if any(p in text_lower for p in ["compose message", "write message to", "send formal", "send casual", "write a whatsapp", "compose a whatsapp", "send an angry", "send a polite"]):
            ai_contact = ""
            tone = "helpful and polite"
            _cmd_c = re.search(r"(?:compose|write|send)(?:\s+a)?\s+(.+?)\s+(?:message|whatsapp)?\s*(?:to|for)\s+([a-zA-Z0-9_ ]+)", text_lower)
            if _cmd_c:
                tone = _cmd_c.group(1).strip()
                ai_contact = _cmd_c.group(2).strip()
            else:
                _alt = re.search(r"write\s+(?:a\s+)?message\s+to\s+([a-zA-Z0-9_ ]+)", text_lower)
                if _alt:
                    ai_contact = _alt.group(1).strip()

            if ai_contact:
                self.jarvis._speak(f"Write a {tone} WhatsApp message to send to '{ai_contact}'. ")
                _composed = self.jarvis._get_input_with_timeout(timeout=15)
                if _composed and _composed.lower() not in ["cancel", "stop", "never mind", "nevermind"]:
                    self.jarvis._speak(f"Message composed. Ready to send?")
                    _conf = self.jarvis._get_input_with_timeout(timeout=10)
                    if _conf and any(w in _conf.lower() for w in ["yes", "yeah", "send", "ok", "do it"]):
                        try:
                            return self.whatsapp.send_message(ai_contact, _composed)
                        except Exception as e:
                            log.exception(e)
                            return "I encountered an error trying to do that."
                    else:
                        return "Message cancelled."
                return "Cancelled composing."

            # If it's pure "compose and send" matching phase 4
            try:
                return self.whatsapp.compose_and_send(self.jarvis.gemini, self.jarvis._speak, self.jarvis._get_input)
            except Exception as e:
                log.exception(e)
                return "I encountered an error trying to do that."

        # Translate and send
        if "translate" in text_lower and ("send" in text_lower or "whatsapp" in text_lower):
            try:
                return self.whatsapp.translate_and_send(self.jarvis.gemini, self.jarvis._speak, self.jarvis._get_input)
            except Exception as e:
                log.exception(e)
                return "I encountered an error trying to do that."

        # Send to group
        if any(p in text_lower for p in ["send to group", "message group", "whatsapp group"]):
            _g_m = re.search(r"(?:send to|message)\s+(?:the\s+)?(.+?)\s+group\s+(?:saying|that)\s+(.+)", text_lower)
            if _g_m:
                g_name = _g_m.group(1).strip()
                g_msg = _g_m.group(2).strip()
                self.jarvis._speak(f"Sending to the {g_name} group, sir.")
                try:
                    return self.whatsapp.send_to_group(g_name, g_msg, self.jarvis._stop_event)
                except Exception as e:
                    log.exception(e)
                    return "I encountered an error trying to do that."

        # Bulk send
        if "send to multiple" in text_lower or "send message to" in text_lower and " and " in text_lower:
            contacts_bulk = self.whatsapp.parse_bulk_contacts(text)
            if contacts_bulk:
                self.jarvis._speak(f"What is the message for {', '.join(contacts_bulk)}?")
                msg_bulk = self.jarvis._get_input_with_timeout()
                if msg_bulk:
                    self.jarvis._speak("Sending to everyone now, sir.")
                    try:
                        return self.whatsapp.send_to_multiple(contacts_bulk, msg_bulk, self.jarvis._stop_event)
                    except Exception as e:
                        log.exception(e)
                        return "I encountered an error trying to do that."
                return "Bulk message cancelled."

        # Auto-response
        if "enable auto response" in text_lower or "turn on auto reply" in text_lower:
            m = re.search(r"(?:saying|with)\s+(.+)", text_lower)
            ar_msg = m.group(1).strip() if m else "I'm currently busy. I'll reply later."
            try:
                return self.whatsapp.enable_auto_response(ar_msg)
            except Exception as e:
                log.exception(e)
                return "I encountered an error trying to do that."
        if "disable auto response" in text_lower or "turn off auto reply" in text_lower:
            try:
                return self.whatsapp.disable_auto_response()
            except Exception as e:
                log.exception(e)
                return "I encountered an error trying to do that."

        # ---------------------------------------------------------
        # Standard Intent (from Intent Parser / Smart Router)
        # ---------------------------------------------------------
        if intent == "whatsapp":
            contact, message = self.whatsapp.parse_whatsapp_command(text)
            if contact and message:
                _ws_msg = re.sub(r"\s*(?:in|on)\s+whatsapp\s*$", "", message, flags=re.IGNORECASE)
                self.jarvis._speak(
                    f"Ready to send '{_ws_msg}' to {contact}. "
                    f"Say yes to confirm, or stop to cancel."
                )
                confirmed = False
                try:
                    import speech_recognition as _sr
                    _r = _sr.Recognizer()
                    with _sr.Microphone() as _src:
                        _r.adjust_for_ambient_noise(_src, duration=0.3)
                        _audio = _r.listen(_src, timeout=4, phrase_time_limit=3)
                    try:
                        _conf = _r.recognize_google(_audio).lower().strip()
                    except Exception:
                        _conf = _r.recognize_whisper(_audio, model="tiny", language="english").lower().strip()
                    if any(w in _conf for w in ["yes", "yeah", "yep", "send", "confirm", "ok", "okay", "do it"]):
                        confirmed = True
                    elif any(w in _conf for w in ["stop", "cancel", "no", "abort"]):
                        return "Cancelled, sir."
                    else:
                        return f"I heard '{_conf}'. Cancelled to be safe."
                except Exception:
                    return "Couldn't hear confirmation. Cancelled, sir."
                    
                if confirmed:
                    self.jarvis._speak(f"Sending to {contact}, sir!")
                    try:
                        return self.whatsapp.send_message(contact, _ws_msg, stop_event=self.jarvis._stop_event)
                    except Exception as e:
                        log.exception(e)
                        return "I encountered an error trying to do that."
            else:
                return "Who should I message? Say: message to Sarvani hello"

        # Not handled
        return None
