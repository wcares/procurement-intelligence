"""Planning assistant: a chat that turns a planner's messages into edits of a project plan.

The language model only reads messages and proposes edits (interpret.py); every edit is checked against the data's own
vocabulary (resolve.py: countries, procurement types, methods) before it reaches the plan; the numbers shown with a
plan always come from the forecast engine, never from the model. A conversation lives in the browser: the server keeps
nothing between calls, so each call carries the history and the current plan, and a context guard (context.py) stops a
conversation before it outgrows the model's window.
"""
