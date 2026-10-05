"""A harmless example to copy into ~/payloads on your device."""
import sys
from pathlib import Path

print('Hello from Kali Touch UI!')
print('Working folder:', Path.cwd())
print('Arguments:', sys.argv[1:])
print('Your Python payload is ready.')
