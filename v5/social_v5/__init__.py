"""Local Chinese companion: face perception and consented, tiered memory."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path[:0] = [str(PROJECT / 'v4'), str(PROJECT / 'v2')]
