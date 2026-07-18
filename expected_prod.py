import asyncio
from dataclasses import dataclass
from typing import Dict, List

# Define a data class for a user
@dataclass
class User:
    """Class for a user."""
    id: int
    name: str

    def __init__(self, id: int, name: str):
        """Initialize a user."""
        self.id = id
        self.name = name

    def __repr__(self):
        """Return a string representation of the user."""
        return f"User(id={self.id}, name='{self.name}')"


# Define a decorator for async functions
def async_decorator(func):
    """Decorator for async functions."""
    async def wrapper(*args, **kwargs):
        """Wrapper function."""
        print("Starting async function")
        result = await func(*args, **kwargs)
        print("Finished async function")
        return result
    return wrapper


# Define an async function
@async_decorator
async def async_function(user: User) -> None:
    """Async function."""
    await asyncio.sleep(1)
    print(f"User id: {user.id}, User name: {user.name}")


# Define a nested dictionary
nested_dict: Dict[str, Dict[str, str]] = {
    "user1": {
        "id": "1",
        "name": "John"
    },
    "user2": {
        "id": "2",
        "name": "Jane"
    }
}


# Define a multiline string
multiline_string = """
This is a multiline string.
It can span multiple lines.
"""


# Define a list of users
users: List[User] = [
    User(1, "John"),
    User(2, "Jane")
]


# Define a main function
async def main() -> None:
    """Main function."""
    for user in users:
        await async_function(user)


# Run the main function
asyncio.run(main())