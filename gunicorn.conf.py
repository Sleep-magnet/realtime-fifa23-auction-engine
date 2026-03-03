# gunicorn.conf.py
import multiprocessing

# Bind to port 5000
bind = "0.0.0.0:5000"

# Formula: 2 * CPU Cores + 1. 
# If you are on a basic 1-core server, this will be 3 workers.
workers = multiprocessing.cpu_count() * 2 + 1

# Handle 4 simultaneous requests per worker process
threads = 4

# Use thread-based concurrency
worker_class = "gthread"

# Give database locks time to resolve before crashing the worker
timeout = 120 

# Keep connections alive slightly longer to help with the 1-second JS polling
keepalive = 5

# Optional: Log to terminal for easy debugging
accesslog = "-"
errorlog = "-"