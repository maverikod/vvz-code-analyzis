import tempfile
from pathlib import Path
from code_analysis.core.config import ServerConfig

tmp = Path(tempfile.mkdtemp())
data = {"host": "127.0.0.1", "port": 15000, "unknown": "value"}
try:
    ServerConfig(**data)
except Exception as e:
    print("Exception type:", type(e))
    print("Exception:", e)
    print("MRO:", type(e).__mro__)
    print("Is ValidationError?", isinstance(e, type(e)))
