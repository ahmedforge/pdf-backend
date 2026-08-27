from collections import defaultdict, deque
from time import monotonic


REQUEST_LIMIT = 10
WINDOW_SECONDS = 60

_requests: dict[int, deque[float]] = defaultdict(deque)


def check_rate_limit(user_id: int) -> bool:
    now = monotonic()
    window_start = now - WINDOW_SECONDS

    user_requests = _requests[user_id]

    while user_requests and user_requests[0] < window_start:
        user_requests.popleft()

    if len(user_requests) >= REQUEST_LIMIT:
        return False

    user_requests.append(now)

    return True