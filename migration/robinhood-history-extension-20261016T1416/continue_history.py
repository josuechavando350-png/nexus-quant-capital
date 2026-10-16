"""A new registered window using the immutable PR19 engine, not its old policy."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'robinhood-paced-history-20261016T1222'
sys.path.insert(0,str(PRIOR))
import history_acquisition as engine
import audit_history as replay

def main():
    previous=engine.HERE
    try:
        engine.HERE=HERE
        return engine.main()
    finally:
        engine.HERE=previous

if __name__=='__main__':raise SystemExit(main())
