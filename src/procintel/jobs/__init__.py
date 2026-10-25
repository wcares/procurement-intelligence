"""Background jobs that run only while the app is idle: a persistent queue (store), job kinds (handlers) and the
worker that drains the queue between requests (worker). The backend starts the worker; set PROCINTEL_JOBS=0 to
disable it."""
