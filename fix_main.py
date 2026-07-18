import sys, re

with open('c:/Users/srini/OneDrive/Attachments/Desktop/PROJECTS/JARVIS/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

start_str = '            # Try LEARN first (so "remember my name is X" saves before recall triggers)\n            learned = self._personal_mem.try_learn(text)'
end_str = '                self._speak(learned)\n                return ""\n'

start_idx = content.find(start_str)
end_idx = content.find(end_str, start_idx) + len(end_str)

if start_idx == -1 or end_idx == -1:
    print('Block not found!')
    sys.exit(1)

block = content[start_idx:end_idx]

# Remove the block
new_content = content[:start_idx] + content[end_idx:]

insert_str = '        # ── Fallback: WolframAlpha → Gemini AI ──────────────────\n        else:\n'
insert_idx = new_content.find(insert_str)

if insert_idx == -1:
    print('Insert point not found!')
    sys.exit(1)

insert_idx += len(insert_str)

block_with_header = '            # LAST ATTEMPT: Teach/Learn (if all other skills failed)\n            try:\n                if self._personal_mem is None:\n                    from memory.personal_memory import PersonalMemory\n                    self._personal_mem = PersonalMemory()\n            except Exception:\n                pass\n\n' + block

new_content = new_content[:insert_idx] + block_with_header + new_content[insert_idx:]

with open('c:/Users/srini/OneDrive/Attachments/Desktop/PROJECTS/JARVIS/main.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Successfully moved try_learn block.')
