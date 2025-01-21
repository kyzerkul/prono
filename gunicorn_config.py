bind = "0.0.0.0:10000"
workers = 2  # Réduit pour éviter la surcharge
threads = 4
timeout = 120
worker_class = "gthread"
max_requests = 1000
max_requests_jitter = 50
log_level = "debug"
