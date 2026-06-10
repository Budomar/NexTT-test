import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nextt.core.normalizer import SpecNormalizer

if __name__ == "__main__":
    n = SpecNormalizer(debug=True)
    n.debug_parse("VK-Profil 22-03-12 la")