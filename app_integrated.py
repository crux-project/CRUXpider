"""
Compatibility wrapper for older local scripts.
"""

from app import app
from config import HOST, PORT


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=True)
