"""Load Redis fixtures. Run: python scripts/load_redis_fixtures.py"""
import json, os
from pathlib import Path
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATA = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "redis_data.json"

r = redis.from_url(REDIS_URL, decode_responses=True)
r.ping()
d = json.loads(DATA.read_text())
n = 0
for sid, msgs in d["chat_histories"].items():
    r.setex(f"sip:chat:{sid}", 3600, json.dumps(msgs)); n += 1
for job, ts in d["job_last_run"].items():
    r.setex(f"sip:job_last_run:{job}", 172800, json.dumps(ts)); n += 1
for jid, res in d["match_cache"].items():
    r.setex(f"sip:match:job_{jid}", 180, json.dumps(res)); n += 1
for k, v in d["query_cache"].items():
    r.setex(f"sip:{k}", 300, json.dumps(v)); n += 1
print(f"Loaded {n} keys into Redis")
print("Verify: docker compose exec redis redis-cli KEYS 'sip:*'")
