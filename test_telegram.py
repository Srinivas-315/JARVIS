"""
A complex 100-line python file to test typing fidelity.
Includes dunders, decorators, async, dicts, multiline strings, f-strings.
"""
import asyncio
import time
from functools import wraps

def timer_decorator(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        print(f"Starting {func.__name__}")
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            end = time.time()
            print(f"Finished {func.__name__} in {end - start:.4f}s")
    return wrapper

class BaseEntity:
    def __init__(self, name: str):
        self._name = name
        self.__internal_state = "init"
        
    @property
    def name(self):
        return self._name

class ComplexSystem(BaseEntity):
    """
    This system handles complex operations.
    Multi-line strings are supported natively.
    """
    def __init__(self, name: str):
        super().__init__(name)
        self.config = {
            "retries": 3,
            "endpoints": [
                "http://localhost:8080/api/v1",
                "http://localhost:8080/api/v2"
            ],
            "timeouts": {
                "connect": 5.0,
                "read": 15.0,
                "write": 30.0
            }
        }
        self.cache = {}

    @timer_decorator
    async def fetch_data(self, endpoint_idx: int) -> dict:
        """Simulates an async network fetch."""
        if endpoint_idx >= len(self.config["endpoints"]):
            raise ValueError("Invalid endpoint index")
            
        url = self.config["endpoints"][endpoint_idx]
        print(f"Fetching from {url}...")
        await asyncio.sleep(0.1)  # Simulate network latency
        
        return {
            "status": 200,
            "data": [
                {"id": 1, "value": "A"},
                {"id": 2, "value": "B"}
            ],
            "meta": {
                "url": url,
                "timestamp": time.time()
            }
        }
        
    async def process_all(self):
        results = []
        for i in range(len(self.config["endpoints"])):
            try:
                res = await self.fetch_data(i)
                results.append(res)
            except Exception as e:
                print(f"Failed on {i}: {e}")
                
        # List comprehension with complex dict mapping
        summary = [
            f"Result {r['status']} from {r['meta']['url']} with {len(r['data'])} items"
            for r in results
            if r.get("status") == 200
        ]
        
        return summary

async def main():
    sys = ComplexSystem("E2E_Test_System")
    print(f"Initialized: {sys.name}")
    
    summary = await sys.process_all()
    
    for item in summary:
        print(item)
        
    # Check if dunders are maintained
    if hasattr(sys, "__init__"):
        print("Dunder __init__ is intact.")

if __name__ == "__main__":
    asyncio.run(main())
