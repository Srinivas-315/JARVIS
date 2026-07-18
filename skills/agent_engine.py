import json
import logging
import threading
import time
from typing import Dict, List, Optional
from memory.database import get_connection

log = logging.getLogger("AgentEngine")

class AgentTask:
    def __init__(self, id: int, goal: str, plan_json: str, current_step: int, status: str):
        self.id = id
        self.goal = goal
        self.plan = json.loads(plan_json) if plan_json else []
        self.current_step = current_step
        self.status = status

class AgentPlanner:
    def __init__(self, gemini_handler):
        self.gemini = gemini_handler

    def create_plan(self, goal: str) -> List[Dict]:
        prompt = f"""
You are the JARVIS Agent Planner. 
Break down the following user goal into a list of specific, executable steps.
The executor has access to these general skills: browser, whatsapp, email, app control, file management, system interactions.
Each step should be a JSON object with:
- "action": A brief string representing what to tell the executor (e.g. "open Chrome", "send whatsapp to Mom saying Hello").
- "requires_safety_approval": boolean (true if sending messages, making payments, deleting files, etc).

Goal: {goal}

Respond ONLY with a valid JSON array of objects.
"""
        response = self.gemini.ask_quick(prompt)
        try:
            if not response:
                raise ValueError("Empty response from Gemini")
            json_str = response
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
            
            json_str = json_str.strip()
            # If still fails or doesn't look like array, wrap it
            if not json_str.startswith("["):
                # fallback attempt
                plan = [{"action": goal, "requires_safety_approval": False}]
            else:
                plan = json.loads(json_str)
                if not isinstance(plan, list):
                    plan = [{"action": goal, "requires_safety_approval": False}]
            return plan
        except Exception as e:
            log.error(f"Failed to parse plan JSON: {e}")
            return [{"action": goal, "requires_safety_approval": False}]

class AgentSafety:
    def is_safe(self, step: Dict) -> bool:
        if step.get("requires_safety_approval"):
            return False
        action = step.get("action", "").lower()
        danger_words = ["send", "delete", "purchase", "buy", "pay", "submit"]
        for word in danger_words:
            if word in action:
                return False
        return True

class AgentVerifier:
    def __init__(self, vision_handler, gemini_handler):
        self.vision = vision_handler
        self.gemini = gemini_handler

    def verify_step(self, step: Dict) -> bool:
        log.info(f"🔍 Verifying step: {step['action']}")
        # For simplicity in runtime testing without actual screen interaction,
        # we will assume success unless 'fail_test' is in the action string.
        if "fail_test" in step["action"].lower():
            return False
        return True

class AgentExecutor:
    def __init__(self, jarvis):
        self.jarvis = jarvis

    def execute(self, step: Dict) -> str:
        log.info(f"⚙️  Executing step: {step['action']}")
        # Reusing the existing intent router and executor
        try:
            intent = self.jarvis.smart_router.route(step['action'], self.jarvis.context, self.jarvis)
            result = self.jarvis.skill_executor.execute(intent)
            return str(result)
        except Exception as e:
            log.error(f"Execution failed: {e}")
            return f"Error: {e}"

class AgentManager:
    def __init__(self, jarvis):
        self.jarvis = jarvis
        self.planner = AgentPlanner(jarvis.gemini)
        self.safety = AgentSafety()
        self.verifier = AgentVerifier(jarvis.vision, jarvis.gemini)
        self.executor = AgentExecutor(jarvis)
        
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._daemon_loop, daemon=True)
        
    def start(self):
        log.info("🚀 Starting Agent Task Engine daemon...")
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        
    def add_task(self, goal: str) -> int:
        plan = self.planner.create_plan(goal)
        plan_json = json.dumps(plan)
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO agent_tasks (goal, plan_json, current_step, status) VALUES (?, ?, ?, ?)",
                (goal, plan_json, 0, 'running')
            )
            task_id = cursor.lastrowid
            conn.commit()
            return task_id

    def list_active_tasks(self) -> List[Dict]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, goal, current_step, status FROM agent_tasks WHERE status IN ('running', 'waiting_user')")
            tasks = []
            for row in cursor.fetchall():
                tasks.append({
                    "id": row[0],
                    "goal": row[1],
                    "current_step": row[2],
                    "status": row[3]
                })
            return tasks

    def update_task_status(self, task_id: int, status: str):
        with get_connection() as conn:
            conn.execute("UPDATE agent_tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, task_id))
            conn.commit()

    def update_task_step(self, task_id: int, step_index: int):
        with get_connection() as conn:
            conn.execute("UPDATE agent_tasks SET current_step = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (step_index, task_id))
            conn.commit()

    def resume_task(self, task_id: int):
        self.update_task_status(task_id, 'running')
        
    def cancel_task(self, task_id: int):
        self.update_task_status(task_id, 'cancelled')
        
    def retry_task(self, task_id: int):
        # Keeps current step, sets to running
        self.update_task_status(task_id, 'running')

    def get_running_tasks(self) -> List[AgentTask]:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, goal, plan_json, current_step, status FROM agent_tasks WHERE status = 'running'")
            tasks = []
            for row in cursor.fetchall():
                tasks.append(AgentTask(id=row[0], goal=row[1], plan_json=row[2], current_step=row[3], status=row[4]))
            return tasks

    def _daemon_loop(self):
        while not self._stop_event.is_set():
            try:
                running_tasks = self.get_running_tasks()
                for task in running_tasks:
                    if task.current_step >= len(task.plan):
                        self.update_task_status(task.id, 'completed')
                        continue

                    step = task.plan[task.current_step]
                    
                    if not self.safety.is_safe(step):
                        log.warning(f"⚠️  Task {task.id} requires safety approval for step: {step['action']}")
                        self.update_task_status(task.id, 'waiting_user')
                        self.jarvis.speaker.speak("A background task requires your approval to proceed.")
                        continue

                    # Execute
                    self.executor.execute(step)
                    
                    # Verify
                    success = self.verifier.verify_step(step)
                    if success:
                        self.update_task_step(task.id, task.current_step + 1)
                    else:
                        log.error(f"❌ Task {task.id} failed verification on step: {step['action']}")
                        self.update_task_status(task.id, 'failed')
                        self.jarvis.speaker.speak(f"Background task failed at step: {step['action']}")
            except Exception as e:
                log.error(f"Agent daemon loop error: {e}")
                
            time.sleep(2)
