#-----------------------------------------------------
# NOTIFICATIONS
#
# A curated set of business events somebody is expected to act on, the people
# they go to, and the record of who has seen what.
#
#   models.py     the three tables — event, delivery, threshold state
#   catalogue.py  every event that can be raised, and how it is classified
#   emit.py       raising one, without ever affecting the caller
#   routing.py    who receives it
#   routes/       the API surface
#
# Deliberately NOT the activity log. app/logs/ records every data-changing
# request for audit; this records the handful of things that need a decision.
# Nothing here is derived from activity_logs.
#-----------------------------------------------------
