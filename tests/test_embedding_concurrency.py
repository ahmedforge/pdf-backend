from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from time import sleep

import app.services.embedding_service as embeddings


def test_concurrent_embedding_requests_do_not_overlap(monkeypatch):
    guard = Lock()
    start = Barrier(2)
    active = 0
    peak = 0
    class Result:
        def tolist(self):
            return [[0.1, 0.2]]
    class Model:
        def encode(self, texts, *, batch_size, show_progress_bar):
            nonlocal active, peak
            assert batch_size == 1
            with guard:
                active += 1
                peak = max(peak, active)
            try:
                sleep(0.03)
                return Result()
            finally:
                with guard:
                    active -= 1
    monkeypatch.setattr(embeddings, 'get_embedding_model', lambda: Model())
    def request():
        start.wait(timeout=2)
        return embeddings.generate_embedding('question')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(request), pool.submit(request)]
        assert [future.result(timeout=2) for future in futures] == [[0.1, 0.2], [0.1, 0.2]]
    assert peak == 1
