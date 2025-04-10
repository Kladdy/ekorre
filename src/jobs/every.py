# Based on https://gist.github.com/allanfreitas/e2cd0ff49bbf7ddf1d85a3962d577dbf
import time
import traceback


def every(delay: float, task: callable):
    next_time = time.time()
    while True:
        sleep_time = max(0, next_time - time.time())
        print(f"Sleeping for {sleep_time:.0f} s... 💤 (delay is {delay} s)")
        time.sleep(sleep_time)
        try:
            task()
        except Exception:
            traceback.print_exc()

        # skip tasks if we are behind schedule:
        next_time += (time.time() - next_time) // delay * delay + delay
