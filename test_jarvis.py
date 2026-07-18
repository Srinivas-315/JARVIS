import pythoncom
import concurrent.futures
from main import JARVIS

print("Initializing JARVIS...")
j = JARVIS()
print("JARVIS ready.")

def run():
    print("Running in thread...")
    pythoncom.CoInitialize()
    res = j.process_command('status')
    pythoncom.CoUninitialize()
    return res

with concurrent.futures.ThreadPoolExecutor() as pool:
    try:
        print("Submitting to pool...")
        print(pool.submit(run).result())
    except Exception as e:
        print("ERROR:", e)
