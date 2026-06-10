"""
Точка входа в приложение NexTT.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    """Запускает приложение."""
    from nextt.app import App
    app = App()
    app.run()


if __name__ == "__main__":
    main()